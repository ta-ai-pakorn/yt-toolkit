"""คอมเมนต์ปักหมุดของเจ้าของช่อง (C-A2, owner round 2): ดึงเมื่อผู้ใช้กดเปิดดูเท่านั้น ไม่ดึงตอน probe

ลำดับ:
1. ข้อมูลคลิป (VideoService.get) บอกว่าคอมเมนต์ = 0 -> None ทันที ไม่ต่อเน็ต
2. cache ในเครื่อง `<cache_root>/<videoId>/pinned.json` อายุไม่เกิน 24 ชม. (ทั้งมีคอมเมนต์และไม่มี)
3. ยูทูปขอยืนยันว่าไม่ใช่บอท (E_BOT_CHECK) เมื่อไม่ถึง 5 นาทีก่อน -> โยนซ้ำ (เก็บในหน่วยความจำ) ไม่ยิงยูทูปถี่ ๆ
   error ที่ลองใหม่แล้วช่วยได้ (E_NETWORK, E_UNKNOWN ฯลฯ) ไม่จำ ปุ่ม "ลองใหม่" จึงดึงใหม่จริง (review I-1)
4. ดึงใหม่ผ่าน Extractor.pinned_comment แล้วเก็บลง cache

ส่งออกได้แค่ text / likes / publishedText เท่านั้น ไม่มีชื่อหรือ id ของผู้เขียน (PDPA)
ไม่ import yt_dlp เอง และไม่ import api/platform
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .subtitles import _atomic_write
from .videos import CLOCK_SKEW, utcnow
from .yterrors import YtError

if TYPE_CHECKING:
    from .videos import VideoService

log = logging.getLogger("yttoolkit")

CACHE_TTL = timedelta(hours=24)
ERROR_TTL = timedelta(minutes=5)
# จำเฉพาะ error ที่หน้าเว็บไม่มีปุ่มลองใหม่ (ตรงกับ FINAL_CODES ฝั่งเว็บ) ยิงซ้ำมีแต่ทำให้ถูกบล็อกนานขึ้น
CACHED_ERRORS = frozenset({"E_BOT_CHECK"})
CACHE_FILE = "pinned.json"
CACHE_VERSION = 1
_MISS = object()


def clean_comment(value: Any) -> dict | None:
    """เหลือเฉพาะฟิลด์ที่ส่งออกได้: text (ต้องมีข้อความ), likes (จำนวนเต็ม >= 0), publishedText"""
    if not isinstance(value, dict):
        return None
    text = value.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    out: dict[str, Any] = {"text": text}
    likes = value.get("likes")
    if isinstance(likes, int) and not isinstance(likes, bool) and likes >= 0:
        out["likes"] = likes
    published = value.get("publishedText")
    if isinstance(published, str) and published.strip():
        out["publishedText"] = published.strip()
    return out


class PinnedCommentService:
    def __init__(
        self,
        videos: VideoService,
        fetch_pinned: Callable[[str], dict | None],
        cache_root: Path,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        self._videos = videos
        self._fetch = fetch_pinned
        self._cache_root = Path(cache_root)
        self._now = now
        self._guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}
        self._errors: dict[str, tuple[datetime, YtError]] = {}

    def _lock(self, video_id: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(video_id, threading.Lock())

    def get(self, video_id: str) -> dict | None:
        """{"text", "likes"?, "publishedText"?} หรือ None (ไม่มีคอมเมนต์ปักหมุดจากเจ้าของช่อง)

        error ของข้อมูลคลิป (คลิปไม่มี, ส่วนตัว ฯลฯ) และของการดึง (E_BOT_CHECK, E_NETWORK ฯลฯ) โยนต่อ
        """
        info = self._videos.get(video_id)  # ตรวจ id และว่าคลิปมีจริงด้วย
        stats = info.get("stats") or {}
        if stats.get("comments") == 0:
            return None
        with self._lock(video_id):
            moment = self._now().astimezone(UTC)
            cached = self._read(video_id, moment)
            if cached is not _MISS:
                return cached
            failed = self._recent_error(video_id, moment)
            if failed is not None:
                raise YtError(failed.code, failed.detail)
            try:
                comment = clean_comment(self._fetch(video_id))
            except YtError as exc:
                if exc.code in CACHED_ERRORS:
                    with self._guard:
                        self._errors[video_id] = (moment, exc)
                raise
            with self._guard:
                self._errors.pop(video_id, None)
            self._write(video_id, moment, comment)
            return comment

    def _recent_error(self, video_id: str, moment: datetime) -> YtError | None:
        """error ที่จำไว้ของคลิปนี้ (ยังไม่ถึง 5 นาที) และล้าง error ที่หมดอายุของทุกคลิปทิ้ง (M-7)"""
        with self._guard:
            for key, (when, _) in list(self._errors.items()):
                if not timedelta(0) <= moment - when < ERROR_TTL:
                    del self._errors[key]
            failed = self._errors.get(video_id)
        return failed[1] if failed is not None else None

    # ---------- cache ----------

    def _path(self, video_id: str) -> Path:
        return self._cache_root / video_id / CACHE_FILE

    def _read(self, video_id: str, moment: datetime) -> Any:
        """ค่าใน cache (dict หรือ None) หรือ _MISS ถ้าไม่มี/เสีย/หมดอายุ/เป็นของคลิปอื่น (NTFS ไม่สนตัวพิมพ์)"""
        try:
            doc = json.loads(self._path(video_id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return _MISS
        if not isinstance(doc, dict) or doc.get("v") != CACHE_VERSION or doc.get("videoId") != video_id:
            return _MISS
        try:
            fetched = datetime.fromisoformat(doc["fetchedAt"])
        except (KeyError, TypeError, ValueError):
            return _MISS
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=UTC)
        if not -CLOCK_SKEW <= moment - fetched < CACHE_TTL:
            return _MISS
        raw = doc.get("comment")
        if raw is None:
            return None
        comment = clean_comment(raw)
        return _MISS if comment is None else comment

    def _write(self, video_id: str, moment: datetime, comment: dict | None) -> None:
        doc = {
            "v": CACHE_VERSION,
            "videoId": video_id,
            "fetchedAt": moment.isoformat(timespec="seconds"),
            "comment": comment,
        }
        target = self._path(video_id)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(target, json.dumps(doc, ensure_ascii=False).encode("utf-8"))
        except OSError:
            log.warning("เก็บคอมเมนต์ปักหมุดของ %s ลง cache ไม่สำเร็จ (ครั้งหน้าจะดึงใหม่)", video_id, exc_info=True)
