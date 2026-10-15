"""API สถิติของฉัน (M6 รอบ C spec §2.2, PRD :625-626): GET /stats · POST /stats/reset

คำนวณในเครื่องจากตาราง jobs ไม่มีคำขอออกนอกเครื่อง (FR-STAT-3) · POST ผ่าน token + Origin ของ LocalOnlyMiddleware
route เป็น `def` ธรรมดา (อ่าน SQLite) FastAPI จึงส่งไปรันใน threadpool · ไม่อ่าน body
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .. import runstate
from ..core.stats import compute

if TYPE_CHECKING:
    from ..app import AppContext

NO_STORE = {"Cache-Control": "no-store"}


def build_stats_router(ctx: AppContext) -> APIRouter:
    router = APIRouter()
    db, settings = ctx.db, ctx.settings
    assert db is not None and settings is not None  # create_app เรียกต่อเมื่อมีทั้งสองอย่าง

    @router.get("/stats")
    def stats() -> JSONResponse:
        since = settings.get().get("statsResetAt")
        return JSONResponse(compute(db, since, datetime.now(UTC)), headers=NO_STORE)

    @router.post("/stats/reset")
    def stats_reset() -> JSONResponse:
        return JSONResponse({"since": settings.reset_stats(runstate.now_iso())}, headers=NO_STORE)

    return router
