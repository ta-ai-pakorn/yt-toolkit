"""CLI ต้องยังบอกผลเป็นภาษาไทยและเขียน log ได้ แม้ไลบรารีของเว็บ (fastapi) หายหรือพัง"""

import os
import subprocess
import sys
import time

# ซ่อน fastapi แล้วรัน `python -m yttoolkit` ในโปรเซสลูก เหมือนไลบรารีหายจาก .venv
HIDE_FASTAPI = (
    "import runpy, sys\n"
    "sys.modules['fastapi'] = None\n"
    "runpy.run_module('yttoolkit', run_name='__main__')\n"
)


def _env(tmp_path) -> dict[str, str]:
    return {
        **os.environ,
        "YT_TOOLKIT_DATA_ROOT": str(tmp_path),
        "PYTHONUTF8": "1",
        # ถ้า start ดันเปิดได้จริง ต้องไม่เด้ง tray หรือเบราว์เซอร์ (timeout ด้านล่างจะตัดจบแทน)
        "YT_TOOLKIT_TRAY": "0",
        "YT_TOOLKIT_OPEN_BROWSER": "0",
        "YT_TOOLKIT_FFMPEG_PATH_LOOKUP": "0",
    }


def _run(args: list[str], tmp_path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        env=_env(tmp_path),
        capture_output=True,
        encoding="utf-8",
        timeout=60,
    )


def _app_log(tmp_path) -> str:
    return (tmp_path / "run" / "logs" / "app.log").read_text(encoding="utf-8")


def test_wait_reports_in_thai_without_fastapi(tmp_path):
    result = _run(["-c", HIDE_FASTAPI, "wait", "--timeout", "0"], tmp_path)
    assert result.returncode == 1
    assert "เปิดโปรแกรมไม่สำเร็จ ดูรายละเอียดได้ที่" in result.stdout
    assert "Traceback" not in result.stderr


def test_start_logs_import_failure_to_app_log(tmp_path):
    result = _run(["-c", HIDE_FASTAPI, "start"], tmp_path)
    assert result.returncode != 0
    log = _app_log(tmp_path)
    assert "เปิดโปรแกรมไม่สำเร็จ" in log
    assert "Traceback" in log
    assert "ModuleNotFoundError" in log or "ImportError" in log


def test_start_fails_fast_when_lock_path_is_a_folder(tmp_path):  # AC-LIFE-02b
    (tmp_path / "run" / "app.lock").mkdir(parents=True)
    began = time.monotonic()
    result = _run(["-m", "yttoolkit", "start"], tmp_path)
    elapsed = time.monotonic() - began
    assert result.returncode == 1
    assert elapsed < 15  # ไม่วนรอ 20 วินาทีเหมือนตอนมีโปรเซสอื่นถือ lock
    assert "app.lock" in _app_log(tmp_path)
    waited = _run(["-m", "yttoolkit", "wait", "--timeout", "0"], tmp_path)
    assert waited.returncode == 1
    assert "เปิดโปรแกรมไม่สำเร็จ ดูรายละเอียดได้ที่" in waited.stdout
