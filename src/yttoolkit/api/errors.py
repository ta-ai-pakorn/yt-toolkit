from __future__ import annotations

from fastapi.responses import JSONResponse


def error_body(code: str, message: str, detail: str | None = None) -> dict:
    return {"error": {"code": code, "message": message, "detail": detail}}


def error_response(status: int, code: str, message: str, detail: str | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content=error_body(code, message, detail))
