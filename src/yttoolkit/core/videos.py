"""ข้อมูลคลิป: แปลงผล probe ดิบเป็น VideoInfo (PRD 6.2.1), cache 24 ชม. ใน SQLite,
ประวัติคลิปล่าสุด และรายการคลิปในเพลย์ลิสต์

ไม่ import yt_dlp เอง (เรียกผ่าน Extractor) และไม่ import api/platform (PRD 6.6)
"""

from __future__ import annotations

import json
import logging
import re
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from .db import PEEK_SENTINEL, Database
from .extractor import Extractor
from .inputs import PLAYLIST_ID, VIDEO_ID, is_mix
from .yterrors import YtError

log = logging.getLogger("yttoolkit")

CACHE_TTL = timedelta(hours=24)
# probe ใหม่พลาดด้วยรหัสเหล่านี้ (ไม่มีเน็ต / ยูทูปให้รอก่อน) แต่มีข้อมูลเดิมในเครื่อง = ใช้ข้อมูลเดิมไปก่อน
STALE_OK_CODES = frozenset({"E_NETWORK", "E_BOT_CHECK"})
# นาฬิกาเครื่องเลื่อนถอยได้ไม่เกินนี้ยังถือว่า probe ล่าสุดยังใหม่
CLOCK_SKEW = timedelta(minutes=5)
PLAYLIST_LIMIT = 200
# มิกซ์อัตโนมัติของยูทูปยาวได้ไม่รู้จบ เอาแค่ช่วงต้น (เจ้าของตัดสิน 2026-09-30)
MIX_LIMIT = 25

_DRC_NOTE = re.compile(r"\bdrc\b", re.IGNORECASE)
_STORYBOARD = "storyboard"

# ฟิลด์ของ format ที่เก็บลง probe_json (ไม่เก็บ URL ตรงของ googlevideo)
_MEDIA_FIELDS = (
    "format_id",
    "format_note",
    "height",
    "fps",
    "vcodec",
    "acodec",
    "filesize",
    "filesize_approx",
    "language",
    "language_preference",
    "abr",
)
_STORYBOARD_FIELDS = (
    "format_id",
    "format_note",
    "width",
    "height",
    "rows",
    "columns",
    "fps",
)


def utcnow() -> datetime:
    return datetime.now(UTC)


# ---------- แปลงข้อมูลดิบ ----------


def _is_storyboard(fmt: dict) -> bool:
    return fmt.get("format_note") == _STORYBOARD


def _thumbnail(raw: dict) -> str:
    if raw.get("thumbnail"):
        return str(raw["thumbnail"])
    for item in reversed(raw.get("thumbnails") or []):
        if isinstance(item, dict) and item.get("url"):
            return str(item["url"])
    video_id = raw.get("id") or ""
    return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id else ""


def _seconds(value: Any) -> int:
    return round(value) if isinstance(value, int | float) else 0


def _number(value: Any) -> int | float:
    """fps/เวลา: 30.0 -> 30 ให้อ่านง่ายและเทียบเท่ากันได้"""
    if not isinstance(value, int | float) or isinstance(value, bool):
        return 0
    return int(value) if float(value).is_integer() else value


def _published_at(raw: dict) -> str | None:
    upload_date = str(raw.get("upload_date") or "")
    if re.fullmatch(r"\d{8}", upload_date):
        return f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
    timestamp = raw.get("timestamp")
    if isinstance(timestamp, int | float):
        try:
            return datetime.fromtimestamp(timestamp, UTC).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    return None


def _chapters(raw: dict) -> list[dict]:
    items = [c for c in (raw.get("chapters") or []) if isinstance(c, dict)]
    duration = raw.get("duration")
    result = []
    for index, chapter in enumerate(items):
        start = _number(chapter.get("start_time"))
        end = chapter.get("end_time")
        if end is None:
            following = (
                items[index + 1].get("start_time") if index + 1 < len(items) else None
            )
            end = following if following is not None else duration
        result.append(
            {
                "startS": start,
                "endS": _number(end) if end is not None else start,
                "title": chapter.get("title") or "",
            }
        )
    return result


def _codec_family(vcodec: str) -> str:
    family = vcodec.split(".")[0].lower()
    return "vp9" if family == "vp09" else family


def _size(fmt: dict) -> int | None:
    for key in ("filesize", "filesize_approx"):
        value = fmt.get(key)
        if isinstance(value, int | float) and not isinstance(value, bool):
            return round(value)
    return None


