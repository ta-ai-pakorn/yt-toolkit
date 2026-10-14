"""API ข้อมูลชั่วคราว (M6 รอบ A, FR-SET-6): GET /storage (ขนาด) · POST /storage/clear (ล้าง)

POST ผ่าน token + Origin ของ LocalOnlyMiddleware เหมือนคำขออื่นที่ไม่ใช่ GET · body ไม่ถูกอ่าน
route เป็น `def` ธรรมดา (เดินดิสก์) FastAPI จึงส่งไปรันใน threadpool · OSError ที่ไม่คาดคิด = 500 E_UNKNOWN (M6 รอบ B)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..core.storage import StorageService

if TYPE_CHECKING:
    from ..app import AppContext

NO_STORE = {"Cache-Control": "no-store"}


def build_storage_router(ctx: AppContext) -> APIRouter:
    router = APIRouter()
    assert ctx.cache_root is not None  # create_app เรียกต่อเมื่อมี ctx.cache_root เท่านั้น
    service = StorageService(ctx.cache_root, ctx.paths.work, queue=ctx.queue, captures=ctx.captures)

    @router.get("/storage")
    def storage_usage() -> JSONResponse:
        return JSONResponse(service.usage().to_api(), headers=NO_STORE)

    @router.post("/storage/clear")
    def storage_clear() -> JSONResponse:
        return JSONResponse({"freedBytes": service.clear()}, headers=NO_STORE)

    return router
