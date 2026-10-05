"""API ถ่ายภาพคมตรงจุด (M5 รอบ B2 สัญญา C11): รายการ ถ่าย ลบ และเปิดโฟลเดอร์ ภาพที่ถ่าย

route เป็น `def` ธรรมดา (โหลดชิ้นวิดีโอ เรียก ffmpeg เขียนไฟล์) FastAPI จึงส่งไปรันใน threadpool
ไม่ผ่านคิว (E1) · ยูทูปขอยืนยันว่าไม่ใช่บอท = CaptureService พักคิวเองแล้ว route นี้จึงไม่เรียก on_bot_check ซ้ำ
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from ..core.capture import CAPTURE_FOLDER, Capture, CaptureRejected
from ..core.inputs import VIDEO_ID
from ..core.yterrors import YtError
from .errors import BAD_REQUEST_MESSAGE, error_response
from .videos import yt_error_response

if TYPE_CHECKING:
    from ..app import AppContext

log = logging.getLogger(__name__)

MAX_CAPTURE_MS = 172_800_000  # 48 ชั่วโมง (ยาวกว่านี้ CaptureService ปฏิเสธด้วยความยาวคลิปอยู่แล้ว)


class CaptureBody(BaseModel):
    """{tMs} อย่างเดียว (spec 3.3) key อื่น / ไม่ใช่จำนวนเต็ม / ติดลบ = 422"""

    model_config = ConfigDict(extra="forbid")
    tMs: StrictInt = Field(ge=0, le=MAX_CAPTURE_MS)


def build_captures_router(ctx: AppContext) -> APIRouter:
    service = ctx.captures
    cache_root = ctx.cache_root
    if service is None or cache_root is None:
        raise ValueError("ต้องมี captures และ cache_root ถึงจะเปิด API ถ่ายภาพคมได้")
    router = APIRouter()

    def item(video_id: str, capture: Capture) -> dict:
        """ภาพหนึ่งภาพในรูปของ API · url ต่อ ?v=<เวลาแก้ไขไฟล์> (ภาพ immutable ถ่ายใหม่ที่เวลาเดิมได้ URL ใหม่)"""
        try:
            version = f"?v={service.cache_path(video_id, capture).stat().st_mtime_ns}"
        except OSError:
            version = ""
        return {
            "id": capture.id,
            "tMs": capture.t_ms,
            "width": capture.width,
            "height": capture.height,
            "url": f"/api/cache/{video_id}/{CAPTURE_FOLDER}/{capture.file}{version}",
        }

    def invalid_id(video_id: str) -> JSONResponse:
        return yt_error_response(YtError("E_INVALID_INPUT", f"video id ไม่ถูกรูปแบบ: {video_id!r}"), "-")

    @router.get("/videos/{video_id}/captures", response_model=None)
    def list_captures(video_id: str) -> dict | JSONResponse:
        if not VIDEO_ID.fullmatch(video_id):
            return invalid_id(video_id)
        return {"captures": [item(video_id, capture) for capture in service.list(video_id)]}

    @router.post("/videos/{video_id}/captures", status_code=201, response_model=None)
    def create_capture(video_id: str, body: CaptureBody, response: Response) -> dict | JSONResponse:
        if not VIDEO_ID.fullmatch(video_id):
            return invalid_id(video_id)
        try:
            capture, created = service.capture(video_id, body.tMs)
        except CaptureRejected as exc:
            return error_response(422, "E_BAD_REQUEST", BAD_REQUEST_MESSAGE, f"{video_id}: {exc.detail}")
        except YtError as exc:
            return yt_error_response(exc, video_id)
        if not created:
            response.status_code = 200  # เวลาเดิมที่ถ่ายไว้แล้ว: คืนภาพเดิม (idempotent)
        return item(video_id, capture)

    @router.delete("/videos/{video_id}/captures/{capture_id}", status_code=204, response_model=None)
    def delete_capture(video_id: str, capture_id: str) -> Response | JSONResponse:
        try:
            service.delete(video_id, capture_id)
        except KeyError:
            raise HTTPException(status_code=404) from None
        except YtError as exc:
            return yt_error_response(exc, video_id)
        return Response(status_code=204)

    @router.post("/videos/{video_id}/captures/reveal")
    def reveal_captures(video_id: str) -> dict:
        folder: Path | None = service.reveal_dir(video_id) if VIDEO_ID.fullmatch(video_id) else None
        if folder is None:
            raise HTTPException(status_code=404)
        try:
            (ctx.open_folder or ctx.plat.open_folder)(folder)
        except OSError as exc:  # โฟลเดอร์หายไประหว่างทาง / เปิดไม่ได้: log แค่ชื่อชนิด error (ข้อความมี path เต็ม)
            log.warning("เปิดโฟลเดอร์ภาพที่ถ่ายไม่สำเร็จ (%s): %s", video_id, type(exc).__name__)
            raise HTTPException(status_code=404) from None
        return {"ok": True}

    return router
