"""API คิวงาน (สัญญา C4): สร้างงาน ดูรายการ ยกเลิก ลองใหม่ เรียงคิว ทำคิวต่อ และส่งไฟล์ผลลัพธ์

route เป็น `def` ธรรมดา (แตะฐานข้อมูลและดิสก์) FastAPI จึงส่งไปรันใน threadpool
ค่าของงานแต่ละชนิด (C3) ตรวจด้วย pydantic: key ที่ไม่รู้จัก ช่วงเวลา แยกตามบท และภาพคม = 422 ใน M4
"""

from __future__ import annotations

import re
from datetime import UTC
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from ..core.download import FFMPEG_KINDS
from ..core.jobs import InvalidTransition, Job, NewJob, OutputFile
from ..core.srt_builder import options_from_dict
from ..core.yterrors import MESSAGES
from .errors import error_response, redact_home
from .safepath import safe_parts
from .videos import attachment_header

if TYPE_CHECKING:
    from ..app import AppContext
    from ..core.queue import QueueRunner

ITEMS_MAX = 500
ORDER_IDS_MAX = 1000
LIST_LIMIT_DEFAULT = 50
LIST_LIMIT_MAX = 200
TITLE_MAX_CHARS = 500
MP3_KBPS_DEFAULT = 192
# ชนิดไฟล์ผลลัพธ์ตามนามสกุล (ไม่พึ่ง mimetypes: บน Windows เดา zip เป็น application/x-zip-compressed)
OUTPUT_MEDIA_TYPES = {
    ".zip": "application/zip",
    ".jpg": "image/jpeg",
    ".mp4": "video/mp4",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".srt": "application/x-subrip",
    ".vtt": "text/vtt; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
}
OUTPUT_MEDIA_TYPE_DEFAULT = "application/octet-stream"

JOB_ID = re.compile(r"[0-9a-f-]{36}")
_VIDEO_ID = r"^[A-Za-z0-9_-]{11}$"
_FORMAT_ID = r"^[A-Za-z0-9_-]{1,32}$"
_TRACK_ID = r"^[oat]\.[A-Za-z0-9_-]{1,64}$"
_LANGUAGE = re.compile(r"[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*")

JobStatus = Literal["queued", "running", "done", "failed", "cancelled", "interrupted"]


# ---------- ค่าของงานแต่ละชนิด (C3) ----------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _audio_language(value: str) -> str:
    if value != "original" and not _LANGUAGE.fullmatch(value):
        raise ValueError("audioLanguage must be 'original' or a language tag")
    return value


class SubOptionsModel(_Strict):
    maxChars: int
    lines: int
    minMs: int
    maxMs: int
    mode: Literal["chars", "tokens"] = "chars"
    tokensPerCue: int | None = None

    @model_validator(mode="after")
    def _limits(self) -> SubOptionsModel:
        options_from_dict(self.model_dump(exclude_none=True))  # ช่วงค่าและเงื่อนไขเดียวกับหน้าซับ (ValueError = 422)
        return self


class VideoParams(_Strict):
    formatId: str | None = Field(None, pattern=_FORMAT_ID)
    maxQuality: bool = False
    maxHeight: Literal[720, 1080] | None = None
    splitChapters: Literal[False] = False  # แยกตามบทมาใน M5
    noAudio: bool = False
    audioLanguage: str = "original"
    embedSubs: str | None = Field(None, pattern=_TRACK_ID)
    subOptions: SubOptionsModel | None = None

    _language = field_validator("audioLanguage")(_audio_language)

    @model_validator(mode="after")
    def _embed_needs_options(self) -> VideoParams:
        if self.embedSubs is not None and self.subOptions is None:
            raise ValueError("embedSubs requires subOptions")
        return self


class AudioParams(_Strict):
    format: Literal["m4a", "mp3", "wav"]
    mp3Kbps: Literal[128, 192, 320] | None = None
    splitChapters: Literal[False] = False
    audioLanguage: str = "original"

    _language = field_validator("audioLanguage")(_audio_language)

    @model_validator(mode="after")
    def _normalise_kbps(self) -> AudioParams:
        if self.format == "mp3" and self.mp3Kbps is None:
            self.mp3Kbps = MP3_KBPS_DEFAULT
        elif self.format != "mp3":
            self.mp3Kbps = None
        return self


class SubtitleParams(_Strict):
    trackId: str | None = Field(None, pattern=_TRACK_ID)
    format: Literal["srt", "txt", "md"]
    options: SubOptionsModel


class ContactSheetParams(_Strict):
    source: Literal["fast"] = "fast"
    columns: Literal[5] = 5


class FramesZipParams(_Strict):
    source: Literal["fast"] = "fast"


PARAMS_BY_KIND: dict[str, type[BaseModel]] = {
    "video": VideoParams,
    "audio": AudioParams,
    "subtitle": SubtitleParams,
    "contact_sheet": ContactSheetParams,
    "frames_zip": FramesZipParams,
}


class NewJobModel(_Strict):
    videoId: str = Field(pattern=_VIDEO_ID)
    kind: Literal["video", "audio", "subtitle", "contact_sheet", "frames_zip"]  # frames_sharp = M5
    params: dict[str, Any]
    title: str = Field("", max_length=TITLE_MAX_CHARS)

    @model_validator(mode="after")
    def _params_for_kind(self) -> NewJobModel:
        try:
            parsed = PARAMS_BY_KIND[self.kind].model_validate(self.params)
        except ValidationError as exc:
            # validator ห้ามโยน ValidationError ต่อตรงๆ แปลงเป็น ValueError ให้ pydantic รวมเป็น 422
            raise ValueError(f"params of {self.kind}: {exc}") from None
        self.params = parsed.model_dump(exclude_none=True)
        return self

    def to_new_job(self) -> NewJob:
        return NewJob(self.videoId, self.kind, self.params, self.title)


