"""ภาพคมอัตโนมัติหลังงานวิดีโอ (M5 รอบ B D6, C8): ทำเมื่อเงื่อนไขครบ ไม่ทำให้งานวิดีโอล้ม ไม่แทนชุดที่ผู้ใช้ขอเอง"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest
from helpers_sharp import BBB, MEDIA, VIDEO, ZOO, SharpEnv

from yttoolkit.core import files
from yttoolkit.core.cancel import JobCancelled
from yttoolkit.core.download import MediaFacts
from yttoolkit.core.events import EventBus
from yttoolkit.core.handlers import build_handlers
from yttoolkit.core.jobs import JobResult, JobStore, NewJob
from yttoolkit.core.media import FakeMediaTools
from yttoolkit.core.queue import QueueRunner
from yttoolkit.core.settings import SettingsStore
from yttoolkit.core.sharp_store import ManualSetKept, commit_sharp, prepare_sharp, read_sharp
from yttoolkit.core.yterrors import YtError

HD = MediaFacts(1280, 720, "SDR")


class NoFfmpeg(FakeMediaTools):
    def available(self) -> bool:
        return False


class FailingFrames(FakeMediaTools):
    def extract_frame(self, src, dst, t_ms, *, long_side, dynamic_range, cancel):
        raise YtError("E_DISK_FULL", "No space left on device")


class GateMedia(FakeMediaTools):
    """ภาพที่สองรอจนถูกสั่งหยุด แล้วหยุดแบบ ffmpeg ที่ถูก kill ตอนปิดโปรแกรม"""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.reached = threading.Event()

    def extract_frame(self, src, dst, t_ms, *, long_side, dynamic_range, cancel):
        if len(self.frames) == 1:
            self.reached.set()
            deadline = time.monotonic() + 10
            while not cancel() and time.monotonic() < deadline:
                time.sleep(0.01)
            raise JobCancelled()
        return super().extract_frame(src, dst, t_ms, long_side=long_side, dynamic_range=dynamic_range, cancel=cancel)


class ManualLandsMidway(FakeMediaTools):
    """งานภาพคมที่ผู้ใช้ขอเองสลับชุดเข้า cache ระหว่างที่ขั้นอัตโนมัติกำลังดึงภาพ (หลังเช็กแรกผ่านไปแล้ว)"""

    def __init__(self, root: Path, cache: Path) -> None:
        super().__init__(root)
        self._cache = cache

    def extract_frame(self, src, dst, t_ms, *, long_side, dynamic_range, cancel):
        if not self.frames:
            staged = prepare_sharp(self._cache, BBB, "manual-job", [(0, MEDIA / "cover.jpg"), (5000, MEDIA / "cover.jpg")],
                                   origin="manual", interval_ms=5000, created_at="2026-10-05T03:00:00+00:00")  # fmt: skip
            commit_sharp(self._cache, BBB, staged)
        return super().extract_frame(src, dst, t_ms, long_side=long_side, dynamic_range=dynamic_range, cancel=cancel)


@pytest.fixture
def env(tmp_path):
    made = SharpEnv(tmp_path)
    made.downloader.media = HD
    made.deps = replace(made.deps, auto_sharp=lambda: True)
    yield made
    made.close()


def _video_file(result: JobResult) -> Path:
    (out,) = result.outputs
    return Path(out.root) / out.rel


def _cache_children(env: SharpEnv, video_id: str = BBB) -> list[str]:
    folder = env.cache / video_id
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


def _stage(cache: Path, origin: str, job_id: str) -> Path:
    return prepare_sharp(cache, BBB, job_id, [(0, MEDIA / "cover.jpg")], origin=origin, interval_ms=None,
                         created_at="2026-10-05T03:00:00+00:00")  # fmt: skip


def test_auto_sharp_after_a_full_720p_video(env):
    result, ctx = env.run("video", BBB, dict(VIDEO))
    video = _video_file(result)
    assert [o.kind for o in result.outputs] == ["video"] and result.notes == ()
    index = read_sharp(env.cache, BBB)
    assert index["origin"] == "auto" and index["intervalMs"] is None and len(index["frames"]) == 128
    assert ctx.stages[-128:] == [f"sharp_frames:{i}/128" for i in range(1, 129)]
    assert {call.src_name for call in env.media.frames} == {video.name}  # อ่านไฟล์ที่อยู่ในโฟลเดอร์ผลลัพธ์แล้ว
    assert sorted(p.name for p in video.parent.iterdir()) == sorted([video.name, files.SOURCE_NOTE_NAME])
    assert _cache_children(env) == ["sharp"]


@pytest.mark.parametrize(
    ("case", "params"),
    [
        ("setting off", {}),
        ("range", {"range": {"startMs": 0, "endMs": 60_000}}),
        ("sponsorblock", {"sponsorblock": ["sponsor"]}),
        ("split chapters", {"splitChapters": True}),
        ("unknown file", {}),
        ("hdr file", {}),
        ("below 720", {}),
        ("above 1080", {}),
        ("no ffmpeg", {}),
    ],
)
def test_auto_sharp_is_skipped(env, case, params):
    deps = env.deps
    if case == "setting off":
        deps = replace(deps, auto_sharp=lambda: False)
    elif case == "unknown file":
        env.downloader.media = None
    elif case == "hdr file":
        env.downloader.media = MediaFacts(3840, 2160, "HDR10")
    elif case == "below 720":
        env.downloader.media = MediaFacts(854, 480, "SDR")
    elif case == "above 1080":
        env.downloader.media = MediaFacts(2560, 1440, "SDR")
    elif case == "no ffmpeg":
        deps = replace(deps, media=NoFfmpeg(MEDIA))
    result, ctx = env.run("video", BBB, {**VIDEO, **params}, deps=deps)
    assert result.outputs[0].kind == "video" and _video_file(result).is_file()
    assert read_sharp(env.cache, BBB) is None
    assert not any(stage.startswith("sharp_frames:") for stage in ctx.stages)


def test_a_1080p_file_still_runs_and_the_1440p_skip_is_logged(env, caplog):
    env.downloader.media = MediaFacts(1920, 1080, "SDR")
    env.run("video", BBB, dict(VIDEO))
    assert read_sharp(env.cache, BBB)["origin"] == "auto"
    env.downloader.media = MediaFacts(2560, 1440, "SDR")
    with caplog.at_level(logging.INFO, logger="yttoolkit"):
        env.run("video", ZOO, dict(VIDEO))
    assert read_sharp(env.cache, ZOO) is None
    assert any("ไม่ทำภาพคมอัตโนมัติ (above 1080)" in r.getMessage() for r in caplog.records)


def test_a_portrait_720_file_runs(env):
    env.downloader.media = MediaFacts(720, 1280, "SDR")
    env.run("video", BBB, dict(VIDEO))
    assert read_sharp(env.cache, BBB)["origin"] == "auto"


def test_without_a_storyboard_the_default_interval_is_used(env):
    env.run("video", ZOO, dict(VIDEO))
    index = read_sharp(env.cache, ZOO)
    assert index["intervalMs"] == 1000 and len(index["frames"]) == 19


def test_zero_frames_is_not_fatal(env):
    env.media.frame_limit_ms = 0
    result, _ = env.run("video", BBB, dict(VIDEO))
    assert _video_file(result).is_file() and result.notes == ()
    assert read_sharp(env.cache, BBB) is None and _cache_children(env) == []


def test_an_extraction_error_is_logged_not_fatal(env, caplog):
    deps = replace(env.deps, media=FailingFrames(MEDIA))
    with caplog.at_level(logging.INFO, logger="yttoolkit"):
        result, _ = env.run("video", BBB, dict(VIDEO), deps=deps)
    assert _video_file(result).is_file()
    assert any("ข้ามภาพคมอัตโนมัติ (YtError)" in r.getMessage() for r in caplog.records)
    assert all(str(env.tmp) not in r.getMessage() for r in caplog.records)


def test_a_broken_setting_read_is_not_fatal(env, caplog):
    def broken() -> bool:
        raise OSError("database is locked")

    with caplog.at_level(logging.INFO, logger="yttoolkit"):
        result, _ = env.run("video", BBB, dict(VIDEO), deps=replace(env.deps, auto_sharp=broken))
    assert _video_file(result).is_file() and result.notes == ()
    assert read_sharp(env.cache, BBB) is None
    assert any("ข้ามภาพคมอัตโนมัติ (OSError)" in r.getMessage() for r in caplog.records)


def test_cancel_during_auto_sharp_ends_done(env):  # Review Focus 5
    result, _ = env.run("video", BBB, dict(VIDEO), cancel_on="sharp_frames:2/128")
    assert _video_file(result).is_file()
    assert read_sharp(env.cache, BBB) is None and _cache_children(env) == []


def test_shutdown_during_auto_sharp_ends_done(tmp_path):  # Review Focus 5
    env = SharpEnv(tmp_path, media=GateMedia(MEDIA))
    env.downloader.media = HD
    try:
        deps = replace(env.deps, auto_sharp=lambda: True)
        store = JobStore(env.db)
        runner = QueueRunner(store, EventBus(), build_handlers(deps), settings=SettingsStore(env.db, env.out),
                             work_root=tmp_path / "queue-work", delay_range=(0.0, 0.0), redact=lambda text: text)  # fmt: skip
        runner.start()
        (job,) = runner.enqueue([NewJob(BBB, "video", dict(VIDEO))])
        assert env.media.reached.wait(10)
        runner.shutdown(timeout=5)
        finished = store.get(job.id)
        assert finished.status == "done" and finished.outputs[0].kind == "video"
        assert read_sharp(env.cache, BBB) is None
    finally:
        env.close()


def test_manual_set_is_not_replaced(env):  # Review Focus 5
    env.run("frames_sharp", BBB, {"intervalS": 60})
    env.run("video", BBB, dict(VIDEO))
    index = read_sharp(env.cache, BBB)
    assert index["origin"] == "manual" and len(index["frames"]) == 11


def test_a_manual_set_that_lands_during_extraction_is_not_replaced(env, caplog):  # race: เช็กแรกผ่านแล้ว
    deps = replace(env.deps, media=ManualLandsMidway(MEDIA, env.cache))
    with caplog.at_level(logging.INFO, logger="yttoolkit"):
        result, ctx = env.run("video", BBB, dict(VIDEO), deps=deps)
    assert _video_file(result).is_file() and result.notes == ()
    assert ctx.stages[-1] == "sharp_frames:128/128"  # ขั้นอัตโนมัติทำจนครบ แล้วถูกกันตอนสลับชุด
    index = read_sharp(env.cache, BBB)
    assert index["origin"] == "manual" and index["intervalMs"] == 5000 and len(index["frames"]) == 2
    assert _cache_children(env) == ["sharp"]  # ไม่มี sharp.tmp-* / sharp.old-* ค้าง
    assert any("ไม่ทำภาพคมอัตโนมัติ (มีชุดที่ขอเองอยู่แล้ว)" in r.getMessage() for r in caplog.records)


def test_an_auto_set_is_replaced_by_the_next_auto_set(env):
    env.run("video", BBB, dict(VIDEO))
    env.media.frame_limit_ms = 300_000
    env.run("video", BBB, dict(VIDEO))
    index = read_sharp(env.cache, BBB)
    assert index["origin"] == "auto" and len(index["frames"]) == 61
    assert _cache_children(env) == ["sharp"]


# ---------- commit_sharp(keep_manual=True): กันชุดที่ขอเองใต้ล็อกเดียวกับการสลับ ----------


def test_keep_manual_refuses_to_replace_a_manual_set(tmp_path):
    cache = tmp_path / "cache"
    commit_sharp(cache, BBB, _stage(cache, "manual", "job-1"))
    staged = _stage(cache, "auto", "job-2")
    with pytest.raises(ManualSetKept):
        commit_sharp(cache, BBB, staged, keep_manual=True)
    assert read_sharp(cache, BBB)["origin"] == "manual"
    assert not staged.exists() and sorted(p.name for p in (cache / BBB).iterdir()) == ["sharp"]


@pytest.mark.parametrize("existing", [None, "auto"])
def test_keep_manual_commits_over_nothing_or_an_auto_set(tmp_path, existing):
    cache = tmp_path / "cache"
    if existing is not None:
        commit_sharp(cache, BBB, _stage(cache, existing, "job-1"))
    index = commit_sharp(cache, BBB, _stage(cache, "auto", "job-2"), keep_manual=True)
    assert index["origin"] == "auto" and sorted(p.name for p in (cache / BBB).iterdir()) == ["sharp"]


def test_without_keep_manual_a_manual_set_is_still_replaced(tmp_path):
    cache = tmp_path / "cache"
    commit_sharp(cache, BBB, _stage(cache, "manual", "job-1"))
    assert commit_sharp(cache, BBB, _stage(cache, "manual", "job-2"))["origin"] == "manual"
    assert commit_sharp(cache, BBB, _stage(cache, "auto", "job-3"))["origin"] == "auto"
