"""ข้อมูลชั่วคราว (M6 รอบ A spec 3, AC-SET-07 / AC-SET-08): core/storage.StorageService และ sweep_clear_leftovers

ไฟล์ใหญ่สร้างด้วย truncate (sparse: st_size ตามที่ตั้ง ไม่เขียนข้อมูลจริง) เทสจึงเร็ว · ไม่แตะเครือข่าย
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

from yttoolkit import lifecycle
from yttoolkit.config import Paths
from yttoolkit.core import storage as storage_module
from yttoolkit.core.queue import ActiveJobs
from yttoolkit.core.storage import STAGING_GRACE_S, StorageService, StorageUsage, sweep_clear_leftovers, tree_bytes

BBB = "aqz-KE-bpKQ"
ZOO = "jNQXAC9IVRw"
THAI = "88o5Sk8_m1Y"
JOB = "0190a1b2-c3d4-7e5f-8a6b-7c8d9e0f1a2b"
OTHER_JOB = "0190a1b2-c3d4-7e5f-8a6b-000000000002"
CAPTURE = "capture-" + "a" * 32
NOW = 2_000_000_000.0
MB = 1_000_000


def sized(path: Path, size: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.truncate(size)
    return path


class FakeQueue:
    def __init__(self) -> None:
        self.jobs: dict[str, str] = {}  # job id -> video id
        self.held = 0

    @contextmanager
    def hold_active(self):
        self.held += 1
        yield ActiveJobs(frozenset(self.jobs), frozenset(self.jobs.values()))


class FakeCaptures:
    def __init__(self) -> None:
        self.current: tuple[str, str] | None = None

    @contextmanager
    def hold_active(self):
        yield self.current


@pytest.fixture
def env(tmp_path: Path):
    paths = Paths(data_root=tmp_path)
    paths.ensure()
    queue, captures = FakeQueue(), FakeCaptures()
    service = StorageService(paths.cache, paths.work, queue=queue, captures=captures, now=lambda: NOW)
    return paths, queue, captures, service


def _keep_outside(paths: Paths) -> list[Path]:
    """ของที่ต้องไม่ถูกแตะเลย: ไฟล์ผลลัพธ์ app.db เซสชันผู้ชม และ log"""
    return [
        sized(paths.data_root / "output" / f"คลิป [{BBB}]" / "คลิป.mp4", 3 * MB),
        sized(paths.db, 10_000),
        sized(paths.data / "visitor-session.txt", 100),
        sized(paths.data / "visitor-session.json", 100),
        sized(paths.logs / "app.log", 1_000),
    ]


# ---------- AC-SET-07 ----------


def test_ac_set_07_sizes_within_one_percent_and_clear_empties_the_cache(env):
    paths, _, _, service = env
    keep = _keep_outside(paths)
    written = 0
    for video_id, sizes in ((BBB, (20 * MB, 1 * MB)), (ZOO, (15 * MB,)), (THAI, (10 * MB, 4 * MB))):
        for i, size in enumerate(sizes):
            written += sized(paths.cache / video_id / "storyboard" / f"f_{i:04d}.jpg", size).stat().st_size
    usage = service.usage()
    assert abs(usage.cache_bytes - written) <= written * 0.01
    assert usage.reclaimable_bytes == usage.cache_bytes == 50 * MB and usage.work_bytes == 0
    freed = service.clear()
    assert freed == usage.reclaimable_bytes
    assert list(paths.cache.iterdir()) == []
    assert all(p.is_file() for p in keep)
    assert service.usage() == StorageUsage(0, 0, 0)


def test_usage_api_shape():
    assert StorageUsage(1, 2, 3).to_api() == {"cacheBytes": 1, "workBytes": 2, "reclaimableBytes": 3}


# ---------- AC-SET-08: งานที่กำลังทำ และการถ่ายภาพที่กำลังทำ ----------


def test_ac_set_08_an_active_job_keeps_its_work_dir_and_clip_cache(env):
    paths, queue, _, service = env
    queue.jobs = {JOB: BBB}
    sized(paths.work / JOB / "media.mp4.part", 7 * MB)
    sized(paths.work / OTHER_JOB / "media.mp4", 2 * MB)  # งานที่จบไปแล้ว (เหลือค้าง)
    sized(paths.cache / BBB / "storyboard" / "f_0000.jpg", 5 * MB)
    sized(paths.cache / ZOO / "storyboard" / "f_0000.jpg", 3 * MB)
    usage = service.usage()
    assert (usage.cache_bytes, usage.work_bytes, usage.reclaimable_bytes) == (8 * MB, 9 * MB, 5 * MB)
    assert service.clear() == 5 * MB
    assert (paths.work / JOB / "media.mp4.part").is_file()
    assert (paths.cache / BBB / "storyboard" / "f_0000.jpg").is_file()
    assert not (paths.work / OTHER_JOB).exists() and not (paths.cache / ZOO).exists()
    assert queue.held == 2


def test_the_running_capture_keeps_its_clip_cache_and_work_dir(env):
    paths, _, captures, service = env
    captures.current = (ZOO, CAPTURE)
    sized(paths.work / CAPTURE / "piece.mp4", MB)
    sized(paths.work / ("capture-" + "b" * 32) / "piece.mp4", MB)
    sized(paths.cache / ZOO / "captures" / "c1.jpg", MB)
    service.clear()
    assert (paths.work / CAPTURE / "piece.mp4").is_file() and (paths.cache / ZOO / "captures" / "c1.jpg").is_file()
    assert not (paths.work / ("capture-" + "b" * 32)).exists()


def test_without_queue_or_captures_everything_known_is_clearable(tmp_path):
    paths = Paths(data_root=tmp_path)
    paths.ensure()
    sized(paths.cache / BBB / "pinned.json", 10)
    sized(paths.work / JOB / "x", 10)
    service = StorageService(paths.cache, paths.work, queue=None, captures=None)
    assert service.usage().reclaimable_bytes == 20 and service.clear() == 20


# ---------- ของกำลังเตรียม ของที่ไม่รู้จัก ลิงก์ ----------


def test_a_young_staging_folder_keeps_the_clip_and_an_old_one_does_not(env):
    paths, _, _, service = env
    young = paths.cache / BBB / "storyboard.tmp-0123"
    sized(young / "f_0000.jpg", MB)
    os.utime(young, (NOW - 10, NOW - 10))
    old = paths.cache / ZOO / ("sharp.tmp-" + JOB)
    sized(old / "f_0000.jpg", MB)
    os.utime(old, (NOW - STAGING_GRACE_S - 1, NOW - STAGING_GRACE_S - 1))
    assert service.usage().reclaimable_bytes == MB
    service.clear()
    assert young.is_dir() and not (paths.cache / ZOO).exists()


def test_unknown_entries_are_counted_but_never_cleared(env):
    paths, _, _, service = env
    keep = [
        sized(paths.cache / "notes.txt", 100),
        sized(paths.cache / "storyboard" / "x.jpg", 200),  # ไม่ใช่รหัสคลิป
        sized(paths.cache / "toolongvideoid1" / "x.jpg", 300),
        sized(paths.work / "ffmpeg-download.zip", 400),  # tools.py โหลด ffmpeg ลง work/
        sized(paths.work / "random-dir" / "x", 500),
        sized(paths.work / ".clear-short" / "x", 600),  # ชื่อไม่ตรงรูปแบบของเรา
    ]
    usage = service.usage()
    assert (usage.cache_bytes, usage.work_bytes, usage.reclaimable_bytes) == (600, 1500, 0)
    assert service.clear() == 0
    assert all(p.is_file() for p in keep)


def _link_dir(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        try:
            import _winapi  # Windows: junction ไม่ต้องใช้สิทธิ์ผู้ดูแล

            _winapi.CreateJunction(str(target), str(link))
        except (ImportError, OSError, AttributeError):
            pytest.skip("this machine cannot create a directory link")


def test_a_linked_folder_is_never_followed_or_cleared(env, tmp_path):
    paths, _, _, service = env
    elsewhere = tmp_path / "elsewhere"
    secret = sized(elsewhere / "big.bin", 9 * MB)
    _link_dir(paths.cache / BBB, elsewhere)
    nested = sized(paths.cache / ZOO / "storyboard" / "f.jpg", MB)
    _link_dir(paths.cache / ZOO / "linked", elsewhere)
    usage = service.usage()
    assert usage.cache_bytes == MB and usage.reclaimable_bytes == MB
    service.clear()
    assert secret.is_file() and not nested.exists()
    assert tree_bytes(elsewhere) == 9 * MB


def test_missing_roots_count_as_zero(tmp_path):
    service = StorageService(tmp_path / "no-cache", tmp_path / "no-work", queue=FakeQueue(), captures=FakeCaptures())
    assert service.usage() == StorageUsage(0, 0, 0) and service.clear() == 0


# ---------- Windows: ไฟล์เปิดค้าง ----------


def test_a_folder_that_cannot_be_renamed_stays_and_is_not_counted(env, monkeypatch):
    paths, _, _, service = env
    sized(paths.cache / BBB / "storyboard" / "f.jpg", 2 * MB)
    sized(paths.cache / ZOO / "storyboard" / "f.jpg", 3 * MB)
    real = os.rename

    def locked(src, dst):
        if Path(src).name == BBB:
            raise PermissionError(13, "The process cannot access the file")
        return real(src, dst)

    monkeypatch.setattr(storage_module.os, "rename", locked)
    assert service.clear() == 3 * MB
    assert (paths.cache / BBB / "storyboard" / "f.jpg").is_file()
    assert [p.name for p in paths.cache.iterdir()] == [BBB]  # ไม่มี .clear-* เหลือ


def test_a_file_that_cannot_be_deleted_is_left_in_trash_and_not_counted(env, monkeypatch):
    paths, _, _, service = env
    sized(paths.cache / BBB / "storyboard" / "a.jpg", 2 * MB)
    sized(paths.cache / BBB / "storyboard" / "b.jpg", 3 * MB)
    real = shutil.rmtree

    def partial(path, ignore_errors=False, **kwargs):
        for file in Path(path).rglob("a.jpg"):
            file.unlink()
        return None  # b.jpg "เปิดค้าง" ลบไม่ได้

    monkeypatch.setattr(storage_module.shutil, "rmtree", partial)
    assert service.clear() == 2 * MB
    monkeypatch.setattr(storage_module.shutil, "rmtree", real)
    (trash,) = [p for p in paths.cache.iterdir()]
    assert trash.name.startswith(".clear-")
    assert service.usage().reclaimable_bytes == 3 * MB  # รอบหน้าล้างต่อได้
    assert service.clear() == 3 * MB and list(paths.cache.iterdir()) == []


def test_a_second_clear_waits_for_the_first(env, monkeypatch):
    paths, _, _, service = env
    sized(paths.cache / BBB / "storyboard" / "f.jpg", MB)
    started, release = threading.Event(), threading.Event()
    real = shutil.rmtree

    def slow(path, *args, **kwargs):
        started.set()
        release.wait(5)
        return real(path, *args, **kwargs)

    monkeypatch.setattr(storage_module.shutil, "rmtree", slow)
    results: list[int] = []
    first = threading.Thread(target=lambda: results.append(service.clear()))
    first.start()
    assert started.wait(5)
    second = threading.Thread(target=lambda: results.append(service.clear()))
    second.start()
    second.join(0.2)
    assert second.is_alive()  # รอครั้งแรก
    release.set()
    first.join(5)
    second.join(5)
    assert sorted(results) == [0, MB]


# ---------- ของค้างจากการล้างที่ถูกตัดกลางทาง ----------


def test_sweep_clear_leftovers_removes_only_our_trash(tmp_path):
    cache = tmp_path / "cache"
    sized(cache / (".clear-" + "c" * 32) / BBB / "f.jpg", 10)
    keep = [sized(cache / BBB / "f.jpg", 10), sized(cache / ".clear-x" / "f", 10)]
    assert sweep_clear_leftovers(cache) == 1
    assert all(p.is_file() for p in keep) and not (cache / (".clear-" + "c" * 32)).exists()
    assert sweep_clear_leftovers(tmp_path / "missing") == 0


def test_open_services_sweeps_clear_leftovers(tmp_path, monkeypatch):
    called: list[Path] = []
    monkeypatch.setattr(lifecycle, "sweep_clear_leftovers", lambda root: called.append(root) or 1)
    lifecycle.sweep_clear_once(tmp_path / "cache")
    assert called == [tmp_path / "cache"]

    def broken(root):
        raise OSError("boom")

    monkeypatch.setattr(lifecycle, "sweep_clear_leftovers", broken)
    lifecycle.sweep_clear_once(tmp_path / "cache")  # พลาดแค่ log ไม่ยกต่อ


def test_trash_left_in_the_cache_is_cleared_again(env):
    paths, _, _, service = env
    sized(paths.cache / (".clear-" + "d" * 32) / BBB / "f.jpg", MB)
    sized(paths.work / (".clear-" + "e" * 32) / JOB / "f", MB)
    assert service.usage().reclaimable_bytes == 2 * MB
    assert service.clear() == 2 * MB
    assert list(paths.cache.iterdir()) == [] and list(paths.work.iterdir()) == []


# ---------- C4: log ไม่มี path ไม่มีชื่อคลิป ----------


def test_logs_have_no_paths_or_titles(env, caplog, monkeypatch):
    paths, _, _, service = env
    sized(paths.cache / BBB / "storyboard" / "คลิปลับ.jpg", MB)
    sized(paths.cache / ZOO / "storyboard" / "f.jpg", MB)
    real = os.rename

    def locked(src, dst):
        if Path(src).name == ZOO:
            raise PermissionError(13, f"denied {src}")
        return real(src, dst)

    monkeypatch.setattr(storage_module.os, "rename", locked)
    with caplog.at_level(logging.DEBUG, logger="yttoolkit"):
        service.usage()
        service.clear()
    assert "storage_clear freed=1000000 entries=1 skipped=1" in caplog.text
    assert "storage_skip reason=PermissionError" in caplog.text
    assert str(paths.data_root) not in caplog.text and "คลิปลับ" not in caplog.text
    assert BBB not in caplog.text and ZOO not in caplog.text


# ---------- M6-A final fix: a root that cannot be listed ----------


def test_a_work_root_that_cannot_be_listed_is_skipped_and_the_cache_trash_still_goes(env, caplog, monkeypatch):
    paths, _, _, service = env
    sized(paths.cache / BBB / "storyboard" / "f.jpg", MB)
    sized(paths.work / JOB / "f.part", MB)
    real = os.scandir

    def denied(path="."):
        # os.scandir ถูกแทนทั้งโปรเซส: shutil.rmtree บน macOS/Linux เรียก os.scandir(fd) (ตัวเลข) ไม่ใช่ path ส่งต่อตามเดิม
        if not isinstance(path, int) and Path(path) == paths.work:
            raise PermissionError(13, f"denied {path}")
        return real(path)

    monkeypatch.setattr(storage_module.os, "scandir", denied)
    with caplog.at_level(logging.DEBUG, logger="yttoolkit"):
        freed = service.clear()
    assert freed == MB
    assert list(paths.cache.iterdir()) == []  # no stranded .clear-* trash
    assert (paths.work / JOB / "f.part").is_file()
    assert "storage_skip root=work" in caplog.text
    assert "storage_clear freed=1000000 entries=1 skipped=1" in caplog.text
    assert str(paths.data_root) not in caplog.text and str(paths.work) not in caplog.text
