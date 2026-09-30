"""API ข้อมูลคลิปของ M2: แยกลิงก์, VideoInfo, ภาพเฟรม (storyboard), contact sheet, zip,
เพลย์ลิสต์, ประวัติ และไฟล์ภาพใน cache

งานที่บล็อก (probe, สร้าง storyboard, ทำภาพ) อยู่ใน route แบบ `def` ธรรมดา FastAPI จึงส่งไปรันใน threadpool
"""

from __future__ import annotations

import functools
import json
import logging
import os
import re
import unicodedata
import uuid
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from ..core.frames import contact_sheet, file_timecode, frames_zip
from ..core.inputs import VIDEO_ID, InputItem, parse_text
from ..core.storyboard import FOLDER as STORYBOARD_FOLDER
from ..core.storyboard import INDEX as STORYBOARD_INDEX
from ..core.storyboard import get_storyboard
from ..core.yterrors import MESSAGES, YtError
from .errors import error_response
from .safepath import safe_parts

if TYPE_CHECKING:
    from ..app import AppContext

log = logging.getLogger("yttoolkit")

RESOLVE_MAX_CHARS = 20_000
HISTORY_DEFAULT_LIMIT = 20
HISTORY_MAX_LIMIT = 100
TITLE_MAX_CHARS = 100
FRAME_CACHE_CONTROL = "public, max-age=86400, immutable"

# รหัส error -> HTTP status (รหัสอื่นทั้งหมด รวม E_UNKNOWN = 500)
STATUS_BY_CODE: dict[str, int] = {
    "E_INVALID_INPUT": 422,
    "E_VIDEO_UNAVAILABLE": 404,
    "E_VIDEO_PRIVATE": 404,
    "E_NO_STORYBOARD": 404,
    "E_LIVE_NOT_READY": 409,
    "E_AGE_RESTRICTED": 409,
    "E_GEO_BLOCKED": 409,
    "E_BOT_CHECK": 429,
    "E_NETWORK": 502,
}

# อักขระที่ Windows ห้ามใช้ในชื่อไฟล์
_FORBIDDEN_NAME_CHARS = frozenset('\\/:*?"<>|')
# ชื่อไฟล์ใน cache ทุกไฟล์แอพตั้งเอง: ตัวอักษรอังกฤษ ตัวเลข _ - และนามสกุล ไม่มีจุดหรือช่องว่างท้ายชื่อ
_CACHE_PART = re.compile(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9]+)*")
_CACHE_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
_FRAME_FILE = re.compile(r"f_\d{4,}\.jpg")


class ResolveBody(BaseModel):
    text: str = Field(max_length=RESOLVE_MAX_CHARS)


# ---------- ชื่อไฟล์ที่โหลด ----------


def safe_title(title: str) -> str:
    """ชื่อคลิปที่ใช้เป็นชื่อไฟล์ได้: ตัดอักขระต้องห้ามของ Windows และอักขระควบคุม
    (รวมตัวกลับทิศข้อความ ซึ่งใช้หลอกนามสกุลไฟล์ได้) รวมช่องว่าง แล้วตัดให้ยาวไม่เกิน 100 ตัว"""
    kept = []
    for ch in title:
        if ch.isspace():
            kept.append(" ")
        elif ch in _FORBIDDEN_NAME_CHARS or unicodedata.category(ch) in ("Cc", "Cf"):
            continue
        else:
            kept.append(ch)
    text = " ".join("".join(kept).split())
    return text[:TITLE_MAX_CHARS].rstrip()


def attachment_header(fallback: str, filename: str) -> str:
    """Content-Disposition ตาม RFC 6266/5987: ชื่อ ASCII สำรอง + ชื่อจริง (UTF-8) ใน filename*"""
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"


def _download_stem(info: dict, video_id: str) -> str:
    return safe_title(str(info.get("title") or "")) or video_id


# ---------- error ----------


def yt_error_response(exc: YtError, subject: str) -> JSONResponse:
    """YtError -> error envelope ตามตารางรหัส ข้อความถึงผู้ใช้มาจาก MESSAGES (ไม่รู้จักใช้ของ E_UNKNOWN)"""
    status = STATUS_BY_CODE.get(exc.code, 500)
    unexpected = status == 500
    # รหัสที่หน้าเว็บไม่รู้จักส่งเป็น E_UNKNOWN (log ยังเก็บรหัสเดิมไว้)
    code = exc.code if exc.code in MESSAGES else "E_UNKNOWN"
    # error ที่คาดไว้ (คลิปส่วนตัว ไลฟ์ ฯลฯ) ไม่ต้องมี traceback ให้รก log
    log.warning(
        "ดึงข้อมูลคลิปไม่สำเร็จ %s (%s): %s",
        exc.code,
        subject,
        exc.detail,
        exc_info=exc if unexpected else None,
    )
    return error_response(status, code, exc.message, exc.detail or None)


