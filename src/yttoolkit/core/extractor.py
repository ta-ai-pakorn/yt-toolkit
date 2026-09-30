"""ตัวกลางคุยกับยูทูป: โมดูลเดียวในแอพที่ import yt_dlp (ที่อื่นเรียกผ่านที่นี่เท่านั้น)

- YtDlpExtractor: ใช้ yt-dlp จริง (ต้องต่อเน็ต)
- FakeExtractor: อ่านข้อมูลจริงที่ตัดเก็บไว้ใน tests/fixtures/ ใช้กับเทสและโหมด YT_TOOLKIT_FAKE=1

ทั้งสองแบบโยน YtError (รหัสตาม PRD ข้อ 7) แทน error ดิบของ yt-dlp/httpx
"""

from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Protocol, runtime_checkable

import httpx

from .inputs import PLAYLIST_ID, VIDEO_ID, is_mix_id
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

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport
        self._client: httpx.Client | None = None
        self._client_lock = threading.Lock()

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
        info = self._extract(f"https://www.youtube.com/watch?v={video_id}", _PROBE_OPTS)
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

    @staticmethod
    def _extract(url: str, opts: dict) -> dict:
        """เรียก yt-dlp แล้วแปลงทุกความผิดพลาดเป็น YtError (ห้ามมี exception ดิบหลุดออกไป)"""
        import yt_dlp
        from yt_dlp.utils import YoutubeDLError

        try:
            with yt_dlp.YoutubeDL({**opts, "logger": _YtDlpLogger()}) as ydl:
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
    _SAFE_NAME = re.compile(r"[A-Za-z0-9_-]+")

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