def _video_formats(formats: list[dict]) -> list[dict]:
    best: dict[tuple, dict] = {}
    for fmt in formats:
        vcodec = fmt.get("vcodec")
        height = fmt.get("height")
        if (
            _is_storyboard(fmt)
            or not vcodec
            or vcodec == "none"
            or fmt.get("acodec") not in (None, "none")
        ):
            continue
        if not isinstance(height, int | float) or not fmt.get("format_id"):
            continue
        entry: dict[str, Any] = {
            "formatId": str(fmt["format_id"]),
            "height": round(height),
            "fps": _number(fmt.get("fps")),
            "vcodec": str(vcodec),
            "compat": str(vcodec).startswith("avc1"),
        }
        size = _size(fmt)
        if size is not None:
            entry["sizeBytes"] = size
        key = (entry["height"], entry["fps"], _codec_family(entry["vcodec"]))
        held = best.get(key)
        if held is None or (entry.get("sizeBytes") or -1) > (
            held.get("sizeBytes") or -1
        ):
            best[key] = entry
    return sorted(
        best.values(),
        key=lambda e: (
            -e["height"],
            -e["fps"],
            -(e.get("sizeBytes") or 0),
            e["formatId"],
        ),
    )


def _audio_candidates(formats: list[dict]) -> list[dict]:
    result = []
    for fmt in formats:
        if (
            _is_storyboard(fmt)
            or fmt.get("vcodec") != "none"
            or fmt.get("acodec") in (None, "none", "")
        ):
            continue  # ไม่มี acodec = เล่นไม่ได้/ข้อมูลไม่ครบ ห้ามมาเป็นเสียงต้นฉบับ
        if not fmt.get("format_id"):
            continue
        if str(fmt["format_id"]).endswith("-drc") or _DRC_NOTE.search(
            str(fmt.get("format_note") or "")
        ):
            continue
        result.append(fmt)
    return result


def _preference(fmt: dict) -> int | float | None:
    value = fmt.get("language_preference")
    return (
        value
        if isinstance(value, int | float) and not isinstance(value, bool)
        else None
    )


def _audio_formats(formats: list[dict]) -> list[dict]:
    candidates = _audio_candidates(formats)
    by_note = [
        "original" in (note := str(f.get("format_note") or "").lower())
        or "default" in note
        for f in candidates
    ]
    if not any(by_note):
        preferences = {p for f in candidates if (p := _preference(f)) is not None}
        if len(preferences) > 1:
            top = max(preferences)
            by_note = [_preference(f) == top for f in candidates]
    result = []
    for fmt, original in zip(candidates, by_note, strict=True):
        entry: dict[str, Any] = {"formatId": str(fmt["format_id"])}
        if fmt.get("language"):
            entry["language"] = str(fmt["language"])
        entry["isOriginal"] = original
        entry["acodec"] = str(fmt["acodec"])
        abr = fmt.get("abr")
        if isinstance(abr, int | float) and not isinstance(abr, bool) and abr > 0:
            entry["abrKbps"] = round(abr)
        result.append(entry)
    return result


def to_video_info(raw: dict) -> dict:
    """ข้อมูลดิบ (หรือแบบที่ตัดแล้วจาก trim_probe) -> VideoInfo ตาม PRD 6.2.1 (คีย์ camelCase)"""
    formats = [f for f in (raw.get("formats") or []) if isinstance(f, dict)]
    info: dict[str, Any] = {
        "videoId": raw.get("id") or "",
        "title": raw.get("title") or "",
        "channel": raw.get("channel") or raw.get("uploader") or "",
        "durationS": _seconds(raw.get("duration")),
    }
    published = _published_at(raw)
    if published:
        info["publishedAt"] = published
    info["thumbnailUrl"] = _thumbnail(raw)
    info["chapters"] = _chapters(raw)
    info["video"] = _video_formats(formats)
    info["audio"] = _audio_formats(formats)
    info["hasStoryboard"] = any(_is_storyboard(f) for f in formats)
    info["isLive"] = raw.get("live_status") == "is_live"
    return info


