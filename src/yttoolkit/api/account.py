"""API บัญชียูทูปชั่วคราว (M5 รอบ C spec 2.5): GET /cookies · POST /cookies/import · DELETE /cookies

ชื่อ path คงตาม PRD เดิม (/cookies) แต่ไม่มีไฟล์คุกกี้ใด ๆ: ทุกอย่างอยู่ในหน่วยความจำของ AccountService
คำขอที่เปลี่ยนสถานะผ่าน token + Origin ของ LocalOnlyMiddleware เหมือน API อื่น
body ของการนำเข้าไม่ถูก log และไม่ถูกสะท้อนกลับใน error (ตรวจรูปร่างเองแทน pydantic ที่ยกค่าที่ส่งมาใส่ข้อความ error)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from ..core.account_session import MAX_IMPORT_BYTES, import_size
from ..core.yterrors import MESSAGES, YtError
from .errors import BAD_REQUEST_MESSAGE, error_response

if TYPE_CHECKING:
    from ..app import AppContext

IMPORT_KEYS = frozenset({"text", "acceptWarning"})


def build_account_router(ctx: AppContext) -> APIRouter:
    router = APIRouter()
    accounts = ctx.accounts
    assert accounts is not None  # create_app เรียกต่อเมื่อมี ctx.accounts เท่านั้น

    @router.get("/cookies")
    def account_status() -> dict:
        return accounts.status()

    @router.post("/cookies/import", response_model=None)
    def import_account(body: Any = Body(...)) -> dict | JSONResponse:
        if not isinstance(body, dict) or set(body) - IMPORT_KEYS or not isinstance(body.get("text"), str):
            return error_response(422, "E_BAD_REQUEST", BAD_REQUEST_MESSAGE, "body must be {text, acceptWarning}")
        if body.get("acceptWarning") is not True:
            return error_response(409, "E_BAD_REQUEST", BAD_REQUEST_MESSAGE, "acceptWarning must be true")
        try:
            if import_size(body["text"]) > MAX_IMPORT_BYTES:
                detail = f"file larger than {MAX_IMPORT_BYTES} bytes"
                return error_response(413, "E_COOKIES_INVALID", MESSAGES["E_COOKIES_INVALID"], detail)
            return accounts.import_text(body["text"])
        except YtError as exc:
            return error_response(422, exc.code, exc.message, exc.detail or None)

    @router.delete("/cookies")
    def delete_account() -> dict:
        return accounts.clear("manual")

    return router
