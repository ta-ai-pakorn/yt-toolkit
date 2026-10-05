"""ตัวกลางคุยกับยูทูป: โมดูลเดียวในแอพที่ import yt_dlp (ที่อื่นเรียกผ่านที่นี่เท่านั้น)

- YtDlpExtractor: ใช้ yt-dlp จริง (ต้องต่อเน็ต)
- FakeExtractor: อ่านข้อมูลจริงที่ตัดเก็บไว้ใน tests/fixtures/ ใช้กับเทสและโหมด YT_TOOLKIT_FAKE=1

ทั้งสองแบบโยน YtError (รหัสตาม PRD ข้อ 7) แทน error ดิบของ yt-dlp/httpx
"""

from __future__ import annotations

import functools
import importlib.metadata
import json
import logging
import math
import os
import re
import shutil
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from urllib.parse import parse_qs

import httpx

from .cancel import JobCancelled
from .download import (
    DownloadChoice,
    DownloadHooks,
    DownloadResult,
    MediaFacts,
    SponsorBlockError,
    SponsorSegment,
    media_facts,
)
from .frame_piece import PieceInfo, fetch_piece, pick_capture_format, piece_info, read_index, write_piece
from .inputs import PLAYLIST_ID, VIDEO_ID, is_mix_id
from .visitor_session import VisitorSession
from .yterrors import YtError, classify

log = logging.getLogger("yttoolkit")

# สถานะที่ยังโหลดไม่ได้ (ไลฟ์กำลังออกอากาศ / ยังไม่เริ่ม) ส่วน was_live, post_live โหลดได้ตามปกติ
LIVE_NOT_READY = frozenset({"is_live", "is_upcoming"})

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_PROBE_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "noplaylist": True,
    "socket_timeout": 10,
}
FETCH_TIMEOUT = 10  # วินาที ต่อทุกช่วงของคำขอ (เชื่อมต่อ/ส่ง/รอ/อ่าน) เท่ากับ httpx.get(timeout=10) แบบเดิม
# แผ่น storyboard โหลดพร้อมกันได้ถึง 8 แผ่น (storyboard.build) เก็บการเชื่อมต่อไว้ใช้ซ้ำ ไม่ต้องจับมือ TLS ใหม่ทุกแผ่น
_FETCH_LIMITS = httpx.Limits(max_connections=16, max_keepalive_connections=8)
# ข้อเท็จจริงของชิ้นภาพจาก fixture ของตัวปลอม (testsrc 1920x1080 SDR) M5 รอบ B2
_FAKE_CAPTURE_FORMAT = {"format_id": "fake-capture", "width": 1920, "height": 1080, "dynamic_range": "SDR"}
_PLAYLIST_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "extract_flat": "in_playlist",
    "socket_timeout": 10,
}


@runtime_checkable
class Extractor(Protocol):
    def probe(self, video_id: str) -> dict:
        """ข้อมูลดิบของคลิป (info dict ของ yt-dlp)"""
        ...

    def playlist(self, playlist_id: str, limit: int, video_id: str | None = None) -> dict:
        """ข้อมูลแบบแบน: title + entries[{id,title,duration,thumbnails|thumbnail}] อ่านไม่เกิน limit+1 รายการ

        มิกซ์ (id ขึ้นต้น RD) ดึงได้จากลิงก์ watch เท่านั้น จึงต้องส่ง video_id (คลิปตั้งต้น) มาด้วย
        เพลย์ลิสต์ปกติไม่ใช้ video_id
        """
        ...

    def fetch(self, url: str) -> bytes:
        """โหลดไฟล์ภาพ (เช่นแผ่น storyboard) ด้วย HTTP GET"""
        ...

    def fetch_subtitle(self, url: str) -> bytes:
        """โหลดไฟล์ซับ (json3/vtt) จากลิงก์ timedtext ใน probe

        ลิงก์มีลายเซ็นและหมดอายุ: 403/404/410 -> E_NETWORK (ผู้เรียกไป probe ใหม่แล้วลองอีกครั้ง), 429 -> E_BOT_CHECK
        """
        ...

    def pinned_comment(self, video_id: str) -> dict | None:
        """คอมเมนต์ที่ปักหมุดไว้ (ของใครก็ได้ C-A2): {"text", "byUploader", "likes"?, "publishedText"?} หรือ None

        byUploader = เจ้าของช่องเขียนเอง · None = ไม่มีคอมเมนต์ปักหมุดหรือปิดคอมเมนต์ ไม่คืนชื่อ/id ของผู้เขียน (PDPA)
        """
        ...


def check_live(info: dict) -> dict:
    """ไลฟ์ที่ยังออกอากาศหรือยังไม่เริ่ม -> E_LIVE_NOT_READY (AC-PROBE-02)"""
    status = info.get("live_status")
    if status in LIVE_NOT_READY:
        raise YtError("E_LIVE_NOT_READY", f"live_status={status}")
    return info


def _check_video_id(video_id: str) -> None:
    """กฎ id เดียวกับตัวแยกลิงก์ (core/inputs.py) ใช้ทั้งตัวจริงและตัวปลอม"""
    if not VIDEO_ID.fullmatch(video_id):
        raise YtError("E_INVALID_INPUT", f"video id ไม่ถูกรูปแบบ: {video_id!r}")


def _check_playlist_id(playlist_id: str) -> None:
    if not PLAYLIST_ID.fullmatch(playlist_id):
        raise YtError("E_INVALID_INPUT", f"playlist id ไม่ถูกรูปแบบ: {playlist_id!r}")


def _playlist_url(playlist_id: str, video_id: str | None) -> str:
    """ตรวจ id แล้วคืนลิงก์ที่ใช้ดึงรายการ: มิกซ์ใช้ลิงก์ watch ของคลิปตั้งต้น เพลย์ลิสต์ปกติใช้ลิงก์ playlist"""
    _check_playlist_id(playlist_id)
    if not is_mix_id(playlist_id):
        return f"https://www.youtube.com/playlist?list={playlist_id}"
    if not video_id:
        raise YtError("E_INVALID_INPUT", f"มิกซ์ {playlist_id!r} ต้องมีคลิปตั้งต้น (v)")
    _check_video_id(video_id)
    return f"https://www.youtube.com/watch?v={video_id}&list={playlist_id}"


def ytdlp_version() -> str:
    from yt_dlp.version import __version__

    return __version__


def pinned_from_comment(comment: object) -> dict | None:
    """คอมเมนต์หนึ่งอันของ yt-dlp -> {"text", "likes"?, "publishedText"?, "byUploader"} หรือ None

    นับทุกคอมเมนต์ที่ปักหมุด (is_pinned) ไม่ว่าใครเขียน (C-A2 v2) byUploader = เจ้าของช่องเขียนเอง (author_is_uploader)
    ไม่เก็บชื่อ, id, ลิงก์ หรือรูปของผู้เขียน (PDPA: ส่งออกแค่ true/false ว่าเป็นเจ้าของช่องหรือไม่)
    """
    if not isinstance(comment, dict):
        return None
    if comment.get("is_pinned") is not True:
        return None
    text = comment.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    out: dict = {"text": text, "byUploader": comment.get("author_is_uploader") is True}
    likes = comment.get("like_count")
    if isinstance(likes, int) and not isinstance(likes, bool) and likes >= 0:
        out["likes"] = likes
    published = comment.get("_time_text")
    if isinstance(published, str) and published.strip():
        out["publishedText"] = published.strip()
    return out


