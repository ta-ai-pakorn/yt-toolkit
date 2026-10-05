"""API คิวงาน (สัญญา C4): สร้างงาน ดูรายการ ยกเลิก ลองใหม่ เรียงคิว ทำคิวต่อ และส่งไฟล์ผลลัพธ์

route เป็น `def` ธรรมดา (แตะฐานข้อมูลและดิสก์) FastAPI จึงส่งไปรันใน threadpool
ค่าของงานแต่ละชนิด (C3 + M5 รอบ A) ตรวจด้วย pydantic: key ที่ไม่รู้จัก คุกกี้ และภาพคม = 422
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    ValidationError,
    field_validator,
    model_validator,
)

from ..core.download import FFMPEG_KINDS
from ..core.jobs import (
    MIN_RANGE_MS,
    RANGE_TOLERANCE_MS,
    SPONSORBLOCK_CATEGORIES,
    InvalidTransition,
    Job,
    NewJob,
    OutputFile,
)
from ..core.srt_builder import options_from_dict
from ..core.yterrors import MESSAGES
from .errors import BAD_REQUEST_MESSAGE, error_response, redact_home
from .safepath import safe_parts
from .videos import attachment_header

if TYPE_CHECKING:
    from ..app import AppContext
    from ..core.queue import QueueRunner

ITEMS_MAX = 1200  # 200 คลิป x 6 งาน (W3: หลัก + srt + txt + โน้ต + ภาพรวมเฟรม + zip)
# PUT /jobs/order: หน้าเว็บส่ง id ของงาน queued "ทั้งหมด" ทุกครั้งที่ลากเรียง จึงต้องรับได้หลายชุดใหญ่ที่ค้างคิว
# (ชุดเดียวจาก W3 ก็ได้ ITEMS_MAX งาน) เรียงใหม่เป็น O(n) ในหนึ่ง transaction
ORDER_IDS_MAX = 10 * ITEMS_MAX
LIST_LIMIT_DEFAULT = 50
LIST_LIMIT_MAX = 200
TITLE_MAX_CHARS = 500
FOLDER_MAX_CHARS = 80  # params.folder (ชื่อโฟลเดอร์กลุ่มของ W3) หลัง strip
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


class _Grouped(_Strict):
    """params ทุกชนิดรับ folder ได้ (owner preview round 2): ชื่อโฟลเดอร์กลุ่มของงานจาก W3

    strip แล้วยาว 1..80 ตัวอักษร (เกิน = 422) strip แล้วว่าง = ไม่มี (ไม่เก็บลง params)
    เก็บข้อความตามที่ส่งมา (strip แล้ว) ตัวทำงานทำความสะอาดเป็นชื่อโฟลเดอร์เอง (files.group_folder_name)
    """

    folder: str | None = None

    @field_validator("folder")
    @classmethod
    def _folder(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if len(value) > FOLDER_MAX_CHARS:
            raise ValueError(f"folder must be at most {FOLDER_MAX_CHARS} characters")
        return value or None


def _audio_language(value: str) -> str:
    if value != "original" and not _LANGUAGE.fullmatch(value):
        raise ValueError("audioLanguage must be 'original' or a language tag")
    return value


class RangeModel(_Strict):
    """ช่วงเวลาของงาน (M5 รอบ A): มิลลิวินาทีเต็มวินาที เริ่มก่อนจบอย่างน้อย 1 วินาที"""

    startMs: StrictInt = Field(ge=0)
    endMs: StrictInt

    @model_validator(mode="after")
    def _whole_seconds(self) -> RangeModel:
        if self.startMs % 1000 or self.endMs % 1000:
            raise ValueError("range must be whole seconds (multiples of 1000 ms)")
        if self.endMs - self.startMs < MIN_RANGE_MS:
            raise ValueError("range must start before it ends and last at least 1 second")
        return self


def _sponsor_categories(value: list[str] | None) -> list[str] | None:
    if value is None:
        return None
    if not value:
        raise ValueError("sponsorblock must list at least one category")
    if len(set(value)) != len(value):
        raise ValueError("sponsorblock categories must be unique")
    unknown = [v for v in value if v not in SPONSORBLOCK_CATEGORIES]
    if unknown:
        raise ValueError(f"unknown sponsorblock categories: {unknown}")
    return value


class _CutOptions(_Grouped):
    """ตัวเลือกขั้นสูงของงานวิดีโอและเสียง: แยกตาม chapter ใช้คู่กับช่วงเวลาหรือตัดโฆษณาไม่ได้"""

    range: RangeModel | None = None
    sponsorblock: list[str] | None = None
    splitChapters: StrictBool = False

    _sponsorblock = field_validator("sponsorblock")(_sponsor_categories)

    @model_validator(mode="after")
    def _chapters_alone(self) -> _CutOptions:
        if self.splitChapters and (self.range is not None or self.sponsorblock is not None):
            raise ValueError("splitChapters cannot be combined with range or sponsorblock")
        return self


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


class VideoParams(_CutOptions):
    formatId: str | None = Field(None, pattern=_FORMAT_ID)
    maxQuality: bool = False
    maxHeight: Literal[720, 1080] | None = None
    noAudio: bool = False
    audioLanguage: str = "original"
    embedSubs: str | None = Field(None, pattern=_TRACK_ID)
    subOptions: SubOptionsModel | None = None

    _language = field_validator("audioLanguage")(_audio_language)

    @model_validator(mode="after")
    def _embed_rules(self) -> VideoParams:
        if self.embedSubs is not None and self.subOptions is None:
            raise ValueError("embedSubs requires subOptions")
        if self.embedSubs is not None and self.splitChapters:
            raise ValueError("embedSubs cannot be combined with splitChapters")  # AC-VID-10 part 2
        return self


class AudioParams(_CutOptions):
    format: Literal["m4a", "mp3", "wav"]
    mp3Kbps: Literal[128, 192, 320] | None = None
    audioLanguage: str = "original"

    _language = field_validator("audioLanguage")(_audio_language)

    @model_validator(mode="after")
    def _normalise_kbps(self) -> AudioParams:
        if self.format == "mp3" and self.mp3Kbps is None:
            self.mp3Kbps = MP3_KBPS_DEFAULT
        elif self.format != "mp3":
            self.mp3Kbps = None
        return self


class SubtitleParams(_Grouped):
    trackId: str | None = Field(None, pattern=_TRACK_ID)
    format: Literal["srt", "txt", "md"]
    options: SubOptionsModel
    range: RangeModel | None = None

    @model_validator(mode="after")
    def _range_formats(self) -> SubtitleParams:
        if self.range is not None and self.format == "md":
            raise ValueError("range works with srt and txt only")
        return self


class ContactSheetParams(_Grouped):
    source: Literal["fast"] = "fast"
    columns: Literal[5] = 5


class FramesZipParams(_Grouped):
    source: Literal["fast"] = "fast"


class NoteParams(_Grouped):
    """โน้ต .md ของคลิป ไม่ส่ง trackId = แทร็กที่เลือกให้เอง (เหมือน GET /videos/{id}/note)"""

    trackId: str | None = Field(None, pattern=_TRACK_ID)


PARAMS_BY_KIND: dict[str, type[BaseModel]] = {
    "video": VideoParams,
    "audio": AudioParams,
    "subtitle": SubtitleParams,
    "note": NoteParams,
    "contact_sheet": ContactSheetParams,
    "frames_zip": FramesZipParams,
}


class NewJobModel(_Strict):
    videoId: str = Field(pattern=_VIDEO_ID)
    kind: Literal["video", "audio", "subtitle", "note", "contact_sheet", "frames_zip"]  # frames_sharp = M5
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


def clip_problem(params: Mapping[str, Any], info: Mapping[str, Any] | None) -> str | None:
    """ตรวจช่วงเวลาและการแยก chapter กับข้อมูลคลิปที่เก็บไว้ (C1) ไม่มีข้อมูล = None (ตัวทำงานตรวจอีกรอบ)"""
    rng = params.get("range")
    split = bool(params.get("splitChapters"))
    if info is None or (rng is None and not split):
        return None
    if rng is not None:
        duration_ms = int(info.get("durationS") or 0) * 1000
        if info.get("isLive") or duration_ms <= 0:
            return "range needs a clip with a known duration"
        if rng["endMs"] > duration_ms + RANGE_TOLERANCE_MS:
            return f"range ends after the clip ({duration_ms} ms)"
    if split and len(info.get("chapters") or []) < 2:
        return "splitChapters needs a clip with at least 2 chapters"
    return None


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
        videos = ctx.videos
        if videos is not None:
            for item in body.items:
                if "range" not in item.params and not item.params.get("splitChapters"):
                    continue
                problem = clip_problem(item.params, videos.peek_cached(item.videoId))
                if problem is not None:
                    return error_response(422, "E_BAD_REQUEST", BAD_REQUEST_MESSAGE, f"{item.videoId}: {problem}")
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
