from __future__ import annotations

import logging
import random
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path, PureWindowsPath

import pytest

from yttoolkit import redact
from yttoolkit.api import errors
from yttoolkit.core import queue as queue_module
from yttoolkit.core.cancel import JobCancelled
from yttoolkit.core.db import Database
from yttoolkit.core.events import Event
from yttoolkit.core.jobs import STATUSES, InvalidTransition, JobResult, JobStore, NewJob, OutputFile
from yttoolkit.core.queue import QueueRunner
from yttoolkit.core.yterrors import MESSAGES, YtError, queue_paused_error

KINDS = ("video", "audio", "subtitle", "contact_sheet", "frames_zip")
WALL0 = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
CLEARED_ON_REQUEUE = ("error", "stage", "progress", "speedBps", "etaS", "attempt", "notes", "outputs")


# ---------- test helpers ----------


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


class Wall:
    def __init__(self) -> None:
        self.now = WALL0

    def __call__(self) -> datetime:
        return self.now


class RecordingBus:
    """EventBus ที่ไม่หน่วง: เก็บทุกข่าวตามลำดับ (คิวใช้แค่ publish กับ job_updated)"""

    def __init__(self) -> None:
        self.events: list[Event] = []
        self.on_update = None  # เทสเสียบโค้ดแทรกตอนมีข่าว job.updated ได้ (จำลองจังหวะชนกันของเธรด)
        self._lock = threading.Lock()

    def publish(self, name: str, data: dict) -> None:
        with self._lock:
            self.events.append(Event(name, dict(data)))

    def job_updated(self, job_id: str, fields: dict) -> None:
        with self._lock:
            self.events.append(Event("job.updated", {"id": job_id, **fields}))
        if self.on_update is not None:
            self.on_update(job_id, fields)

    def updates(self, job_id: str) -> list[dict]:
        with self._lock:
            return [e.data for e in self.events if e.name == "job.updated" and e.data["id"] == job_id]


class ManualSpawn:
    """เก็บงานที่ตัวรันคิวสั่งเริ่มไว้ เทสสั่งรันเองทีละงาน (ในเธรดของเทส)"""

    def __init__(self) -> None:
        self.pending: list = []

    def __call__(self, fn) -> None:
        self.pending.append(fn)

    def run_one(self) -> None:
        self.pending.pop(0)()

    def run_all(self) -> None:
        while self.pending:
            self.run_one()


class ScriptedHandler:
    """จบทันที: fail[video_id] = รหัส YtError, exception, หรือ list ของผลแต่ละรอบ (None = สำเร็จ)"""

    def __init__(self, fail: dict | None = None) -> None:
        self.fail = {k: (list(v) if isinstance(v, list) else v) for k, v in (fail or {}).items()}
        self.calls: list[str] = []

    def __call__(self, job, ctx) -> JobResult:
        self.calls.append(job.video_id)
        outcome = self.fail.get(job.video_id)
        if isinstance(outcome, list):
            outcome = outcome.pop(0) if outcome else None
        if isinstance(outcome, BaseException):
            raise outcome
        if isinstance(outcome, str):
            raise YtError(outcome, f"fake {outcome}")
        ctx.stage("downloading_video")
        ctx.progress(0.5, 1000, 3)
        (ctx.workdir / "media.mp4").write_bytes(b"x")
        return JobResult(
            outputs=(OutputFile(str(ctx.output_root), f"คลิป [{job.video_id}]/คลิป.mp4", 10, "video"),),
            notes=("AUDIO_LANG_FALLBACK",),
            title="ชื่อจริง",
        )


class BlockingHandler:
    """รอจนเทสปล่อย (finish) หรือถูกยกเลิก เช็ก ctx.cancelled() ทุก 0.05 วินาทีเหมือน handler จริง"""

    def __init__(self) -> None:
        self.started: dict[str, threading.Event] = {}
        self.release: dict[str, threading.Event] = {}
        self.workdirs: dict[str, Path] = {}
        self._lock = threading.Lock()

    def _events(self, job_id: str) -> tuple[threading.Event, threading.Event]:
        with self._lock:
            return (self.started.setdefault(job_id, threading.Event()),
                    self.release.setdefault(job_id, threading.Event()))

    def __call__(self, job, ctx) -> JobResult:
        started, release = self._events(job.id)
        (ctx.workdir / "media.part").write_bytes(b"partial")
        self.workdirs[job.id] = ctx.workdir
        started.set()
        while not release.wait(0.05):
            ctx.check_cancelled()
        return JobResult(title="จบ")

    def wait_started(self, job_id: str, timeout: float = 5.0) -> None:
        assert self._events(job_id)[0].wait(timeout), "handler did not start"

    def finish(self, job_id: str) -> None:
        self._events(job_id)[1].set()


class StubSettings:
    def __init__(self, concurrency: int, output: Path) -> None:
        self.value = concurrency
        self.output = output
        self.style = "title"  # M6 รอบ A: รูปแบบชื่อไฟล์ปัจจุบัน (เทสเปลี่ยนได้)

    def concurrency(self) -> int:
        return self.value

    def output_dir(self) -> Path:
        return self.output

    def filename_style(self) -> str:
        return self.style