# คอมเมนต์อันดับแรกของแบบ "ยอดนิยม" (= คอมเมนต์ปักหมุด ถ้ามี) ไม่เอาคำตอบ
# max_comments = max-comments, max-parents, max-replies, max-replies-per-thread, max-depth
_COMMENT_ARGS = {"youtube": {"comment_sort": ["top"], "max_comments": ["1", "1", "0", "0", "1"]}}
# error ของทางหลักที่ไม่ถอยไปทางสำรอง: ทางสำรองก็จะเจอแบบเดียวกัน (review M-1)
# E_YT_REFUSED = ยูทูปตอบ 4xx (ไม่ใช่ 429) ยิงซ้ำทางสำรองก็ได้คำตอบเดิม (M4 T4 review M-1)
_NO_FALLBACK = frozenset({"E_NETWORK", "E_BOT_CHECK", "E_YT_REFUSED"})


def _first_comment_direct(ydl: Any, video_id: str) -> dict | None:
    """ทางหลัก: ตัวดึงคอมเมนต์ของ YoutubeIE โดยตรง ไม่ probe คลิปซ้ำ (API ภายในของ yt-dlp)

    contents ว่าง = yt-dlp สร้าง continuation จาก id เอง (ทางเดียวกับที่ yt-dlp ใช้เมื่อหน้าเว็บไม่มี)
    """
    ie = ydl.get_info_extractor("Youtube")
    ie.initialize()
    comments = ie._get_comments(ie._get_default_ytcfg("web"), video_id, [], None)
    first = next(iter(comments), None)
    return first if isinstance(first, dict) else None


def _first_comment_public(ydl: Any, video_id: str) -> dict | None:
    """ทางสำรอง: probe พร้อม getcomments (API สาธารณะ) จำกัดคอมเมนต์ด้วย extractor_args ชุดเดียวกัน"""
    ydl.params["getcomments"] = True
    info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    comments = (info or {}).get("comments") or []
    return comments[0] if comments and isinstance(comments[0], dict) else None


def _cookie_jar(filename: str) -> Any:
    """jar เปล่าแบบเดียวกับที่ yt-dlp ใช้กับ cookiefile (อ่าน/เขียนไฟล์ Netscape และเข้าใจคุกกี้แบบ session ของ yt-dlp)"""
    from yt_dlp.cookies import YoutubeDLCookieJar

    return YoutubeDLCookieJar(filename)


def visitor_session(folder: Path) -> VisitorSession:
    """เซสชันผู้ชมแบบไม่ระบุตัวตนที่ probe และการโหลดซับใช้ร่วมกัน (ไฟล์ <folder>/visitor-session.txt)"""
    return VisitorSession(folder, _cookie_jar)


def _attach_session(ydl: Any, session: VisitorSession) -> None:
    """ให้ YoutubeDL ตัวนี้ใช้ jar ก้อนเดียวของเซสชัน และบันทึกผ่านเซสชัน (ล็อก + เขียนไฟล์แบบ replace)

    API ภายในของ yt-dlp: `cookiejar` เป็น cached_property จึงใส่ค่าไว้ล่วงหน้าใน __dict__ ได้ (ต้องทำก่อนคำขอแรก
    ตัวส่งคำขอของ yt-dlp จะได้ถือ jar ก้อนนี้)
    ถ้า yt-dlp รุ่นหน้าเปลี่ยนจนใส่ไม่ได้ ผลขึ้นกับว่า yt-dlp สร้าง jar ของตัวเองเมื่อไร:
    - โหลดจาก cookiefile ก่อนคำขอแรก: ยังได้คุกกี้ผู้เข้าชมจากไฟล์ และ save ด้านล่างรวมคุกกี้ใหม่กลับเข้าก้อนกลาง
    - สร้างตัวส่งคำขอจาก jar ของตัวเองไปก่อนแล้ว (ไม่ได้อ่านจากก้อนกลาง): คุกกี้ผู้เข้าชมจะ**ไม่ถูกใช้ร่วมกันโดยไม่มีอะไรเตือน**
      ซับแปลจะกลับไปได้ 429 ตัวกันคือเทสสัญญากับ YoutubeDL จริง (test_attach_session_on_a_real_youtubedl)
      ที่ตรวจว่า cookiejar และตัวส่งคำขอถือ jar ก้อนนี้ ต้องผ่านทุกครั้งที่อัปเดต yt-dlp
    save_cookies ของ yt-dlp (เรียกตอนปิด) เขียนไฟล์ตรง ๆ ไม่มีล็อก จึงแทนด้วยของเซสชัน
    """
    ydl.__dict__["cookiejar"] = session.jar()

    def save_cookies() -> None:
        try:
            session.save(ydl.cookiejar)
        except Exception as exc:  # ปิด YoutubeDL ต้องไม่พังเพราะบันทึกคุกกี้ไม่ได้ (ไม่มีค่าคุกกี้ใน log)
            log.warning("บันทึกเซสชันผู้ชมของยูทูปไม่สำเร็จ (%s)", type(exc).__name__)

    ydl.save_cookies = save_cookies


_impersonation_warned = threading.Event()


def _can_impersonate(ydl: Any) -> bool:
    """มีตัวส่งคำขอที่ทำตัวเป็นเบราว์เซอร์ได้ (curl_cffi) หรือไม่ (API ภายในของ yt-dlp: พังเมื่อไรถือว่าไม่มี)"""
    from yt_dlp.networking.impersonate import ImpersonateTarget

    try:
        return bool(ydl._impersonate_target_available(ImpersonateTarget()))
    except Exception:
        return False


def _subtitle_request(ydl: Any, url: str) -> Any:
    """คำขอโหลดซับแบบเดียวกับที่ตัวโหลดของ yt-dlp ทำ (ทุกลิงก์ซับของยูทูปขอ impersonate)

    ไม่มี curl_cffi = คำขอธรรมดา และเตือนใน log ครั้งเดียวต่อการเปิดโปรแกรม
    """
    from yt_dlp.networking import Request
    from yt_dlp.networking.impersonate import ImpersonateTarget

    if _can_impersonate(ydl):
        return Request(url, extensions={"impersonate": ImpersonateTarget()})
    if not _impersonation_warned.is_set():
        _impersonation_warned.set()
        log.warning("ไม่มี curl_cffi (ทำงานแบบเบราว์เซอร์) โหลดซับด้วยคำขอธรรมดาแทน")
    return Request(url)


@functools.cache
def impersonation_info() -> tuple[bool, str | None]:
    """(yt-dlp ทำตัวเป็นเบราว์เซอร์ได้ไหม, เวอร์ชัน curl_cffi) สำหรับหน้าตรวจสุขภาพ ไม่ต่อเน็ต

    ตรวจครั้งเดียวต่อการเปิดโปรแกรม (แพ็กเกจไม่เปลี่ยนระหว่างรัน)
    """
    import yt_dlp

    try:
        version: str | None = importlib.metadata.version("curl_cffi")
    except importlib.metadata.PackageNotFoundError:
        version = None
    with yt_dlp.YoutubeDL({**_PROBE_OPTS, "logger": _YtDlpLogger()}) as ydl:
        return _can_impersonate(ydl), version


