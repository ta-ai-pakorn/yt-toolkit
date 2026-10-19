from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from yttoolkit.config import Paths
from yttoolkit.platform import LockFileError


@dataclass
class FakePlatform:
    """แทน yttoolkit.platform ในเทส บันทึกทุกการเรียกไว้ให้ตรวจ"""

    name: str = "windows"
    popen_flags: int = 0
    ffmpeg_auto_install: bool = True
    downloads: Path = Path("Downloads")
    alive: set[int] = field(default_factory=set)
    killed: list[int] = field(default_factory=list)
    opened: list[Path] = field(default_factory=list)
    revealed: list[Path] = field(default_factory=list)
    locked: set[Path] = field(default_factory=set)
    unopenable: set[Path] = field(default_factory=set)  # ไฟล์ lock ที่เปิดไม่ได้ (เช่นมีโฟลเดอร์ชื่อเดียวกัน)
    aliases: list[str] = field(default_factory=list)  # ชื่ออื่นของ path (Windows: ชื่อสั้นแบบ 8.3)
    os_version_text: str = "Windows 11 (10.0.26200)"  # M6 รอบ B: บรรทัด "ระบบ:" ของรายงานแจ้งปัญหา
    adopted: list[int] = field(default_factory=list)  # M6 รอบ D1: pid ของโปรเซสลูกที่ผูกไว้กับแอพ
    children_killed: int = 0  # จำนวนครั้งที่ kill_children ถูกเรียก

    def exe_name(self, name: str) -> str:
        return f"{name}.exe" if self.name == "windows" else name

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

    def try_lock(self, path: Path) -> object | None:
        if path in self.unopenable:
            raise LockFileError(f"เปิดไฟล์ lock ไม่ได้: {path}")
        if path in self.locked:
            return None
        self.locked.add(path)
        return path

    def release_lock(self, handle: object) -> None:
        self.locked.discard(handle)

    def path_aliases(self, path: Path) -> list[str]:
        return list(self.aliases)

    def os_version(self) -> str:
        return self.os_version_text

    def adopt_child(self, proc) -> None:
        self.adopted.append(proc.pid)

    def kill_children(self) -> None:
        self.children_killed += 1

    def tray_message_handlers(self, on_session_end, window, reason) -> dict:
        return {}


@pytest.fixture
def fake_platform(tmp_path: Path) -> FakePlatform:
    return FakePlatform(downloads=tmp_path / "Downloads")


@pytest.fixture
def paths(tmp_path: Path) -> Paths:
    p = Paths(data_root=tmp_path)
    p.ensure()
    return p


@pytest.fixture(autouse=True)
def no_pypi_lookup(monkeypatch):
    """เทสต้องไม่ต่อ PyPI จริง ถ้าไม่ได้ส่ง fetcher เองให้ถือว่าออฟไลน์ และล้าง cache ทุกเทส"""
    from yttoolkit.core import tools

    def offline() -> str:
        raise OSError("เทสห้ามเรียก PyPI จริง")

    monkeypatch.setattr(tools, "_fetch_latest_ytdlp", offline)
    monkeypatch.setattr(tools, "_latest_ytdlp_cache", None)
    monkeypatch.setattr(tools, "_network_cache", None)


@pytest.fixture(autouse=True)
def own_child_job(monkeypatch):
    """แต่ละเทสได้ Job Object ของตัวเอง (M6 รอบ D1): kill_children ในเทสหนึ่งไม่ไปปิดลูกของเทสอื่น
    จบเทสปิด job ทิ้ง ลูกที่เทสผูกไว้แล้วลืมปิดโดน kill ตามไปด้วย
    (macOS: import โมดูล windows ไม่ได้เพราะไม่มี msvcrt ไม่มี job ให้แยก)"""
    try:
        from yttoolkit.platform import windows
    except ImportError:
        yield
        return
    job = windows._ChildJob()
    monkeypatch.setattr(windows, "_CHILD_JOB", job)
    yield
    job.close()