def trim_probe(raw: dict) -> dict:
    """ตัดข้อมูลดิบให้เหลือที่งานถัดไปต้องใช้: ฟิลด์ของ VideoInfo, format วิดีโอ/เสียงล้วน
    และ storyboard (พร้อม fragments/rows/columns/fps/width/height) ไม่เก็บ URL ตรงของสื่อ"""
    formats: list[dict] = []
    for fmt in raw.get("formats") or []:
        if not isinstance(fmt, dict):
            continue
        if _is_storyboard(fmt):
            kept = {k: fmt[k] for k in _STORYBOARD_FIELDS if fmt.get(k) is not None}
            kept["fragments"] = [
                {"url": frag["url"], "duration": frag.get("duration")}
                for frag in (fmt.get("fragments") or [])
                if isinstance(frag, dict) and frag.get("url")
            ]
            formats.append(kept)
        elif fmt.get("vcodec") == "none" or fmt.get("acodec") in (None, "none"):
            formats.append({k: fmt[k] for k in _MEDIA_FIELDS if fmt.get(k) is not None})
    trimmed: dict[str, Any] = {
        key: raw[key]
        for key in (
            "id",
            "title",
            "channel",
            "uploader",
            "duration",
            "upload_date",
            "timestamp",
            "live_status",
        )
        if raw.get(key) is not None
    }
    trimmed["thumbnail"] = _thumbnail(raw)
    trimmed["chapters"] = [
        {k: c[k] for k in ("start_time", "end_time", "title") if c.get(k) is not None}
        for c in (raw.get("chapters") or [])
        if isinstance(c, dict)
    ]
    trimmed["formats"] = formats
    return trimmed


# ---------- บริการ ----------


def _like_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _playlist_thumbnail(entry: dict, video_id: str) -> str:
    for item in reversed(entry.get("thumbnails") or []):
        if isinstance(item, dict) and item.get("url"):
            return str(item["url"])
    return str(
        entry.get("thumbnail") or f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"
    )