class _YtDlpLogger:
    """เก็บข้อความของ yt-dlp ลง log ของแอพแทนการพิมพ์ลงจอ (error ถูกโยนเป็น YtError อยู่แล้ว)"""

    def debug(self, msg: str) -> None:
        log.debug("yt-dlp: %s", msg)

    def info(self, msg: str) -> None:
        log.debug("yt-dlp: %s", msg)

    def warning(self, msg: str) -> None:
        log.warning("yt-dlp: %s", msg)

    def error(self, msg: str) -> None:
        log.debug("yt-dlp: %s", msg)


class _PathHidingLogger(_YtDlpLogger):
    """logger ของตัวโหลด: ข้อความของ yt-dlp มี path เต็มได้ (เช่น "Unable to delete file C:\\Users\\<ชื่อ>\\...")

    แทน workdir ด้วย <workdir> และโฟลเดอร์ home ของผู้ใช้ด้วย ~ ก่อนลง log (ชื่อผู้ใช้ Windows ห้ามลง log)
    เทียบแบบไม่สนตัวพิมพ์ และทั้งแบบ \\ กับ / (path อันยาวแทนก่อน)
    """

    def __init__(self, workdir: Path) -> None:
        pairs: dict[str, str] = {}
        for path, label in ((workdir, "<workdir>"), (workdir.resolve(), "<workdir>"), (Path.home(), "~")):
            text = str(path)
            if len(text) > 1:
                for variant in (text, text.replace("\\", "/"), text.replace("/", "\\")):
                    pairs.setdefault(variant.lower(), label)
        ordered = sorted(pairs, key=len, reverse=True)
        self._labels = pairs
        self._pattern = re.compile("|".join(re.escape(p) for p in ordered), re.IGNORECASE)

    def _hide(self, msg: str) -> str:
        return self._pattern.sub(lambda m: self._labels[m.group(0).lower()], str(msg))

    def debug(self, msg: str) -> None:
        super().debug(self._hide(msg))

    def info(self, msg: str) -> None:
        super().info(self._hide(msg))

    def warning(self, msg: str) -> None:
        super().warning(self._hide(msg))

    def error(self, msg: str) -> None:
        super().error(self._hide(msg))


# ---------- งานโหลดไฟล์ (C8) ----------

# ไฟล์ที่ตัวโหลดเขียนใน workdir ขึ้นต้นด้วย "media." ทั้งหมด (ไฟล์สุดท้าย ไฟล์ format ย่อย .part .ytdl)
_MEDIA_GLOB = "media.*"
# Q2: ยูทูปไม่ส่งไฟล์ (4xx ที่ไม่ใช่ 429) ตอนโหลด -> ดึงข้อมูลใหม่ (ลิงก์ใหม่) แล้วโหลดอีกรอบเดียว
_REFUSED_ATTEMPTS = 2
_SPONSORBLOCK_RETRIES = 1  # ลองซ้ำครั้งเดียวพอ: ติดต่อไม่ได้ก็ยังได้คลิปเต็มพร้อมโน้ต


def _sponsor_from_chapters(chapters: object, categories: Sequence[str]) -> list[SponsorSegment]:
    """sponsorblock_chapters ของ SponsorBlockPP -> [(startMs, endMs, หมวด)] เฉพาะแบบ "skip" ของหมวดที่ขอ"""
    wanted = set(categories)
    found: list[SponsorSegment] = []
    for chapter in chapters if isinstance(chapters, list) else []:
        if not isinstance(chapter, dict) or chapter.get("type") != "skip" or chapter.get("category") not in wanted:
            continue
        start, end = chapter.get("start_time"), chapter.get("end_time")
        if isinstance(start, int | float) and isinstance(end, int | float) and end > start:
            found.append((round(start * 1000), round(end * 1000), str(chapter["category"])))
    return sorted(found)


def _yt_error(exc: BaseException) -> YtError:
    """exception จาก yt-dlp -> YtError: YoutubeDLError จัดรหัสจากข้อความ ที่เหลือ (บั๊กภายใน) = E_UNKNOWN"""
    from yt_dlp.utils import YoutubeDLError

    if isinstance(exc, YoutubeDLError):
        message = _ANSI.sub("", str(exc)) or type(exc).__name__
        return YtError(classify(message), message)
    return YtError("E_UNKNOWN", f"{type(exc).__name__}: {exc}")


def _count(value: object) -> int | None:
    """ตัวเลขจาก hook ของ yt-dlp (ไบต์ ความเร็ว วินาที) -> int ที่ไม่ติดลบ อย่างอื่น = ไม่รู้"""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return int(value)


def _cancelled() -> BaseException:
    """DownloadCancelled ของ yt-dlp: โยนจาก hook แล้ว yt-dlp หยุดโหลดทันที (download() แปลงเป็น JobCancelled)"""
    from yt_dlp.utils import DownloadCancelled

    return DownloadCancelled("cancelled by the user")


def _progress_hook(hooks: DownloadHooks) -> Callable[[dict], None]:
    """progress hook ของ yt-dlp -> on_stage / on_progress (ยกเลิกแล้ว = โยน DownloadCancelled)

    แทร็กที่ไม่มีภาพ (vcodec "none") = กำลังโหลดเสียง เรียก on_stage เฉพาะตอนขั้นเปลี่ยน
    สัดส่วนนับต่อแทร็ก (yt-dlp โหลดภาพกับเสียงแยกไฟล์กัน)
    """
    last: list[str] = []

    def hook(d: dict) -> None:
        if d.get("status") != "downloading":
            return
        if hooks.is_cancelled():
            raise _cancelled()
        info = d.get("info_dict") or {}
        stage = "downloading_audio" if info.get("vcodec") == "none" else "downloading_video"
        if last != [stage]:
            last[:] = [stage]
            hooks.on_stage(stage)
        done = _count(d.get("downloaded_bytes"))
        total = _count(d.get("total_bytes")) or _count(d.get("total_bytes_estimate"))
        fraction = min(1.0, done / total) if done is not None and total else None
        hooks.on_progress(fraction, _count(d.get("speed")), _count(d.get("eta")))

    return hook


def _pp_hook(hooks: DownloadHooks) -> Callable[[dict], None]:
    """postprocessor hook: ตัวรวมภาพกับเสียง (FFmpegMergerPP ชื่อ "Merger") เริ่ม = ขั้น merging"""

    def hook(d: dict) -> None:
        if d.get("status") != "started":
            return
        if hooks.is_cancelled():
            raise _cancelled()
        if d.get("postprocessor") == "Merger":
            hooks.on_stage("merging")

    return hook


def _download_opts(choice: DownloadChoice, workdir: Path, hooks: DownloadHooks) -> dict:
    """ค่าตั้งของ YoutubeDL ตัวที่สอง (ตัวโหลด) ตาม C8 ไฟล์ออกเป็น workdir/media.<ext> ไฟล์ชั่วคราวก็อยู่ใน workdir"""
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "overwrites": True,
        "socket_timeout": 20,
        "retries": 3,
        "fragment_retries": 3,
        "format": choice.format_spec,
        "outtmpl": {"default": "media.%(ext)s"},
        "paths": {"home": str(workdir), "temp": str(workdir)},
        "progress_hooks": [_progress_hook(hooks)],
        "postprocessor_hooks": [_pp_hook(hooks)],
        "logger": _PathHidingLogger(workdir),
    }
    if choice.merge_mp4:
        opts["merge_output_format"] = "mp4"
    if hooks.ffmpeg_location is not None:
        opts["ffmpeg_location"] = str(hooks.ffmpeg_location)
    return opts


