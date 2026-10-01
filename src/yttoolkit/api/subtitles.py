"""API ซับของ M3 (สัญญา C4): รายการแทร็ก, token ของแทร็ก, โหลดไฟล์ .srt / .txt / .md
และโน้ตของคลิปแบบ .md สำหรับ Obsidian (C-A3, owner round 2)

Q1 = ก: เบราว์เซอร์โหลดไฟล์ทันที (ยังไม่มีคิวงาน M4 ค่อยย้ายเข้าคิว)
Q2 = ก: ชื่อไฟล์ `<ชื่อคลิป>.<ภาษา>.<นามสกุล>` เช่น `ชื่อคลิป.th.srt` ให้โปรแกรมเล่นเปิดซับให้เอง

route เป็น `def` ธรรมดา (โหลดซับ/probe บล็อก) FastAPI จึงส่งไปรันใน threadpool
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal

from fastapi import APIRouter, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator

from ..core.srt_builder import LIMITS, PRESETS, options_from_dict
from ..core.tracks import TRACK_ID
from ..core.yterrors import YtError
from .errors import BAD_REQUEST_MESSAGE, error_response
from .videos import _maps_yt_errors, attachment_header, safe_title

if TYPE_CHECKING:
    from ..app import AppContext

MEDIA_TYPES = {
    "srt": "application/x-subrip; charset=utf-8",
    "txt": "text/plain; charset=utf-8",
    "md": "text/markdown; charset=utf-8",
}
_DEFAULT = PRESETS["medium"]  # ค่าที่ไม่ได้ส่งมา = preset กลาง (หน้าเว็บส่งครบทุกช่องอยู่แล้ว)


class OptionsQuery(BaseModel):
    """ตัวเลือกซับ (C5) ผิดช่วง/ผิดเงื่อนไข = 422 E_BAD_REQUEST ผ่านตัวจัดการ validation เดิม"""

    maxChars: int = Field(_DEFAULT.max_chars, ge=LIMITS["maxChars"][0], le=LIMITS["maxChars"][1])
    lines: int = Field(_DEFAULT.lines, ge=LIMITS["lines"][0], le=LIMITS["lines"][1])
    minMs: int = Field(_DEFAULT.min_ms, ge=LIMITS["minMs"][0], le=LIMITS["minMs"][1])
    maxMs: int = Field(_DEFAULT.max_ms, ge=LIMITS["maxMs"][0], le=LIMITS["maxMs"][1])
    mode: Literal["chars", "tokens"] = "chars"
    tokensPerCue: int | None = Field(None, ge=LIMITS["tokensPerCue"][0], le=LIMITS["tokensPerCue"][1])

    @model_validator(mode="after")
    def _consistent(self) -> OptionsQuery:
        if self.minMs >= self.maxMs:
            raise ValueError("minMs must be less than maxMs")
        if self.mode == "tokens" and self.tokensPerCue is None:
            raise ValueError("tokensPerCue is required when mode is tokens")
        return self


class ExportQuery(OptionsQuery):
    """ไฟล์ซับ: รูปแบบไฟล์ + ตัวเลือกซับ"""

    format: Literal["srt", "txt", "md"]


class NoteQuery(OptionsQuery):
    """โน้ต .md (C-A3): แทร็ก (ไม่ส่ง = แทร็กที่เลือกให้เอง) + ตัวเลือกชุดเดียวกับไฟล์ซับ

    ตัวเลือกตรวจแบบเดียวกับไฟล์ซับ (หน้าเว็บส่งชุดที่ใช้อยู่มาด้วย) แต่ทรานสคริปต์ในโน้ตแบ่งย่อหน้าตามเวลา
    เหมือนไฟล์ .md จึงไม่ได้ใช้ค่าความยาวซับ
    """

    trackId: str | None = None


def export_filenames(title: str, video_id: str, lang: str, fmt: str) -> tuple[str, str]:
    """(ชื่อไฟล์จริง, ชื่อ ASCII สำรอง) ตาม Q2 = ก: `<ชื่อคลิปที่ปลอดภัย หรือ id>.<lang>.<fmt>`"""
    return f"{safe_title(title) or video_id}.{lang}.{fmt}", f"subtitles.{lang}.{fmt}"


def note_filenames(title: str, video_id: str) -> tuple[str, str]:
    """(ชื่อไฟล์จริง, ชื่อ ASCII สำรอง) ของโน้ต: `<ชื่อคลิปที่ปลอดภัย หรือ id>.note.md`, `<id>.note.md`"""
    return f"{safe_title(title) or video_id}.note.md", f"{video_id}.note.md"


def _check_track_id(track_id: str) -> None:
    if not TRACK_ID.match(track_id):
        raise YtError("E_NO_SUBTITLES", f"id แทร็กไม่ถูกรูปแบบ: {track_id[:80]!r}")


def build_subtitles_router(ctx: AppContext) -> APIRouter:
    subtitles = ctx.subtitles
    if subtitles is None:
        raise ValueError("ต้องมี subtitles ถึงจะเปิด API ซับได้")
    router = APIRouter()

    @router.get("/videos/{video_id}/subtitles", response_model=None)
    @_maps_yt_errors
    def subtitle_tracks(video_id: str) -> dict:
        return subtitles.tracks(video_id)

    @router.get("/videos/{video_id}/subtitles/{track_id}/tokens", response_model=None)
    @_maps_yt_errors
    def subtitle_tokens(video_id: str, track_id: str) -> dict:
        _check_track_id(track_id)
        parsed = subtitles.tokens(video_id, track_id)
        return {
            "hasWordTiming": parsed.has_word_timing,
            "tokens": [{"t": tok.t, "s": tok.s, "e": tok.e} for tok in parsed.tokens],
        }

    @router.get("/videos/{video_id}/subtitles/{track_id}/export", response_model=None)
    @_maps_yt_errors
    def subtitle_export(video_id: str, track_id: str, query: Annotated[ExportQuery, Query()]) -> Response:
        _check_track_id(track_id)
        try:
            # ตรวจซ้ำด้วยตัวตรวจของ builder (เข้มกว่า: เฉพาะจำนวนเต็ม) build_cues จึงไม่มีทางโยน ValueError
            opts = options_from_dict(query.model_dump(exclude={"format"}))
        except ValueError as exc:
            return error_response(422, "E_BAD_REQUEST", BAD_REQUEST_MESSAGE, str(exc))
        result = subtitles.export(video_id, track_id, query.format, opts)
        filename, fallback = export_filenames(result.title, video_id, result.lang, query.format)
        return Response(
            result.data,
            media_type=MEDIA_TYPES[query.format],
            headers={"Content-Disposition": attachment_header(fallback, filename)},
        )

    @router.get("/videos/{video_id}/note", response_model=None)
    @_maps_yt_errors
    def video_note(video_id: str, query: Annotated[NoteQuery, Query()]) -> Response:
        if query.trackId is not None:
            _check_track_id(query.trackId)
        try:
            options_from_dict(query.model_dump(exclude={"trackId"}))
        except ValueError as exc:
            return error_response(422, "E_BAD_REQUEST", BAD_REQUEST_MESSAGE, str(exc))
        result = subtitles.note(video_id, query.trackId, pinned=ctx.pinned.get if ctx.pinned is not None else None)
        filename, fallback = note_filenames(result.title, video_id)
        return Response(
            result.data,
            media_type=MEDIA_TYPES["md"],
            headers={"Content-Disposition": attachment_header(fallback, filename)},
        )

    return router
