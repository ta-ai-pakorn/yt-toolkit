import ctypes
import importlib
import os
import subprocess
import sys
import types
from ctypes import wintypes
from pathlib import Path

import pytest

from yttoolkit.platform import current


def test_current_matches_os():
    expected = {"win32": "windows", "darwin": "macos"}[sys.platform]
    assert current().name == expected


def test_downloads_dir_is_absolute():
    assert current().downloads_dir().is_absolute()


def test_pid_alive_for_self():
    assert current().pid_alive(os.getpid()) is True


def test_pid_not_alive_after_exit():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    assert current().pid_alive(proc.pid) is False


def test_pid_alive_rejects_non_positive():
    assert current().pid_alive(0) is False
    assert current().pid_alive(-1) is False


def test_kill_stops_process():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    plat = current()
    assert plat.pid_alive(proc.pid) is True
    plat.kill(proc.pid)
    proc.wait(timeout=10)
    assert plat.pid_alive(proc.pid) is False


def test_try_lock_is_exclusive_until_released(tmp_path):
    plat = current()
    lock_path = tmp_path / "app.lock"
    handle = plat.try_lock(lock_path)
    assert handle is not None
    assert plat.try_lock(lock_path) is None  # ถืออยู่แล้ว ห้ามซ้อน
    plat.release_lock(handle)
    other = plat.try_lock(lock_path)
    assert other is not None  # ปล่อยแล้ว เปิดใหม่ได้
    plat.release_lock(other)


def test_try_lock_returns_none_when_lock_file_cannot_be_opened(tmp_path, caplog):  # M1 follow-up item 5
    plat = current()
    lock_path = tmp_path / "app.lock"
    lock_path.mkdir()  # โฟลเดอร์ชื่อเดียวกับไฟล์ lock เปิดเป็นไฟล์ไม่ได้
    with caplog.at_level("WARNING", logger="yttoolkit"):
        assert plat.try_lock(lock_path) is None
    assert any(r.levelname == "WARNING" for r in caplog.records)


def test_macos_try_lock_returns_none_when_lock_file_cannot_be_opened(macos_module, tmp_path, monkeypatch, caplog):
    def deny(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr("builtins.open", deny)
    with caplog.at_level("WARNING", logger="yttoolkit"):
        assert macos_module.MacPlatform().try_lock(tmp_path / "app.lock") is None
    assert any(r.levelname == "WARNING" for r in caplog.records)


def test_try_lock_logs_unopenable_lock_file_only_once(tmp_path, caplog):
    plat = current()
    lock_path = tmp_path / "app.lock"
    lock_path.mkdir()
    with caplog.at_level("DEBUG", logger="yttoolkit"):
        for _ in range(5):  # start() วนลองซ้ำทุก 0.5 วินาที
            assert plat.try_lock(lock_path) is None
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    assert warnings[0].exc_info is not None  # ครั้งแรกเก็บ traceback ไว้ให้ตรวจ
    # ที่อื่นไม่ถูกกลบ: ไฟล์ lock คนละที่ยังต้องเตือนของมันเอง
    other = tmp_path / "other" / "app.lock"
    other.mkdir(parents=True)
    with caplog.at_level("WARNING", logger="yttoolkit"):
        assert plat.try_lock(other) is None
    assert len([r for r in caplog.records if r.levelname == "WARNING"]) == 2


# (ชื่อโมดูล, ก่อน, หลัง) ที่ fixture ด้านล่างจดไว้ ให้เทสท้ายไฟล์ตรวจว่าไม่มีอะไรรั่ว
_module_snapshots: list[tuple[str, object, object]] = []


def _load_isolated(name: str):
    """โหลดสำเนาใหม่ของ yttoolkit.platform.<name> แล้วคืนของเดิมเข้าที่ (หรือเอาออกถ้าเดิมไม่มี) เมื่อเสร็จ

    บน Windows จริง windows.py อาจถูก import ไว้แล้วโดยเทสอื่น จึงต้องคืนตัวเดิม ไม่ใช่ลบทิ้ง
    """
    import yttoolkit.platform as platform_pkg

    full = f"yttoolkit.platform.{name}"
    before = sys.modules.get(full)
    had_attr = hasattr(platform_pkg, name)
    old_attr = getattr(platform_pkg, name, None)
    sys.modules.pop(full, None)
    try:
        yield importlib.import_module(full)
    finally:
        sys.modules.pop(full, None)
        if before is not None:
            sys.modules[full] = before
        if had_attr:
            setattr(platform_pkg, name, old_attr)
        elif hasattr(platform_pkg, name):
            delattr(platform_pkg, name)
        _module_snapshots.append((full, before, sys.modules.get(full)))


@pytest.fixture
def macos_module(monkeypatch):
    """โหลด yttoolkit.platform.macos บนเครื่องไหนก็ได้ (Windows ไม่มี fcntl จึงใช้ตัวแทน) แล้วเก็บกวาดเมื่อเสร็จ"""
    if sys.platform != "darwin":
        monkeypatch.setitem(sys.modules, "fcntl", types.SimpleNamespace(LOCK_EX=2, LOCK_NB=4, LOCK_UN=8, flock=None))
    yield from _load_isolated("macos")


@pytest.fixture
def windows_module(monkeypatch):
    """เหมือน macos_module แต่สำหรับ windows.py ที่ import msvcrt และใช้ค่าคงที่ของ subprocess เฉพาะ Windows"""
    if sys.platform != "win32":
        monkeypatch.setitem(sys.modules, "msvcrt", types.SimpleNamespace(LK_NBLCK=2, LK_UNLCK=0, locking=None))
        monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
        monkeypatch.setattr(os, "startfile", None, raising=False)
    yield from _load_isolated("windows")


def _record_run(monkeypatch) -> list:
    calls: list = []
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs)))
    return calls


