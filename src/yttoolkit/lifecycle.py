"""เปิด ปิด และดูแลวงจรชีวิตของแอพ (FR-LIFE-*)"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
import webbrowser
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import uvicorn

from . import __version__, runstate
from .app import AppContext, create_app
from .config import CODE_ROOT, HOST, Paths, default_paths, env_flag
from .core import tools
from .core.db import Database, purge_stale_cache
from .core.extractor import Extractor, FakeExtractor, YtDlpExtractor
from .core.videos import VideoService
from .platform import LockFileError, Platform, current

# ตัวจริงอยู่ใน probe (stdlib ล้วน) ที่นี่ส่งต่อชื่อเดิมให้โค้ดและเทสที่เรียกผ่าน lifecycle
from .probe import base_url, find_running, is_alive, setup_file_log  # noqa: F401

log = logging.getLogger("yttoolkit")

DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


def default_output_dir(plat: Platform) -> Path:
    return plat.downloads_dir() / "YT-Toolkit"


def prepare_environment() -> None:
    scripts = str(tools.scripts_dir())
    parts = os.environ.get("PATH", "").split(os.pathsep)
    if not parts or parts[0] != scripts:
        os.environ["PATH"] = os.pathsep.join([scripts, *[p for p in parts if p != scripts]])


def git_commit(root: Path, plat: Platform) -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
            creationflags=plat.popen_flags,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() or None


def setup_file_logging(paths: Paths) -> None:
    setup_file_log(paths)  # เรียกซ้ำได้ (__main__ ตั้งไว้ก่อน import lifecycle แล้ว) ไม่เกิด handler ซ้ำ
    if sys.stdout is None or sys.stderr is None:  # แอพที่เปิดแบบไม่มีหน้าต่างดำจะไม่มี console
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
    if tools.find_ffmpeg(paths, plat) is not None or not plat.ffmpeg_auto_install:
        return
    try:
        tools.install_ffmpeg(paths, plat)
        log.info("ติดตั้ง ffmpeg อัตโนมัติสำเร็จ")
    except Exception:  # รันใน daemon thread ถ้าหลุดจะเหลือแค่ traceback ดิบ ไม่ลง log
        log.exception("ติดตั้ง ffmpeg อัตโนมัติไม่สำเร็จ")


def open_services(paths: Paths) -> tuple[Database, VideoService, Extractor]:
    """เปิดฐานข้อมูล (สร้างตารางถ้ายังไม่มี) ล้าง cache เก่า และเลือก extractor

    YT_TOOLKIT_FAKE=1 = ใช้ข้อมูลทดสอบใน tests/fixtures แทนยูทูปจริง (ใช้กับ E2E)
    ล้าง cache ไม่สำเร็จแค่บันทึก log แล้วเปิดโปรแกรมต่อ ส่วนฐานข้อมูลเปิดไม่ได้จะโยนต่อ
    """
    if env_flag("YT_TOOLKIT_FAKE", False):
        log.warning("โหมดข้อมูลปลอม (YT_TOOLKIT_FAKE): ใช้ข้อมูลทดสอบใน tests/fixtures ไม่ต่อยูทูปจริง")
        extractor: Extractor = FakeExtractor(CODE_ROOT / "tests" / "fixtures")
    else:
        extractor = YtDlpExtractor()
    paths.db.parent.mkdir(parents=True, exist_ok=True)
    db = Database(paths.db)
    try:
        db.migrate()
    except BaseException:
        db.close()
        raise
    try:
        removed = purge_stale_cache(db, paths.cache, datetime.now(UTC))
        if removed:
            log.info("ล้าง cache ของคลิปที่ไม่ได้เปิดเกิน 30 วันแล้ว %s คลิป", removed)
    except Exception:  # ห้ามทำให้เปิดโปรแกรมไม่ได้ รอบหน้าค่อยลองใหม่
        log.exception("ล้าง cache เก่าไม่สำเร็จ (ข้ามไปก่อน)")
    return db, VideoService(db, extractor), extractor


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
    try:
        db, videos, extractor = open_services(paths)
    except Exception:
        log.exception("เปิดฐานข้อมูลไม่สำเร็จ (%s)", paths.db)
        return 1
    try:
        return _run_server(
            paths=paths,
            plat=plat,
            port=port,
            with_tray=with_tray,
            open_browser=open_browser,
            auto_ffmpeg=auto_ffmpeg,
            extra_origins=extra_origins,
            db=db,
            videos=videos,
            extractor=extractor,
        )
    finally:
        db.close()


def _run_server(
    *,
    paths: Paths,
    plat: Platform,
    port: int,
    with_tray: bool,
    open_browser: bool,
    auto_ffmpeg: bool,
    extra_origins: Iterable[str],
    db: Database,
    videos: VideoService,
    extractor: Extractor,
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
        commit=git_commit(paths.code_root, plat),
        output_dir=default_output_dir(plat),
        request_shutdown=request_shutdown,
        extra_origins=tuple(extra_origins),
        db=db,
        videos=videos,
        extractor=extractor,
        cache_root=paths.cache,
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
    try:
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
    except LockFileError as error:  # เปิดไฟล์ lock ไม่ได้ ไม่ใช่มีคนถือ lock รอไปก็ไม่หาย
        log.error("เปิดโปรแกรมไม่สำเร็จ: %s", error)
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
    try:
        lock = plat.try_lock(paths.run / "app.lock")
    except LockFileError as error:
        log.error("เปิดเซิร์ฟเวอร์ไม่สำเร็จ: %s", error)
        return 1
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
    """True ถ้ามีแอพถือ run/app.lock อยู่ ถ้าจับได้เองจะปล่อยคืนทันที ถ้าเปิดไฟล์ lock ไม่ได้จะโยน LockFileError"""
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
    try:
        return _stop(paths, plat, post=post, ask=ask, sleep=sleep, out=out)
    except LockFileError as error:
        # เปิดไฟล์ lock ไม่ได้ จึงบอกไม่ได้ว่าแอพยังถือ lock อยู่หรือไม่ ห้าม kill และห้ามลบ app.json
        log.error("ตรวจสถานะโปรแกรมไม่ได้: %s", error)
        out(f"ตรวจสถานะโปรแกรมไม่ได้ ดูรายละเอียดได้ที่ {(paths.logs / 'app.log').absolute()}")
        return 1


def _stop(
    paths: Paths,
    plat: Platform,
    *,
    post,
    ask: Callable[[str], str],
    sleep: Callable[[float], None],
    out: Callable[[str], None],
) -> int:
    info = runstate.read(paths.app_json)
    # pid ใน app.json อาจค้างจากตอนเครื่องดับ แล้ว Windows เอาเลขนี้ไปให้โปรแกรมอื่น
    # แอพที่รันอยู่จริงถือ run/app.lock ไว้ตลอด ถ้าจับ lock ได้แปลว่าไม่มีแอพเปิดอยู่
    if info is None or not plat.pid_alive(info.pid) or not _app_holds_lock(paths, plat):
        if info is not None and _still_named_by_app_json(paths, info):  # ห้ามลบ app.json ของอินสแตนซ์ใหม่
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
        # ตอนเริ่ม stop แอพเปิดอยู่จริง แอพเดิมปิดตัวไปแล้ว จึงบอกว่าปิดแล้ว ไม่ใช่ "ไม่ได้เปิดอยู่"
        if not _still_named_by_app_json(paths, info):
            out("ปิดโปรแกรมแล้ว")
            return 0
        if _app_holds_lock(paths, plat):  # lock ว่างแล้วแปลว่าแอพปิดตัวไปแล้ว ห้าม kill
            plat.kill(info.pid)
    if _still_named_by_app_json(paths, info):  # ห้ามลบ app.json ของอินสแตนซ์ใหม่
        runstate.clear(paths.app_json)
    out("ปิดโปรแกรมแล้ว")
    return 0