def wait_for(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


@pytest.fixture
def runner_factory(tmp_path):
    made: list[tuple[QueueRunner, Database]] = []

    def make(concurrency=2, fail=None, handler=None, spawn="manual", **kwargs):
        db = Database(tmp_path / f"app{len(made)}.db")
        db.migrate()
        store = JobStore(db)

        def get_by_video(video_id: str):
            return next(j for s in STATUSES for j in store.list_status(s, -1) if j.video_id == video_id)

        store.get_by_video = get_by_video  # type: ignore[attr-defined]
        handler = handler or ScriptedHandler(fail)
        spawner = ManualSpawn() if spawn == "manual" else spawn
        bus = RecordingBus()
        clock, wall = Clock(), Wall()
        settings = StubSettings(concurrency, tmp_path / "out")
        kwargs.setdefault("redact", lambda text: text)
        runner = QueueRunner(
            store, bus, dict.fromkeys(KINDS, handler), settings=settings, work_root=tmp_path / "work",
            monotonic=clock, wall=wall, rng=random.Random(1), spawn=spawner, **kwargs,
        )
        runner.clock, runner.wall, runner.bus, runner.settings_view = clock, wall, bus, settings  # type: ignore[attr-defined]
        runner.bus_events = lambda: list(bus.events)  # type: ignore[attr-defined]
        made.append((runner, db))
        return runner, spawner, handler

    yield make
    for runner, db in made:
        runner.shutdown(timeout=0.2)
        db.close()


def jobs_of(kind: str, n: int, params: dict | None = None) -> list[NewJob]:
    return [NewJob(f"vid{i:08d}", kind, params or {}) for i in range(1, n + 1)]


# ---------- scheduling ----------


def test_ac_q_01_never_more_than_concurrency(runner_factory):
    r, spawn, h = runner_factory(concurrency=2)
    r.enqueue(jobs_of("contact_sheet", 5, {"source": "fast", "columns": 5}))
    assert len(r.tick()) == 2 and len(r.tick()) == 0
    assert len(r.store.running()) == 2
    spawn.run_one()
    assert len(r.store.running()) == 1
    assert len(r.tick()) == 1
    assert len(r.store.running()) <= 2
    spawn.run_all()
    while r.tick():
        assert len(r.store.running()) <= 2
        spawn.run_all()
    assert [j.status for j in r.store.list_status("done", -1)] == ["done"] * 5


def test_ac_q_02_gap_between_youtube_starts(runner_factory):
    r, spawn, h = runner_factory(concurrency=2)
    r.enqueue(jobs_of("video", 2))
    assert r.next_youtube_at == float("-inf")  # first YouTube job after idle starts at once
    assert len(r.tick()) == 1
    gap = r.next_youtube_at - r.clock.t
    assert 2.0 <= gap <= 5.0
    r.clock.t += gap - 0.01
    assert r.tick() == []
    r.clock.t += 0.02
    assert len(r.tick()) == 1


def test_gap_does_not_hold_back_non_youtube_jobs(runner_factory):
    r, spawn, h = runner_factory(concurrency=3)
    r.enqueue([NewJob("vid00000001", "video", {}), NewJob("vid00000002", "audio", {"format": "m4a"}),
               NewJob("vid00000003", "frames_zip", {"source": "fast"})])
    started = r.tick()
    assert [r.store.get(i).video_id for i in started] == ["vid00000001", "vid00000003"]
    assert r.store.get_by_video("vid00000002").status == "queued"


def test_gap_uses_the_given_rng(runner_factory):
    r, spawn, h = runner_factory(concurrency=1)
    r.enqueue(jobs_of("subtitle", 1))
    r.tick()
    assert r.next_youtube_at - r.clock.t == pytest.approx(random.Random(1).uniform(2.0, 5.0))


def test_concurrency_change_applies_next_tick(runner_factory):
    r, spawn, h = runner_factory(concurrency=1)
    r.enqueue(jobs_of("frames_zip", 4, {"source": "fast"}))
    assert len(r.tick()) == 1
    r.settings_view.value = 3
    assert len(r.tick()) == 2
    r.settings_view.value = 1
    assert r.tick() == []
    assert len(r.store.running()) == 3


def test_start_creates_workdir_and_publishes_running(runner_factory, tmp_path):
    r, spawn, h = runner_factory()
    (job,) = r.enqueue(jobs_of("contact_sheet", 1))
    created = [e for e in r.bus_events() if e.name == "job.created"]
    assert created[0].data["id"] == job.id and created[0].data["status"] == "queued"
    r.tick()
    assert (tmp_path / "work" / job.id).is_dir()
    patch = r.bus.updates(job.id)[-1]
    assert patch["status"] == "running" and patch["startedAt"]


def test_job_created_is_published_before_a_concurrent_tick_can_start_the_job(runner_factory):
    # เว็บทิ้ง job.updated ของงานที่ยังไม่เคยเห็น job.created ถ้าตัวจัดคิวแทรกเริ่มงานก่อนข่าว created
    # แถวจะค้างเป็น "รอคิว" จำลองจังหวะนั้น: ตอนจะประกาศ job.created ให้อีกเธรดเรียก tick แทรกเข้ามา
    r, spawn, h = runner_factory(concurrency=1)
    original = r.bus.publish
    ticker: list[threading.Thread] = []

    def publish(name: str, data: dict) -> None:
        if name == "job.created" and not ticker:
            thread = threading.Thread(target=r.tick)
            ticker.append(thread)
            thread.start()
            thread.join(0.5)  # ถ้าคิวยังถือ lock อยู่ tick จะรอจน enqueue เสร็จ
        original(name, data)

    r.bus.publish = publish  # type: ignore[method-assign]
    (job,) = r.enqueue(jobs_of("contact_sheet", 1))
    ticker[0].join(5)
    names = [e.name for e in r.bus_events() if e.data.get("id") == job.id]
    assert names[0] == "job.created"
    assert "job.updated" in names
    spawn.run_all()


def test_done_records_outputs_notes_title_and_removes_workdir(runner_factory, tmp_path):
    r, spawn, h = runner_factory()
    (job,) = r.enqueue(jobs_of("video", 1))
    r.tick()
    spawn.run_all()
    done = r.store.get(job.id)
    assert done.status == "done" and done.progress == 1.0 and done.title == "ชื่อจริง"
    assert done.notes == ("AUDIO_LANG_FALLBACK",)
    assert done.outputs[0].root == str(tmp_path / "out")
    assert not (tmp_path / "work" / job.id).exists()
    last = r.bus.updates(job.id)[-1]
    assert last["status"] == "done" and last["outputs"][0]["name"] == "คลิป.mp4"
    assert last["stage"] is None and last["cancelling"] is None and last["error"] is None


# ---------- progress ----------


def test_progress_is_deduped_and_db_writes_are_throttled(runner_factory, monkeypatch):
    writes: list[dict] = []

    def handler(job, ctx):
        ctx.stage("downloading_video")
        original = r.store.update

        def spy(job_id, **fields):
            writes.append(fields)
            return original(job_id, **fields)

        monkeypatch.setattr(r.store, "update", spy)
        for fraction in (0.1, 0.1, 0.2, 0.3):  # same clock: 0.1 twice is one event, DB not yet due
            ctx.progress(fraction, 500, 9)
        r.clock.t += 1.5
        ctx.progress(0.4, 500, 8)
        return JobResult()

    r, spawn, _ = runner_factory(handler=handler)
    (job,) = r.enqueue(jobs_of("frames_zip", 1))
    r.tick()
    spawn.run_all()
    progress = [u["progress"] for u in r.bus.updates(job.id) if "progress" in u and "status" not in u]
    assert progress == [None, 0.1, 0.2, 0.3, 0.4]  # None = stage change resets the bar
    assert writes == [{"progress": 0.4, "speed_bps": 500, "eta_s": 8}]


def test_progress_after_interrupt_does_not_raise(runner_factory):
    seen: list[str] = []

    def handler(job, ctx):
        ctx.progress(0.5)
        ctx.stage("writing")
        ctx.set_title("ใหม่")
        seen.append("ok")
        return JobResult()

    r, spawn, _ = runner_factory(handler=handler)
    (job,) = r.enqueue(jobs_of("frames_zip", 1))
    r.tick()
    r.store.interrupt_running(MESSAGES["E_INTERRUPTED"])  # what shutdown does to a stuck job
    spawn.run_all()
    assert seen == ["ok"]
    assert r.store.get(job.id).status == "interrupted"


# ---------- bot check ----------


def test_ac_q_03_bot_check_pauses_and_resume(runner_factory):
    r, spawn, h = runner_factory(concurrency=1, fail={"vid00000001": "E_BOT_CHECK"})
    r.enqueue(jobs_of("video", 2))
    r.tick()
    spawn.run_all()
    events = r.bus_events()
    paused = [e for e in events if e.name == "queue.paused"]
    assert [(e.name, e.data.get("reason")) for e in paused] == [("queue.paused", "E_BOT_CHECK")]
    assert paused[0].data["until"] == (WALL0 + timedelta(seconds=600)).isoformat(timespec="seconds")
    first = r.store.get_by_video("vid00000001")
    assert first.status == "queued" and first.bot_checks == 1
    assert first.position < r.store.get_by_video("vid00000002").position
    r.clock.t += 100
    assert r.tick() == []  # still paused, nothing starts
    r.resume()
    assert r.bus_events()[-1].name == "queue.resumed"
    started = r.tick()
    assert [r.store.get(i).video_id for i in started] == ["vid00000001"]  # "ลองต่อเลย" starts at once


def test_bot_check_requeue_patch_clears_fields_with_nulls(runner_factory):
    r, spawn, h = runner_factory(concurrency=1, fail={"vid00000001": "E_BOT_CHECK"})
    (job,) = r.enqueue(jobs_of("video", 1))
    r.tick()
    spawn.run_all()
    patch = r.bus.updates(job.id)[-1]
    assert patch["status"] == "queued"
    for key in CLEARED_ON_REQUEUE:
        assert key in patch and patch[key] is None, key


def test_brake_expires_by_wall_clock(runner_factory):
    r, spawn, h = runner_factory(concurrency=1)
    r.enqueue(jobs_of("video", 1))
    r.brake()
    r.wall.now += timedelta(seconds=599)
    assert r.pause_state() is not None and r.tick() == []
    r.wall.now += timedelta(seconds=2)
    assert len(r.tick()) == 1
    assert [e.name for e in r.bus_events()].count("queue.resumed") == 1


def test_brake_extends_a_running_pause(runner_factory):
    r, spawn, h = runner_factory()
    r.brake()
    r.wall.now += timedelta(seconds=300)
    r.brake()
    assert r.pause_state().until == WALL0 + timedelta(seconds=900)


@pytest.mark.parametrize("code", ["E_TRANSLATION_BLOCKED", "E_SESSION_WARMING", "E_YT_REFUSED"])
def test_brake_keys_on_code_not_status(runner_factory, code):
    r, spawn, h = runner_factory(concurrency=1, fail={"vid00000001": code})
    r.enqueue(jobs_of("subtitle", 1))
    r.tick()
    spawn.run_all()
    failed = r.store.get_by_video("vid00000001")
    assert r.pause_state() is None and failed.status == "failed" and failed.error_code == code
    assert failed.error_message == MESSAGES[code]


def test_second_bot_check_fails_the_job_and_manual_retry_resets(runner_factory):
    r, spawn, h = runner_factory(concurrency=1, fail={"vid00000001": ["E_BOT_CHECK", "E_BOT_CHECK", None]})
    (job,) = r.enqueue(jobs_of("video", 1))
    r.tick()
    spawn.run_all()
    r.resume()
    r.clock.t += 10
    r.tick()
    spawn.run_all()
    failed = r.store.get(job.id)
    assert (failed.status, failed.error_code, failed.bot_checks) == ("failed", "E_BOT_CHECK", 1)
    assert failed.error_message == MESSAGES["E_BOT_CHECK"]
    retried = r.retry(job.id)
    assert (retried.status, retried.bot_checks) == ("queued", 0)
    r.resume()
    r.clock.t += 10
    r.tick()
    spawn.run_all()
    assert r.store.get(job.id).status == "done"


# ---------- network retries ----------


def test_network_retries_wait_2_5_10_then_fail(runner_factory, monkeypatch):
    waits: list[float] = []
    monkeypatch.setattr(queue_module._JobContext, "wait", lambda self, s: waits.append(s))
    r, spawn, h = runner_factory(fail={"vid00000001": ["E_NETWORK"] * 4})
    (job,) = r.enqueue(jobs_of("video", 1))
    r.tick()
    spawn.run_all()
    assert waits == [2.0, 5.0, 10.0]
    assert h.calls == ["vid00000001"] * 4
    attempts = [u["attempt"] for u in r.bus.updates(job.id) if "attempt" in u and "status" not in u]
    assert attempts == [1, 2, 3]
    failed = r.store.get(job.id)
    assert (failed.status, failed.error_code, failed.attempt) == ("failed", "E_NETWORK", 0)
    assert failed.error_message == "เน็ตหลุด ลองใหม่อีกครั้ง"
    assert r.bus.updates(job.id)[-1]["attempt"] is None


def test_network_retry_then_success(runner_factory, monkeypatch):
    monkeypatch.setattr(queue_module._JobContext, "wait", lambda self, s: None)
    r, spawn, h = runner_factory(fail={"vid00000001": ["E_NETWORK", None]})
    (job,) = r.enqueue(jobs_of("audio", 1, {"format": "m4a"}))
    r.tick()
    spawn.run_all()
    assert r.store.get(job.id).status == "done"
    assert r.bus.updates(job.id)[-1]["attempt"] is None


def test_cancel_during_network_wait_ends_cancelled(runner_factory):
    r, spawn, h = runner_factory(fail={"vid00000001": ["E_NETWORK"] * 4}, retry_waits=(30.0, 30.0, 30.0),
                                 spawn=None)
    (job,) = r.enqueue(jobs_of("video", 1))
    r.tick()
    assert wait_for(lambda: r.store.get(job.id).attempt == 1)
    r.cancel(job.id)
    assert wait_for(lambda: r.store.get(job.id).status == "cancelled", 3.0)


# ---------- cancel ----------


def test_ac_q_07_cancel_running_within_3s_removes_workdir(runner_factory, tmp_path):
    h = BlockingHandler()
    r, spawn, _ = runner_factory(handler=h, spawn=None)  # real worker threads
    (job,) = r.enqueue(jobs_of("contact_sheet", 1))
    r.tick()
    h.wait_started(job.id)
    workdir = h.workdirs[job.id]
    assert workdir.is_dir()
    answer = r.cancel(job.id)
    assert answer.status == "running"  # the final "cancelled" arrives later (SSE)
    started = time.monotonic()
    assert wait_for(lambda: r.store.get(job.id).status == "cancelled", 3.0)
    assert time.monotonic() - started < 3.0
    assert not workdir.exists()
    assert wait_for(lambda: not r.is_cancelling(job.id))
    assert any(u.get("cancelling") is True for u in r.bus.updates(job.id))
    last = r.bus.updates(job.id)[-1]
    assert last["status"] == "cancelled" and last["cancelling"] is None


def test_cancelling_flag_while_the_worker_stops(runner_factory):
    def handler(job, ctx):
        ctx.check_cancelled()
        return JobResult()

    r, spawn, _ = runner_factory(handler=handler)
    (job,) = r.enqueue(jobs_of("frames_zip", 1))
    r.tick()
    r.cancel(job.id)
    assert r.is_cancelling(job.id)
    assert r.job_api(r.store.get(job.id))["cancelling"] is True
    assert r.bus.updates(job.id)[-1] == {"id": job.id, "cancelling": True}
    spawn.run_all()
    assert not r.is_cancelling(job.id) and r.store.get(job.id).status == "cancelled"
    assert "cancelling" not in r.job_api(r.store.get(job.id))


def test_cancel_queued_is_immediate(runner_factory):
    r, spawn, h = runner_factory(concurrency=1)
    a, b = r.enqueue(jobs_of("frames_zip", 2))
    cancelled = r.cancel(b.id)
    assert cancelled.status == "cancelled" and cancelled.finished_at
    assert r.bus.updates(b.id)[-1]["status"] == "cancelled"
    assert r.tick() == [a.id]
    spawn.run_all()
    assert r.tick() == []


def test_cancel_errors(runner_factory):
    r, spawn, h = runner_factory()
    (job,) = r.enqueue(jobs_of("frames_zip", 1))
    with pytest.raises(KeyError):
        r.cancel("00000000-0000-7000-8000-000000000000")
    r.tick()
    spawn.run_all()
    with pytest.raises(InvalidTransition):
        r.cancel(job.id)


def test_error_after_cancel_counts_as_cancelled(runner_factory):
    def handler(job, ctx):
        r.cancel(job.id)
        raise YtError("E_UNKNOWN", "ffmpeg exit 1")  # e.g. the killed ffmpeg reports an error

    r, spawn, _ = runner_factory(handler=handler)
    (job,) = r.enqueue(jobs_of("video", 1))
    r.tick()
    spawn.run_all()
    assert r.store.get(job.id).status == "cancelled"


# ---------- retry and reorder ----------


def test_retry_failed_goes_to_end(runner_factory):
    r, spawn, h = runner_factory(concurrency=1, fail={"vid00000001": "E_YT_REFUSED"})
    a, b, c = r.enqueue(jobs_of("frames_zip", 3, {"source": "fast"}))
    r.tick()
    spawn.run_all()
    assert r.store.get(a.id).status == "failed"
    retried = r.retry(a.id)
    assert retried.status == "queued" and retried.position > r.store.get(c.id).position
    assert retried.error_code is None
    patch = r.bus.updates(a.id)[-1]
    assert patch["status"] == "queued" and patch["error"] is None and patch["finishedAt"] is None
    with pytest.raises(InvalidTransition):
        r.retry(b.id)  # queued
    with pytest.raises(KeyError):
        r.retry("00000000-0000-7000-8000-000000000000")


def test_retry_done_or_cancelled_is_rejected(runner_factory):
    r, spawn, h = runner_factory()
    a, b = r.enqueue(jobs_of("frames_zip", 2))
    r.cancel(b.id)
    r.tick()
    spawn.run_all()
    for job in (a, b):
        with pytest.raises(InvalidTransition):
            r.retry(job.id)


def test_reorder_publishes_moved_positions(runner_factory):
    r, spawn, h = runner_factory()
    a, b, c = r.enqueue(jobs_of("frames_zip", 3))
    r.reorder([c.id, a.id])
    assert [j.id for j in r.store.queued()] == [c.id, b.id, a.id]
    moved = {e.data["id"]: e.data for e in r.bus_events() if e.name == "job.updated"}
    assert moved == {c.id: {"id": c.id, "position": 1}, a.id: {"id": a.id, "position": 3}}


# ---------- failures ----------


def test_unexpected_exception_fails_with_unknown(runner_factory):
    r, spawn, h = runner_factory(fail={"vid00000001": RuntimeError("boom")})
    (job,) = r.enqueue(jobs_of("audio", 1, {"format": "mp3"}))
    r.tick()
    spawn.run_all()
    failed = r.store.get(job.id)
    assert (failed.status, failed.error_code) == ("failed", "E_UNKNOWN")
    assert failed.error_message == MESSAGES["E_UNKNOWN"] and "RuntimeError: boom" in failed.error_detail


def test_kind_without_handler_fails_with_unknown(runner_factory):
    r, spawn, h = runner_factory()
    (job,) = r.enqueue([NewJob("vid00000001", "frames_sharp", {})])
    r.tick()
    spawn.run_all()
    assert r.store.get(job.id).error_code == "E_UNKNOWN"


def test_uncommanded_job_cancelled_is_a_failure(runner_factory):
    r, spawn, h = runner_factory(fail={"vid00000001": JobCancelled()})
    (job,) = r.enqueue(jobs_of("frames_zip", 1))
    r.tick()
    spawn.run_all()
    assert r.store.get(job.id).error_code == "E_UNKNOWN"


def test_sse_error_detail_uses_redact(runner_factory):
    r, spawn, h = runner_factory(fail={"vid00000001": "E_YT_REFUSED"}, redact=lambda s: s.replace("fake", "~"))
    (job,) = r.enqueue(jobs_of("video", 1))
    r.tick()
    spawn.run_all()
    assert r.bus.updates(job.id)[-1]["error"]["detail"] == "~ E_YT_REFUSED"
    assert r.store.get(job.id).error_detail == "fake E_YT_REFUSED"  # stored raw


# ---------- startup and shutdown ----------


def test_ac_q_05_recover_interrupts_running_and_empties_work(runner_factory, tmp_path):
    r, spawn, h = runner_factory()
    a, b = r.enqueue(jobs_of("video", 2))
    r.store.transition(a.id, "running")  # left over from a previous run
    leftover = tmp_path / "work" / a.id
    leftover.mkdir(parents=True)
    (leftover / "media.part").write_bytes(b"x")
    (tmp_path / "work" / "stray.tmp").write_bytes(b"x")
    assert r.recover() == 1
    got = r.store.get(a.id)
    assert (got.status, got.error_code, got.error_message) == ("interrupted", "E_INTERRUPTED", MESSAGES["E_INTERRUPTED"])
    assert r.store.get(b.id).status == "queued"
    assert list((tmp_path / "work").iterdir()) == []


def test_recover_without_work_root(runner_factory):
    r, spawn, h = runner_factory()
    assert r.recover() == 0


def test_shutdown_interrupts_running(runner_factory, tmp_path):
    h = BlockingHandler()
    r, spawn, _ = runner_factory(handler=h, spawn=None)
    a, b = r.enqueue(jobs_of("frames_zip", 2))
    r.settings_view.value = 1
    r.tick()
    h.wait_started(a.id)
    r.shutdown(timeout=3.0)
    got = r.store.get(a.id)
    assert (got.status, got.error_code) == ("interrupted", "E_INTERRUPTED")
    assert r.store.get(b.id).status == "queued"
    assert list((tmp_path / "work").iterdir()) == []
    assert r.tick() == []
    assert r.bus.updates(a.id)[-1]["status"] == "interrupted"


def test_shutdown_interrupts_a_job_that_does_not_stop(runner_factory, tmp_path):
    r, spawn, h = runner_factory()
    (job,) = r.enqueue(jobs_of("frames_zip", 1))
    r.tick()  # worker never runs: it cannot react to the stop request
    r.shutdown(timeout=0.05)
    assert r.store.get(job.id).status == "interrupted"
    spawn.run_all()  # the late worker must not crash or change the status
    assert r.store.get(job.id).status == "interrupted"


def test_dispatcher_thread_runs_jobs(runner_factory):
    r, spawn, h = runner_factory(spawn=None)
    r.start()
    r.start()  # idempotent
    (job,) = r.enqueue(jobs_of("frames_zip", 1))
    assert wait_for(lambda: r.store.get(job.id).status == "done")
    assert r.pending_count() == 0
    r.shutdown(timeout=1.0)


# ---------- fix round 1 ----------


def test_redact_is_required(tmp_path):
    db = Database(tmp_path / "app.db")
    db.migrate()
    with pytest.raises(TypeError):
        QueueRunner(JobStore(db), RecordingBus(), {}, settings=StubSettings(1, tmp_path), work_root=tmp_path)  # type: ignore[call-arg]
    db.close()


def test_fast_retry_keeps_the_new_runs_workdir(runner_factory, tmp_path):
    r, spawn, h = runner_factory(fail={"vid00000001": ["E_YT_REFUSED", None]})
    (job,) = r.enqueue(jobs_of("frames_zip", 1))
    restarted: list[str] = []

    def retry_at_once(job_id, fields):
        # the old worker has written "failed" but has not reached its finally block yet
        if fields.get("status") == "failed" and not restarted:
            r.retry(job_id)
            restarted.extend(r.tick())

    r.bus.on_update = retry_at_once
    r.tick()
    spawn.run_one()
    assert restarted == [job.id]
    assert (tmp_path / "work" / job.id).is_dir()  # the second run's workdir survived the first run's cleanup
    assert r.store.get(job.id).status == "running"
    spawn.run_one()
    assert r.store.get(job.id).status == "done"


def test_cancel_during_bot_check_is_not_lost(runner_factory, monkeypatch):
    r, spawn, h = runner_factory(fail={"vid00000001": "E_BOT_CHECK"})
    (job,) = r.enqueue(jobs_of("video", 1))
    original_brake = r.brake

    def brake_then_cancel(reason="E_BOT_CHECK"):
        original_brake(reason)
        r.cancel(job.id)  # arrives after the worker checked ctx.reason, before the requeue

    monkeypatch.setattr(r, "brake", brake_then_cancel)
    r.tick()
    spawn.run_all()
    got = r.store.get(job.id)
    assert got.status == "cancelled" and got.bot_checks == 0
    assert not r.is_cancelling(job.id)


def test_spawn_failure_fails_the_job(runner_factory, tmp_path):
    def broken_spawn(fn):
        raise RuntimeError("can't start new thread")

    r, spawn, h = runner_factory(spawn=broken_spawn)
    (job,) = r.enqueue(jobs_of("frames_zip", 1))
    assert r.tick() == []
    got = r.store.get(job.id)
    assert (got.status, got.error_code) == ("failed", "E_UNKNOWN")
    assert "RuntimeError: can't start new thread" in got.error_detail
    assert not r.is_cancelling(job.id) and r.store.running() == []
    assert not (tmp_path / "work" / job.id).exists()
    assert r.bus.updates(job.id)[-1]["status"] == "failed"


def test_first_progress_after_a_network_retry_clears_attempt(runner_factory, monkeypatch):
    monkeypatch.setattr(queue_module._JobContext, "wait", lambda self, s: None)
    seen_attempts: list[int] = []

    def handler(job, ctx):
        ctx.progress(0.25, 100, 5)
        seen_attempts.append(r.store.get(job.id).attempt)
        if len(seen_attempts) < 3:
            raise YtError("E_NETWORK", "reset")
        ctx.progress(0.5, 100, 4)
        return JobResult()

    r, spawn, _ = runner_factory(handler=handler)
    (job,) = r.enqueue(jobs_of("frames_zip", 1))
    r.tick()
    spawn.run_all()
    assert seen_attempts == [0, 0, 0]  # cleared in the DB by the first progress of each retry run
    patches = [u for u in r.bus.updates(job.id) if "status" not in u]
    assert patches == [
        {"id": job.id, "progress": 0.25, "speedBps": 100, "etaS": 5},
        {"id": job.id, "attempt": 1},
        {"id": job.id, "progress": 0.25, "speedBps": 100, "etaS": 5, "attempt": None},  # same values, still sent
        {"id": job.id, "attempt": 2},  # the retry limit keeps counting
        {"id": job.id, "progress": 0.25, "speedBps": 100, "etaS": 5, "attempt": None},
        {"id": job.id, "progress": 0.5, "speedBps": 100, "etaS": 4},
    ]
    assert r.store.get(job.id).status == "done"


def test_network_retry_limit_counts_even_when_attempt_is_cleared(runner_factory, monkeypatch):
    monkeypatch.setattr(queue_module._JobContext, "wait", lambda self, s: None)
    calls: list[int] = []

    def handler(job, ctx):
        calls.append(1)
        ctx.progress(len(calls) / 10)
        raise YtError("E_NETWORK", "reset")

    r, spawn, _ = runner_factory(handler=handler)
    (job,) = r.enqueue(jobs_of("frames_zip", 1))
    r.tick()
    spawn.run_all()
    assert len(calls) == 4
    assert r.store.get(job.id).error_code == "E_NETWORK"


def test_one_spawn_failure_does_not_fail_the_whole_queue(runner_factory):
    tries: list[int] = []

    def flaky_spawn(fn):
        tries.append(1)
        if len(tries) == 1:
            raise RuntimeError("can't start new thread")
        fn()

    r, spawn, h = runner_factory(concurrency=3, spawn=flaky_spawn)
    a, b, c = r.enqueue(jobs_of("frames_zip", 3))
    assert r.tick() == []  # stops after the first failure
    assert r.store.get(a.id).status == "failed"
    assert [r.store.get(j.id).status for j in (b, c)] == ["queued", "queued"]
    assert r.tick() == [b.id, c.id]


@pytest.mark.parametrize("stages", [["probing"], ["downloading_video", "downloading_video"]])
def test_stage_after_a_network_retry_clears_attempt(runner_factory, monkeypatch, stages):
    monkeypatch.setattr(queue_module._JobContext, "wait", lambda self, s: None)
    seen_attempts: list[int] = []

    def handler(job, ctx):
        stage = stages[min(len(seen_attempts), len(stages) - 1)]
        ctx.stage(stage)  # no progress at all in this handler
        seen_attempts.append(r.store.get(job.id).attempt)
        if len(seen_attempts) == 1:
            ctx.stage("downloading_video")
            raise YtError("E_NETWORK", "reset")
        return JobResult()

    r, spawn, _ = runner_factory(handler=handler)
    (job,) = r.enqueue(jobs_of("frames_zip", 1))
    r.tick()
    spawn.run_all()
    assert seen_attempts == [0, 0]
    patches = [u for u in r.bus.updates(job.id) if "status" not in u]
    attempt_index = patches.index({"id": job.id, "attempt": 1})
    after = patches[attempt_index + 1]
    assert after["attempt"] is None and after["stage"] == stages[-1]
    assert r.store.get(job.id).status == "done"


def test_context_accepts_m5a_stages(runner_factory):
    seen: list[str | None] = []

    def handler(job, ctx):
        for stage in ("cutting", "cutting_ads", "splitting:2/3"):
            ctx.stage(stage)
            seen.append(r.store.get(job.id).stage)
        return JobResult()

    r, spawn, _ = runner_factory(handler=handler)
    (job,) = r.enqueue(jobs_of("frames_zip", 1))
    r.tick()
    spawn.run_all()
    assert seen == ["cutting", "cutting_ads", "splitting:2/3"]
    assert r.store.get(job.id).status == "done"


def test_context_rejects_an_unknown_stage(runner_factory):
    def handler(job, ctx):
        ctx.stage("splitting:x")
        return JobResult()

    r, spawn, _ = runner_factory(handler=handler)
    (job,) = r.enqueue(jobs_of("frames_zip", 1))
    r.tick()
    spawn.run_all()
    assert (r.store.get(job.id).status, r.store.get(job.id).error_code) == ("failed", "E_UNKNOWN")


# ---------- M5 รอบ C: ผู้ฟังคิว (grace ของบัญชียูทูปชั่วคราว) ----------


class RecordingListener:
    """จดทุกครั้งที่คิวแจ้ง: ("queued",) / ("ended", job_id, สถานะในฐานข้อมูลตอนนั้น, จำนวนงานค้าง, ถือล็อกคิวอยู่ไหม)"""

    def __init__(self, runner) -> None:
        self.runner = runner
        self.calls: list[tuple] = []

    def _queue_lock_held(self) -> bool:
        """ลองจับล็อกคิวจากอีกเธรด: จับไม่ได้ = เธรดที่เรียกผู้ฟังยังถือล็อกอยู่ (RLock ของเธรดเดียวกันจับซ้ำได้เสมอ จึงต้องข้ามเธรด)"""
        got: list[bool] = []

        def probe() -> None:
            if self.runner._lock.acquire(blocking=False):
                self.runner._lock.release()
                got.append(True)
            else:
                got.append(False)

        thread = threading.Thread(target=probe)
        thread.start()
        thread.join(5.0)
        return not got[0]

    def job_queued(self) -> None:
        self.calls.append(("queued", self._queue_lock_held()))

    def job_ended(self, job_id: str) -> None:
        job = self.runner.store.get(job_id)
        self.calls.append(("ended", job_id, job.status, self.runner.pending_count(), self._queue_lock_held()))


def test_listener_hears_enqueue_and_retry_once_per_call(runner_factory):
    r, spawn, h = runner_factory(concurrency=1, fail={"vid00000001": "E_YT_REFUSED"})
    heard = r.listener = RecordingListener(r)
    a, _b = r.enqueue(jobs_of("frames_zip", 2))
    assert heard.calls == [("queued", False)]
    r.tick()
    spawn.run_all()
    heard.calls.clear()
    r.retry(a.id)
    assert heard.calls == [("queued", False)]


def test_listener_hears_every_final_state_after_it_is_stored(runner_factory):
    r, spawn, h = runner_factory(concurrency=2, fail={"vid00000002": "E_YT_REFUSED"})
    heard = r.listener = RecordingListener(r)
    a, b, c = r.enqueue(jobs_of("frames_zip", 3))
    r.cancel(c.id)
    r.tick()
    spawn.run_all()
    ended = [call[1:] for call in heard.calls if call[0] == "ended"]
    # c ยกเลิกตอนรอคิว (a, b ยังรอ) · a เสร็จตอน b ยังทำอยู่ · b จบเป็นงานสุดท้าย · ไม่มีครั้งไหนถือล็อกคิว
    assert ended == [(c.id, "cancelled", 2, False), (a.id, "done", 1, False), (b.id, "failed", 0, False)]


def test_cancelling_a_running_job_is_heard_exactly_once(runner_factory):
    def handler(job, ctx):
        ctx.check_cancelled()
        return JobResult()

    r, spawn, _ = runner_factory(handler=handler)
    (job,) = r.enqueue(jobs_of("frames_zip", 1))
    r.tick()
    heard = r.listener = RecordingListener(r)
    r.cancel(job.id)
    assert heard.calls == []  # แค่ส่งสัญญาณหยุด: ยังไม่มีสถานะสุดท้ายให้แจ้ง
    spawn.run_all()
    assert r.store.get(job.id).status == "cancelled"
    assert heard.calls == [("ended", job.id, "cancelled", 0, False)]


def test_last_job_ends_with_an_empty_queue(runner_factory):
    r, spawn, h = runner_factory(concurrency=1)
    heard = r.listener = RecordingListener(r)
    (job,) = r.enqueue(jobs_of("frames_zip", 1))
    r.tick()
    spawn.run_all()
    assert heard.calls[-1] == ("ended", job.id, "done", 0, False)


def test_spawn_failure_is_heard_as_ended(runner_factory):
    def broken_spawn(fn):
        raise RuntimeError("can't start new thread")

    r, spawn, h = runner_factory(spawn=broken_spawn)
    heard = r.listener = RecordingListener(r)
    (job,) = r.enqueue(jobs_of("frames_zip", 1))
    r.tick()
    assert heard.calls[-1] == ("ended", job.id, "failed", 0, False)


def test_listener_errors_do_not_break_the_queue(runner_factory):
    class Broken:
        def job_queued(self) -> None:
            raise RuntimeError("boom")

        def job_ended(self, job_id: str) -> None:
            raise RuntimeError("boom")

    r, spawn, h = runner_factory()
    r.listener = Broken()
    (job,) = r.enqueue(jobs_of("frames_zip", 1))
    r.tick()
    spawn.run_all()
    assert r.store.get(job.id).status == "done"


# ---------- E_QUEUE_PAUSED from a running job (M5 round C follow-up) ----------


class PausedOnceHandler:
    """รอบแรก: งานอื่นเบรกคิวกลางทาง แล้ว with_account_retry โยน E_QUEUE_PAUSED · รอบต่อไปสำเร็จ"""

    def __init__(self, brake: bool = True) -> None:
        self.runner: QueueRunner | None = None
        self.brake = brake
        self.calls = 0

    def __call__(self, job, ctx) -> JobResult:
        self.calls += 1
        if self.calls == 1:
            if self.brake:
                self.runner.brake("E_BOT_CHECK")
            raise queue_paused_error(WALL0 + timedelta(seconds=600))
        return JobResult(title="จบ")


def test_queue_paused_mid_run_requeues_at_front_and_runs_after_pause(runner_factory):
    handler = PausedOnceHandler()
    r, spawn, h = runner_factory(concurrency=1, handler=handler)
    handler.runner = r
    first, second = r.enqueue(jobs_of("video", 2))
    r.tick()
    spawn.run_all()
    job = r.store.get(first.id)
    assert (job.status, job.bot_checks, job.error_code) == ("queued", 0, None)
    assert job.position < r.store.get(second.id).position
    patch = r.bus.updates(first.id)[-1]
    assert patch["status"] == "queued"
    paused = [e for e in r.bus_events() if e.name == "queue.paused"]
    assert len(paused) == 1  # only the brake from the other call, the requeue does not brake again
    assert r.tick() == []  # still paused
    r.wall.now += timedelta(seconds=601)
    r.clock.t += 10
    started = r.tick()
    assert started == [first.id]  # same id, front of the queue
    spawn.run_all()
    done = r.store.get(first.id)
    assert (done.status, done.bot_checks) == ("done", 0)
    assert handler.calls == 2


def test_queue_paused_without_an_active_pause_fails_as_before(runner_factory):
    handler = PausedOnceHandler(brake=False)
    r, spawn, h = runner_factory(concurrency=1, handler=handler)
    handler.runner = r
    (job,) = r.enqueue(jobs_of("video", 1))
    r.tick()
    spawn.run_all()
    failed = r.store.get(job.id)
    assert (failed.status, failed.error_code, failed.bot_checks) == ("failed", "E_QUEUE_PAUSED", 0)
    assert r.pause_state() is None
    assert [e for e in r.bus_events() if e.name == "queue.paused"] == []


# ---------- M6 รอบ B: บรรทัด job_failed ใน app.log (AC-SET-03 · spec 3.2) ----------


def failed_records(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.getMessage().startswith("job_failed ")]


def run_one_job(runner_factory, caplog, outcome, *, title: str = "", kind: str = "video"):
    r, spawn, h = runner_factory(concurrency=1, fail={"vid00000001": outcome})
    (job,) = r.enqueue([NewJob("vid00000001", kind, {}, title)])
    with caplog.at_level(logging.INFO, logger="yttoolkit"):
        r.tick()
        spawn.run_all()
    return r, job


def test_yt_error_failure_logs_one_detailed_warning_with_a_traceback(runner_factory, caplog):
    r, job = run_one_job(runner_factory, caplog, "E_YT_REFUSED")
    (record,) = failed_records(caplog)
    assert record.levelno == logging.WARNING
    first, trace = record.getMessage().split("\n", 1)
    assert first == f"job_failed id={job.id} kind=video code=E_YT_REFUSED detail=fake E_YT_REFUSED"
    assert trace.startswith("Traceback (most recent call last):") and "YtError" in trace
    assert record.exc_info is None  # traceback อยู่ในข้อความ จึงผ่านตัวปิดชื่อคลิปด้วย
    assert r.store.get(job.id).error_code == "E_YT_REFUSED"


def test_unexpected_exception_logs_once_at_error_with_e_unknown(runner_factory, caplog):
    run_one_job(runner_factory, caplog, RuntimeError("boom"))
    (record,) = failed_records(caplog)
    assert record.levelno == logging.ERROR
    assert "code=E_UNKNOWN detail=RuntimeError: boom" in record.getMessage()
    assert "RuntimeError: boom" in record.getMessage().split("\n", 1)[1]
    assert [r for r in caplog.records if r.exc_info] == []  # log.exception เดิมของงานที่พังถูกเอาออก (ไม่ซ้ำสองที่)


def test_cancelled_without_a_reason_logs_a_warning_without_traceback(runner_factory, caplog):
    run_one_job(runner_factory, caplog, JobCancelled())
    (record,) = failed_records(caplog)
    assert record.levelno == logging.WARNING
    assert "\n" not in record.getMessage()
    assert "code=E_UNKNOWN detail=JobCancelled" in record.getMessage()


def test_spawn_failure_logs_a_job_failed_line(runner_factory, caplog):
    def broken_spawn(fn):
        raise RuntimeError("can't start new thread")

    r, spawn, h = runner_factory(spawn=broken_spawn)
    (job,) = r.enqueue(jobs_of("frames_zip", 1))
    with caplog.at_level(logging.INFO, logger="yttoolkit"):
        assert r.tick() == []
    (record,) = failed_records(caplog)
    assert record.levelno == logging.ERROR
    assert record.getMessage().startswith(
        f"job_failed id={job.id} kind=frames_zip code=E_UNKNOWN detail=RuntimeError: can't start new thread\nTraceback"
    )
    assert [r for r in caplog.records if r.exc_info] == []


def test_second_bot_check_logs_a_job_failed_line_and_the_first_does_not(runner_factory, caplog):
    r, spawn, h = runner_factory(concurrency=1, fail={"vid00000001": ["E_BOT_CHECK", "E_BOT_CHECK"]})
    (job,) = r.enqueue(jobs_of("video", 1))
    with caplog.at_level(logging.INFO, logger="yttoolkit"):
        r.tick()
        spawn.run_all()
        assert failed_records(caplog) == []  # ครั้งแรกกลับหัวคิว ไม่ใช่ความล้มเหลว
        r.resume()
        r.clock.t += 10
        r.tick()
        spawn.run_all()
    (record,) = failed_records(caplog)
    assert record.levelno == logging.WARNING
    assert f"job_failed id={job.id} kind=video code=E_BOT_CHECK detail=fake E_BOT_CHECK\nTraceback" in record.getMessage()


def test_job_failed_hides_the_title_home_and_other_drive_paths(runner_factory, caplog, monkeypatch):
    # โฟลเดอร์ผู้ใช้ปลอมแบบ Windows: ไม่พึ่งว่า tmp_path อยู่ใต้ home (CI บน macOS ไม่เป็นแบบนั้น)
    monkeypatch.setattr(errors.Path, "home", lambda: PureWindowsPath("C:/Users/somchai"))
    monkeypatch.setattr(redact, "_home_aliases", lambda home: ())
    title = "สูตรลับขนมไทยของยาย ตอนที่ 3"
    detail = (
        f"[Errno 13] Permission denied: 'C:\\Users\\somchai\\out\\{title}.mp4'"
        f" · copy to 'D:\\backup\\{title}.mp4'"
    )
    run_one_job(runner_factory, caplog, YtError("E_OUTPUT_NOT_WRITABLE", detail), title=title)
    text = caplog.text
    assert title not in text and "somchai" not in text and "D:\\backup" not in text
    assert "<title>" in text and "<path>" in text
    assert "~\\out\\<title>" in text


def test_job_failed_detail_is_one_line_and_capped(runner_factory, caplog):
    run_one_job(runner_factory, caplog, YtError("E_YT_REFUSED", "line one\r\nline two\n" + "x" * 5000))
    first = failed_records(caplog)[0].getMessage().split("\n", 1)[0]
    detail = first.split(" detail=", 1)[1]
    assert detail.startswith("line one\\r\\nline two\\n")
    assert len(detail) <= queue_module.JOB_FAILED_DETAIL_MAX + 6  # \r \n ที่ escape แล้วยาวขึ้นตัวละ 1
    assert detail.endswith("…")


def test_job_failed_line_reaches_app_log(runner_factory, caplog, paths):
    from yttoolkit import probe

    root = logging.getLogger()
    before, level = list(root.handlers), root.level
    try:
        probe.setup_file_log(paths)
        r, job = run_one_job(runner_factory, caplog, "E_YT_REFUSED")
        for handler in root.handlers:
            handler.flush()
        text = (paths.logs / "app.log").read_text(encoding="utf-8")
    finally:
        for handler in list(root.handlers):
            if handler not in before:
                root.removeHandler(handler)
                handler.close()
        root.setLevel(level)
    assert f"WARNING yttoolkit: job_failed id={job.id} kind=video code=E_YT_REFUSED" in text


def test_job_failed_logging_error_never_blocks_the_failed_transition(runner_factory, caplog, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("redaction exploded")

    monkeypatch.setattr(queue_module, "redact_log_detail", boom)
    r, job = run_one_job(runner_factory, caplog, "E_YT_REFUSED")
    assert r.store.get(job.id).status == "failed"
    assert r.store.get(job.id).error_code == "E_YT_REFUSED"
    assert f"job_failed job={job.id} code=E_YT_REFUSED" in caplog.text
    assert "redaction exploded" not in caplog.text


def test_spawn_failure_still_fails_the_job_when_logging_raises(runner_factory, caplog, monkeypatch):
    def broken_spawn(fn):
        raise RuntimeError("can't start new thread")

    def boom(*args, **kwargs):
        raise RuntimeError("redaction exploded")

    monkeypatch.setattr(queue_module, "redact_log_detail", boom)
    r, spawn, h = runner_factory(spawn=broken_spawn)
    (job,) = r.enqueue(jobs_of("frames_zip", 1))
    with caplog.at_level(logging.INFO, logger="yttoolkit"):
        r.tick()
    assert r.store.get(job.id).status == "failed"


def test_job_failed_for_an_untitled_job_is_written_and_not_over_masked(runner_factory, caplog):
    run_one_job(runner_factory, caplog, YtError("E_YT_REFUSED", "refused by the server"), title="")
    (record,) = failed_records(caplog)
    first = record.getMessage().split("\n", 1)[0]
    assert first.endswith("code=E_YT_REFUSED detail=refused by the server")
    assert "<title>" not in record.getMessage()


# ---------- รีวิวท้ายรอบ I1: ชื่อ chapter และชื่อโฟลเดอร์ playlist/ชุดงานต้องไม่หลุดลงบรรทัด job_failed ----------

CHAPTER = "Chapter About Somchai"
FOLDER = "Secret Playlist Name"


def _chapters_row(r, video_id: str, chapters: list[dict]) -> None:
    import json

    r.store._db.execute(
        "INSERT INTO videos (video_id, title, chapters_json, probe_json, probed_at, opened_at)"
        " VALUES (?, ?, ?, '{}', 'x', 'x')",
        (video_id, "row title", json.dumps(chapters, ensure_ascii=False)),
    )


def test_job_failed_hides_chapter_titles_and_the_playlist_folder(runner_factory, caplog):
    detail = (
        f"no free name for 03 {CHAPTER}.mp4 · [Errno 13] Permission denied:"
        f" '~\\Downloads\\{FOLDER}\\Main Clip Title [vid00000001]\\split\\03 {CHAPTER}.mp4'"
    )
    r, spawn, h = runner_factory(concurrency=1, fail={"vid00000001": YtError("E_OUTPUT_NOT_WRITABLE", detail)})
    _chapters_row(r, "vid00000001", [{"start_s": 0, "end_s": 5, "title": CHAPTER}, {"start_s": 5, "end_s": 9}])
    (job,) = r.enqueue([NewJob("vid00000001", "video", {"folder": FOLDER}, "Main Clip Title")])
    with caplog.at_level(logging.INFO, logger="yttoolkit"):
        r.tick()
        spawn.run_all()
    (record,) = failed_records(caplog)
    assert CHAPTER not in record.getMessage() and FOLDER not in record.getMessage()
    assert "no free name for 03 <title>.mp4" in record.getMessage()


@pytest.mark.parametrize("chapters_json", [None, "", "not json", "{}", "[1, null]", '[{"title": 5}]'])
def test_job_titles_ignores_a_broken_chapters_column(chapters_json):
    job = NewJob("vid00000001", "video", {"folder": 7}, "Main Clip Title")
    fake = type("J", (), {"title": job.title, "params": job.params})()
    assert queue_module.job_titles(fake, chapters_json) == ("Main Clip Title",)


def test_job_titles_lists_title_folder_and_every_chapter():
    fake = type("J", (), {"title": "T1", "params": {"folder": FOLDER}})()
    chapters = '[{"title": "A chapter"}, {"title": ""}, {"start_s": 1}, {"title": "B chapter"}]'
    assert queue_module.job_titles(fake, chapters) == ("T1", FOLDER, "A chapter", "B chapter")


def test_a_crash_after_the_job_hides_paths_below_the_output_folder(runner_factory, caplog, monkeypatch):
    # รีวิวท้ายรอบ M3: traceback ของทาง crash ไม่ใช้ log.exception และปิดทุกอย่างใต้โฟลเดอร์ผลลัพธ์
    r, spawn, h = runner_factory(concurrency=1)
    clip = r.settings_view.output / "Another Clip Title [x]" / "a.mp4"

    def broken(job, ctx):
        raise PermissionError(13, "Permission denied", str(clip))

    monkeypatch.setattr(r, "_run_job", broken)
    r.enqueue(jobs_of("video", 1))
    with caplog.at_level(logging.INFO, logger="yttoolkit"):
        r.tick()
        spawn.run_all()
    (record,) = [x for x in caplog.records if "Traceback (most recent call last)" in x.getMessage()]
    assert "PermissionError" in record.getMessage() and "<path>" in record.getMessage()
    assert "Another Clip Title" not in caplog.text
    assert record.exc_info is None


# ---------- M6 รอบ A: รูปแบบชื่อไฟล์ตั้งตอนงานเริ่มครั้งแรก (D4) ----------


class StyleRecorder(ScriptedHandler):
    """ScriptedHandler ที่จดรูปแบบชื่อไฟล์ที่งานได้รับในแต่ละรอบ (ctx.filename_style)"""

    def __init__(self, fail: dict | None = None) -> None:
        super().__init__(fail)
        self.styles: list[str] = []

    def __call__(self, job, ctx) -> JobResult:
        self.styles.append(ctx.filename_style)
        return super().__call__(job, ctx)


def test_the_first_start_stores_the_current_style(runner_factory):
    h = StyleRecorder()
    r, spawn, _ = runner_factory(concurrency=1, handler=h)
    (job,) = r.enqueue(jobs_of("video", 1))
    assert r.store.get(job.id).filename_style is None  # ยังไม่เริ่ม
    r.settings_view.style = "title-channel"
    r.tick()
    assert r.store.get(job.id).filename_style == "title-channel"
    spawn.run_all()
    assert h.styles == ["title-channel"]
    assert r.store.get(job.id).filename_style == "title-channel"
    api = r.job_api(r.store.get(job.id))
    assert "filenameStyle" not in api and "filename_style" not in api  # ข้อมูลภายใน ไม่อยู่ใน API


def test_a_job_queued_before_a_style_change_uses_the_style_at_its_start(runner_factory):
    h = StyleRecorder()
    r, spawn, _ = runner_factory(concurrency=1, handler=h)
    first, second = r.enqueue(jobs_of("frames_zip", 2, {"source": "fast"}))
    r.tick()  # งานแรกเริ่มด้วย "title"
    r.settings_view.style = "title-quality"  # เปลี่ยนระหว่างงานแรกรันอยู่ (AC-OUT-10)
    spawn.run_all()
    r.tick()
    spawn.run_all()
    assert h.styles == ["title", "title-quality"]
    assert (r.store.get(first.id).filename_style, r.store.get(second.id).filename_style) == ("title", "title-quality")


def test_a_retry_after_a_style_change_keeps_the_first_style(runner_factory):
    h = StyleRecorder(fail={"vid00000001": ["E_YT_REFUSED", None]})
    r, spawn, _ = runner_factory(concurrency=1, handler=h)
    r.settings_view.style = "title-channel"
    (job,) = r.enqueue(jobs_of("video", 1))
    r.tick()
    spawn.run_all()
    assert r.store.get(job.id).status == "failed"
    r.settings_view.style = "title-quality"
    requeued = r.retry(job.id)
    assert requeued.filename_style == "title-channel"  # requeue ไม่ล้างรูปแบบ
    r.clock.t += 10  # พ้นช่วงเว้นระหว่างงานยูทูป
    r.tick()
    spawn.run_all()
    assert r.store.get(job.id).status == "done"
    assert h.styles == ["title-channel", "title-channel"]


def test_the_bot_check_requeue_keeps_the_first_style(runner_factory):
    h = StyleRecorder(fail={"vid00000001": ["E_BOT_CHECK", None]})
    r, spawn, _ = runner_factory(concurrency=1, handler=h)
    r.settings_view.style = "title-quality"
    (job,) = r.enqueue(jobs_of("video", 1))
    r.tick()
    spawn.run_all()
    assert r.store.get(job.id).status == "queued"  # ครั้งแรกกลับหัวคิว
    r.settings_view.style = "title"
    r.resume()
    r.clock.t += 10  # พ้นช่วงเว้นระหว่างงานยูทูป
    r.tick()
    spawn.run_all()
    assert h.styles == ["title-quality", "title-quality"]
    assert r.store.get(job.id).filename_style == "title-quality"


def test_network_retries_inside_one_run_keep_the_style(runner_factory, monkeypatch):
    monkeypatch.setattr(queue_module._JobContext, "wait", lambda self, s: None)
    h = StyleRecorder(fail={"vid00000001": ["E_NETWORK", "E_NETWORK", None]})
    r, spawn, _ = runner_factory(concurrency=1, handler=h)
    r.settings_view.style = "title-channel"
    r.enqueue(jobs_of("video", 1))
    r.tick()
    r.settings_view.style = "title"
    spawn.run_all()
    assert h.styles == ["title-channel"] * 3


def test_job_titles_include_the_channel():
    fake = type("J", (), {"title": "T1", "params": {}})()
    assert queue_module.job_titles(fake, None, "ครัวบ้านเรา") == ("T1", " - ครัวบ้านเรา", "ครัวบ้านเรา")
    assert queue_module.job_titles(fake, None) == ("T1",)


def test_job_failed_hides_the_channel_name(runner_factory, caplog):
    channel = "Somchai Kitchen Channel"
    detail = f"[Errno 13] Permission denied: '~\\\\Downloads\\\\Main Clip Title - {channel} [vid00000001]\\\\x.mp4'"
    r, spawn, h = runner_factory(concurrency=1, fail={"vid00000001": YtError("E_OUTPUT_NOT_WRITABLE", detail)})
    r.store._db.execute(
        "INSERT INTO videos (video_id, title, channel, probe_json, probed_at, opened_at)"
        " VALUES ('vid00000001', 'row title', ?, '{}', 'x', 'x')",
        (channel,),
    )
    r.enqueue([NewJob("vid00000001", "video", {}, "Main Clip Title")])
    with caplog.at_level(logging.INFO, logger="yttoolkit"):
        r.tick()
        spawn.run_all()
    (record,) = failed_records(caplog)
    assert channel not in record.getMessage() and "Somchai Kitchen" not in caplog.text


def _failed_line_for(runner_factory, caplog, channel: str, detail: str) -> str:
    r, spawn, _ = runner_factory(concurrency=1, fail={"vid00000001": YtError("E_OUTPUT_NOT_WRITABLE", detail)})
    r.store._db.execute(
        "INSERT INTO videos (video_id, title, channel, probe_json, probed_at, opened_at)"
        " VALUES ('vid00000001', 'row title', ?, '{}', 'x', 'x')",
        (channel,),
    )
    r.enqueue([NewJob("vid00000001", "video", {}, "Main Clip Title")])
    with caplog.at_level(logging.INFO, logger="yttoolkit"):
        r.tick()
        spawn.run_all()
    (record,) = failed_records(caplog)
    return record.getMessage()


def test_job_failed_hides_a_short_channel_in_a_styled_file_name(runner_factory, caplog):
    # รีวิว T2 M2: ช่องชื่อสั้น (TED, BBC) สั้นกว่า TITLE_MIN แต่ในชื่อไฟล์แบบ title-channel ต้องถูกปิด
    message = _failed_line_for(runner_factory, caplog, "TED", "no free name for Main Clip Title - TED.mp4")
    assert "TED" not in message


def test_job_failed_keeps_a_plain_word_that_matches_a_short_channel(runner_factory, caplog):
    # คำธรรมดาที่ไม่ได้อยู่หลัง " - " ไม่ถูกปิด (ไม่ทำให้ข้อความวินิจฉัยเสีย)
    message = _failed_line_for(runner_factory, caplog, "TED", "the TED server refused the request")
    assert "the TED server refused the request" in message


# ---------- M6 รอบ A: hold_active (ปุ่มล้างข้อมูลชั่วคราว spec 3.2) ----------


def test_hold_active_lists_running_jobs_and_their_clips(runner_factory):
    r, spawn, h = runner_factory(concurrency=2)
    first, second, third = r.enqueue([NewJob("vid00000001", "frames_zip", {"source": "fast"}),
                                      NewJob("vid00000002", "frames_zip", {"source": "fast"}),
                                      NewJob("vid00000003", "frames_zip", {"source": "fast"})])  # fmt: skip
    with r.hold_active() as idle:
        assert idle.job_ids == frozenset() and idle.video_ids == frozenset()
    r.tick()
    with r.hold_active() as active:
        assert active.job_ids == {first.id, second.id}
        assert active.video_ids == {"vid00000001", "vid00000002"}
    spawn.run_all()
    with r.hold_active() as after:
        assert after.job_ids == frozenset()
    assert r.store.get(third.id).status == "queued"


def test_no_job_starts_while_the_active_set_is_held(runner_factory):
    r, spawn, h = runner_factory(concurrency=2)
    r.enqueue(jobs_of("frames_zip", 1, {"source": "fast"}))
    started: list[list[str]] = []
    with r.hold_active():
        ticker = threading.Thread(target=lambda: started.append(r.tick()))
        ticker.start()
        ticker.join(0.2)
        assert ticker.is_alive()  # tick รอล็อกของคิว
        assert r.store.running() == []
    ticker.join(5)
    assert len(started[0]) == 1


# ---------- M6 รอบ D1: ไฟล์ค้างใน work/ ที่ยังถูกล็อก (ffmpeg ค้างจากแอพที่โดน End task) ----------


def _leftover_job(r, tmp_path):
    (job,) = r.enqueue(jobs_of("frames_zip", 1))
    r.store.transition(job.id, "running")  # left over from a previous run
    leftover = tmp_path / "work" / job.id
    leftover.mkdir(parents=True)
    return job, leftover


def _retry_and_finish(r, spawn, job, leftover):
    r.retry(job.id)
    started = r.tick()
    assert started == [job.id]
    spawn.run_all()
    got = r.store.get(job.id)
    assert got.status == "done"
    assert leftover.exists()  # the locked leftover was not touched by the retry


@pytest.mark.skipif(sys.platform != "win32", reason="ไฟล์ที่เปิดค้างลบไม่ได้แค่บน Windows")
def test_recover_skips_a_locked_work_file_and_the_retry_uses_a_fresh_folder(runner_factory, tmp_path, caplog):
    r, spawn, h = runner_factory()
    job, leftover = _leftover_job(r, tmp_path)
    locked = leftover / "media.mp4"
    with open(locked, "wb") as handle:  # Python เปิดไฟล์แบบไม่แชร์สิทธิ์ลบ เหมือน ffmpeg ที่ยังเขียนอยู่
        handle.write(b"x")
        with caplog.at_level(logging.WARNING, logger="yttoolkit"):
            assert r.recover() == 1  # must not raise
        assert locked.exists()
        stuck = [rec.getMessage() for rec in caplog.records if "ลบของค้างในโฟลเดอร์ทำงานไม่ได้" in rec.getMessage()]
        assert len(stuck) == 1
        assert str(tmp_path) not in stuck[0] and "media.mp4" not in stuck[0]  # ไม่มี path ใน log
        assert r.store.get(job.id).status == "interrupted"
        _retry_and_finish(r, spawn, job, leftover)
        assert h.calls == ["vid00000001"]
    r.shutdown(timeout=0.2)
    assert not leftover.exists()  # ปิดไฟล์แล้ว รอบเก็บกวาดถัดไปลบได้


def test_retry_uses_a_fresh_folder_when_the_old_one_cannot_be_removed(runner_factory, tmp_path, monkeypatch, caplog):
    r, spawn, h = runner_factory()
    job, leftover = _leftover_job(r, tmp_path)
    (leftover / "media.mp4").write_bytes(b"x")
    monkeypatch.setattr(queue_module.shutil, "rmtree", lambda path, ignore_errors=False: None)  # ลบไม่ได้ทุกอย่าง
    with caplog.at_level(logging.WARNING, logger="yttoolkit"):
        assert r.recover() == 1
    assert any("ลบของค้างในโฟลเดอร์ทำงานไม่ได้ 1 รายการ" in rec.getMessage() for rec in caplog.records)
    seen: list[Path] = []
    original = h.__call__

    class Recording(ScriptedHandler):
        def __call__(self, job, ctx):
            seen.append(ctx.workdir)
            return original(job, ctx)

    r._handlers = dict.fromkeys(KINDS, Recording())  # type: ignore[attr-defined]
    _retry_and_finish(r, spawn, job, leftover)
    assert len(seen) == 1 and seen[0] != leftover and seen[0].parent == leftover.parent
    assert seen[0].name.startswith(f"{job.id}-")
