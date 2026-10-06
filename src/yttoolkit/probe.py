"""เช็กว่าแอพเปิดอยู่หรือไม่ และตั้ง log ขั้นต่ำ ใช้แค่ stdlib

start.bat เรียก `wait` และ `start` ผ่านโมดูลนี้ก่อนโหลด FastAPI หรือ uvicorn
ถ้าไลบรารีเหล่านั้นหายหรือพัง ผู้ใช้ยังเห็นข้อความภาษาไทย และ traceback ยังลง run/logs/app.log
"""

from __future__ import annotations

import http.client
import json
import logging
import logging.handlers
import os
import time
import urllib.request
from collections.abc import Callable

from . import runstate
from .config import HOST, Paths, default_paths
from .platform import Platform, current
from .redact import add_redaction

PING_TIMEOUT = 2

# ไม่ผ่าน proxy ที่ตั้งไว้ในเครื่อง เพราะ 127.0.0.1 ต้องต่อตรงเสมอ
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class _Response:
    def __init__(self, status_code: int, body: bytes) -> None:
        self.status_code = status_code
        self._body = body

    def json(self):
        return json.loads(self._body)


def _get(url: str, timeout: float) -> _Response:
    with _opener.open(url, timeout=timeout) as response:
        return _Response(response.status, response.read())


def base_url(port: int) -> str:
    return f"http://{HOST}:{port}"


def is_alive(port: int, pid: int | None = None, get=_get) -> bool:
    """พอร์ตนี้ตอบ /api/ping และ (ถ้าระบุ pid) pid ที่ตอบกลับตรงกัน กันพอร์ตที่โปรแกรมอื่นมาใช้แทน"""
    try:
        response = get(f"{base_url(port)}/api/ping", timeout=PING_TIMEOUT)
        if response.status_code != 200:
            return False
        return pid is None or response.json().get("pid") == pid
    except (OSError, http.client.HTTPException, ValueError, AttributeError):
        return False


def find_running(paths: Paths, plat: Platform, alive=is_alive) -> runstate.RunInfo | None:
    info = runstate.read(paths.app_json)
    if info and plat.pid_alive(info.pid) and alive(info.port, info.pid):
        return info
    return None


def setup_file_log(paths: Paths) -> None:
    """เขียน log ลง run/logs/app.log แบบหมุนไฟล์ เรียกซ้ำได้ ไม่เพิ่ม handler ซ้ำ"""
    paths.logs.mkdir(parents=True, exist_ok=True)
    filename = paths.logs / "app.log"
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    target = os.path.abspath(filename)
    for existing in root.handlers:
        if isinstance(existing, logging.handlers.RotatingFileHandler) and existing.baseFilename == target:
            add_redaction(existing)
            return
    handler = logging.handlers.RotatingFileHandler(filename, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    # M5 รอบ C: ซ่อนโฟลเดอร์ผู้ใช้และค่าคุกกี้ตั้งแต่สร้าง handler (ก่อนโหลด lifecycle) ไม่มีบรรทัดไหนหลุดก่อนตั้ง log
    add_redaction(handler)
    root.addHandler(handler)


def wait(
    paths: Paths | None = None,
    plat: Platform | None = None,
    *,
    timeout: float = 25.0,
    sleep: Callable[[float], None] = time.sleep,
    out: Callable[[str], None] = print,
) -> int:
    """รอจนแอพตอบกลับ ใช้ตอน start แบบไม่มีหน้าต่าง (ไฟล์ .bat) เพื่อบอกผลให้ผู้ใช้ทราบ"""
    paths = paths or default_paths()
    plat = plat or current()
    deadline = time.monotonic() + timeout
    while True:
        info = find_running(paths, plat)
        if info is not None:
            out(f"เปิด YT Toolkit แล้ว ที่ {base_url(info.port)}")
            return 0
        if time.monotonic() >= deadline:
            break
        sleep(0.5)
    out(f"เปิดโปรแกรมไม่สำเร็จ ดูรายละเอียดได้ที่ {(paths.logs / 'app.log').absolute()}")
    return 1