def _clear_media(workdir: Path) -> None:
    """ลบไฟล์ media.* ที่โหลดค้างไว้ใน workdir (โหลดพลาดหรือถูกยกเลิก) ไม่แตะไฟล์อื่นของงาน

    log บอกแค่ชื่อไฟล์ ไม่บอก path เต็ม (มีชื่อผู้ใช้ Windows)
    """
    for path in workdir.glob(_MEDIA_GLOB):
        try:
            if path.is_file():
                path.unlink()
        except OSError as exc:
            log.warning("ลบไฟล์ที่โหลดค้าง %s ไม่ได้ (%s)", path.name, type(exc).__name__)


def _is_partial(path: Path) -> bool:
    return ".part" in path.name or path.name.endswith(".ytdl")


def _media_path(result: object, workdir: Path) -> Path:
    """ไฟล์ที่โหลดเสร็จ: requested_downloads[-1].filepath ถ้ามีและอยู่ใน workdir ไม่งั้นไฟล์ media.* ไฟล์เดียวที่ไม่ใช่ไฟล์ค้าง"""
    downloads = result.get("requested_downloads") if isinstance(result, dict) else None
    if isinstance(downloads, list) and downloads and isinstance(downloads[-1], dict):
        filepath = downloads[-1].get("filepath")
        if isinstance(filepath, str) and filepath:
            path = Path(filepath)
            if path.is_file() and path.resolve().is_relative_to(workdir.resolve()):
                return path
    found = [p for p in workdir.glob(_MEDIA_GLOB) if p.is_file() and not _is_partial(p)]
    if len(found) == 1:
        return found[0]
    raise YtError("E_UNKNOWN", f"yt-dlp โหลดจบแต่หาไฟล์สื่อไม่ได้ (เจอ {len(found)} ไฟล์)")


def _downloaded_facts(result: object) -> MediaFacts | None:
    """ขนาดภาพและช่วงสีของไฟล์ที่โหลดจริง: requested_downloads ตัวสุดท้าย (yt-dlp รวมค่าของภาพไว้ให้ตอนรวมไฟล์)
    หรือผลระดับบน · ไม่รู้ความสูง = None"""
    if not isinstance(result, dict):
        return None
    downloads = result.get("requested_downloads")
    source = downloads[-1] if isinstance(downloads, list) and downloads and isinstance(downloads[-1], dict) else result
    facts = media_facts(source)
    return facts if facts.height is not None else None


