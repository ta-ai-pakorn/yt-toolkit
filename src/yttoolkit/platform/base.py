from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

log = logging.getLogger("yttoolkit")

_lock_failures_reported: set[Path] = set()


class LockFileError(OSError):
    """เปิดหรือสร้างไฟล์ lock ไม่ได้ ต่างจาก try_lock คืน None ซึ่งแปลว่ามีโปรเซสอื่นถือ lock อยู่จริง"""


def report_lock_open_failure(path: Path) -> None:
    """try_lock ถูกเรียกซ้ำทุก 0.5 วินาทีตอนรอ จึงเก็บ traceback แค่ครั้งแรกของแต่ละไฟล์ ไม่ให้ log ท่วม"""
    if path in _lock_failures_reported:
        log.debug("เปิดไฟล์ lock ไม่ได้ (ซ้ำ): %s", path)
        return
    _lock_failures_reported.add(path)
    log.warning("เปิดไฟล์ lock ไม่ได้: %s", path, exc_info=True)


class Platform(Protocol):
    name: str
    popen_flags: int  # creationflags สำหรับ subprocess (Windows: ไม่เด้งหน้าต่างดำ)
    ffmpeg_auto_install: bool  # แอพโหลด ffmpeg ให้เองได้บนระบบนี้หรือไม่

    def exe_name(self, name: str) -> str: ...

    def downloads_dir(self) -> Path: ...

    def open_folder(self, path: Path) -> None: ...

    def reveal(self, path: Path) -> None: ...

    def pid_alive(self, pid: int) -> bool: ...

    def kill(self, pid: int) -> None: ...

    def try_lock(self, path: Path) -> object | None:
        """คืนตัวจัดการ lock หรือ None ถ้ามีโปรเซสอื่นถือ lock อยู่ ถ้าเปิดไฟล์ไม่ได้จะโยน LockFileError"""
        ...

    def release_lock(self, handle: object) -> None: ...

    def path_aliases(self, path: Path) -> list[str]:
        """ชื่ออื่นที่ชี้ไปที่เดียวกับ path (Windows: ชื่อสั้นแบบ 8.3) ใช้ตัดชื่อผู้ใช้ออกจากข้อความ error"""
        ...

    def os_version(self) -> str:
        """ชื่อและเลขรุ่นของระบบปฏิบัติการสำหรับรายงานแจ้งปัญหา"""
        ...
