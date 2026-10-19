import ctypes
import importlib
import os
import re
import subprocess
import sys
import types
from ctypes import wintypes
from pathlib import Path

import pytest

from yttoolkit.platform import LockFileError, current


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


def test_try_lock_raises_when_lock_file_cannot_be_opened(tmp_path, caplog):  # M1 follow-up item 5, final fix item 2
    plat = current()
    lock_path = tmp_path / "app.lock"
    lock_path.mkdir()  # โฟลเดอร์ชื่อเดียวกับไฟล์ lock เปิดเป็นไฟล์ไม่ได้
    with caplog.at_level("WARNING", logger="yttoolkit"), pytest.raises(LockFileError):
        plat.try_lock(lock_path)  # ต้องไม่คืน None เพราะ None แปลว่า "มีคนถือ lock อยู่"
    assert any(r.levelname == "WARNING" for r in caplog.records)


def test_macos_try_lock_raises_when_lock_file_cannot_be_opened(macos_module, tmp_path, monkeypatch, caplog):
    def deny(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr("builtins.open", deny)
    with caplog.at_level("WARNING", logger="yttoolkit"), pytest.raises(LockFileError):
        macos_module.MacPlatform().try_lock(tmp_path / "app.lock")
    assert any(r.levelname == "WARNING" for r in caplog.records)


def test_lock_file_error_is_an_oserror():
    assert issubclass(LockFileError, OSError)


def test_try_lock_logs_unopenable_lock_file_only_once(tmp_path, caplog):
    plat = current()
    lock_path = tmp_path / "app.lock"
    lock_path.mkdir()
    with caplog.at_level("DEBUG", logger="yttoolkit"):
        for _ in range(5):  # start() วนลองซ้ำทุก 0.5 วินาที
            with pytest.raises(LockFileError):
                plat.try_lock(lock_path)
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    assert warnings[0].exc_info is not None  # ครั้งแรกเก็บ traceback ไว้ให้ตรวจ
    # ที่อื่นไม่ถูกกลบ: ไฟล์ lock คนละที่ยังต้องเตือนของมันเอง
    other = tmp_path / "other" / "app.lock"
    other.mkdir(parents=True)
    with caplog.at_level("WARNING", logger="yttoolkit"), pytest.raises(LockFileError):
        plat.try_lock(other)
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
    calls: list = []
    monkeypatch.setattr(windows_module, "run_adopted", lambda *args, **kwargs: calls.append((args, kwargs)))
    plat = windows_module.WindowsPlatform()
    plat.kill(4321)
    ((args, adopt), kwargs) = calls[0]
    assert args == ["taskkill", "/PID", "4321", "/T", "/F"]
    assert adopt == plat.adopt_child  # M6 รอบ D1: taskkill ก็ผูกกับแอพ
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


# ---- final fix item 9: ชื่อสั้นแบบ 8.3 ---------------------------------------------------------------------------------


def test_macos_path_aliases_is_empty(macos_module):
    assert macos_module.MacPlatform().path_aliases(Path("/Users/somchai")) == []


def test_windows_path_aliases_is_empty_when_lookup_fails(windows_module, monkeypatch):
    def unavailable():
        raise OSError("no kernel32")

    monkeypatch.setattr(windows_module, "_short_path_name", unavailable)
    assert windows_module.WindowsPlatform().path_aliases(Path("C:/Users/Somchai Jaidee")) == []


@pytest.mark.skipif(sys.platform != "win32", reason="ใช้ GetShortPathNameW จริง")
def test_windows_path_aliases_returns_short_name(tmp_path):
    folder = tmp_path / "a rather long folder name"
    folder.mkdir()
    aliases = current().path_aliases(folder)
    if not aliases:
        pytest.skip("ไดรฟ์นี้ปิดการสร้างชื่อสั้นแบบ 8.3")
    assert len(aliases) == 1
    assert aliases[0] != str(folder)
    assert "~" in aliases[0]
    assert os.path.samefile(aliases[0], folder)


@pytest.mark.skipif(sys.platform != "win32", reason="ใช้ GetShortPathNameW จริง")
def test_windows_path_aliases_empty_when_missing_or_same(tmp_path):
    plat = current()
    assert plat.path_aliases(tmp_path / "does-not-exist") == []
    assert plat.path_aliases(Path(os.environ["SystemRoot"])) == []  # C:\Windows ชื่อสั้นอยู่แล้ว


@pytest.mark.skipif(sys.platform != "win32", reason="ใช้ kernel32 จริง")
def test_windows_short_path_name_is_typed_and_loaded_once():
    from yttoolkit.platform import windows

    fn = windows._short_path_name()
    assert windows._short_path_name() is fn
    assert fn.argtypes == (wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD)
    assert fn.restype is wintypes.DWORD


# ---- M6 รอบ B: ชื่อและเลขรุ่นของระบบปฏิบัติการ (บรรทัด "ระบบ:" ของรายงานแจ้งปัญหา) ------------------------------


def _winver(major: int, minor: int, build: int):
    return lambda: types.SimpleNamespace(major=major, minor=minor, build=build)


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ((10, 0, 26200), "Windows 11 (10.0.26200)"),
        ((10, 0, 22000), "Windows 11 (10.0.22000)"),
        ((10, 0, 19045), "Windows 10 (10.0.19045)"),
        ((6, 3, 9600), "Windows 6 (6.3.9600)"),
    ],
)
def test_windows_os_version_names_11_by_build(windows_module, monkeypatch, version, expected):
    monkeypatch.setattr(windows_module.sys, "getwindowsversion", _winver(*version), raising=False)
    assert windows_module.WindowsPlatform().os_version() == expected


