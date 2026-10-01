from __future__ import annotations

import random
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from yttoolkit.core import queue as queue_module
from yttoolkit.core.cancel import JobCancelled
from yttoolkit.core.db import Database
from yttoolkit.core.events import Event
from yttoolkit.core.jobs import STATUSES, InvalidTransition, JobResult, JobStore, NewJob, OutputFile
from yttoolkit.core.queue import QueueRunner
from yttoolkit.core.yterrors import MESSAGES, YtError

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
        self._lock = threading.Lock()

    def publish(self, name: str, data: dict) -> None:
        with self._lock:
            self.events.append(Event(name, dict(data)))

    def job_updated(self, job_id: str, fields: dict) -> None:
        with self._lock:
            self.events.append(Event("job.updated", {"id": job_id, **fields}))

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

    def concurrency(self) -> int:
        return self.value

    def output_dir(self) -> Path:
        return self.output


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
