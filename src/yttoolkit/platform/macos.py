from __future__ import annotations

import fcntl
import os
import platform
import signal
import subprocess
from collections.abc import Callable
from pathlib import Path

from .base import LockFileError, MessageHandler, report_lock_open_failure


class MacPlatform:
    name = "macos"
    popen_flags = 0
    ffmpeg_auto_install = False

    def exe_name(self, name: str) -> str:
        return name

    def downloads_dir(self) -> Path:
        return Path.home() / "Downloads"

    def open_folder(self, path: Path) -> None:
        subprocess.run(["open", str(path)], check=False)

    def reveal(self, path: Path) -> None:
        subprocess.run(["open", "-R", str(path)], check=False)

    def pid_alive(self, pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def kill(self, pid: int) -> None:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass

    def try_lock(self, path: Path) -> object | None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            handle = open(path, "a+b")  # noqa: SIM115 (ตัวจัดการเก็บไว้ให้ release_lock ปิดเอง)
        except OSError as error:
            report_lock_open_failure(path)
            raise LockFileError(f"เปิดไฟล์ lock ไม่ได้: {path}") from error
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return None
        return handle

    def release_lock(self, handle: object) -> None:
        f = handle
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        f.close()

    def path_aliases(self, path: Path) -> list[str]:
        return []

    def os_version(self) -> str:
        """ชื่อและเลขรุ่นสำหรับรายงานแจ้งปัญหา เช่น macOS 15.6 (M6 รอบ B: ให้ protocol ครบ · macOS จริงมาใน M7)"""
        # platform ตัวนี้คือโมดูลของ stdlib (import แบบ absolute) ไม่ใช่แพ็กเกจ yttoolkit.platform
        release = platform.mac_ver()[0]
        return f"macOS {release}" if release else "macOS"

    def adopt_child(self, proc: subprocess.Popen) -> None:
        """macOS ยังไม่มีกลไกผูกโปรเซสลูก (M7) ไม่ทำอะไร"""

    def kill_children(self) -> None:
        """ไม่มีโปรเซสลูกที่ผูกไว้ ไม่ทำอะไร"""

    def tray_message_handlers(
        self, on_session_end: Callable[[], None], window: Callable[[], int | None], reason: str
    ) -> dict[int, MessageHandler]:
        """เมนูบาร์ของ macOS ไม่มีข้อความปิดเครื่องแบบ Windows"""
        return {}
