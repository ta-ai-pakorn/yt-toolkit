import os
import subprocess
import sys

from yttoolkit.platform import current


def test_current_matches_os():
    expected = {"win32": "windows", "darwin": "macos"}[sys.platform]
    assert current().name == expected


def test_ffmpeg_names():
    plat = current()
    if plat.name == "windows":
        assert (plat.ffmpeg_exe, plat.ffprobe_exe) == ("ffmpeg.exe", "ffprobe.exe")
    else:
        assert (plat.ffmpeg_exe, plat.ffprobe_exe) == ("ffmpeg", "ffprobe")


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
