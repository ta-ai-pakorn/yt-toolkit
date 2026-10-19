"""M6 รอบ D1: โปรเซสลูกของแอพต้องตายตามแอพ เมื่อแอพโดนปิดแบบ Task Manager "End task" (TerminateProcess)

ก่อนแก้ (audit Exp 2) ffmpeg ที่แอพเปิดไว้ทำงานต่อเต็ม CPU และล็อกไฟล์ใน work/ หลังแอพตาย
เทสนี้เปิดลูกผ่านทางเดียวกับของจริง (core.media.run_ffmpeg + Platform.adopt_child) ลูกเป็น Python ที่แค่หลับ
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from yttoolkit.platform import current

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Job Object มีแค่บน Windows")

# ตัวแม่เลียนแบบแอพ: เปิด "ffmpeg" (Python ที่หลับ) ผ่าน run_ffmpeg ของจริง แล้วรอเหมือนงานที่กำลังทำ
PARENT = """
import os, sys
from yttoolkit.core.media import run_ffmpeg
from yttoolkit.platform import current

plat = current()
child_pid_file, parent_pid_file, child_exe = sys.argv[1], sys.argv[2], sys.argv[3]
with open(parent_pid_file, "w") as f:
    f.write(str(os.getpid()))
code = "import os, sys, time; open(sys.argv[1], 'w').write(str(os.getpid())); time.sleep(120)"
run_ffmpeg([child_exe, "-c", code, child_pid_file], duration_s=None, cancel=lambda: False,
           on_progress=lambda p: None, popen_flags=plat.popen_flags, adopt=plat.adopt_child)
"""


def _read_pid(path: Path, timeout: float = 15.0) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            text = path.read_text().strip()
        except OSError:
            text = ""
        if text:
            return int(text)
        time.sleep(0.05)
    raise AssertionError("process did not write its pid")


def _wait_dead(pid: int, timeout: float) -> bool:
    plat = current()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not plat.pid_alive(pid):
            return True
        time.sleep(0.05)
    return not plat.pid_alive(pid)


@pytest.mark.parametrize("target", ["interpreter", "launcher"])
def test_child_dies_when_app_is_terminated(tmp_path, target):
    """End task บน pythonw ตัวใน (Details) หรือบนตัวเปิดของ .venv (Processes) แล้วลูกต้องหายภายใน ~5 วินาที"""
    child_pid_file = tmp_path / "child.pid"
    parent_pid_file = tmp_path / "parent.pid"
    child_exe = getattr(sys, "_base_executable", sys.executable)  # ลูกไม่ต้องใช้แพ็กเกจใน .venv
    proc = subprocess.Popen(
        [sys.executable, "-c", PARENT, str(child_pid_file), str(parent_pid_file), child_exe],
        stdin=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    child_pid = None
    try:
        interpreter_pid = _read_pid(parent_pid_file)
        child_pid = _read_pid(child_pid_file)
        assert current().pid_alive(child_pid)
        # TerminateProcess แบบ Task Manager (ไม่ใช่ taskkill /T ที่ปิดทั้งต้นไม้เอง)
        os.kill(interpreter_pid if target == "interpreter" else proc.pid, signal.SIGTERM)
        assert _wait_dead(interpreter_pid, 5.0), "the app process did not die"
        assert _wait_dead(child_pid, 5.0), "the child outlived the app (orphan)"
    finally:
        for pid in (child_pid, proc.pid):  # เทสพัง: เก็บเฉพาะโปรเซสที่เทสนี้เปิดเอง ตาม pid
            if pid is not None and current().pid_alive(pid):
                os.kill(pid, signal.SIGTERM)
        proc.wait(timeout=10)


def test_adopted_child_is_killed_by_kill_children_and_others_are_not():
    """kill_children (ตอน Windows ปิดเครื่อง) ปิดเฉพาะลูกที่ผูกไว้ ลูกที่ไม่ได้ผูกต้องไม่โดน"""
    plat = current()
    code = "import time; time.sleep(60)"
    adopted = subprocess.Popen([sys.executable, "-c", code], creationflags=subprocess.CREATE_NO_WINDOW)
    other = subprocess.Popen([sys.executable, "-c", code], creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        plat.adopt_child(adopted)
        plat.kill_children()
        assert adopted.wait(timeout=5) is not None
        time.sleep(0.2)
        assert other.poll() is None
    finally:
        for p in (adopted, other):
            if p.poll() is None:
                p.kill()
            p.wait(timeout=5)