class PostJobsBody(_Strict):
    items: list[NewJobModel] = Field(min_length=1, max_length=ITEMS_MAX)


class OrderBody(_Strict):
    ids: list[str] = Field(min_length=1, max_length=ORDER_IDS_MAX)


# ---------- ไฟล์ผลลัพธ์ ----------


def output_path(out: OutputFile) -> Path | None:
    """path จริงของไฟล์ผลลัพธ์ ต้องอยู่ใต้โฟลเดอร์ผลลัพธ์ที่บันทึกไว้ตอนทำงาน และยังมีไฟล์อยู่ ไม่ผ่าน = None

    rel ตรวจแบบไม่แตะดิสก์ก่อน (ห้าม .. / backslash / ไดรฟ์) และ root ต้องไม่ใช่ path เครือข่าย (UNC)
    เพราะการแตะ path แบบนั้นบน Windows ทำให้เครื่องไปต่อ SMB
    """
    parts = safe_parts(out.rel)
    root_text = out.root
    if parts is None or root_text.startswith(("\\\\", "//")):
        return None
    root = Path(root_text)
    if not root.is_absolute():
        return None
    try:
        root = root.resolve()
        target = root.joinpath(*parts).resolve()
    except (OSError, RuntimeError):
        return None
    if not target.is_relative_to(root) or not target.is_file():
        return None
    return target


# ---------- router ----------


def build_jobs_router(ctx: AppContext) -> APIRouter:
    router = APIRouter()
    queue: QueueRunner | None = ctx.queue
    assert queue is not None  # create_app เรียกต่อเมื่อมี ctx.queue เท่านั้น
    store = queue.store

    def find(job_id: str) -> Job:
        job = store.get(job_id) if JOB_ID.fullmatch(job_id) else None
        if job is None:
            raise HTTPException(status_code=404)
        return job

    def api(job: Job) -> dict:
        """Job ในรูป C2 (+ cancelling) และ error.detail ที่ซ่อนโฟลเดอร์ผู้ใช้แล้ว"""
        data = queue.job_api(job)
        error = data.get("error")
        if error and error.get("detail"):
            data["error"] = {**error, "detail": redact_home(error["detail"])}
        return data

    def job_state_error() -> JSONResponse:
        return error_response(409, "E_JOB_STATE", MESSAGES["E_JOB_STATE"])

    def output_of(job_id: str, index: int) -> Path:
        job = find(job_id)
        if not 0 <= index < len(job.outputs):
            raise HTTPException(status_code=404)
        target = output_path(job.outputs[index])
        if target is None:
            raise HTTPException(status_code=404)
        return target

    @router.post("/jobs", response_model=None)
    def create_jobs(body: PostJobsBody) -> dict | JSONResponse:
        if any(item.kind in FFMPEG_KINDS for item in body.items):
            if ctx.media is None or not ctx.media.available():
                return error_response(409, "E_FFMPEG_MISSING", MESSAGES["E_FFMPEG_MISSING"])
        jobs = queue.enqueue([item.to_new_job() for item in body.items])
        return {"jobs": [api(job) for job in jobs]}

    @router.get("/jobs")
    def list_jobs(
        status: JobStatus | None = None,
        limit: int = Query(LIST_LIMIT_DEFAULT, ge=1, le=LIST_LIMIT_MAX),
    ) -> dict:
        jobs = store.list_default() if status is None else store.list_status(status, limit)
        return {"jobs": [api(job) for job in jobs]}

    @router.get("/queue")
    def queue_state() -> dict:
        pause = queue.pause_state()
        return {
            "pausedUntil": pause.until.astimezone(UTC).isoformat(timespec="seconds") if pause else None,
            "reason": pause.reason if pause else None,
            "concurrency": queue.concurrency(),
        }

    @router.post("/jobs/{job_id}/cancel", response_model=None)
    def cancel_job(job_id: str) -> dict | JSONResponse:
        find(job_id)
        try:
            job = queue.cancel(job_id)
        except KeyError:
            raise HTTPException(status_code=404) from None
        except InvalidTransition:
            return job_state_error()
        return api(job)

    @router.post("/jobs/{job_id}/retry", response_model=None)
    def retry_job(job_id: str) -> dict | JSONResponse:
        find(job_id)
        try:
            job = queue.retry(job_id)
        except KeyError:
            raise HTTPException(status_code=404) from None
        except InvalidTransition:
            return job_state_error()
        return api(job)

    @router.put("/jobs/order")
    def reorder_jobs(body: OrderBody) -> dict:
        queue.reorder(body.ids)
        return {"ok": True}

    @router.post("/queue/resume")
    def resume_queue() -> dict:
        queue.resume()
        return {"ok": True}

    @router.get("/jobs/{job_id}/outputs/{index}", response_model=None)
    def get_output(job_id: str, index: int) -> FileResponse:
        target = output_of(job_id, index)
        suffix = PurePosixPath(target.name).suffix.lower()
        return FileResponse(
            target,
            media_type=OUTPUT_MEDIA_TYPES.get(suffix, OUTPUT_MEDIA_TYPE_DEFAULT),
            headers={"Content-Disposition": attachment_header(f"download{suffix}", target.name)},
        )

    @router.post("/jobs/{job_id}/outputs/{index}/reveal")
    def reveal_output(job_id: str, index: int) -> dict:
        target = output_of(job_id, index)
        revealer = ctx.reveal or ctx.plat.reveal
        revealer(target)
        return {"ok": True}

    return router
