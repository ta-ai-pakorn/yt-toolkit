"""เปิด ปิด และดูแลวงจรชีวิตของแอพ (FR-LIFE-*)"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
import uvicorn

from . import __version__, runstate
from .api.errors import redact_home
from .app import AppContext, create_app
from .config import CODE_ROOT, HOST, Paths, default_paths, env_flag
from .core import files, thai_fallback, tools
from .core.advanced import ADS_SUFFIX
from .core.comments import PinnedCommentService
from .core.db import Database, purge_stale_cache
from .core.events import CLOSED, Event, EventBus
from .core.extractor import Extractor, FakeExtractor, YtDlpExtractor, visitor_session
from .core.handlers import (
    CONTACT_SHEET_SUFFIX,
    FRAMES_ZIP_SUFFIX,
    NO_AUDIO_SUFFIX,
    HandlerDeps,
    build_handlers,
    job_group,
)
from .core.jobs import JobStore
from .core.media import FakeMediaTools, FfmpegTools, MediaTools
from .core.queue import QueueRunner
from .core.settings import SettingsStore
from .core.subtitles import SubtitleService
from .core.videos import VideoService
from .platform import LockFileError, Platform, current

# ตัวจริงอยู่ใน probe (stdlib ล้วน) ที่นี่ส่งต่อชื่อเดิมให้โค้ดและเทสที่เรียกผ่าน lifecycle
from .probe import base_url, find_running, is_alive, setup_file_log  # noqa: F401

log = logging.getLogger("yttoolkit")

DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
PURGE_INTERVAL_S = 24 * 60 * 60  # ล้าง cache เก่าซ้ำทุก 24 ชม. สำหรับเครื่องที่เปิดโปรแกรมทิ้งไว้หลายวัน
# ชื่อเก่าของตัวแปรโฟลเดอร์ข้อมูล PyThaiNLP ถ้าตั้งไว้คู่กับ PYTHAINLP_DATA PyThaiNLP จะโยน ValueError
LEGACY_PYTHAINLP_ENV = "PYTHAINLP_DATA_DIR"
# โหมดข้อมูลปลอม (E2E) ไม่ต้องเว้นช่วงเริ่มงานยูทูป 2-5 วินาทีเหมือนของจริง
FAKE_DELAY_RANGE = (0.05, 0.2)
QUEUE_SHUTDOWN_TIMEOUT_S = 5.0  # รองานที่กำลังทำหยุดตอนปิดโปรแกรมไม่เกินเท่านี้
GRACEFUL_SHUTDOWN_S = 3  # uvicorn รอ request ที่ค้าง (เช่นสตรีมข่าว) ไม่เกินเท่านี้
TRAY_REFRESH_INTERVAL_S = 1.0  # อัปเดตตัวเลขงานในเมนู tray ไม่เกิน 1 ครั้งต่อวินาที
# ตอนเปิดโปรแกรม ล้างไฟล์ค้างในโฟลเดอร์ของงานที่หยุดกลางคันล่าสุดไม่เกินเท่านี้งาน (รวมงานที่เพิ่งกู้คืนเสมอ)
SWEEP_RECENT_INTERRUPTED = 20
# ชื่อไฟล์ที่ core/handlers.py เขียนจริง (ล้างไฟล์ค้างเฉพาะชื่อแบบนี้ ไม่แตะไฟล์อื่นของผู้ใช้)
_SWEEP_SUFFIXES = (NO_AUDIO_SUFFIX, CONTACT_SHEET_SUFFIX, FRAMES_ZIP_SUFFIX)
_SWEEP_MEDIA_EXTS = ("mp4", "m4a", "mp3", "wav", "jpg", "zip")  # video, audio, contact_sheet, frames_zip
# subtitle (api/jobs.py SubtitleParams.format) และโน้ต "<ชื่อ>.note.md" (ส่วน ".note" อยู่ตำแหน่งรหัสภาษา)
_SWEEP_SUB_EXTS = ("srt", "txt", "md")
# M5 รอบ A: ส่วนต่อท้ายช่วงเวลา " (01.30-05.00)" / " (1.02.30-1.05.00)" (core/advanced.range_suffix)
_RANGE_SUFFIX = r" \((?:\d{2}\.\d{2}-\d{2}\.\d{2}|\d{1,3}\.\d{2}\.\d{2}-\d{1,3}\.\d{2}\.\d{2})\)"
_UNIQUE = r"(?: \((?:[2-9]|[1-9][0-9])\))?"  # " (2)" ... " (99)" จาก files._candidates
# ไฟล์ในโฟลเดอร์ย่อย "แยกตาม chapter (<ext>)": "<NN> - <ชื่อ>.<ext>" หรือ "<NN>.<ext>" (files.plan_chapter_output)
_CHAPTER_EXTS = ("mp4", "m4a", "mp3", "wav")
_CHAPTER_FILE = re.compile(rf"\d{{2,3}}(?: - .+)?{_UNIQUE}\.(?:{'|'.join(_CHAPTER_EXTS)})(?:\.part)?")
# stop รอแอพปิดเองไม่เกินเท่านี้ก่อน kill ต้องนานกว่า หยุดคิว + uvicorn รอ request ค้าง (มีเทสคุม)
STOP_WAIT_S = 10.0
STOP_POLL_S = 0.1


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


class HomePathFilter(logging.Filter):
    """แทนโฟลเดอร์ผู้ใช้ด้วย ~ ในข้อความ log และ traceback ก่อนเขียนลงไฟล์

    log.exception ของคิวงานและ lifecycle อาจมี path เต็ม ซึ่งมีชื่อผู้ใช้ Windows ติดไปกับไฟล์ log ที่ส่งต่อ
    """

    _formatter = logging.Formatter()

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True  # ข้อความจัดรูปไม่ได้ ปล่อยให้ logging รายงานตามปกติ
        record.msg = redact_home(message)
        record.args = None
        if record.exc_info and not record.exc_text:
            record.exc_text = self._formatter.formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact_home(record.exc_text)
        if record.stack_info:
            record.stack_info = redact_home(record.stack_info)
        return True


class ConnectionResetNoiseFilter(logging.Filter):
    """ทิ้งเฉพาะรายงาน ConnectionResetError ของ asyncio ตอนปิดการเชื่อมต่อ (_call_connection_lost)

    บน Windows ทุกครั้งที่ปิดแท็บที่ต่อสตรีมข่าว (SSE) อยู่ proactor ของ asyncio จะรายงาน
    "[WinError 10054]" เป็น error พร้อม traceback ซึ่งไม่ใช่ปัญหา แต่ทำให้ app.log รกจนหาปัญหาจริงยาก
    รายงานอื่นของ asyncio (และ ConnectionResetError จากที่อื่น) ยังลง log ตามปกติ
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != "asyncio" or not record.exc_info:
            return True
        if not isinstance(record.exc_info[1], ConnectionResetError):
            return True
        try:
            message = record.getMessage()
        except Exception:
            return True
        return "_call_connection_lost" not in message


