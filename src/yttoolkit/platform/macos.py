from __future__ import annotations

import fcntl
import os
import signal
import subprocess
from pathlib import Path

from .base import LockFileError, report_lock_open_failure


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