def test_windows_os_version_falls_back_when_unreadable(windows_module, monkeypatch):
    def broken():
        raise OSError("no version")

    monkeypatch.setattr(windows_module.sys, "getwindowsversion", broken, raising=False)
    assert windows_module.WindowsPlatform().os_version() == "Windows"


@pytest.mark.parametrize(("release", "expected"), [("15.6", "macOS 15.6"), ("", "macOS")])
def test_macos_os_version(macos_module, monkeypatch, release, expected):
    monkeypatch.setattr(macos_module.platform, "mac_ver", lambda: (release, ("", "", ""), ""))
    assert macos_module.MacPlatform().os_version() == expected


@pytest.mark.skipif(sys.platform != "win32", reason="อ่านเลขรุ่นของ Windows จริง")
def test_windows_os_version_live():
    text = current().os_version()
    assert text.startswith("Windows ")
    assert text.endswith(")") and "(10." in text


# ---- กฎของโปรเจกต์: เช็กระบบปฏิบัติการได้ที่ yttoolkit.platform ที่เดียว (M6 รอบ B C2) ------------------------------

SRC = Path(__file__).resolve().parents[2] / "src" / "yttoolkit"
_OS_CHECK = re.compile(
    r"\bsys\.platform\b|\bos\.name\b|getwindowsversion"
    r"|\bplatform\.(?:system|release|version|mac_ver|win32_ver|uname|platform|win32_edition)\("
    r"|\bfrom\s+(?:sys|os)\s+import\s+[^#\n]*\b(?:platform|name)\b"  # from sys import platform · from os import name
)


def test_only_the_platform_package_checks_the_os():
    offenders = [
        f"{path.relative_to(SRC).as_posix()}:{n}"
        for path in sorted(SRC.rglob("*.py"))
        if path.relative_to(SRC).parts[0] != "platform"
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if _OS_CHECK.search(line)
    ]
    assert offenders == []


def test_os_check_detector():
    for line in ("if sys.platform == 'win32':", "os.name == 'nt'", "platform.system()", "sys.getwindowsversion()",
                 "from sys import platform", "from os import name", "from os import path, name as os_name",
                 "platform.uname()", "platform.platform()", "platform.win32_edition()"):  # fmt: skip
        assert _OS_CHECK.search(line), line
    for line in ("platform.os_version()", "ctx.plat.name", "from ..platform import Platform",
                 "from .platform import current", "from os import environ", "from sys import argv  # platform"):  # fmt: skip
        assert not _OS_CHECK.search(line), line