class VideoService:
    def __init__(
        self,
        db: Database,
        extractor: Extractor,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        self._db = db
        self._extractor = extractor
        self._now = now
        self._guard = threading.Lock()
        self._id_locks: dict[str, threading.Lock] = {}

    def _id_lock(self, video_id: str) -> threading.Lock:
        with self._guard:
            return self._id_locks.setdefault(video_id, threading.Lock())

    def _stamp(self) -> tuple[datetime, str]:
        moment = self._now().astimezone(UTC)
        return moment, moment.isoformat(timespec="microseconds")

    @staticmethod
    def _check_video_id(video_id: str) -> None:
        if not VIDEO_ID.fullmatch(video_id):
            raise YtError("E_INVALID_INPUT", f"video id ไม่ถูกรูปแบบ: {video_id!r}")

    def get(self, video_id: str, refresh: bool = False, peek: bool = False) -> dict:
        """คืน VideoInfo ของคลิป (probe ใหม่ถ้าไม่มี cache, cache เก่ากว่า 24 ชม. หรือ refresh)

        peek=True = ขอดูข้อมูล (เช่น ชื่อคลิปในรายการผล W1) โดยไม่นับว่าเปิดคลิป: ไม่แตะ opened_at
        ของแถวที่มีอยู่ และแถวใหม่ได้ PEEK_SENTINEL จึงไม่ขึ้นใน "ล่าสุด" จนกว่าจะมี get ปกติ

        เรียกซ้อนกันด้วย id เดียวกัน (เช่น กดเปิดคลิปเดิมสองแท็บ) จะ probe ครั้งเดียว:
        คนที่มาทีหลังรอคิว แล้วอ่าน cache ที่คนแรกเพิ่งเขียนแทนการ probe ซ้ำ

        cache หมดอายุแล้ว probe ใหม่พลาดด้วย E_NETWORK/E_BOT_CHECK แต่มีข้อมูลเดิม = คืนข้อมูลเดิม
        (บันทึก warning ไม่แตะ probed_at) ยกเว้น refresh=True ที่โยน error ต่อเสมอ
        """
        self._check_video_id(video_id)
        if not refresh:
            info = self._cached_hit(video_id, peek)
            if info is not None:
                return info
        lock = self._id_lock(video_id)
        contended = not lock.acquire(blocking=False)
        if contended:
            lock.acquire()
        try:
            if contended or not refresh:
                # มีคนกำลัง probe ให้อยู่ (หรือเพิ่งเสร็จ) ใช้ผลของเขา แม้จะเป็นการ refresh
                info = self._cached_hit(video_id, peek)
                if info is not None:
                    return info
            try:
                return self._probe_and_store(video_id, peek)
            except YtError as exc:
                # cache หมดอายุแต่ไม่มีเน็ต: คืนข้อมูลเดิม (หน้า W2, contact sheet, zip ใช้ต่อได้)
                # ไม่แตะ probed_at รอบหน้าจึง probe ใหม่เมื่อเน็ตกลับมา
                # refresh=True = ผู้เรียกรู้ว่าของเดิมใช้ไม่ได้แล้ว (ลิงก์ storyboard หมดอายุ) จึงโยนต่อ
                if refresh or exc.code not in STALE_OK_CODES:
                    raise
                info = self._stored_hit(video_id, peek)
                if info is None:
                    raise
                log.warning(
                    "probe คลิป %s ใหม่ไม่สำเร็จ (%s) ใช้ข้อมูลเดิมที่เก่ากว่า 24 ชม. ไปก่อน: %s",
                    video_id,
                    exc.code,
                    exc.detail,
                )
                return info
        finally:
            lock.release()

    def _cached_hit(self, video_id: str, peek: bool = False) -> dict | None:
        moment, stamp = self._stamp()
        info = self._cached_info(video_id, moment)
        if info is not None and not peek:
            self._db.execute(
                "UPDATE videos SET opened_at = ? WHERE video_id = ?", (stamp, video_id)
            )
        return info

    def _stored_hit(self, video_id: str, peek: bool = False) -> dict | None:
        """ข้อมูลที่เก็บไว้โดยไม่ดูอายุ (แถวเสีย/ไม่มี = None) นับว่าเปิดคลิปเหมือน _cached_hit"""
        _, stamp = self._stamp()
        rows = self._db.execute(
            "SELECT probe_json FROM videos WHERE video_id = ?", (video_id,)
        )
        try:
            info = to_video_info(json.loads(rows[0]["probe_json"])) if rows else None
        except (ValueError, TypeError, AttributeError, KeyError):
            info = None
        if info is not None and not peek:
            self._db.execute(
                "UPDATE videos SET opened_at = ? WHERE video_id = ?", (stamp, video_id)
            )
        return info

    def _probe_and_store(self, video_id: str, peek: bool = False) -> dict:
        trimmed = trim_probe(self._extractor.probe(video_id))
        info = to_video_info(trimmed)
        _, stamp = self._stamp()
        chapters = [
            {"start_s": c["startS"], "end_s": c["endS"], "title": c["title"]}
            for c in info["chapters"]
        ]
        self._db.execute(
            "INSERT INTO videos (video_id, title, channel, duration_s, thumbnail_url, chapters_json,"
            " probe_json, probed_at, opened_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(video_id) DO UPDATE SET title = excluded.title, channel = excluded.channel,"
            " duration_s = excluded.duration_s, thumbnail_url = excluded.thumbnail_url,"
            " chapters_json = excluded.chapters_json, probe_json = excluded.probe_json,"
            " probed_at = excluded.probed_at, opened_at = CASE WHEN excluded.opened_at = ?"
            " THEN videos.opened_at ELSE excluded.opened_at END",
            (
                video_id,
                info["title"],
                info["channel"],
                info["durationS"],
                info["thumbnailUrl"],
                json.dumps(chapters, ensure_ascii=False),
                json.dumps(trimmed, ensure_ascii=False, separators=(",", ":")),
                stamp,
                PEEK_SENTINEL if peek else stamp,
                PEEK_SENTINEL,
            ),
        )
        return info

    def _cached_info(self, video_id: str, moment: datetime) -> dict | None:
        rows = self._db.execute(
            "SELECT probe_json, probed_at FROM videos WHERE video_id = ?", (video_id,)
        )
        if not rows:
            return None
        try:
            probed = datetime.fromisoformat(rows[0]["probed_at"])
            if probed.tzinfo is None:
                probed = probed.replace(tzinfo=UTC)
            age = moment - probed
            # อายุติดลบเกิน CLOCK_SKEW = นาฬิกาถอยหลังมาก ถือว่าเก่า
            if not -CLOCK_SKEW <= age < CACHE_TTL:
                return None
            return to_video_info(json.loads(rows[0]["probe_json"]))
        except (ValueError, TypeError, AttributeError, KeyError):
            return None  # แถวเสีย: probe ใหม่แล้วเขียนทับ

    def raw(self, video_id: str) -> dict:
        """ข้อมูลดิบที่ตัดแล้ว (ใช้ทำ storyboard) ถ้ายังไม่มีในเครื่องจะ probe ให้ก่อน

        ข้อมูลที่คืนอาจเก่ากว่า 24 ชม. (ไม่ตรวจอายุ) URL ของ storyboard เป็นลิงก์ที่ยูทูป
        เซ็นชื่อไว้และหมดอายุได้ ผู้เรียกที่โหลดภาพจากลิงก์เหล่านี้แล้วโหลดพลาด ให้เรียก
        `get(video_id, refresh=True)` เพื่อ probe ใหม่ แล้วอ่าน `raw()` ซ้ำและลองอีกครั้งเดียว
        """
        self._check_video_id(video_id)
        for _ in range(2):
            rows = self._db.execute(
                "SELECT probe_json FROM videos WHERE video_id = ?", (video_id,)
            )
            if rows:
                try:
                    data = json.loads(rows[0]["probe_json"])
                except ValueError:
                    data = None
                if isinstance(data, dict):
                    return data
            self.get(video_id, refresh=True)
        raise YtError("E_UNKNOWN", f"อ่านข้อมูลคลิป {video_id} ที่เก็บไว้ไม่ได้")

    def recent(
        self, limit: int, offset: int = 0, q: str | None = None
    ) -> tuple[list[dict], int]:
        # คลิปที่แค่ peek (ยังไม่เคยเปิดจริง) ไม่ขึ้นใน "ล่าสุด" ทั้งรายการและยอดรวม
        where, params = " WHERE opened_at != ?", [PEEK_SENTINEL]
        if q and q.strip():
            where += " AND title LIKE ? ESCAPE '\\'"
            params.append(f"%{_like_escape(q.strip())}%")
        total = self._db.execute(f"SELECT count(*) AS n FROM videos{where}", params)[0][
            "n"
        ]
        rows = self._db.execute(
            "SELECT video_id, title, thumbnail_url, duration_s, opened_at FROM videos"
            f"{where} ORDER BY opened_at DESC, video_id LIMIT ? OFFSET ?",
            [*params, max(limit, 0), max(offset, 0)],
        )
        items = [
            {
                "videoId": row["video_id"],
                "title": row["title"],
                "thumbnailUrl": row["thumbnail_url"] or "",
                "durationS": row["duration_s"] or 0,
                "outputs": [],
                "lastAt": row["opened_at"],
            }
            for row in rows
        ]
        return items, total

    def playlist(
        self,
        playlist_id: str,
        limit: int = PLAYLIST_LIMIT,
        video_id: str | None = None,
    ) -> dict:
        """รายการคลิปในเพลย์ลิสต์ (สูงสุด limit คลิป)

        มิกซ์อัตโนมัติ (id ขึ้นต้น RD) ต้องมี video_id = คลิปตั้งต้น และได้ไม่เกิน MIX_LIMIT คลิป
        คำตอบของมิกซ์มี isMix: true และ total = จำนวนที่ได้มา (มิกซ์ไม่มีจำนวนจริง ยูทูปต่อให้เรื่อย ๆ)
        เพลย์ลิสต์ปกติไม่ใช้ video_id
        """
        if not PLAYLIST_ID.fullmatch(playlist_id):
            raise YtError("E_INVALID_INPUT", f"playlist id ไม่ถูกรูปแบบ: {playlist_id!r}")
        mix = is_mix(playlist_id)
        if mix:
            if not video_id or not VIDEO_ID.fullmatch(video_id):
                raise YtError(
                    "E_INVALID_INPUT",
                    f"มิกซ์ {playlist_id!r} ต้องมีคลิปตั้งต้นที่ถูกรูปแบบ: {video_id!r}",
                )
            limit = MIX_LIMIT
            info = self._extractor.playlist(playlist_id, limit, video_id=video_id)
        else:
            limit = max(limit, 0)
            info = self._extractor.playlist(playlist_id, limit)
        returned = [e for e in (info.get("entries") or []) if isinstance(e, dict)]
        entries = []
        for entry in returned[:limit]:
            video_id = str(entry.get("id") or "")
            if not VIDEO_ID.fullmatch(video_id):
                continue  # คลิปที่ถูกลบ/ไม่มี id เปิดต่อไม่ได้
            item: dict[str, Any] = {
                "videoId": video_id,
                "title": entry.get("title") or "",
            }
            duration = entry.get("duration")
            if isinstance(duration, int | float) and not isinstance(duration, bool):
                item["durationS"] = round(duration)
            item["thumbnailUrl"] = _playlist_thumbnail(entry, video_id)
            entries.append(item)
        truncated = len(returned) > limit
        if mix:
            return {
                "title": info.get("title") or "",
                "total": len(entries),
                "truncated": truncated,
                "entries": entries,
                "isMix": True,
            }
        count = info.get("playlist_count")
        return {
            "title": info.get("title") or "",
            "total": count
            if isinstance(count, int) and not isinstance(count, bool)
            else len(returned),
            "truncated": truncated,
            "entries": entries,
        }
