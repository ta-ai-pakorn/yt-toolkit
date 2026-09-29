from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

log = logging.getLogger("yttoolkit")

_lock_failures_reported: set[Path] = set()


def report_lock_open_failure(path: Path) -> None:
    """try_lock ถูกเรียกซ้ำทุก 0.5 วินาทีตอนรอ จึงเก็บ traceback แค่ครั้งแรกของแต่ละไฟล์ ไม่ให้ log ท่วม"""
    if path in _lock_failures_reported:
        log.debug("เปิดไฟล์ lock ไม่ได้ (ซ้ำ): %s", path)
        return
    _lock_failures_reported.add(path)
    log.warning("เปิดไฟล์ lock ไม่ได้: %s", path, exc_info=True)


class Platform(Protocol):
    name: str
    ffmpeg_exe: str
    ffprobe_exe: str

    def downloads_dir(self) -> Path: ...

    def open_folder(self, path: Path) -> None: ...

    def reveal(self, path: Path) -> None: ...

    def pid_alive(self, pid: int) -> bool: ...

    def kill(self, pid: int) -> None: ...

    def try_lock(self, path: Path) -> object | None: ...

    def release_lock(self, handle: object) -> None: ...
