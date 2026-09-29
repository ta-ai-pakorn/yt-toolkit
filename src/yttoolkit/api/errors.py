from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

log = logging.getLogger("yttoolkit")

NOT_FOUND_MESSAGE = "ไม่พบสิ่งที่ขอ"
BAD_REQUEST_MESSAGE = "ข้อมูลที่ส่งมาไม่ถูกต้อง ลองรีเฟรชหน้าเว็บ"
UNKNOWN_MESSAGE = "มีบางอย่างผิดพลาด ถ่ายภาพหน้าจอนี้ส่งให้ผู้ดูแล"


def _redact_home(text: str) -> str:
    """แทนโฟลเดอร์ผู้ใช้ด้วย ~ เพื่อไม่ให้ชื่อผู้ใช้หลุดไปกับภาพหน้าจอที่ส่งต่อ"""
    home = str(Path.home())
    if not home.strip("/\\"):
        return text
    for variant in {home, home.replace("\\", "/")}:
        # ไม่แตะโฟลเดอร์ข้างเคียงที่ชื่อขึ้นต้นเหมือนกัน เช่น C:\Users\Som กับ C:\Users\Somchai
        text = re.sub(re.escape(variant) + r"(?![\w.\-])", "~", text, flags=re.IGNORECASE)
    return text


def error_body(code: str, message: str, detail: str | None = None) -> dict:
    if detail is not None:
        detail = _redact_home(detail)
    return {"error": {"code": code, "message": message, "detail": detail}}


def error_response(
    status: int, code: str, message: str, detail: str | None = None, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(status_code=status, content=error_body(code, message, detail), headers=headers)


async def _http_error(request: Request, exc: HTTPException) -> JSONResponse:
    detail = str(exc.detail) if exc.detail is not None else None
    if exc.status_code == 404:
        return error_response(404, "E_NOT_FOUND", NOT_FOUND_MESSAGE, detail, exc.headers)
    return error_response(exc.status_code, f"E_HTTP_{exc.status_code}", BAD_REQUEST_MESSAGE, detail, exc.headers)


async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return error_response(422, "E_BAD_REQUEST", BAD_REQUEST_MESSAGE, str(exc))


async def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    log.error("เกิดข้อผิดพลาดที่ไม่ได้คาดไว้ที่ %s %s", request.method, request.url.path, exc_info=exc)
    return error_response(500, "E_UNKNOWN", UNKNOWN_MESSAGE, str(exc))


def install_error_handlers(app: FastAPI) -> None:
    """ให้ทุก error ตอบเป็นรูปแบบเดียวกัน {"error": {...}} แทน {"detail": ...} ของ FastAPI"""
    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unhandled_error)
