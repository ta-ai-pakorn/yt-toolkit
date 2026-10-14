"""API รายงานแจ้งปัญหา (M6 รอบ B spec 2.1 · PRD ข้อ 7.1): POST /diagnostics

POST ไม่ใช่ GET: error ที่ไม่ใช่งานในคิวส่ง code + detail มาจากหน้าเว็บ (ข้อความเทคนิคต้องไม่อยู่ใน URL)
และรายงานมี log ล่าสุด จึงต้องผ่าน token + Origin ของ LocalOnlyMiddleware เหมือนคำขออื่นที่ไม่ใช่ GET
ตรวจ body เอง (ไม่ใช้ pydantic ที่ยกค่าที่ส่งมาใส่ข้อความ error) · ไม่เคยตอบ 404: ปุ่มต้องได้รายงานเสมอ
ไม่ import yt_dlp หรือ extractor (เวอร์ชัน yt-dlp มาจาก tools.ytdlp_status ที่ import extractor เองตอนเรียก)
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from ..core import tools
from ..core.diagnostics import ErrorSection, ReportInputs, build_report
from ..core.queue import job_titles
from .errors import BAD_REQUEST_MESSAGE, error_response

if TYPE_CHECKING:
    from ..app import AppContext

log = logging.getLogger("yttoolkit")

MAX_DETAIL = 4000  # เท่ากับ MAX_DETAIL ของ web/src/lib/report.ts
# ช่องที่รับ: รูปแบบที่ต้องตรงทั้งค่า (fullmatch) · ข้อความ error บอกแค่ชื่อช่องกับกฎ ไม่ยกค่าที่ส่งมา
PATTERNS: dict[str, str] = {
    "jobId": r"[A-Za-z0-9_-]{1,64}",
    "code": r"E_[A-Z0-9_]{1,40}",
    "context": r"[a-z][a-z0-9-]{0,31}",
    "videoId": r"[A-Za-z0-9_-]{11}",
}
FIELDS = frozenset({*PATTERNS, "detail"})
_COMPILED = {key: re.compile(rule) for key, rule in PATTERNS.items()}
# สถานะ yt-dlp / ffmpeg / JS runtime จำไว้เท่านี้ (ต่อแอพ): import yt_dlp ครั้งแรกกับ subprocess สองตัวช้า
# ส่วน error และ log ล่าสุดไม่เคยจำ · ระหว่างติดตั้ง ffmpeg ไม่จำ (สถานะกำลังเปลี่ยน)
STATUS_CACHE_S = 60.0


def parse_body(raw: bytes) -> dict[str, str] | str:
    """body ที่ผ่านกฎ (ทุกช่องไม่บังคับ {} ก็ได้) หรือข้อความอังกฤษคงที่ที่บอกว่าผิดกฎข้อไหน"""
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeDecodeError, RecursionError):  # RecursionError: [[[[... ซ้อนลึกเกิน
        return "body must be a JSON object"
    if not isinstance(body, dict):
        return "body must be a JSON object"
    if set(body) - FIELDS:
        return "body has an unknown field"
    for key, value in body.items():
        if not isinstance(value, str):
            return f"{key} must be a string"
        if key == "detail":
            if len(value) > MAX_DETAIL:
                return f"detail longer than {MAX_DETAIL} characters"
        elif not _COMPILED[key].fullmatch(value):
            return f"{key} must match ^{PATTERNS[key]}$"
    return body


def _video_row(ctx: AppContext, video_id: str | None) -> tuple[str, str | None, str]:
    """(ชื่อคลิป, chapters_json, ชื่อช่อง) จากตาราง videos · ไม่มีแถวหรืออ่านไม่ได้ = ("", None, "")"""
    if not video_id or ctx.db is None:
        return "", None, ""
    try:
        rows = ctx.db.execute("SELECT title, chapters_json, channel FROM videos WHERE video_id = ?", (video_id,))
    except sqlite3.Error:
        return "", None, ""
    if not rows:
        return "", None, ""
    return str(rows[0]["title"] or ""), rows[0]["chapters_json"], str(rows[0]["channel"] or "")


@dataclass(frozen=True)
class _NoJob:
    """ไม่มีงานในคิว: job_titles ใช้แค่ชื่อ chapter ของคลิป"""

    title: str = ""
    params: dict | None = None


@dataclass(frozen=True)
class ToolStatuses:
    ytdlp: tools.ToolStatus
    ffmpeg: tools.ToolStatus
    js_runtime: tools.ToolStatus


def tool_statuses(ctx: AppContext) -> ToolStatuses:
    return ToolStatuses(
        ytdlp=tools.ytdlp_status(lookup_latest=False),  # ไม่ถาม PyPI รายงานไม่ต่อเน็ต
        ffmpeg=tools.ffmpeg_status(ctx.paths, ctx.plat),
        js_runtime=tools.find_js_runtime(ctx.plat),
    )


def collect_inputs(ctx: AppContext, body: dict[str, str], statuses: ToolStatuses | None = None) -> ReportInputs:
    """ข้อมูลของรายงาน: งานในคิวก่อน (jobId ที่มีอยู่) ไม่มีงานใช้ code/detail ที่ส่งมา ไม่ส่งอะไรเลย = ไม่มีหัวข้อ error"""
    job_id = body.get("jobId")
    job = ctx.queue.store.get(job_id) if job_id and ctx.queue is not None else None
    if job is not None:
        error: ErrorSection | None = ErrorSection(
            code=job.error_code, detail=job.error_detail, kind=job.kind, video_id=job.video_id
        )
        video_id: str | None = job.video_id
    elif body.keys() & {"code", "detail", "jobId"}:
        video_id = body.get("videoId")
        error = ErrorSection(code=body.get("code"), detail=body.get("detail"), video_id=video_id,
                             context=body.get("context"))  # fmt: skip
    else:
        error, video_id = None, body.get("videoId")
    row_title, chapters_json, channel = _video_row(ctx, video_id)
    # ชุดชื่อเดียวกับบรรทัด job_failed (job_titles): ชื่องาน โฟลเดอร์ playlist/ชุดงาน ชื่อช่อง ชื่อ chapter + ชื่อในตาราง videos
    names = job_titles(job if job is not None else _NoJob(), chapters_json, channel)
    titles = tuple(dict.fromkeys(t for t in (*names, row_title) if t))
    statuses = statuses or tool_statuses(ctx)
    return ReportInputs(
        now=datetime.now().astimezone(),
        version=ctx.version,
        commit=ctx.commit,
        os_version=ctx.plat.os_version(),
        ytdlp=statuses.ytdlp,
        ffmpeg=statuses.ffmpeg,
        js_runtime=statuses.js_runtime,
        account_active=bool(ctx.accounts.status()["active"]) if ctx.accounts is not None else False,
        error=error,
        log_dir=ctx.paths.logs,
        token=ctx.token,
        titles=titles,
    )


def build_diagnostics_router(ctx: AppContext) -> APIRouter:
    router = APIRouter()
    lock = threading.Lock()
    cache: dict[str, tuple[float, ToolStatuses]] = {}  # ต่อแอพ: ไม่มีสถานะค้างข้ามแอพ/ข้ามเทส

    def cached_statuses() -> ToolStatuses:
        with lock:
            if tools._ffmpeg_installing.is_set():
                cache.clear()
                return tool_statuses(ctx)
            now = time.monotonic()
            hit = cache.get("tools")
            if hit is not None and now - hit[0] < STATUS_CACHE_S:
                return hit[1]
            fresh = tool_statuses(ctx)
            cache["tools"] = (now, fresh)
            return fresh

    def collect(body: dict[str, str]) -> ReportInputs:
        return collect_inputs(ctx, body, cached_statuses())

    @router.post("/diagnostics", response_model=None)
    async def diagnostics(request: Request) -> JSONResponse:
        body = parse_body(await request.body())
        if isinstance(body, str):
            return error_response(422, "E_BAD_REQUEST", BAD_REQUEST_MESSAGE, body)
        inputs = await run_in_threadpool(collect, body)
        report = await run_in_threadpool(build_report, inputs)
        # หลังอ่าน log แล้วเท่านั้น (บรรทัดนี้ไม่อยู่ในรายงานของตัวเอง) · ค่าทุกช่องผ่านกฎแล้ว · ไม่เคย log detail
        code = inputs.error.code if inputs.error is not None and inputs.error.code else "-"
        log.info("diagnostics code=%s context=%s job=%s", code, body.get("context", "-"), body.get("jobId", "-"))
        return JSONResponse({"report": report}, headers={"Cache-Control": "no-store"})

    return router
