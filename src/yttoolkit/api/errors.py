from __future__ import annotations

import json
import logging
import re
from pathlib import Path  # noqa: F401  เทสเดิมแก้ errors.Path.home (คลาสเดียวกับที่ redact.py ใช้)
from urllib.parse import quote

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
    log.error("เกิดข้อผิดพลาดที่ไม่ได้คาดไว้ที่ %s %s code=E_UNKNOWN", request.method, request.url.path, exc_info=exc)
    return error_response(500, "E_UNKNOWN", UNKNOWN_MESSAGE, str(exc))


ERROR_BODY_PEEK = 64 * 1024  # อ่านรหัสจาก body ก้อนแรกที่ไม่เกินเท่านี้
_CODE = re.compile(r"E_[A-Z0-9_]{1,40}")


def _error_code(body: bytes) -> str:
    if len(body) > ERROR_BODY_PEEK:
        return "?"
    try:
        code = json.loads(body)["error"]["code"]
    except (ValueError, UnicodeDecodeError, KeyError, TypeError):
        return "?"
    return code if isinstance(code, str) and _CODE.fullmatch(code) else "?"


def _log_api_error(scope: dict, status: int, code: str) -> None:
    # 404 = คำตอบ "ยังไม่มี" ปกติ (เช่น GET /videos/{id}/sharp) เป็น DEBUG ซึ่งไม่ถูกเขียน (root เป็น INFO)
    level = logging.DEBUG if status == 404 else logging.WARNING if status >= 500 else logging.INFO
    # ไม่มี query string ไม่มี body ไม่มี detail: path ของ API มีแค่ id (videoId, jobId)
    # percent-encode อักขระอื่นทั้งหมด: path ที่มีขึ้นบรรทัด (/api/videos/bad%0Aid) ปลอมบรรทัด log ใหม่ไม่ได้
    path = quote(scope.get("path", ""), safe="/-_.~")
    log.log(level, "api_error method=%s path=%s status=%d code=%s", scope.get("method", "?"), path, status, code)


class ErrorLogMiddleware:
    """ASGI middleware ของ M6 รอบ B (spec 3.3): คำตอบ error ของ /api ทุกคำตอบลง app.log พร้อมรหัส

    วางนอกสุด (หลัง LocalOnlyMiddleware) จึงเห็น 403/421 ของ middleware นั้นด้วย · ส่งต่อทุกข้อความทันทีไม่แก้ไม่กักไว้
    exception ที่หลุดออกมาก่อนเริ่มตอบ = 500 E_UNKNOWN (ServerErrorMiddleware ด้านนอกเป็นตัวตอบ และ _unhandled_error
    เขียน traceback แยกอีกบรรทัด)
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        path = scope.get("path", "") if scope["type"] == "http" else ""
        if path != "/api" and not path.startswith("/api/"):
            await self.app(scope, receive, send)
            return
        state = {"status": 0, "json": False, "done": False}

        async def watch(message) -> None:
            if message["type"] == "http.response.start":
                state["status"] = message["status"]
                headers = dict(message.get("headers") or [])
                state["json"] = headers.get(b"content-type", b"").split(b";")[0].strip().lower() == b"application/json"
                state["done"] = message["status"] < 400
            elif message["type"] == "http.response.body" and not state["done"]:
                state["done"] = True
                code = _error_code(message.get("body", b"")) if state["json"] else "?"
                _log_api_error(scope, state["status"], code)
            await send(message)

        try:
            await self.app(scope, receive, watch)
        except Exception:
            if state["status"] == 0:
                _log_api_error(scope, 500, "E_UNKNOWN")
            raise


def install_error_handlers(app: FastAPI) -> None:
    """ให้ทุก error ตอบเป็นรูปแบบเดียวกัน {"error": {...}} แทน {"detail": ...} ของ FastAPI"""
    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unhandled_error)
