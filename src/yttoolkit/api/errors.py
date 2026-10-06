from __future__ import annotations

import logging
from pathlib import Path  # noqa: F401  เทสเดิมแก้ errors.Path.home (คลาสเดียวกับที่ redact.py ใช้)

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException

from ..core.yterrors import MESSAGES
from ..redact import _home_aliases, redact_home  # noqa: F401  ย้ายไป redact.py (M5 รอบ C) ชื่อเดิมยังใช้ได้

log = logging.getLogger("yttoolkit")

NOT_FOUND_MESSAGE = "ไม่พบสิ่งที่ขอ"
BAD_REQUEST_MESSAGE = "ข้อมูลที่ส่งมาไม่ถูกต้อง ลองรีเฟรชหน้าเว็บ"
UNKNOWN_MESSAGE = MESSAGES["E_UNKNOWN"]
VALIDATION_DETAIL_MAX = 500


# ชื่อเดิม (ก่อน M4) ยังใช้อยู่ในโมดูลอื่น
_redact_home = redact_home


def error_body(code: str, message: str, detail: str | None = None) -> dict:
    if detail is not None:
        detail = redact_home(detail)
    return {"error": {"code": code, "message": message, "detail": detail}}


def error_response(
    status: int, code: str, message: str, detail: str | None = None, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(status_code=status, content=error_body(code, message, detail), headers=headers)


async def _http_error(request: Request, exc: HTTPException) -> Response:
    if exc.status_code in {204, 304}:
        return Response(status_code=exc.status_code, headers=exc.headers)  # แบบเดียวกับ Starlette: ห้ามมี body
    detail = str(exc.detail) if exc.detail is not None else None
    if exc.status_code == 404:
        return error_response(404, "E_NOT_FOUND", NOT_FOUND_MESSAGE, detail, exc.headers)
    return error_response(exc.status_code, f"E_HTTP_{exc.status_code}", BAD_REQUEST_MESSAGE, detail, exc.headers)


async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # ข้อความของ pydantic ยกค่าที่ส่งมาทั้งก้อน (เช่นข้อความยาว 20,000 ตัว) ตัดไว้ไม่ให้สะท้อนกลับยาว ๆ
    # ซ่อนโฟลเดอร์ผู้ใช้ก่อนตัด ไม่งั้นตัดกลาง path แล้วชื่อผู้ใช้ครึ่งหนึ่งจะหลุดไป
    detail = redact_home(str(exc))[:VALIDATION_DETAIL_MAX]
    return error_response(422, "E_BAD_REQUEST", BAD_REQUEST_MESSAGE, detail)


async def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    log.error("เกิดข้อผิดพลาดที่ไม่ได้คาดไว้ที่ %s %s", request.method, request.url.path, exc_info=exc)
    return error_response(500, "E_UNKNOWN", UNKNOWN_MESSAGE, str(exc))


def install_error_handlers(app: FastAPI) -> None:
    """ให้ทุก error ตอบเป็นรูปแบบเดียวกัน {"error": {...}} แทน {"detail": ...} ของ FastAPI"""
    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unhandled_error)