def _app_log_handlers(paths: Paths) -> list[logging.Handler]:
    target = os.path.abspath(paths.logs / "app.log")
    return [
        h for h in logging.getLogger().handlers if isinstance(h, logging.FileHandler) and h.baseFilename == target
    ]


def install_log_filters(paths: Paths) -> None:
    """ใส่ HomePathFilter และ ConnectionResetNoiseFilter ให้ handler ของ app.log ที่ตั้งไว้แล้ว (เรียกซ้ำได้ ไม่ใส่ซ้ำ)"""
    for handler in _app_log_handlers(paths):
        for kind in (ConnectionResetNoiseFilter, HomePathFilter):
            if not any(isinstance(f, kind) for f in handler.filters):
                handler.addFilter(kind())


def setup_file_logging(paths: Paths) -> None:
    setup_file_log(paths)  # เรียกซ้ำได้ (__main__ ตั้งไว้ก่อน import lifecycle แล้ว) ไม่เกิด handler ซ้ำ
    install_log_filters(paths)
    if sys.stdout is None or sys.stderr is None:  # แอพที่เปิดแบบไม่มีหน้าต่างดำจะไม่มี console
        stream = open(paths.logs / "console.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
        sys.stdout = sys.stdout or stream
        sys.stderr = sys.stderr or stream


class Server:
    """uvicorn ที่รันใน thread แยก เพื่อให้ main thread ว่างไว้ให้ tray"""

    def __init__(self, ctx: AppContext) -> None:
        # timeout_graceful_shutdown: request ที่ค้าง (เช่นสตรีมข่าว SSE) ไม่ขวางการปิดโปรแกรม (ปิด bus ก่อนอยู่แล้ว นี่คือกันเหนียว)
        self.config = uvicorn.Config(
            create_app(ctx),
            host=HOST,
            port=ctx.port,
            log_config=None,
            access_log=False,
            timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_S,
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


def warm_up_in_background(extractor: Extractor) -> threading.Thread | None:
    """เตรียม extractor ล่วงหน้าใน daemon thread (ตัวจริง = import yt-dlp) ตัวที่ไม่มี warm_up (โหมดข้อมูลปลอม) ข้าม

    พลาดแค่บันทึก log ห้ามทำให้เปิดโปรแกรมไม่ได้ ลิงก์แรกจะ import เองตามปกติ
    """
    warm_up = getattr(extractor, "warm_up", None)
    if not callable(warm_up):
        return None

    def run() -> None:
        try:
            warm_up()
        except Exception:
            log.warning("เตรียม yt-dlp ล่วงหน้าไม่สำเร็จ (ลิงก์แรกจะช้ากว่าปกติเล็กน้อย)", exc_info=True)

    thread = threading.Thread(target=run, name="ytdlp-warmup", daemon=True)
    thread.start()
    return thread


def configure_thai(paths: Paths) -> None:
    """ให้ PyThaiNLP เก็บข้อมูลใน <data_root>/pythainlp แทน ~/pythainlp-data (ต้องเรียกก่อนแยกคำไทยครั้งแรก)

    ผู้ใช้ตั้ง PYTHAINLP_DATA ไว้เองก็ใช้ของผู้ใช้ ตั้งชื่อเก่า PYTHAINLP_DATA_DIR ไว้ก็ไม่ตั้งซ้ำ (ตั้งคู่กัน = ValueError)
    """
    if os.environ.get(LEGACY_PYTHAINLP_ENV):
        return
    thai_fallback.configure(paths.data_root / "pythainlp")


@dataclass
class Services:
    """บริการทั้งหมดที่ run_app ต่อเข้า AppContext (open_services สร้างให้ ตัวรันคิวยังไม่เริ่มทำงาน)"""

    db: Database
    videos: VideoService
    extractor: Extractor
    subtitles: SubtitleService
    settings: SettingsStore
    events: EventBus
    media: MediaTools
    queue: QueueRunner
    pinned: PinnedCommentService | None = None  # ส่งต่อเป็น ctx.pinned (router ข้อมูลคลิปใช้ตัวนี้ ไม่สร้างใหม่)


def open_services(paths: Paths, plat: Platform, fake: bool = False) -> Services:
    """เปิดฐานข้อมูล (สร้างตารางถ้ายังไม่มี) ล้าง cache เก่า เลือก extractor และสร้างบริการทั้งหมด

    โฟลเดอร์ปลายทางเริ่มต้น: <Downloads>/YT-Toolkit (โหมดข้อมูลปลอม = <data_root>/output ไม่ไปเขียนใน Downloads ของเครื่อง)
    fake=True = ใช้ข้อมูลทดสอบใน tests/fixtures แทนยูทูปจริง และจัดไฟล์สื่อด้วยการคัดลอกแทน ffmpeg
    (serve ส่งมาเมื่อ YT_TOOLKIT_FAKE=1 ใช้กับ E2E ซึ่งเครื่องอาจไม่มี ffmpeg)
    ล้าง cache ไม่สำเร็จแค่บันทึก log แล้วเปิดโปรแกรมต่อ ส่วนฐานข้อมูลเปิดไม่ได้จะโยนต่อ
    ตัวรันคิวยังไม่เริ่ม: run_app กู้งานค้างก่อนเปิดเซิร์ฟเวอร์ แล้วค่อยเริ่มคิวเมื่อเซิร์ฟเวอร์พร้อม
    """
    session = None
    if fake:
        log.warning("โหมดข้อมูลปลอม (YT_TOOLKIT_FAKE): ใช้ข้อมูลทดสอบใน tests/fixtures ไม่ต่อยูทูปจริง")
        extractor: Extractor = FakeExtractor(CODE_ROOT / "tests" / "fixtures")
    else:
        # เซสชันผู้ชมแบบไม่ระบุตัวตน (<data>/visitor-session.txt) ที่ probe และซับใช้ร่วมกัน ซับแปลต้องใช้
        session = visitor_session(paths.data)
        extractor = YtDlpExtractor(session=session)
    paths.db.parent.mkdir(parents=True, exist_ok=True)
    db = Database(paths.db)
    try:
        db.migrate()
        purge_cache_once(db, paths.cache)
        configure_thai(paths)
        videos = VideoService(db, extractor)
        subtitles = SubtitleService(videos, extractor.fetch_subtitle, paths.cache, session=session)
        default_output = paths.data_root / "output" if fake else default_output_dir(plat)
        settings = SettingsStore(db, default_output)
        media: MediaTools
        if fake:
            media = FakeMediaTools(CODE_ROOT / "tests" / "fixtures" / "media")
        else:
            media = FfmpegTools(lambda: tools.find_ffmpeg(paths, plat), popen_flags=plat.popen_flags)
        events = EventBus()
        # ตัวเดียวกับที่ API ข้อมูลคลิปใช้ (ctx.pinned): งานโน้ตในคิวกับ GET pinned-comment ใช้ cache และล็อกร่วมกัน
        # เรียกผ่าน lambda: extractor ทดสอบบางตัวไม่มี pinned_comment และไม่ต้องมีถ้าไม่ได้เรียก
        pinned = PinnedCommentService(videos, lambda vid: extractor.pinned_comment(vid), paths.cache)
        deps = HandlerDeps(
            videos=videos,
            downloader=extractor,  # type: ignore[arg-type]  # ทั้งตัวจริงและตัวปลอมมี download (C8)
            media=media,
            subtitles=subtitles,
            cache_root=paths.cache,
            pinned=pinned.get,
            sponsors=extractor,  # type: ignore[arg-type]  # ทั้งตัวจริงและตัวปลอมมี sponsor_segments (C4)
        )
        delays = {"delay_range": FAKE_DELAY_RANGE} if fake else {}
        queue = QueueRunner(
            JobStore(db),
            events,
            build_handlers(deps),
            settings=settings,
            work_root=paths.work,
            redact=redact_home,
            **delays,
        )
        # ตัวทำงานอ่าน deps ตอนรันงาน: E_BOT_CHECK ที่งานโน้ตกลืนไว้ (คอมเมนต์ปักหมุด) ยังพักคิวได้
        deps.on_bot_check = queue.brake
    except BaseException:
        db.close()
        raise
    return Services(
        db=db,
        videos=videos,
        extractor=extractor,
        subtitles=subtitles,
        settings=settings,
        events=events,
        media=media,
        queue=queue,
        pinned=pinned,
    )


def recover_jobs(services: Services) -> None:
    """ตอนเปิดโปรแกรม ก่อนเปิดเซิร์ฟเวอร์ (AC-Q-05): งานที่ค้าง running จากรอบก่อนเป็น interrupted ล้าง work/
    แล้วล้างไฟล์ค้างในโฟลเดอร์ผลลัพธ์ของงานที่หยุดกลางคัน พลาดแค่บันทึก log (ห้ามทำให้เปิดโปรแกรมไม่ได้)"""
    store = services.queue.store
    try:
        stranded = [job.id for job in store.running()]
        services.queue.recover()
    except Exception:
        log.exception("กู้งานที่ค้างจากรอบก่อนไม่สำเร็จ")
        return
    try:
        removed = sweep_interrupted_outputs(store, services.settings.output_dir(), stranded)
        if removed:
            log.info("ล้างไฟล์ที่ค้างจากงานที่หยุดกลางคันแล้ว %s ไฟล์", removed)
    except Exception:
        log.exception("ล้างไฟล์ที่ค้างจากงานที่หยุดกลางคันไม่สำเร็จ (ข้ามไปก่อน)")


def _clip_folders(root: Path, video_id: str, title: str, group: str | None = None) -> list[tuple[Path, str]]:
    """โฟลเดอร์ของคลิป (กฎตั้งชื่อเดียวกับ files.plan_output รวมโฟลเดอร์กลุ่ม) คู่กับคำขึ้นต้นของชื่อไฟล์ในโฟลเดอร์นั้น

    ลองทั้งชื่องานและชื่อว่าง (คลิปไม่มีชื่อ handler ตั้งชื่อจาก videoId ส่วนชื่องานอาจเป็นชื่อที่หน้าเว็บส่งมา)"""
    found: list[tuple[Path, str]] = []
    for candidate in dict.fromkeys((title, "")):
        try:
            folder = files.plan_output(root, candidate, video_id, "", "x", group).parent
        except Exception:
            continue
        tag = f" [{video_id}]"
        prefix = folder.name[: -len(tag)] if folder.name.endswith(tag) else folder.name
        if prefix and (folder, prefix) not in found:
            found.append((folder, prefix))
    return found


def sweep_interrupted_outputs(store: JobStore, output_root: Path, job_ids: Iterable[str] = ()) -> int:
    """ลบไฟล์ค้างในโฟลเดอร์ผลลัพธ์ของงานที่หยุดกลางคัน คืนจำนวนไฟล์ที่ลบ เรียกตอนไม่มีงานไหนรันอยู่เท่านั้น

    ไฟล์ค้างมาจาก files.move_into_place ที่ถูกตัดกลางทาง (โปรแกรมดับ): ไฟล์ว่าง 0 ไบต์ที่จองชื่อไว้
    และ <ชื่อ>.part ตอนคัดลอกข้ามไดรฟ์ ถ้าไม่ลบ งานถัดไปของคลิปเดียวกันจะได้ชื่อ " (2)" โดยไม่จำเป็น
    งานที่ดู = job_ids (งานที่เพิ่งกู้คืน) + งานที่หยุดกลางคันล่าสุด (เผื่อปิดโปรแกรมตอนกำลังย้ายไฟล์ใหญ่ข้ามไดรฟ์)
    ลบเฉพาะไฟล์ที่ชื่อเป็นแบบที่โปรแกรมสร้างได้ (toolkit_name_pattern) และไม่ใช่ไฟล์ผลลัพธ์ของงานที่เสร็จแล้ว
    การดูงานที่หยุดกลางคันล่าสุดซ้ำทุกครั้งที่เปิดจึงไม่แตะไฟล์ของผู้ใช้
    """
    jobs = {job.id: job for job in store.list_status("interrupted", SWEEP_RECENT_INTERRUPTED)}
    for job_id in job_ids:
        if job_id not in jobs and (job := store.get(job_id)) is not None and job.status == "interrupted":
            jobs[job_id] = job
    if not jobs:
        return 0
    root = output_root.resolve()
    video_ids = {job.video_id for job in jobs.values()}
    keep = {
        os.path.normcase(str(Path(output.root) / output.rel))
        for done in store.list_status("done", -1)
        if done.video_id in video_ids
        for output in done.outputs
    }
    seen: set[Path] = set()
    removed = 0
    for job in jobs.values():
        for folder, prefix in _clip_folders(root, job.video_id, job.title, job_group(job.params)):
            if folder not in seen:
                seen.add(folder)
                removed += _sweep_folder(folder, toolkit_name_pattern(prefix), keep)
                for ext in _CHAPTER_EXTS:
                    chapters = folder / files.chapter_dir_name(ext)
                    removed += _sweep_folder(chapters, _CHAPTER_FILE, keep)
                    _remove_if_empty(chapters)
    return removed


def _prefixes(name: str) -> str:
    """regex ของทุกคำขึ้นต้นที่ไม่ว่างของ name (files.plan_output ตัดชื่อไฟล์ให้สั้นลงเมื่อส่วนท้ายยาวเกิน 30 ตัว)"""
    pattern = ""
    for ch in reversed(name[1:]):
        pattern = f"(?:{re.escape(ch)}{pattern})?"
    return re.escape(name[:1]) + pattern


def toolkit_name_pattern(prefix: str) -> re.Pattern[str]:
    """ชื่อไฟล์ที่ตัวทำงานในคิวสร้างได้จริงในโฟลเดอร์ของคลิป (ใช้ fullmatch) ต่อท้าย .part ได้

    สื่อ/ภาพ/zip: <ชื่อ>[ส่วนต่อท้ายของชนิดงาน][ (N)].<นามสกุล>  เช่น "ชื่อ (ไม่มีเสียง) (2).mp4"
    M5 รอบ A: <ชื่อ>[ (ไม่มีเสียง)][ (ช่วงเวลา)][ (ตัดโฆษณา)][ (N)].<นามสกุล> (ต้องมีช่วงเวลาหรือตัดโฆษณา ชื่ออาจถูกตัดสั้น)
    ซับ: <ชื่อ>[ (ช่วงเวลา)][ (N)].<ภาษา>.<รูปแบบ>  (files วางเลขกันซ้ำไว้หน้ารหัสภาษา)
    ชื่ออื่น (เช่นไฟล์ของผู้ใช้ "<ชื่อ> notes.docx") ไม่ตรง จึงไม่ถูกลบ"""
    name = re.escape(prefix)
    shrunk = _prefixes(prefix)
    suffixes = "|".join(re.escape(s) for s in _SWEEP_SUFFIXES)
    exts = "|".join(_SWEEP_MEDIA_EXTS)
    subs = "|".join(_SWEEP_SUB_EXTS)
    no_audio, ads = re.escape(NO_AUDIO_SUFFIX), re.escape(ADS_SUFFIX)
    media = rf"{name}(?:{suffixes})?{_UNIQUE}\.(?:{exts})"
    cut = rf"{shrunk}(?:{no_audio})?(?:{_RANGE_SUFFIX}(?:{ads})?|{ads}){_UNIQUE}\.(?:{exts})"
    subtitle = rf"{name}{_UNIQUE}\.[A-Za-z0-9-]+\.(?:{subs})"
    subtitle_range = rf"{shrunk}{_RANGE_SUFFIX}{_UNIQUE}\.[A-Za-z0-9-]+\.(?:{subs})"
    return re.compile(rf"(?:{media}|{cut}|{subtitle}|{subtitle_range})(?:\.part)?")


def _remove_if_empty(folder: Path) -> None:
    """โฟลเดอร์ย่อยของ chapter ที่ว่างหลังล้างไฟล์ค้าง = ลบทิ้ง (มีไฟล์อื่นอยู่ = rmdir ไม่สำเร็จ ปล่อยไว้)"""
    try:
        folder.rmdir()
    except OSError:
        return


def _sweep_folder(folder: Path, ours: re.Pattern[str], keep: set[str]) -> int:
    try:
        children = list(folder.iterdir())
    except FileNotFoundError:
        return 0
    except OSError as exc:
        log.warning("อ่านโฟลเดอร์ผลลัพธ์ไม่ได้ตอนล้างไฟล์ค้าง: %s", type(exc).__name__)
        return 0
    removed = 0
    for child in children:
        if not ours.fullmatch(child.name) or os.path.normcase(str(child)) in keep:
            continue
        try:
            if child.is_symlink() or not child.is_file():
                continue
            if child.name.endswith(".part") or child.stat().st_size == 0:
                child.unlink()
                removed += 1
        except OSError as exc:
            log.warning("ลบไฟล์ค้างไม่ได้: %s", type(exc).__name__)
    return removed


def shutdown_services(services: Services, timeout: float = QUEUE_SHUTDOWN_TIMEOUT_S) -> None:
    """ขั้นแรกของการปิดโปรแกรม ก่อนหยุดเซิร์ฟเวอร์: หยุดคิว (งานที่ทำอยู่จบเป็น interrupted) บอกหน้าเว็บว่าแอพปิด
    แล้วปิด bus สตรีมข่าวที่เปิดค้างจึงจบเอง uvicorn ไม่ต้องรอ"""
    try:
        services.queue.shutdown(timeout=timeout)
    except Exception:
        log.exception("หยุดคิวงานไม่สำเร็จ")
    services.events.publish("app.shutdown", {})
    services.events.close()


def running_count(services: Services) -> Callable[[], int]:
    """จำนวนงานที่กำลังทำ สำหรับเมนู tray (อ่านฐานข้อมูลไม่ได้ = 0 เมนูต้องเปิดได้เสมอ)"""

    def count() -> int:
        try:
            return len(services.queue.store.running())
        except Exception:
            return 0

    return count


class TrayRefresher:
    """ฟังข่าวงานแล้วสั่ง icon.update_menu() (ตัวเลข "กำลังทำ n งาน") ไม่เกิน 1 ครั้งต่อ interval

    นับเฉพาะ job.created และ job.updated ที่มีสถานะใหม่ (ข่าวความคืบหน้าไม่ทำให้จำนวนงานเปลี่ยน)
    กล่องข่าวของตัวเองถูกปิด (อ่านไม่ทันจนล้น) = สมัครใหม่แล้วอัปเดตเมนูหนึ่งครั้ง (อาจพลาดข่าวไป)
    จบเมื่อ bus ปิดจริง (ตอนปิดโปรแกรม) คือสมัครใหม่แล้วยังได้ CLOSED"""

    def __init__(
        self,
        bus: EventBus,
        icon,
        *,
        interval: float = TRAY_REFRESH_INTERVAL_S,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._bus = bus
        self._icon = icon
        self._interval = interval
        self._monotonic = monotonic
        self._sub = bus.subscribe()
        self._last = -float("inf")
        self._dirty = False

    def next_wait(self) -> float:
        """เวลาที่รอข่าวรอบถัดไป: มีอัปเดตค้างอยู่ = รอแค่จนครบช่วง"""
        if self._dirty:
            return max(self._last + self._interval - self._monotonic(), 0.0)
        return self._interval

    def handle(self, item: Event | None) -> None:
        """รับข่าวหนึ่งชิ้น (None = รอครบเวลาแล้วไม่มีข่าว) แล้วอัปเดตเมนูถ้าถึงเวลา"""
        if isinstance(item, Event) and (
            item.name == "job.created" or (item.name == "job.updated" and "status" in item.data)
        ):
            self._dirty = True
        if self._dirty and self._monotonic() - self._last >= self._interval:
            self._last = self._monotonic()
            self._dirty = False
            try:
                self._icon.update_menu()
            except Exception:
                log.warning("อัปเดตเมนู tray ไม่สำเร็จ", exc_info=True)

    def poll(self, timeout: float) -> bool:
        """รอข่าวหนึ่งรอบแล้วจัดการ คืน False เมื่อ bus ปิดแล้ว (เลิกฟัง)"""
        item = self._sub.get(timeout)
        if item is CLOSED:
            self._sub = self._bus.subscribe()
            item = self._sub.get(0)
            if item is CLOSED:
                return False
            self._dirty = True  # กล่องเดิมล้น อาจพลาดข่าวเปลี่ยนสถานะไป
        self.handle(item)  # type: ignore[arg-type]
        return True

    def run(self) -> None:
        while self.poll(self.next_wait()):
            pass


def start_tray_refresher(bus: EventBus, icon, **kwargs) -> threading.Thread:
    """เริ่ม TrayRefresher ใน daemon thread (จบเองเมื่อ bus ปิด)"""
    refresher = TrayRefresher(bus, icon, **kwargs)
    thread = threading.Thread(target=refresher.run, name="tray-refresh", daemon=True)
    thread.start()
    return thread


def _fake_open_folder(path: Path) -> None:
    log.info("โหมดข้อมูลปลอม: ไม่เปิดโฟลเดอร์")


def purge_cache_once(db: Database, cache_root: Path) -> None:
    """ล้าง cache ของคลิปที่ไม่ได้เปิดเกิน 30 วัน พลาดแค่บันทึก log (ห้ามทำให้เปิดโปรแกรมไม่ได้ รอบหน้าค่อยลองใหม่)"""
    try:
        removed = purge_stale_cache(db, cache_root, datetime.now(UTC))
        if removed:
            log.info("ล้าง cache ของคลิปที่ไม่ได้เปิดเกิน 30 วันแล้ว %s คลิป", removed)
    except Exception:
        log.exception("ล้าง cache เก่าไม่สำเร็จ (ข้ามไปก่อน)")


def start_periodic_purge(
    db: Database, cache_root: Path, stop: threading.Event, interval: float = PURGE_INTERVAL_S
) -> threading.Thread:
    """ล้าง cache เก่าทุก `interval` วินาทีใน daemon thread จนกว่าจะ set `stop` (รอบแรกหลังเปิดโปรแกรมไปแล้ว 1 รอบเวลา
    เพราะ open_services ล้างไปแล้วตอนเปิด)"""

    def loop() -> None:
        while not stop.wait(interval):
            purge_cache_once(db, cache_root)

    thread = threading.Thread(target=loop, name="cache-purge", daemon=True)
    thread.start()
    return thread


def run_app(
    *,
    paths: Paths,
    plat: Platform,
    port: int,
    with_tray: bool,
    open_browser: bool,
    auto_ffmpeg: bool,
    extra_origins: Iterable[str] = (),
    fake: bool = False,
) -> int:
    try:
        services = open_services(paths, plat, fake=fake)
    except Exception:
        log.exception("เปิดฐานข้อมูลไม่สำเร็จ (%s)", paths.db)
        return 1
    try:
        recover_jobs(services)  # ก่อนเปิดเซิร์ฟเวอร์: หน้าเว็บต้องไม่เห็นงานที่ค้าง running จากรอบก่อน (AC-Q-05)
        return _run_server(
            paths=paths,
            plat=plat,
            port=port,
            with_tray=with_tray,
            open_browser=open_browser,
            auto_ffmpeg=auto_ffmpeg,
            extra_origins=extra_origins,
            services=services,
            fake=fake,
        )
    finally:
        services.events.close()  # เรียกซ้ำได้ (ทางที่เซิร์ฟเวอร์ไม่ขึ้นยังไม่ได้ปิด)
        close_extractor(services.extractor)
        services.db.close()


def close_extractor(extractor: Extractor) -> None:
    """ปิดการเชื่อมต่อที่ extractor ถือไว้ (ตัวจริง = httpx client) ตัวที่ไม่มี close ข้าม พลาดแค่บันทึก log"""
    close = getattr(extractor, "close", None)
    if not callable(close):
        return
    try:
        close()
    except Exception:
        log.warning("ปิดการเชื่อมต่อของ extractor ไม่สำเร็จ", exc_info=True)


def _run_server(
    *,
    paths: Paths,
    plat: Platform,
    port: int,
    with_tray: bool,
    open_browser: bool,
    auto_ffmpeg: bool,
    extra_origins: Iterable[str],
    services: Services,
    fake: bool = False,
) -> int:
    queue = services.queue
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
        output_dir=services.settings.output_dir(),
        request_shutdown=request_shutdown,
        pending_jobs=queue.pending_count,
        extra_origins=tuple(extra_origins),
        db=services.db,
        videos=services.videos,
        extractor=services.extractor,
        cache_root=paths.cache,
        fake=fake,
        subtitles=services.subtitles,
        settings=services.settings,
        queue=queue,
        events=services.events,
        media=services.media,
        pinned=services.pinned,
        # router อ่านค่านี้ตอนเรียกจริง และเรียกจากเธรดของ FastAPI (brake ถือ lock ของคิวเอง)
        on_bot_check=queue.brake,
    )
    if fake:
        # โหมดข้อมูลปลอมไม่เปิดหน้าต่างจริง (E2E รันบนเครื่องพนักงานได้โดยไม่มีหน้าต่างโผล่)
        ctx.open_folder = _fake_open_folder
        ctx.reveal = _fake_open_folder
    server = Server(ctx)
    server.start()
    if not server.wait_until_ready():
        log.error("เปิดเซิร์ฟเวอร์ไม่สำเร็จที่ port %s", port)
        server.stop()
        server.join(timeout=5)
        runstate.clear(paths.app_json)  # lock ปล่อยโดยผู้เรียก (start/serve) ใน finally
        return 1
    url = base_url(port)

    def open_output() -> None:
        folder = services.settings.output_dir()
        folder.mkdir(parents=True, exist_ok=True)
        (ctx.open_folder or plat.open_folder)(folder)

    def quit_from_tray() -> None:
        if ctx.pending_jobs() > 0:
            webbrowser.open(f"{url}/?confirmShutdown=1")  # หน้าเว็บถามยืนยัน (FR-LIFE-4, ทำใน M4)
        else:
            request_shutdown()

    purge_stop = threading.Event()
    purge_thread: threading.Thread | None = None
    # ทุกอย่างหลังเซิร์ฟเวอร์พร้อมอยู่ใน try: พังกลางทางเมื่อไรก็ยังหยุดคิว ปิด bus และหยุดเซิร์ฟเวอร์ใน finally
    try:
        runstate.write(
            paths.app_json, runstate.RunInfo(port=port, pid=os.getpid(), token=token, started_at=runstate.now_iso())
        )
        queue.start()  # หลังเซิร์ฟเวอร์พร้อม: ข่าวของงานแรกไปถึงหน้าเว็บที่เปิดอยู่ได้
        warm_up_in_background(services.extractor)
        purge_thread = start_periodic_purge(services.db, paths.cache, purge_stop)
        if auto_ffmpeg:
            threading.Thread(target=ensure_ffmpeg, args=(paths, plat), name="ffmpeg-setup", daemon=True).start()
        if open_browser:
            webbrowser.open(url)
        if with_tray:
            from .tray import build_tray

            icon = build_tray(lambda: webbrowser.open(url), open_output, quit_from_tray, running_count(services))
            tray_holder.append(icon)
            start_tray_refresher(services.events, icon)  # จบเองเมื่อ bus ปิดใน finally
            icon.run()  # บล็อก main thread จนกว่าจะเรียก icon.stop()
        else:
            while not stop_event.wait(0.5):
                pass
    except KeyboardInterrupt:
        pass
    finally:
        # ลำดับ: หยุดคิว -> app.shutdown -> ปิด bus (สตรีมข่าวจบ) -> หยุดเซิร์ฟเวอร์
        shutdown_services(services)
        server.stop()
        purge_stop.set()  # หยุด timer ก่อนผู้เรียกปิดฐานข้อมูล
        server.join(timeout=10)
        if purge_thread is not None:
            purge_thread.join(timeout=5)
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
    if env_flag("YT_TOOLKIT_FAKE", False):
        # โปรแกรมที่พนักงานเปิดจาก start.bat ต้องใช้ยูทูปจริงเสมอ ตัวแปรที่ค้างในเครื่องจะได้ไม่ทำให้เห็นข้อมูลปลอม
        log.warning("ไม่สนใจ YT_TOOLKIT_FAKE ตอน start (ใช้ได้กับ serve เท่านั้น)")
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
            fake=False,
        )
    finally:
        plat.release_lock(lock)


def serve(port: int | None = None, dev: bool = False) -> int:
    """รันแบบไม่มี tray และไม่เปิดเบราว์เซอร์ ใช้ตอนพัฒนา เทส และ E2E (อ่าน YT_TOOLKIT_FAKE ที่นี่ที่เดียว)"""
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
            fake=env_flag("YT_TOOLKIT_FAKE", False),
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
    install_log_filters(paths)  # __main__ ตั้ง app.log ให้ stop แล้ว log ของ stop ก็ต้องไม่มีโฟลเดอร์ผู้ใช้
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
    for _ in range(round(STOP_WAIT_S / STOP_POLL_S)):  # รอสูงสุด STOP_WAIT_S วินาที (FR-LIFE-5)
        if not plat.pid_alive(info.pid):
            break
        sleep(STOP_POLL_S)
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

