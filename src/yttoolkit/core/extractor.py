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
import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from urllib.parse import parse_qs

import httpx

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
        """คอมเมนต์ปักหมุดที่เจ้าของช่องเขียนเอง (C-A2): {"text", "likes"?, "publishedText"?} หรือ None

        None = ไม่มีคอมเมนต์ปักหมุด, ปักหมุดคอมเมนต์ของผู้ชม หรือปิดคอมเมนต์ ไม่คืนชื่อ/id ของผู้เขียน (PDPA)
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
    """คอมเมนต์หนึ่งอันของ yt-dlp -> {"text", "likes"?, "publishedText"?} หรือ None

    นับเฉพาะคอมเมนต์ที่ปักหมุด (is_pinned) และเจ้าของช่องเขียนเอง (author_is_uploader) เท่านั้น
    ไม่เก็บชื่อ, id, ลิงก์ หรือรูปของผู้เขียน (PDPA: ไม่ส่งข้อมูลของคนอื่นออกไป)
    """
    if not isinstance(comment, dict):
        return None
    if comment.get("is_pinned") is not True or comment.get("author_is_uploader") is not True:
        return None
    text = comment.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    out: dict = {"text": text}
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
_NO_FALLBACK = frozenset({"E_NETWORK", "E_BOT_CHECK"})


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

        params = {**opts, "logger": _YtDlpLogger()}
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
        """คอมเมนต์ปักหมุดของเจ้าของช่อง (C-A2) ดึงเมื่อผู้ใช้เปิดดูเท่านั้น ไม่ดึงตอน probe

        ทางหลัก (ถูกสุด ~2 คำขอ innertube "next"): เรียกตัวดึงคอมเมนต์ของ yt-dlp ตรง ๆ
        ด้วย comment_sort=top และ max_comments=1 (คอมเมนต์ปักหมุดอยู่อันดับแรกเสมอ)
        เป็น API ภายในของ yt-dlp ที่อาจเปลี่ยนได้ทุกรุ่น ทางหลักพังด้วยเหตุอื่นที่ไม่ใช่เน็ตหรือยูทูปบล็อก
        (exception ใดก็ได้ที่ไม่ใช่ YoutubeDLError หรือ YoutubeDLError ที่ไม่ใช่ E_NETWORK/E_BOT_CHECK)
        ถอยไปใช้ getcomments ของ probe ปกติ (API สาธารณะ แพงกว่า: probe ทั้งคลิปอีกรอบ) จำกัดจำนวนเท่ากัน
        เน็ตหลุดหรือยูทูปบล็อกโยนต่อทันที (ลองทางสำรองก็เจอแบบเดียวกัน แถมยิงยูทูปเพิ่ม)
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
    """อ่านจาก fixtures_root: probe/<id>.json, playlist/<id>.json, storyboard/<ชื่อไฟล์>

    ใช้กฎ id เดียวกับ YtDlpExtractor (ผิดรูปแบบ = E_INVALID_INPUT)
    หาไฟล์จากชื่อไฟล์ก่อน ถ้าไม่เจอจึงหาไฟล์ที่ฟิลด์ "id" ตรงกัน (เช่น live_upcoming.json มี id UPCOMINGLV1)
    calls บันทึกทุกการเรียกเป็น (ชื่อเมธอด, อาร์กิวเมนต์) ให้เทสนับได้
    """

    PRIVATE_ID = "PRIVATEVID1"
    STORYBOARD_PREFIX = "https://fake.invalid/storyboard/"
    SUBS_PREFIX = "https://fake.invalid/subs/"
    _SAFE_NAME = re.compile(r"[A-Za-z0-9_-]+")
    _REPEAT_RANGE = range(1, 51)

    def __init__(self, fixtures_root: Path) -> None:
        self.root = Path(fixtures_root)
        self.calls: list[tuple[str, str]] = []

    def probe(self, video_id: str) -> dict:
        self.calls.append(("probe", video_id))
        _check_video_id(video_id)
        if video_id == self.PRIVATE_ID:
            raise YtError(
                "E_VIDEO_PRIVATE", f"ERROR: [youtube] {video_id}: Private video"
            )
        info = self._load("probe", video_id)
        if info is None:
            raise YtError(
                "E_VIDEO_UNAVAILABLE",
                f"ERROR: [youtube] {video_id}: This video is unavailable",
            )
        return check_live(info)

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