def _maps_yt_errors(func: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except YtError as exc:
            subject = kwargs.get("video_id") or kwargs.get("playlist_id") or "-"
            return yt_error_response(exc, str(subject))

    return wrapper


# ---------- resolve ----------


def _resolve_item(item: InputItem) -> dict:
    out: dict[str, Any] = {"input": item.input, "kind": item.kind}
    if item.video_id:
        out["videoId"] = item.video_id
    if item.playlist_id:
        out["playlistId"] = item.playlist_id
    if item.kind == "invalid":
        out["error"] = {"code": "E_INVALID_INPUT", "message": MESSAGES["E_INVALID_INPUT"]}
    return out


# ---------- router ----------


def build_videos_router(ctx: AppContext) -> APIRouter:
    videos, extractor, cache_root = ctx.videos, ctx.extractor, ctx.cache_root
    if videos is None or extractor is None or cache_root is None:
        raise ValueError("ต้องมี videos, extractor และ cache_root ครบถึงจะเปิด API ข้อมูลคลิปได้")
    cache_root = Path(cache_root)
    router = APIRouter()

    def storyboard_index(video_id: str) -> dict:
        return get_storyboard(video_id, videos, cache_root, extractor.fetch)

    def frame_files(video_id: str, index: dict) -> list[tuple[int, Path]]:
        folder = cache_root / video_id / STORYBOARD_FOLDER
        return [(frame["tMs"], folder / frame["file"]) for frame in index["frames"]]

    @router.post("/resolve")
    def resolve(body: ResolveBody) -> dict:
        return {
            "resolveId": uuid.uuid4().hex,  # ยังไม่เก็บลง DB (W3 ใช้ใน M4)
            "items": [_resolve_item(item) for item in parse_text(body.text)],
        }

    @router.get("/videos/{video_id}", response_model=None)
    @_maps_yt_errors
    def video_info(video_id: str, refresh: bool = False, peek: bool = False) -> dict:
        # peek=1: หน้าเว็บขอแค่ชื่อ/ภาพปก (รายการผล W1) ไม่นับว่าเปิดคลิป จึงไม่ขึ้น "ล่าสุด"
        return videos.get(video_id, refresh=refresh, peek=peek)

    @router.get("/videos/{video_id}/storyboard", response_model=None)
    @_maps_yt_errors
    def storyboard(video_id: str) -> dict:
        index = storyboard_index(video_id)
        # ภาพเฟรมตอบแบบ immutable จึงต่อ ?v=<เวลาแก้ไข index.json> ให้ URL เปลี่ยนเมื่อสร้างชุดใหม่
        folder = cache_root / video_id / STORYBOARD_FOLDER
        try:
            query = f"?v={(folder / STORYBOARD_INDEX).stat().st_mtime_ns}"
        except OSError:
            query = ""
        return {
            "intervalMs": index["intervalMs"],
            "frames": [
                {
                    "index": frame["index"],
                    "tMs": frame["tMs"],
                    "url": f"/api/cache/{video_id}/{STORYBOARD_FOLDER}/{frame['file']}{query}",
                }
                for frame in index["frames"]
            ],
        }

    # M4 ย้ายสองอันนี้เข้าคิวงาน (job kind contact_sheet / frames_zip) และบันทึกลงโฟลเดอร์ผลลัพธ์
    @router.get("/videos/{video_id}/storyboard/contact-sheet.jpg", response_model=None)
    @_maps_yt_errors
    def storyboard_contact_sheet(video_id: str) -> Response:
        info = videos.get(video_id)
        frames = frame_files(video_id, storyboard_index(video_id))
        data = contact_sheet(frames, str(info.get("title") or ""), int(info.get("durationS") or 0))
        name = f"{_download_stem(info, video_id)} - contact sheet.jpg"
        return Response(
            data,
            media_type="image/jpeg",
            headers={"Content-Disposition": attachment_header("contact-sheet.jpg", name)},
        )

    @router.get("/videos/{video_id}/storyboard/frames.zip", response_model=None)
    @_maps_yt_errors
    def storyboard_zip(video_id: str) -> Response:
        info = videos.get(video_id)
        data = frames_zip(frame_files(video_id, storyboard_index(video_id)))
        name = f"{_download_stem(info, video_id)} - frames.zip"
        return Response(
            data,
            media_type="application/zip",
            headers={"Content-Disposition": attachment_header("frames.zip", name)},
        )

    @router.get("/playlists/{playlist_id}", response_model=None)
    @_maps_yt_errors
    def playlist(playlist_id: str) -> dict:
        return videos.playlist(playlist_id)

    @router.get("/history")
    def history(
        q: str | None = Query(None, max_length=200),
        limit: int = Query(HISTORY_DEFAULT_LIMIT, ge=1, le=HISTORY_MAX_LIMIT),
        offset: int = Query(0, ge=0, le=1_000_000),
    ) -> dict:
        items, total = videos.recent(limit, offset, q)
        return {"items": items, "total": total}

    @router.get("/cache/{video_id}/{file_path:path}", response_model=None)
    def cache_file(video_id: str, file_path: str, download: bool = False) -> FileResponse:
        found = _cache_target(cache_root, video_id, file_path)
        if found is None:
            raise HTTPException(status_code=404)
        target, parts, media_type = found
        is_frame = len(parts) == 2 and parts[0] == STORYBOARD_FOLDER and _FRAME_FILE.fullmatch(parts[1])
        headers: dict[str, str] = {}
        if is_frame:
            headers["Cache-Control"] = FRAME_CACHE_CONTROL
        if download:
            name = _frame_download_name(target.parent, parts[-1]) if is_frame else parts[-1]
            headers["Content-Disposition"] = f'attachment; filename="{name}"'
        return FileResponse(target, media_type=media_type, headers=headers)

    return router


def _cache_target(
    cache_root: Path, video_id: str, file_path: str
) -> tuple[Path, tuple[str, ...], str] | None:
    """ไฟล์ภาพที่อยู่ใต้ <cache_root>/<video_id>/ เท่านั้น (AC-SEC-04) ไม่ผ่านเกณฑ์คืน None

    ตรวจแบบไม่แตะดิสก์ให้ครบก่อน (id, path, ชื่อไฟล์, นามสกุล) แล้วค่อยเช็คว่ามีไฟล์จริง
    """
    if not VIDEO_ID.fullmatch(video_id):
        return None
    parts = safe_parts(file_path)
    if parts is None or not all(_CACHE_PART.fullmatch(part) for part in parts):
        return None
    # นามสกุลต้องเป็นตัวพิมพ์เล็กเป๊ะ ๆ (แอพตั้งชื่อไฟล์เองเป็นตัวเล็กทั้งหมด)
    media_type = _CACHE_MEDIA_TYPES.get(PurePosixPath(parts[-1]).suffix)
    if media_type is None:
        return None
    folder = cache_root / video_id
    target = folder.joinpath(*parts)
    try:
        if not target.is_file():
            return None
        real_folder = folder.resolve(strict=True)
        real_target = target.resolve(strict=True)
        # NTFS ไม่สนตัวพิมพ์: AQZ-KE-BPKQ หรือ STORYBOARD ก็เปิดโฟลเดอร์จริงได้ ต้องเทียบชื่อจริงบนดิสก์
        # และกันลิงก์ (symlink/junction) ในโฟลเดอร์ cache พาออกไปนอกโฟลเดอร์ของคลิป
        if not real_target.is_relative_to(real_folder):
            return None
        # macOS (APFS) ก็ไม่สนตัวพิมพ์เช่นกัน แต่ resolve() ไม่แก้ตัวพิมพ์ให้ จึงเทียบกับชื่อที่ listdir คืนมาจริง
        if not _exact_names(cache_root, (video_id, *parts)):
            return None
    except (OSError, ValueError):
        return None
    return target, parts, media_type


def _exact_names(root: Path, names: tuple[str, ...]) -> bool:
    """ทุกชื่อในสายต้องมีอยู่จริงบนดิสก์ด้วยตัวพิมพ์ตรงเป๊ะ (ดูจากชื่อในโฟลเดอร์ ไม่พึ่ง resolve)

    แต่ละชื่อเทียบกับโฟลเดอร์แม่ของตัวเองเท่านั้น และหยุดอ่านทันทีที่เจอ
    จึงไม่ต้องไล่รายชื่อคลิปทั้ง cache ทุกครั้งที่หน้าเว็บขอภาพเฟรม
    """
    current = root
    for name in names:
        if not _has_exact_name(current, name):
            return False
        current = current / name
    return True


def _has_exact_name(folder: Path, name: str) -> bool:
    with os.scandir(folder) as entries:
        return any(entry.name == name for entry in entries)


def _frame_download_name(storyboard_dir: Path, file_name: str) -> str:
    """frame_HH-MM-SS.jpg จากเวลาของเฟรมใน index.json (หาไม่เจอใช้ชื่อไฟล์เดิม)"""
    try:
        index = json.loads((storyboard_dir / STORYBOARD_INDEX).read_text(encoding="utf-8"))
        for frame in index["frames"]:
            if frame.get("file") == file_name and isinstance(frame.get("tMs"), int):
                return f"frame_{file_timecode(frame['tMs'])}.jpg"
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    return file_name
