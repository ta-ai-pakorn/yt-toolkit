from __future__ import annotations

from pathlib import Path
from typing import Protocol


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
