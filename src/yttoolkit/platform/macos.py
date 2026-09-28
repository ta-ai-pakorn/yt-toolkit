from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path


class MacPlatform:
    name = "macos"
    ffmpeg_exe = "ffmpeg"
    ffprobe_exe = "ffprobe"

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
