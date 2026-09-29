"""เปิด ปิด และดูแลวงจรชีวิตของแอพ (FR-LIFE-*)"""

from __future__ import annotations

import logging
import logging.handlers
import os
import subprocess
import sys
import threading
import time
import webbrowser
from collections.abc import Callable, Iterable
from pathlib import Path

import httpx
import uvicorn

from . import __version__, runstate
from .app import AppContext, create_app
from .config import HOST, Paths, default_paths, env_flag
from .core import tools
from .platform import Platform, current

log = logging.getLogger("yttoolkit")

DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


def base_url(port: int) -> str:
    return f"http://{HOST}:{port}"


def is_alive(port: int, get=httpx.get) -> bool:
    try:
        return get(f"{base_url(port)}/api/ping", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


def find_running(paths: Paths, plat: Platform, alive=is_alive) -> runstate.RunInfo | None:
    info = runstate.read(paths.app_json)
    if info and plat.pid_alive(info.pid) and alive(info.port):
        return info
    return None


def default_output_dir(plat: Platform) -> Path:
    return plat.downloads_dir() / "YT-Toolkit"


def prepare_environment() -> None:
    scripts = str(tools.scripts_dir())
    parts = os.environ.get("PATH", "").split(os.pathsep)
    if not parts or parts[0] != scripts:
        os.environ["PATH"] = os.pathsep.join([scripts, *[p for p in parts if p != scripts]])


def git_commit(root: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() or None


def setup_file_logging(paths: Paths) -> None:
    paths.logs.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        paths.logs / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if sys.stdout is None or sys.stderr is None:  # pythonw.exe ไม่มี console
        stream = open(paths.logs / "console.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
        sys.stdout = sys.stdout or stream
        sys.stderr = sys.stderr or stream


class Server:
    """uvicorn ที่รันใน thread แยก เพื่อให้ main thread ว่างไว้ให้ tray"""

    def __init__(self, ctx: AppContext) -> None:
        self.config = uvicorn.Config(
            create_app(ctx), host=HOST, port=ctx.port, log_config=None, access_log=False
        )
        self._server = uvicorn.Server(self.config)
        self._thread = threading.Thread(target=self._server.run, name="uvicorn", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.should_exit = True

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout)

    def wait_until_ready(self, timeout: float = 15.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._server.started:
                return True
            if not self._thread.is_alive():
                return False
            time.sleep(0.1)
        return False


def ensure_ffmpeg(paths: Paths, plat: Platform) -> None:
    if tools.find_ffmpeg(paths, plat) is not None or plat.name != "windows":
        return
    try:
        tools.install_ffmpeg(paths, plat)
        log.info("ติดตั้ง ffmpeg อัตโนมัติสำเร็จ")
    except tools.ToolInstallError:
        log.exception("ติดตั้ง ffmpeg อัตโนมัติไม่สำเร็จ")


def run_app(
    *,
    paths: Paths,
    plat: Platform,
    port: int,
    with_tray: bool,
    open_browser: bool,
    auto_ffmpeg: bool,
    extra_origins: Iterable[str] = (),
) -> int:
    token = runstate.new_token()
    stop_event = threading.Event()
    tray_holder: list = []

    def request_shutdown() -> None:
        stop_event.set()
        if tray_holder:
            tray_holder[0].stop()

    ctx = AppContext(
        paths=paths,
        plat=plat,
        port=port,
        token=token,
        version=__version__,
        commit=git_commit(paths.code_root),
        output_dir=default_output_dir(plat),
        request_shutdown=request_shutdown,
        extra_origins=tuple(extra_origins),
    )
    server = Server(ctx)
    server.start()
    if not server.wait_until_ready():
        log.error("เปิดเซิร์ฟเวอร์ไม่สำเร็จที่ port %s", port)
        server.stop()
        server.join(timeout=5)
        runstate.clear(paths.app_json)  # lock ปล่อยโดยผู้เรียก (start/serve) ใน finally
        return 1
    runstate.write(
        paths.app_json, runstate.RunInfo(port=port, pid=os.getpid(), token=token, started_at=runstate.now_iso())
    )
    if auto_ffmpeg:
        threading.Thread(target=ensure_ffmpeg, args=(paths, plat), name="ffmpeg-setup", daemon=True).start()
    url = base_url(port)
    if open_browser:
        webbrowser.open(url)

    def open_output() -> None:
        ctx.output_dir.mkdir(parents=True, exist_ok=True)
        plat.open_folder(ctx.output_dir)

    def quit_from_tray() -> None:
        if ctx.pending_jobs() > 0:
            webbrowser.open(f"{url}/?confirmShutdown=1")  # หน้าเว็บถามยืนยัน (FR-LIFE-4, ทำใน M4)
        else:
            request_shutdown()

    try:
        if with_tray:
            from .tray import build_tray

            icon = build_tray(lambda: webbrowser.open(url), open_output, quit_from_tray)
            tray_holder.append(icon)
            icon.run()  # บล็อก main thread จนกว่าจะเรียก icon.stop()
        else:
            while not stop_event.wait(0.5):
                pass
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
        server.join(timeout=10)
        runstate.clear(paths.app_json)
    return 0


def start(
    paths: Paths | None = None,
    plat: Platform | None = None,
    *,
    wait_timeout: float = 20.0,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    paths = paths or default_paths()
    plat = plat or current()
    paths.ensure()
    setup_file_logging(paths)
    prepare_environment()
    lock = plat.try_lock(paths.run / "app.lock")
    if lock is None:
        # อีกโปรเซสถือ lock อยู่ (กำลังเปิดหรือรันอยู่แล้ว) รอให้มันเขียน run/app.json แล้วค่อยเปิดเบราว์เซอร์
        # แทนที่จะแข่งกันเลือก port เอง (FR-LIFE-2)
        # ถ้าระหว่างรอ lock ว่างลง (โปรเซสนั้นตายไปก่อนเขียน app.json) ให้รับช่วงเป็นเจ้าของเอง
        deadline = time.monotonic() + wait_timeout
        while True:
            info = find_running(paths, plat)
            if info is not None:
                webbrowser.open(base_url(info.port))
                return 0
            if time.monotonic() >= deadline:
                break
            sleep(0.5)
            lock = plat.try_lock(paths.run / "app.lock")
            if lock is not None:
                break
        if lock is None:
            log.error(
                "เปิดโปรแกรมไม่สำเร็จ: มีโปรเซสอื่นกำลังเปิดอยู่ แต่ตรวจไม่พบเซิร์ฟเวอร์ที่ทำงานภายใน %s วินาที",
                wait_timeout,
            )
            return 1
    try:
        # ถือ lock อยู่ แปลว่าไม่มีอินสแตนซ์อื่นรัน app.json ที่เหลืออยู่จึงเป็นของเก่า
        runstate.clear(paths.app_json)
        return run_app(
            paths=paths,
            plat=plat,
            port=runstate.pick_port(),
            with_tray=env_flag("YT_TOOLKIT_TRAY", True),
            open_browser=env_flag("YT_TOOLKIT_OPEN_BROWSER", True),
            auto_ffmpeg=True,
        )
    finally:
        plat.release_lock(lock)


def serve(port: int | None = None, dev: bool = False) -> int:
    """รันแบบไม่มี tray และไม่เปิดเบราว์เซอร์ ใช้ตอนพัฒนา เทส และ E2E"""
    paths = default_paths()
    plat = current()
    paths.ensure()
    logging.basicConfig(level=logging.INFO)
    prepare_environment()
    lock = plat.try_lock(paths.run / "app.lock")
    if lock is None:
        log.error("เปิดเซิร์ฟเวอร์ไม่สำเร็จ: มีโปรเซสอื่นถือ lock ของ YT Toolkit อยู่แล้ว")
        return 1
    try:
        runstate.clear(paths.app_json)  # ถือ lock อยู่ แปลว่า app.json ที่เหลืออยู่เป็นของเก่า
        return run_app(
            paths=paths,
            plat=plat,
            port=port or runstate.pick_port(),
            with_tray=False,
            open_browser=False,
            auto_ffmpeg=False,
            extra_origins=DEV_ORIGINS if dev else (),
        )
    finally:
        plat.release_lock(lock)


def _app_holds_lock(paths: Paths, plat: Platform) -> bool:
    """True ถ้ามีแอพถือ run/app.lock อยู่ ถ้าจับได้เองจะปล่อยคืนทันที"""
    lock = plat.try_lock(paths.run / "app.lock")
    if lock is None:
        return True
    plat.release_lock(lock)
    return False


def _still_named_by_app_json(paths: Paths, info: runstate.RunInfo) -> bool:
    """True ถ้า run/app.json ยังระบุอินสแตนซ์เดิม (pid และ started_at ตรงกับที่อ่านไว้ตอนเริ่ม stop)"""
    current_info = runstate.read(paths.app_json)
    return current_info is not None and (current_info.pid, current_info.started_at) == (info.pid, info.started_at)


def stop(
    paths: Paths | None = None,
    plat: Platform | None = None,
    *,
    post=httpx.post,
    ask: Callable[[str], str] = input,
    sleep: Callable[[float], None] = time.sleep,
    out: Callable[[str], None] = print,
) -> int:
    paths = paths or default_paths()
    plat = plat or current()
    info = runstate.read(paths.app_json)
    # pid ใน app.json อาจค้างจากตอนเครื่องดับ แล้ว Windows เอาเลขนี้ไปให้โปรแกรมอื่น
    # แอพที่รันอยู่จริงถือ run/app.lock ไว้ตลอด ถ้าจับ lock ได้แปลว่าไม่มีแอพเปิดอยู่
    if info is None or not plat.pid_alive(info.pid) or not _app_holds_lock(paths, plat):
        runstate.clear(paths.app_json)
        out("YT Toolkit ไม่ได้เปิดอยู่")
        return 0
    url = f"{base_url(info.port)}/api/shutdown"
    headers = {"X-Toolkit-Token": info.token, "Origin": base_url(info.port)}
    try:
        response = post(url, json={"force": False}, headers=headers, timeout=5)
        if response.status_code == 409:
            pending = response.json().get("pendingJobs", 0)
            answer = ask(f"มีงานค้าง {pending} งาน ปิดเลยไหม (Y/N) ").strip().lower()
            if answer not in ("y", "yes"):
                out("ยกเลิกการปิดโปรแกรม")
                return 1
            post(url, json={"force": True}, headers=headers, timeout=5)
    except httpx.HTTPError:
        pass
    for _ in range(100):  # รอสูงสุด 10 วินาที (FR-LIFE-5)
        if not plat.pid_alive(info.pid):
            break
        sleep(0.1)
    else:
        # อ่าน app.json ซ้ำก่อน kill ถ้าไฟล์หายหรือเป็นของอินสแตนซ์อื่นแล้ว pid นี้ไม่ใช่แอพที่เราจะปิดอีกต่อไป
        if not _still_named_by_app_json(paths, info):
            out("YT Toolkit ไม่ได้เปิดอยู่")
            return 0
        if _app_holds_lock(paths, plat):  # lock ว่างแล้วแปลว่าแอพปิดตัวไปแล้ว ห้าม kill
            plat.kill(info.pid)
    if _still_named_by_app_json(paths, info):  # ห้ามลบ app.json ของอินสแตนซ์ใหม่
        runstate.clear(paths.app_json)
    out("ปิดโปรแกรมแล้ว")
    return 0


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