def test_macos_open_folder_and_reveal_use_argument_lists(macos_module, monkeypatch):
    calls = _record_run(monkeypatch)
    folder = Path("/tmp/out folder")
    plat = macos_module.MacPlatform()
    plat.open_folder(folder)
    plat.reveal(folder / "a b.mp4")
    assert calls == [
        ((["open", str(folder)],), {"check": False}),
        ((["open", "-R", str(folder / "a b.mp4")],), {"check": False}),
    ]
    assert all("shell" not in kwargs for _, kwargs in calls)


def test_windows_open_folder_and_reveal(windows_module, monkeypatch):
    opened: list = []
    monkeypatch.setattr(os, "startfile", opened.append, raising=False)
    calls = _record_run(monkeypatch)
    folder = Path("C:/Users/x/out folder")
    plat = windows_module.WindowsPlatform()
    plat.open_folder(folder)
    plat.reveal(folder / "a b.mp4")
    assert opened == [folder]
    assert calls == [((["explorer", f"/select,{folder / 'a b.mp4'}"],), {"check": False})]
    assert all("shell" not in kwargs for _, kwargs in calls)


def test_windows_kill_uses_argument_list_and_popen_flags(windows_module, monkeypatch):
    calls = _record_run(monkeypatch)
    plat = windows_module.WindowsPlatform()
    plat.kill(4321)
    ((args,), kwargs) = calls[0]
    assert args == ["taskkill", "/PID", "4321", "/T", "/F"]
    assert kwargs["creationflags"] == plat.popen_flags
    assert "shell" not in kwargs


def test_windows_popen_flags_and_exe_name(windows_module):
    plat = windows_module.WindowsPlatform()
    assert plat.popen_flags == subprocess.CREATE_NO_WINDOW
    assert plat.exe_name("deno") == "deno.exe"
    assert plat.exe_name("ffmpeg") == "ffmpeg.exe"


def test_macos_popen_flags_and_exe_name(macos_module):
    plat = macos_module.MacPlatform()
    assert plat.popen_flags == 0
    assert plat.exe_name("deno") == "deno"
    assert plat.exe_name("ffmpeg") == "ffmpeg"


def test_current_popen_flags_and_exe_name_match_os():
    plat = current()
    if plat.name == "windows":
        assert plat.popen_flags == subprocess.CREATE_NO_WINDOW
        assert plat.exe_name("deno") == "deno.exe"
    else:
        assert plat.popen_flags == 0
        assert plat.exe_name("deno") == "deno"


def test_windows_downloads_dir_falls_back_when_shell_dll_unavailable(windows_module, monkeypatch):
    def unavailable():
        raise OSError("no shell32")

    monkeypatch.setattr(windows_module, "_shell_libs", unavailable)
    assert windows_module.WindowsPlatform().downloads_dir() == Path.home() / "Downloads"


@pytest.mark.skipif(sys.platform != "win32", reason="ใช้ shell32 จริง")
def test_windows_shell_libs_are_typed_and_loaded_once():
    from yttoolkit.platform import windows

    shell32, ole32 = windows._shell_libs()
    assert windows._shell_libs() == (shell32, ole32)  # โหลดครั้งเดียว
    assert shell32.SHGetKnownFolderPath.restype is ctypes.HRESULT
    assert shell32.SHGetKnownFolderPath.argtypes == (
        ctypes.POINTER(windows._GUID),
        wintypes.DWORD,
        wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_wchar_p),
    )
    assert ole32.CoTaskMemFree.argtypes == (ctypes.c_void_p,)
    assert ole32.CoTaskMemFree.restype is None


def test_ffmpeg_auto_install_capability(macos_module, windows_module):
    assert windows_module.WindowsPlatform().ffmpeg_auto_install is True
    assert macos_module.MacPlatform().ffmpeg_auto_install is False
    assert current().ffmpeg_auto_install is (sys.platform == "win32")


def test_module_fixtures_restore_sys_modules():
    # เทสที่ใช้ macos_module/windows_module ด้านบนรันมาก่อนแล้ว ทุกครั้งต้องคืน sys.modules ตามเดิม
    # (บน Windows จริง windows.py อาจถูก import ไว้ก่อนแล้วอย่างถูกต้อง จึงเทียบกับที่จดไว้ ไม่ใช่เช็คว่าไม่มี)
    if not _module_snapshots:
        pytest.skip("รันเดี่ยว ไม่มีเทสที่ใช้ fixture ให้ตรวจ")
    for name, before, after in _module_snapshots:
        assert after is before, name
    assert sys.modules.get("yttoolkit.platform.macos") is None or sys.platform == "darwin"
    assert sys.platform != "win32" or "fcntl" not in sys.modules
    assert sys.platform == "win32" or "msvcrt" not in sys.modules