class YtDlpExtractor:
    """ตัวจริง: probe/playlist ผ่าน yt-dlp, fetch ผ่าน httpx.Client ตัวเดียวที่ใช้ร่วมกันทุก thread

    client สร้างเมื่อ fetch ครั้งแรก และปิดด้วย close() ตอนปิดโปรแกรม (เรียกซ้ำได้ ใช้ต่อหลัง close ได้)
    transport มีไว้ให้เทสใส่ httpx.MockTransport แทนเน็ตจริง
    """

    def __init__(
        self, transport: httpx.BaseTransport | None = None, session: VisitorSession | None = None
    ) -> None:
        self._transport = transport
        self._client: httpx.Client | None = None
        self._client_lock = threading.Lock()
        # เซสชันผู้ชมที่ probe และ fetch_subtitle ใช้ร่วมกัน (None = ไม่เก็บคุกกี้ข้ามครั้ง แบบเดิม)
        self.session = session

    @contextmanager
    def _ydl(self, opts: dict, *, with_session: bool = False) -> Iterator[Any]:
        """YoutubeDL หนึ่งตัว with_session = ใช้เซสชันผู้ชม (ผ่าน cookiefile) แล้วบันทึกคืนตอนปิด"""
        import yt_dlp

        # opts ที่มี logger ของตัวเอง (ตัวโหลดใช้ตัวที่ซ่อน path) ใช้ตัวนั้น ไม่งั้นใช้ตัวปกติ
        params = {"logger": _YtDlpLogger(), **opts}
        session = self.session if with_session else None
        if session is not None:
            params["cookiefile"] = str(session.path)
        with yt_dlp.YoutubeDL(params) as ydl:
            if session is not None:
                _attach_session(ydl, session)
            yield ydl

    def _http(self) -> httpx.Client:
        with self._client_lock:
            if self._client is None:
                self._client = httpx.Client(
                    timeout=FETCH_TIMEOUT,
                    follow_redirects=True,
                    limits=_FETCH_LIMITS,
                    transport=self._transport,
                )
            return self._client

    def close(self) -> None:
        with self._client_lock:
            client, self._client = self._client, None
        if client is not None:
            client.close()

    def probe(self, video_id: str) -> dict:
        _check_video_id(video_id)
        # เก็บคุกกี้ผู้เข้าชมที่ยูทูปออกให้ระหว่าง probe ไว้ (ไม่มีคำขอเพิ่ม) ซับแปลต้องใช้เซสชันที่อายุถึง 75 วินาที
        info = self._extract(f"https://www.youtube.com/watch?v={video_id}", _PROBE_OPTS, with_session=True)
        return check_live(info)

    def playlist(self, playlist_id: str, limit: int, video_id: str | None = None) -> dict:
        url = _playlist_url(playlist_id, video_id)
        opts = {**_PLAYLIST_OPTS, "playlistend": limit + 1}
        info = self._extract(url, opts)
        info["entries"] = list(info.get("entries") or [])[: limit + 1]
        return info

    def warm_up(self) -> None:
        """import yt-dlp และตัวดึงของยูทูปไว้ก่อน (ครั้งแรกใช้เวลาเกือบ 1 วินาที) ไม่ต่อเน็ต

        แอพเรียกใน thread แยกหลังเซิร์ฟเวอร์พร้อม ลิงก์แรกที่ผู้ใช้วางจะได้ไม่ต้องรอ import
        import ไม่ได้ก็โยนต่อ (ผู้เรียกบันทึก log เอง) ตอน probe จริงจะแจ้ง error ตามปกติ
        """
        import yt_dlp

        with yt_dlp.YoutubeDL({**_PROBE_OPTS, "logger": _YtDlpLogger()}) as ydl:
            ydl.get_info_extractor("Youtube")

    def fetch(self, url: str) -> bytes:
        try:
            response = self._http().get(url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise YtError("E_NETWORK", f"{type(exc).__name__}: {exc}") from exc
        return response.content

    def fetch_subtitle(self, url: str) -> bytes:
        """โหลดไฟล์ซับผ่าน urlopen ของ yt-dlp แล้วแปลงทุกความผิดพลาดเป็น YtError

        ใช้เซสชันผู้ชมเดียวกับ probe และขอแบบทำตัวเป็นเบราว์เซอร์ (curl_cffi) เหมือนตัวโหลดซับของ yt-dlp เอง
        """
        from yt_dlp.networking.exceptions import HTTPError, RequestError
        from yt_dlp.utils import YoutubeDLError

        try:
            with self._ydl(_PROBE_OPTS, with_session=True) as ydl:
                with ydl.urlopen(_subtitle_request(ydl, url)) as resp:
                    return resp.read()
        except YtError:
            raise
        except HTTPError as exc:
            message = _ANSI.sub("", str(exc)) or type(exc).__name__
            if exc.status == 429:
                raise YtError("E_BOT_CHECK", message) from exc
            # 403/404/410 = ลิงก์ที่เซ็นไว้หมดอายุ (ผู้เรียก probe ใหม่เอง) ที่เหลือก็ถือเป็นปัญหาเครือข่ายเช่นกัน
            raise YtError("E_NETWORK", message) from exc
        except RequestError as exc:
            message = _ANSI.sub("", str(exc)) or type(exc).__name__
            raise YtError("E_NETWORK", message) from exc
        except YoutubeDLError as exc:
            message = _ANSI.sub("", str(exc)) or type(exc).__name__
            raise YtError(classify(message), message) from exc
        except Exception as exc:
            raise YtError("E_UNKNOWN", f"{type(exc).__name__}: {exc}") from exc

    def pinned_comment(self, video_id: str) -> dict | None:
        """คอมเมนต์ที่ปักหมุดไว้ ของใครก็ได้ พร้อม byUploader (C-A2) ดึงเมื่อผู้ใช้เปิดดูเท่านั้น ไม่ดึงตอน probe

        ทางหลัก (ถูกสุด ~2 คำขอ innertube "next"): เรียกตัวดึงคอมเมนต์ของ yt-dlp ตรง ๆ
        ด้วย comment_sort=top และ max_comments=1 (คอมเมนต์ปักหมุดอยู่อันดับแรกเสมอ)
        เป็น API ภายในของ yt-dlp ที่อาจเปลี่ยนได้ทุกรุ่น ทางหลักพังด้วยเหตุอื่นที่ไม่ใช่เน็ตหรือยูทูปบล็อก
        (exception ใดก็ได้ที่ไม่ใช่ YoutubeDLError หรือ YoutubeDLError ที่ไม่อยู่ใน _NO_FALLBACK)
        ถอยไปใช้ getcomments ของ probe ปกติ (API สาธารณะ แพงกว่า: probe ทั้งคลิปอีกรอบ) จำกัดจำนวนเท่ากัน
        เน็ตหลุด ยูทูปบล็อก หรือยูทูปปฏิเสธ (4xx) โยนต่อทันที (ลองทางสำรองก็เจอแบบเดียวกัน แถมยิงยูทูปเพิ่ม)
        """
        _check_video_id(video_id)
        import yt_dlp
        from yt_dlp.utils import YoutubeDLError

        opts = {**_PROBE_OPTS, "logger": _YtDlpLogger(), "extractor_args": _COMMENT_ARGS}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                try:
                    first = _first_comment_direct(ydl, video_id)
                except Exception as exc:
                    if isinstance(exc, YoutubeDLError):
                        message = _ANSI.sub("", str(exc)) or type(exc).__name__
                        if classify(message) in _NO_FALLBACK:
                            raise
                    log.warning(
                        "ดึงคอมเมนต์ปักหมุดของ %s ทางหลักไม่ได้ (yt-dlp อาจเปลี่ยนภายใน) ใช้ probe แทน: %s: %s",
                        video_id,
                        type(exc).__name__,
                        exc,
                    )
                    first = _first_comment_public(ydl, video_id)
        except YtError:
            raise
        except YoutubeDLError as exc:
            message = _ANSI.sub("", str(exc)) or type(exc).__name__
            raise YtError(classify(message), message) from exc
        except Exception as exc:
            raise YtError("E_UNKNOWN", f"{type(exc).__name__}: {exc}") from exc
        return pinned_from_comment(first)

    def sponsor_segments(
        self, video_id: str, categories: Sequence[str], duration_s: float | None
    ) -> list[SponsorSegment]:
        """ช่วงโฆษณาจาก SponsorBlock ผ่าน SponsorBlockPP ของ yt-dlp (ส่งแค่ hash 4 ตัวแรกของ video id)

        ไม่ใช้เซสชันผู้ชม (ไม่ใช่ยูทูป) · ไม่รู้ความยาวคลิป = SponsorBlockError (ตัวกรองของ yt-dlp ต้องใช้)
        พังแบบไหนก็ได้ SponsorBlockError ที่บอกแค่ชื่อชนิด error (ไม่มีข้อมูลผู้ใช้ใน log)
        """
        _check_video_id(video_id)
        if not duration_s:
            raise SponsorBlockError("duration unknown")
        from yt_dlp.postprocessor.sponsorblock import SponsorBlockPP

        try:
            with self._ydl({**_PROBE_OPTS, "extractor_retries": _SPONSORBLOCK_RETRIES}) as ydl:
                pp = SponsorBlockPP(ydl, list(categories))
                _, info = pp.run({"id": video_id, "extractor_key": "Youtube", "duration": duration_s})
        except Exception as exc:
            raise SponsorBlockError(type(exc).__name__) from exc
        return _sponsor_from_chapters(info.get("sponsorblock_chapters"), categories)

    def download(
        self,
        video_id: str,
        choose: Callable[[dict], DownloadChoice],
        workdir: Path,
        hooks: DownloadHooks,
    ) -> DownloadResult:
        """ดึงข้อมูลคลิปครั้งเดียว ให้ choose เลือก format แล้วโหลดลง workdir/media.<ext> (C8)

        - YoutubeDL ตัวแรกดึงข้อมูล (เซสชันผู้ชมเดียวกับ probe) ตัวที่สองสร้างด้วย format ที่เลือก แล้วโหลดจาก
          info ของรอบเดียวกัน (yt-dlp สร้างตัวเลือก format ตอนสร้าง YoutubeDL เปลี่ยนทีหลังไม่ได้) ไม่ดึงข้อมูลซ้ำ
        - YtError จาก choose โยนต่อตามเดิม · ยกเลิก = JobCancelled · error ของ yt-dlp = YtError ตามข้อความ
        - ยูทูปไม่ส่งไฟล์ (E_YT_REFUSED) ตอนโหลด: ดึงข้อมูล + เลือก + โหลดใหม่อีกรอบเดียว แล้วจึงโยน (Q2)
        - พลาดหรือถูกยกเลิก: ลบไฟล์ media.* ที่ค้างใน workdir ไม่ทิ้งไฟล์ครึ่ง ๆ ไว้
        """
        _check_video_id(video_id)
        url = f"https://www.youtube.com/watch?v={video_id}"
        attempt = 1
        while True:
            # ยกเลิกแล้วไม่ต้องรอดึงข้อมูลใหม่ (รอบแรกหรือรอบลองซ้ำของ Q2) หรือรอเริ่มโหลด
            if hooks.is_cancelled():
                raise JobCancelled()
            source, info = self._extract_for_download(url)
            choice = choose(info)
            if hooks.is_cancelled():
                raise JobCancelled()
            try:
                path, media = self._download_media(source, choice, workdir, hooks)
            except YtError as exc:
                _clear_media(workdir)
                if exc.code != "E_YT_REFUSED" or attempt >= _REFUSED_ATTEMPTS:
                    raise
                attempt += 1
                log.warning("ยูทูปไม่ส่งไฟล์ของ %s ดึงข้อมูลใหม่แล้วโหลดอีกครั้ง", video_id)
                continue
            except JobCancelled:
                _clear_media(workdir)
                raise
            return DownloadResult(path=path, info=info, choice=choice, media=media)

    def _extract_for_download(self, url: str) -> tuple[dict, dict]:
        """(info สำหรับ process_ie_result, info ที่ sanitize แล้วสำหรับ choose และ DownloadResult)

        ตอนดึงข้อมูล yt-dlp เลือก format ตามค่าตั้งต้นไปแล้ว (requested_formats ฯลฯ ค้างอยู่ระดับบน)
        ถ้าส่ง info ดิบให้ตัวโหลด งานเสียงอย่างเดียวจะโหลด format เก่าที่ค้างอยู่ จึงล้างแบบเดียวกับที่ yt-dlp
        ทำกับ --load-info-json (sanitize_info แบบ remove_private_keys) ก่อนส่งต่อ
        """
        try:
            with self._ydl(_PROBE_OPTS, with_session=True) as ydl:
                raw = ydl.extract_info(url, download=False)
                if raw is None:
                    raise YtError("E_UNKNOWN", f"yt-dlp ไม่คืนข้อมูลสำหรับ {url}")
                info = check_live(ydl.sanitize_info(raw))
                return ydl.sanitize_info(raw, remove_private_keys=True), info
        except YtError:
            raise
        except Exception as exc:
            raise _yt_error(exc) from exc

    def _download_media(
        self, source: dict, choice: DownloadChoice, workdir: Path, hooks: DownloadHooks
    ) -> tuple[Path, MediaFacts | None]:
        """YoutubeDL ตัวที่สองโหลดตาม choice แล้วคืนไฟล์ใน workdir กับขนาดภาพของไฟล์นั้น"""
        from yt_dlp.utils import DownloadCancelled

        try:
            with self._ydl(_download_opts(choice, workdir, hooks), with_session=True) as ydl:
                result = ydl.process_ie_result(source, download=True)
            return _media_path(result, workdir), _downloaded_facts(result)
        except (YtError, JobCancelled):
            raise
        except DownloadCancelled as exc:
            raise JobCancelled() from exc
        except Exception as exc:
            raise _yt_error(exc) from exc

    def fetch_frame_piece(self, video_id: str, t_ms: int, max_short_side: int | None, dest: Path) -> PieceInfo:
        """ภาพคมตรงจุด (M5 รอบ B2 spec 3.1) โดยไม่โหลดทั้งคลิป

        1. probe ใหม่ (ค่าตั้ง probe + เซสชันผู้ชม): ข้อมูลที่เก็บไว้ไม่มีลิงก์สื่อ และลิงก์ที่ยูทูปเซ็นไว้หมดอายุได้
        2. เลือก mp4 ภาพอย่างเดียวผ่าน https (frame_piece.pick_capture_format) ไม่มี = E_CAPTURE_UNSUPPORTED
        3. โหลดหัวไฟล์ (64 KB) อ่าน sidx แล้วโหลดเฉพาะท่อนที่มี t_ms ด้วยคำขอแบบ Range ผ่านตัวส่งคำขอของ yt-dlp
           (spike 2026-10-05: --download-sections และ ffmpeg ที่ต่อลิงก์ยูทูปตรง ๆ ค้าง)
           คำตอบที่ไม่ใช่ HTTP 206 (เซิร์ฟเวอร์ไม่สน Range แล้วส่งทั้งไฟล์ 200) = E_NETWORK ไม่ใช้ข้อมูลนั้น
        4. เขียน init + ท่อนนั้นลง dest
        error: HTTP 429 = E_BOT_CHECK · 4xx อื่น = E_YT_REFUSED · 5xx และเน็ตหลุด = E_NETWORK
        รายละเอียดของ error และ log ไม่มีลิงก์สื่อ (มีลายเซ็น) หัวคำขอ หรือ path: log บอกแค่ id, format และจำนวนไบต์
        """
        _check_video_id(video_id)
        from yt_dlp.networking import Request
        from yt_dlp.networking.exceptions import HTTPError, RequestError
        from yt_dlp.utils import YoutubeDLError

        fetched = 0
        try:
            with self._ydl(_PROBE_OPTS, with_session=True) as ydl:
                raw = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                if raw is None:
                    raise YtError("E_UNKNOWN", f"yt-dlp ไม่คืนข้อมูลสำหรับ {video_id}")
                fmt = pick_capture_format(check_live(ydl.sanitize_info(raw)), max_short_side)
                if fmt is None:
                    raise YtError("E_CAPTURE_UNSUPPORTED", f"{video_id}: no video-only mp4 over https")
                media_url = str(fmt["url"])
                headers = {str(k): str(v) for k, v in (fmt.get("http_headers") or {}).items()}

                def read_range(first: int, last: int) -> bytes:
                    nonlocal fetched
                    request = Request(media_url, headers={**headers, "Range": f"bytes={first}-{last}"})
                    with ydl.urlopen(request) as response:
                        if response.status != 206:
                            raise YtError("E_NETWORK", f"range not honoured (HTTP {response.status})")
                        data = response.read(last - first + 1)
                    fetched += len(data)
                    return data

                index = read_index(read_range)
                piece, ref = fetch_piece(read_range, index, t_ms)
        except YtError:
            raise
        except HTTPError as exc:
            detail = f"HTTP Error {exc.status}"
            code = classify(detail)
            raise YtError("E_NETWORK" if code == "E_UNKNOWN" else code, detail) from exc
        except RequestError as exc:
            raise YtError("E_NETWORK", type(exc).__name__) from exc
        except YoutubeDLError as exc:
            message = _ANSI.sub("", str(exc)) or type(exc).__name__
            raise YtError(classify(message), message) from exc
        except Exception as exc:
            raise YtError("E_UNKNOWN", f"{type(exc).__name__}: {exc}") from exc
        write_piece(dest, piece)
        log.info("ถ่ายภาพคม %s: format %s โหลด %d ไบต์", video_id, fmt.get("format_id"), fetched)
        return piece_info(fmt, dest, index.sidx, ref)

    def _extract(self, url: str, opts: dict, *, with_session: bool = False) -> dict:
        """เรียก yt-dlp แล้วแปลงทุกความผิดพลาดเป็น YtError (ห้ามมี exception ดิบหลุดออกไป)"""
        from yt_dlp.utils import YoutubeDLError

        try:
            with self._ydl(opts, with_session=with_session) as ydl:
                info = ydl.extract_info(url, download=False)
                if info is None:
                    raise YtError("E_UNKNOWN", f"yt-dlp ไม่คืนข้อมูลสำหรับ {url}")
                return ydl.sanitize_info(info)
        except YtError:
            raise
        except YoutubeDLError as exc:
            # รวม DownloadError, ExtractorError และ networking RequestError
            message = _ANSI.sub("", str(exc)) or type(exc).__name__
            raise YtError(classify(message), message) from exc
        except Exception as exc:
            # บั๊กภายใน yt-dlp (KeyError, RuntimeError ฯลฯ)
            raise YtError("E_UNKNOWN", f"{type(exc).__name__}: {exc}") from exc


class FakeExtractor:
    """อ่านจาก fixtures_root: probe/<id>.json, playlist/<id>.json, storyboard/<ชื่อไฟล์>, sponsorblock/<id>.json

    ใช้กฎ id เดียวกับ YtDlpExtractor (ผิดรูปแบบ = E_INVALID_INPUT)
    หาไฟล์จากชื่อไฟล์ก่อน ถ้าไม่เจอจึงหาไฟล์ที่ฟิลด์ "id" ตรงกัน (เช่น live_upcoming.json มี id UPCOMINGLV1)
    calls บันทึกทุกการเรียกเป็น (ชื่อเมธอด, อาร์กิวเมนต์) ให้เทสนับได้

    งานโหลด (download) ทำตาม behaviors (C14 ค่าตั้งต้น <fixtures_root>/downloads/behaviors.json):
    จำนวนขั้น เวลาต่อขั้น และ error ที่ตั้งไว้ต่อคลิป แล้วคัดลอกไฟล์จาก media/ ไม่ใช้ ffmpeg ไม่ต่อเน็ต
    ภาพคมตรงจุด (fetch_frame_piece) ตัดชิ้นจาก capture/piece.mp4 ตาม "captureError" ใน behaviors (M5 รอบ B2)
    """

    PRIVATE_ID = "PRIVATEVID1"
    STORYBOARD_PREFIX = "https://fake.invalid/storyboard/"
    SUBS_PREFIX = "https://fake.invalid/subs/"
    _SAFE_NAME = re.compile(r"[A-Za-z0-9_-]+")
    _REPEAT_RANGE = range(1, 51)
    _DEFAULT_BEHAVIOR = {"steps": 6, "stepMs": 120}
    _FAKE_SPEED_BPS = 2_000_000  # ความเร็วสมมติที่รายงานทุกขั้น
    CAPTURE_FIXTURE = Path("capture") / "piece.mp4"  # M5 รอบ B2: ชิ้นภาพของ fetch_frame_piece

    def __init__(self, fixtures_root: Path, *, behaviors: Path | None = None) -> None:
        self.root = Path(fixtures_root)
        self.calls: list[tuple[str, str]] = []
        self.behaviors_path = (
            Path(behaviors) if behaviors is not None else self.root / "downloads" / "behaviors.json"
        )
        self._behaviors: dict | None = None
        # จำนวนครั้งที่พลาดไปแล้วต่อคลิป นับตลอดอายุของตัวปลอมตัวนี้ (คิวรันหลายงานพร้อมกันได้ จึงมีล็อก)
        self._failures: dict[str, int] = {}
        self._lock = threading.Lock()

    def probe(self, video_id: str) -> dict:
        """คลิปที่อยู่ใน behaviors และมี probeAs: อ่าน fixture ของ probeAs แล้วเปลี่ยน id (และ title ถ้ามี)"""
        self.calls.append(("probe", video_id))
        _check_video_id(video_id)
        if video_id == self.PRIVATE_ID:
            raise YtError(
                "E_VIDEO_PRIVATE", f"ERROR: [youtube] {video_id}: Private video"
            )
        entry = self._behavior_doc()["videos"].get(video_id) or {}
        probe_as = entry.get("probeAs")
        info = self._load("probe", probe_as if probe_as else video_id)
        if info is None:
            raise YtError(
                "E_VIDEO_UNAVAILABLE",
                f"ERROR: [youtube] {video_id}: This video is unavailable",
            )
        if probe_as:
            info["id"] = video_id
            if entry.get("title"):
                info["title"] = entry["title"]
        return check_live(info)

    def download(
        self,
        video_id: str,
        choose: Callable[[dict], DownloadChoice],
        workdir: Path,
        hooks: DownloadHooks,
    ) -> DownloadResult:
        """C8 ตัวปลอม: probe -> choose -> เดินทีละขั้น (เช็คยกเลิกก่อนทุกขั้น) -> คัดลอกไฟล์สื่อจาก media/

        ขั้นครึ่งแรกเป็น downloading_video ครึ่งหลัง downloading_audio เมื่อรวมภาพกับเสียง (merge_mp4 และมี "+")
        ไม่งั้นมีขั้นเดียว (วิดีโอไม่มีเสียง = downloading_video, เสียง = downloading_audio)
        failAtStep/error/failTimes: พลาดที่ขั้นนั้นด้วยรหัสนั้น ไม่เกิน failTimes ครั้งต่อคลิป
        ไฟล์เขียนเป็น .part ก่อนแล้วจึงเปลี่ยนชื่อ พลาดหรือยกเลิก = ลบ media.* ที่ค้างใน workdir
        """
        self.calls.append(("download", video_id))
        info = self.probe(video_id)
        choice = choose(info)
        conf = self._behavior(video_id)
        steps = max(1, int(conf["steps"]))
        delay = max(0, conf["stepMs"]) / 1000
        two_tracks = choice.merge_mp4 and "+" in choice.format_spec
        if choice.merge_mp4:
            source, target = ("video.mp4" if two_tracks else "video-noaudio.mp4"), "media.mp4"
        else:
            source, target = "audio.m4a", "media.m4a"
        workdir.mkdir(parents=True, exist_ok=True)
        stage = ""
        try:
            for step in range(steps):
                if hooks.is_cancelled():
                    raise JobCancelled()
                self._maybe_fail(video_id, conf, step)
                audio = not choice.merge_mp4 or (two_tracks and step >= steps / 2)
                current = "downloading_audio" if audio else "downloading_video"
                if current != stage:
                    stage = current
                    hooks.on_stage(current)
                if delay:
                    time.sleep(delay)
                eta = math.ceil((steps - step - 1) * delay)
                hooks.on_progress((step + 1) / steps, self._FAKE_SPEED_BPS, eta)
            if hooks.is_cancelled():
                raise JobCancelled()
            if choice.merge_mp4:
                hooks.on_stage("merging")
            part = workdir / f"{target}.part"
            shutil.copyfile(self.root / "media" / source, part)
            os.replace(part, workdir / target)
        except Exception:
            _clear_media(workdir)
            raise
        return DownloadResult(path=workdir / target, info=info, choice=choice, media=self._media_of(conf))

    def fetch_frame_piece(self, video_id: str, t_ms: int, max_short_side: int | None, dest: Path) -> PieceInfo:
        """C6 ตัวปลอม (M5 รอบ B2): probe เหมือนตัวจริง (คลิปส่วนตัว/ไม่มี/ไลฟ์ได้ error เดียวกัน) แล้วตัดชิ้นจาก
        <fixtures_root>/capture/piece.mp4 ด้วยตัวอ่าน sidx ตัวจริง ไม่ต่อเน็ต ไม่สนเพดานความละเอียด (1920x1080 เสมอ)
        fixture ยาว 4 วินาที: เวลาของคลิปวนด้วย t_ms % ความยาว แล้วเลื่อนเวลาเริ่มท่อนกลับเป็นเวลาของคลิป
        "captureError" ของคลิปใน behaviors.json = โยน YtError รหัสนั้น (ไม่เขียนไฟล์)
        """
        self.calls.append(("fetch_frame_piece", video_id))
        self.probe(video_id)
        error = self._behavior(video_id).get("captureError")
        if error:
            raise YtError(str(error), f"fake: capture of {video_id} set to fail")
        data = (self.root / self.CAPTURE_FIXTURE).read_bytes()

        def read_range(first: int, last: int) -> bytes:
            return data[first : last + 1]

        index = read_index(read_range)
        local = t_ms % index.sidx.end_ms
        piece, ref = fetch_piece(read_range, index, local)
        write_piece(dest, piece)
        info = piece_info(_FAKE_CAPTURE_FORMAT, dest, index.sidx, ref)
        return replace(info, segment_start_ms=t_ms - (local - info.segment_start_ms))

    @staticmethod
    def _media_of(conf: dict) -> MediaFacts | None:
        """"media" ของคลิปใน behaviors.json (M5 รอบ B ภาพคมอัตโนมัติ) ไม่มี = ไม่รู้ (ภาพคมอัตโนมัติจะข้าม)"""
        media = conf.get("media")
        return media_facts(media) if isinstance(media, dict) else None

    def _behavior_doc(self) -> dict:
        """behaviors.json (อ่านครั้งเดียว) ไม่มีไฟล์ = ไม่มีคลิปพิเศษ ใช้ค่าตั้งต้น"""
        with self._lock:
            if self._behaviors is None:
                doc: dict = {}
                if self.behaviors_path.is_file():
                    doc = json.loads(self.behaviors_path.read_text(encoding="utf-8"))
                self._behaviors = {
                    "default": dict(doc.get("default") or {}),
                    "videos": dict(doc.get("videos") or {}),
                }
            return self._behaviors

    def _behavior(self, video_id: str) -> dict:
        doc = self._behavior_doc()
        return {**self._DEFAULT_BEHAVIOR, **doc["default"], **(doc["videos"].get(video_id) or {})}

    def _maybe_fail(self, video_id: str, conf: dict, step: int) -> None:
        error = conf.get("error")
        if not error or conf.get("failAtStep") != step:
            return
        with self._lock:
            count = self._failures.get(video_id, 0)
            if count >= int(conf.get("failTimes", 1)):
                return
            self._failures[video_id] = count + 1
        raise YtError(str(error), f"fake: {video_id} ตั้งให้พลาดที่ขั้น {step} (ครั้งที่ {count + 1})")

    def playlist(self, playlist_id: str, limit: int, video_id: str | None = None) -> dict:
        self.calls.append(("playlist", playlist_id))
        _playlist_url(playlist_id, video_id)  # กฎ id และกฎคลิปตั้งต้นของมิกซ์ เหมือนตัวจริง
        info = self._load("playlist", playlist_id)
        if info is None:
            raise YtError(
                "E_VIDEO_UNAVAILABLE",
                f"ERROR: [youtube:tab] {playlist_id}: YouTube said: The playlist does not exist.",
            )
        info["entries"] = list(info.get("entries") or [])[: limit + 1]
        return info

    def fetch(self, url: str) -> bytes:
        self.calls.append(("fetch", url))
        base = (self.root / "storyboard").resolve()
        if url.startswith(self.STORYBOARD_PREFIX):
            parts = url[len(self.STORYBOARD_PREFIX) :].split("/")
            if all(self._SAFE_NAME.fullmatch(p.removesuffix(".jpg")) for p in parts):
                path = base.joinpath(*parts)
                if path.is_file() and path.resolve().is_relative_to(base):
                    return path.read_bytes()
        raise YtError("E_NETWORK", f"fake: ไม่มีไฟล์สำหรับ {url}")

    def fetch_subtitle(self, url: str) -> bytes:
        """https://fake.invalid/subs/<videoId>/<ชื่อ>.<นามสกุล>[?tlang=X][&repeat=n] -> subs/<videoId>/...

        tlang=X อ่านไฟล์ tlang-X.<นามสกุล> แทน, repeat=n (1..50 เฉพาะ json3) ต่อเหตุการณ์ซ้ำ n รอบ
        ใช้ทดสอบคลิปยาวโดยไม่ต้องเก็บไฟล์ใหญ่ ทุกชิ้นส่วนของพาธต้องเป็นชื่อปลอดภัย และไฟล์ต้องอยู่ใต้ subs/
        """
        self.calls.append(("fetch_subtitle", url))
        missing = YtError("E_NETWORK", f"fake: ไม่มีไฟล์สำหรับ {url}")
        if not url.startswith(self.SUBS_PREFIX):
            raise missing
        rest, _, query_text = url[len(self.SUBS_PREFIX) :].partition("?")
        parts = rest.split("/")
        if len(parts) != 2:
            raise missing
        video_id, filename = parts
        stem, dot, ext = filename.rpartition(".")
        if not (dot and all(self._SAFE_NAME.fullmatch(p) for p in (video_id, stem, ext))):
            raise missing
        query = parse_qs(query_text, keep_blank_values=True)
        tlang = query.get("tlang", [None])[0]
        if tlang is not None:
            if not self._SAFE_NAME.fullmatch(tlang):
                raise missing
            stem = f"tlang-{tlang}"
        repeat = self._parse_repeat(query.get("repeat", [None])[0], ext, missing)
        base = (self.root / "subs").resolve()
        path = (base / video_id / f"{stem}.{ext}").resolve()
        if not (path.is_relative_to(base) and path.is_file()):
            raise missing
        data = path.read_bytes()
        return data if repeat is None else self._tile_json3(data, repeat, missing)

    def pinned_comment(self, video_id: str) -> dict | None:
        """comments/<id>.json รูปแบบ {"comment": {...} | null} (ไม่มีไฟล์ = None)

        ไฟล์แบบ {"error": "<รหัส>"} = โยน YtError รหัสนั้น (ใช้เทสหน้าจอ error)
        """
        self.calls.append(("pinned_comment", video_id))
        _check_video_id(video_id)
        path = self.root / "comments" / f"{video_id}.json"
        if not path.is_file():
            return None
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("error"):
            raise YtError(str(doc["error"]), f"fake: คอมเมนต์ของ {video_id} ตั้งให้พลาด")
        comment = doc.get("comment")
        return dict(comment) if isinstance(comment, dict) else None

    def sponsor_segments(
        self, video_id: str, categories: Sequence[str], duration_s: float | None
    ) -> list[SponsorSegment]:
        """sponsorblock/<id>.json: {"segments": [[startMs, endMs, หมวด], ...]} | {"error": ...} ไม่มีไฟล์ = []"""
        self.calls.append(("sponsor_segments", video_id))
        _check_video_id(video_id)
        path = self.root / "sponsorblock" / f"{video_id}.json"
        if not path.is_file():
            return []
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("error"):
            raise SponsorBlockError(f"fake: {doc['error']}")
        wanted = set(categories)
        return sorted((int(s), int(e), str(c)) for s, e, c in doc.get("segments") or [] if c in wanted)

    def _parse_repeat(self, raw: str | None, ext: str, error: YtError) -> int | None:
        if raw is None:
            return None
        if ext != "json3" or not raw.isascii() or not raw.isdigit() or int(raw) not in self._REPEAT_RANGE:
            raise error
        return int(raw)

    @staticmethod
    def _tile_json3(data: bytes, times: int, error: YtError) -> bytes:
        """ต่อเหตุการณ์ n ชุด ชุดที่ k เลื่อน tStartMs ไป k*span (span = เวลาจบสุดท้าย ปัดขึ้นเป็นวินาทีเต็ม)"""
        try:
            doc = json.loads(data)
            events = list(doc["events"])
        except (ValueError, KeyError, TypeError) as exc:
            raise error from exc
        end = max((e.get("tStartMs", 0) + e.get("dDurationMs", 0) for e in events), default=0)
        span = -(-end // 1000) * 1000
        tiled = []
        for k in range(times):
            for event in events:
                copy = json.loads(json.dumps(event))
                if "tStartMs" in copy:
                    copy["tStartMs"] += k * span
                tiled.append(copy)
        doc["events"] = tiled
        return json.dumps(doc, ensure_ascii=False).encode("utf-8")

    def _load(self, kind: str, ident: str) -> dict | None:
        """อ่าน fixture ใหม่ทุกครั้ง ผู้เรียกจึงแก้ dict ที่ได้ไปได้โดยไม่กระทบครั้งถัดไป"""
        folder = self.root / kind
        direct = folder / f"{ident}.json"
        if direct.is_file():
            return json.loads(direct.read_text(encoding="utf-8"))
        for path in sorted(folder.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("id") == ident:
                return data
        return None
