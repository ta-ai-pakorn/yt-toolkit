"""ข้อมูลชั่วคราวของแอพ (M6 รอบ A, FR-SET-6): ขนาดของ data/cache/ และ work/ และปุ่ม "ล้างข้อมูลชั่วคราว"

ล้างได้เฉพาะสิ่งที่แอพสร้างเอง (spec 3.1):
- data/cache/<รหัสคลิป>/ ที่ db.cache_folder ยอมรับ ยกเว้นคลิปของงานที่กำลังทำ ของการถ่ายภาพที่กำลังทำ
  และโฟลเดอร์ที่มีของกำลังเตรียม (ลูกชื่อมี ".tmp-" ที่แก้ไขไม่เกิน STAGING_GRACE_S วินาที)
- work/<jobId>/ (uuid7 36 ตัว) ยกเว้นงานที่กำลังทำ · work/capture-<hex>/ ยกเว้นการถ่ายที่กำลังทำ
- .clear-<hex>/ ที่ค้างจากการล้างครั้งก่อน (ทั้งสองที่)
อย่างอื่นนับขนาดแต่ไม่ลบ ไม่ตาม symlink / junction · app.db, visitor-session, run/ และโฟลเดอร์ผลลัพธ์อยู่นอกทั้งสองที่

ล้างเป็นสองช่วง (spec 3.2): ใต้ล็อกของคิวและของการถ่ายภาพ (ไม่กี่มิลลิวินาที) ย้ายของที่ล้างได้เข้า .clear-<hex>/
ในโฟลเดอร์เดียวกัน (ไม่ข้ามไดรฟ์) · นอกล็อกจึงค่อยลบจริง ลบไม่หมด (ไฟล์เปิดค้าง) = เหลือไว้ล้างรอบหน้าหรือตอนเปิดโปรแกรม
log มีแต่ตัวเลขและชื่อชนิด error ไม่มี path ไม่มีรหัสคลิป (C4) · core/ ไม่ import api/ platform/ หรือ yt_dlp
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .db import cache_folder
from .queue import ActiveJobs

log = logging.getLogger("yttoolkit")

STAGING_GRACE_S = 600  # ของที่กำลังเตรียม (storyboard.tmp-*, sharp.tmp-*) ใหม่กว่านี้ = โฟลเดอร์ของคลิปนั้นยังไม่ล้าง
STAGING_MARK = ".tmp-"
TRASH_PREFIX = ".clear-"
_TRASH = re.compile(r"\.clear-[0-9a-f]{32}")
_JOB_DIR = re.compile(r"[0-9a-f-]{36}")
_CAPTURE_DIR = re.compile(r"capture-[0-9a-f]{32}")


@dataclass(frozen=True)
class StorageUsage:
    cache_bytes: int
    work_bytes: int
    reclaimable_bytes: int

    def to_api(self) -> dict[str, int]:
        return {"cacheBytes": self.cache_bytes, "workBytes": self.work_bytes, "reclaimableBytes": self.reclaimable_bytes}


class JobHold(Protocol):
    def hold_active(self) -> AbstractContextManager[ActiveJobs]: ...


class CaptureHold(Protocol):
    def hold_active(self) -> AbstractContextManager[tuple[str, str] | None]: ...


@dataclass(frozen=True)
class _Active:
    job_ids: frozenset[str]
    video_ids: frozenset[str]
    capture_dir: str | None


@dataclass(frozen=True)
class _Entry:
    path: Path
    clearable: bool


def _skip_link(entry: os.DirEntry[str]) -> bool:
    return entry.is_symlink() or entry.is_junction()


def tree_bytes(path: Path) -> int:
    """ขนาดรวม (st_size) ของไฟล์ปกติทุกไฟล์ใต้ path (path เป็นไฟล์ก็ได้) ไม่ตาม symlink / junction
    อ่านไม่ได้ = นับ 0 แล้วข้าม · ไม่มี path = 0"""
    try:
        if path.is_symlink() or path.is_junction():
            return 0
        if path.is_file():
            return path.stat().st_size
    except OSError:
        return 0
    total = 0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if _skip_link(entry):
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


class StorageService:
    """ขนาดและการล้างข้อมูลชั่วคราว queue / captures = ตัวที่บอกงานที่กำลังทำ (None = ไม่มีบริการนั้น)"""

    def __init__(
        self,
        cache_root: Path,
        work_root: Path,
        *,
        queue: JobHold | None,
        captures: CaptureHold | None,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._cache_root = Path(cache_root)
        self._work_root = Path(work_root)
        self._queue = queue
        self._captures = captures
        self._now = now
        self._clearing = threading.Lock()  # ล้างครั้งละครั้ง (ครั้งที่สองรอแล้วล้างสิ่งที่เหลือ)

    @contextmanager
    def _hold(self) -> Iterator[_Active]:
        """ถือล็อกของคิวแล้วของการถ่ายภาพ (ลำดับนี้เสมอ) ตลอดบล็อก ระหว่างนี้ไม่มีงาน/การถ่ายเริ่มใหม่"""
        with ExitStack() as stack:
            jobs = stack.enter_context(self._queue.hold_active()) if self._queue is not None else None
            capture = stack.enter_context(self._captures.hold_active()) if self._captures is not None else None
            yield _Active(
                job_ids=jobs.job_ids if jobs is not None else frozenset(),
                video_ids=(jobs.video_ids if jobs is not None else frozenset())
                | (frozenset({capture[0]}) if capture is not None else frozenset()),
                capture_dir=capture[1] if capture is not None else None,
            )

    def _staging(self, folder: Path) -> bool:
        """มีของกำลังเตรียมที่ยังใหม่อยู่ในโฟลเดอร์ของคลิป (เช่นอีกแท็บกำลังสร้าง storyboard)"""
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    if STAGING_MARK not in entry.name:
                        continue
                    try:
                        modified = entry.stat(follow_symlinks=False).st_mtime
                    except OSError:
                        return True  # อ่านเวลาไม่ได้ = ถือว่ายังเตรียมอยู่ (ไม่เสี่ยงลบ)
                    if self._now() - modified < STAGING_GRACE_S:
                        return True
        except OSError:
            return True
        return False

    def _list(self, root: Path, active: _Active, *, cache: bool) -> list[_Entry]:
        """ของทุกชิ้นใน root คู่กับว่าล้างได้ไหม (ตามตาราง spec 3.1) · ไม่มี root = [] · อ่าน root ไม่ได้ = OSError ต่อ"""
        try:
            with os.scandir(root) as found:
                entries = list(found)
        except FileNotFoundError:
            return []
        resolved = root.resolve()
        listed: list[_Entry] = []
        for entry in entries:
            path = Path(entry.path)
            try:
                plain_dir = not _skip_link(entry) and entry.is_dir(follow_symlinks=False)
            except OSError:
                plain_dir = False
            clearable = False
            if plain_dir and _TRASH.fullmatch(entry.name):
                clearable = True
            elif plain_dir and cache:
                folder = cache_folder(resolved, entry.name)
                clearable = folder is not None and entry.name not in active.video_ids and not self._staging(path)
            elif plain_dir and _JOB_DIR.fullmatch(entry.name):
                clearable = entry.name not in active.job_ids
            elif plain_dir and _CAPTURE_DIR.fullmatch(entry.name):
                clearable = entry.name != active.capture_dir
            listed.append(_Entry(path, clearable))
        return listed

    def usage(self) -> StorageUsage:
        """ขนาดตอนนี้: ถือล็อกแค่ตอนดูว่าอะไรล้างได้ วัดขนาดนอกล็อก"""
        with self._hold() as active:
            cache = self._list(self._cache_root, active, cache=True)
            work = self._list(self._work_root, active, cache=False)
        sizes = {entry.path: tree_bytes(entry.path) for entry in (*cache, *work)}
        return StorageUsage(
            cache_bytes=sum(sizes[e.path] for e in cache),
            work_bytes=sum(sizes[e.path] for e in work),
            reclaimable_bytes=sum(sizes[e.path] for e in (*cache, *work) if e.clearable),
        )

    def clear(self) -> int:
        """ล้างทุกอย่างที่ล้างได้ คืนจำนวนไบต์ที่ลบได้จริง (ไม่ใช่ที่วางแผนไว้)"""
        with self._clearing:
            trashes: list[Path] = []
            moved = skipped = 0
            with self._hold() as active:
                for root, cache in ((self._cache_root, True), (self._work_root, False)):
                    try:
                        listed = self._list(root, active, cache=cache)
                    except OSError:  # อ่าน root ไม่ได้ (เช่นสิทธิ์): ข้าม root นี้ แต่ยังลบถังขยะที่ย้ายไปแล้ว
                        skipped += 1
                        log.warning("storage_skip root=%s", "cache" if cache else "work")
                        continue
                    targets = [e.path for e in listed if e.clearable]
                    if not targets:
                        continue
                    trash = root / f"{TRASH_PREFIX}{uuid.uuid4().hex}"
                    try:
                        trash.mkdir()
                    except OSError as exc:
                        skipped += len(targets)
                        log.debug("storage_skip reason=%s", type(exc).__name__)
                        continue
                    trashes.append(trash)
                    for path in targets:
                        try:
                            os.rename(path, trash / path.name)  # โฟลเดอร์แม่เดียวกัน ไม่ข้ามไดรฟ์
                            moved += 1
                        except OSError as exc:  # Windows: มีไฟล์เปิดค้างในโปรแกรมอื่น
                            skipped += 1
                            log.debug("storage_skip reason=%s", type(exc).__name__)
            freed = 0
            for trash in trashes:
                planned = tree_bytes(trash)
                shutil.rmtree(trash, ignore_errors=True)
                left = tree_bytes(trash) if trash.exists() else 0
                try:
                    trash.rmdir()
                except OSError:
                    pass  # ยังมีไฟล์ลบไม่ได้: เหลือ .clear-* ไว้ล้างรอบหน้า
                freed += planned - left
            log.info("storage_clear freed=%s entries=%s skipped=%s", freed, moved, skipped)
            return freed


def sweep_clear_leftovers(cache_root: Path) -> int:
    """ตอนเปิดโปรแกรม: ลบ data/cache/.clear-*/ ที่ค้างจากการล้างที่ถูกตัดกลางทาง คืนจำนวนโฟลเดอร์ที่ลบหมด
    (work/.clear-* ถูกลบอยู่แล้วตอน QueueRunner.recover ล้าง work/ ทั้งโฟลเดอร์)"""
    try:
        with os.scandir(cache_root) as found:
            entries = list(found)
    except FileNotFoundError:
        return 0
    removed = 0
    for entry in entries:
        if not _TRASH.fullmatch(entry.name) or _skip_link(entry) or not entry.is_dir(follow_symlinks=False):
            continue
        shutil.rmtree(entry.path, ignore_errors=True)
        if not os.path.exists(entry.path):
            removed += 1
    return removed
