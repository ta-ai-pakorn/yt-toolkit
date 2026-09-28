from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest


@dataclass
class FakePlatform:
    """แทน yttoolkit.platform ในเทส บันทึกทุกการเรียกไว้ให้ตรวจ"""

    name: str = "windows"
    ffmpeg_exe: str = "ffmpeg.exe"
    ffprobe_exe: str = "ffprobe.exe"
    downloads: Path = Path("Downloads")
    alive: set[int] = field(default_factory=set)
    killed: list[int] = field(default_factory=list)
    opened: list[Path] = field(default_factory=list)
    revealed: list[Path] = field(default_factory=list)

    def downloads_dir(self) -> Path:
        return self.downloads

    def open_folder(self, path: Path) -> None:
        self.opened.append(path)

    def reveal(self, path: Path) -> None:
        self.revealed.append(path)

    def pid_alive(self, pid: int) -> bool:
        return pid in self.alive

    def kill(self, pid: int) -> None:
        self.killed.append(pid)
        self.alive.discard(pid)


@pytest.fixture
def fake_platform(tmp_path: Path) -> FakePlatform:
    return FakePlatform(downloads=tmp_path / "Downloads")
