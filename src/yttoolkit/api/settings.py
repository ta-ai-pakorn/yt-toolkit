"""API ตั้งค่า (สัญญา C5): ดู แก้ และเปิดโฟลเดอร์ปลายทาง · M6 รอบ A: สำรอง (export) และนำเข้า (import) ค่าตั้ง

route ส่วนใหญ่เป็น `def` ธรรมดา (แตะดิสก์และฐานข้อมูล) FastAPI จึงส่งไปรันใน threadpool
POST /settings/import เป็น async เพื่ออ่าน body ดิบเองทีละชิ้น (หยุดที่ 1 MB) แล้วส่งงานเขียนไปรันใน threadpool
body ของการนำเข้าไม่ถูก log และไม่ถูกยกกลับใน error (detail บอกชื่อ key อย่างมาก C4)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

from fastapi import APIRouter, Body, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response

from ..core.settings import EXPORT_APP, EXPORT_SCHEMA, SettingsError, ensure_writable
from ..core.yterrors import MESSAGES
from .errors import BAD_REQUEST_MESSAGE, error_response
from .videos import attachment_header

if TYPE_CHECKING:
    from ..app import AppContext

OUTPUT_NOT_WRITABLE_MESSAGE = "บันทึกลงโฟลเดอร์นี้ไม่ได้ ลองเปลี่ยนโฟลเดอร์ในหน้าตั้งค่า"
OUTPUT_DIR_BAD_MESSAGE = "ใส่ที่อยู่โฟลเดอร์แบบเต็ม เช่น C:\\Users\\ชื่อ\\Videos"
_MESSAGES = {
    "E_BAD_REQUEST": BAD_REQUEST_MESSAGE,
    "E_OUTPUT_NOT_WRITABLE": MESSAGES.get("E_OUTPUT_NOT_WRITABLE", OUTPUT_NOT_WRITABLE_MESSAGE),
}
# M6 รอบ A: ไฟล์ค่าตั้งใหญ่สุดที่รับ (เท่ากับ MAX_SETTINGS_FILE_BYTES ของเว็บ)
MAX_SETTINGS_IMPORT_BYTES = 1_048_576
EXPORT_FILE_PREFIX = "yt-toolkit-settings-"


def _settings_error(error: SettingsError) -> JSONResponse:
    if error.code == "E_SETTINGS_INVALID":
        return _invalid(error.detail)
    if error.code == "E_BAD_REQUEST" and error.key == "outputDir":
        return error_response(422, error.code, OUTPUT_DIR_BAD_MESSAGE, error.detail)
    return error_response(422, error.code, _MESSAGES.get(error.code, BAD_REQUEST_MESSAGE), error.detail)


def _invalid(detail: str, status: int = 422) -> JSONResponse:
    return error_response(status, "E_SETTINGS_INVALID", MESSAGES["E_SETTINGS_INVALID"], detail)


def _too_large() -> JSONResponse:
    return _invalid(f"file larger than {MAX_SETTINGS_IMPORT_BYTES} bytes", 413)


def _reject_constant(name: str) -> NoReturn:
    """NaN / Infinity / -Infinity ไม่ใช่ JSON จริง (json.loads ของ Python รับเอง ต้องปฏิเสธเอง)"""
    raise ValueError(f"{name} is not JSON")


def export_document(settings: dict[str, Any], now: datetime) -> dict[str, Any]:
    """เนื้อไฟล์สำรองค่าตั้ง: app + schema พอสำหรับตรวจตอนนำเข้า (ไม่มีอะไรเฉพาะยูทูป C12)"""
    return {
        "app": EXPORT_APP,
        "schema": EXPORT_SCHEMA,
        "exportedAt": now.astimezone(UTC).isoformat(timespec="seconds"),
        "settings": settings,
    }


def export_file_name(now: datetime) -> str:
    """yt-toolkit-settings-YYYY-MM-DD.json ตามวันที่ของเครื่อง"""
    return f"{EXPORT_FILE_PREFIX}{now.astimezone():%Y-%m-%d}.json"


def build_settings_router(ctx: AppContext) -> APIRouter:
    router = APIRouter()
    store = ctx.settings
    assert store is not None  # create_app เรียกต่อเมื่อมี ctx.settings เท่านั้น

    @router.get("/settings")
    def get_settings() -> dict:
        return store.get()

    @router.patch("/settings", response_model=None)
    def patch_settings(body: Any = Body(...)) -> dict | JSONResponse:
        try:
            return store.patch(body)
        except SettingsError as error:
            return _settings_error(error)

    @router.post("/settings/open-output", response_model=None)
    def open_output() -> dict | JSONResponse:
        folder: Path = store.output_dir()
        try:
            ensure_writable(folder)
        except SettingsError as error:
            return _settings_error(error)
        opener = ctx.open_folder or ctx.plat.open_folder
        opener(folder)
        return {"ok": True}

    @router.get("/settings/export")
    def export_settings() -> Response:
        """ไฟล์สำรองค่าตั้ง (FR-SET-7): GET ไม่ต้องใช้ token เหมือน GET /settings ที่ให้ค่าเดียวกันอยู่แล้ว"""
        now = datetime.now(UTC)
        text = json.dumps(export_document(store.exportable(), now), ensure_ascii=False, indent=2, allow_nan=False)
        name = export_file_name(now)
        return Response(
            (text + "\n").encode("utf-8"),
            media_type="application/json",
            headers={"Content-Disposition": attachment_header(name, name), "Cache-Control": "no-store"},
        )

    @router.post("/settings/import", response_model=None)
    async def import_settings(request: Request) -> dict | JSONResponse:
        """นำเข้าไฟล์สำรอง: ไม่เกิน 1 MB (413) · UTF-8 มี BOM ได้ · JSON จริง (ไม่มี NaN) · ตรวจทั้งไฟล์ก่อนเขียน"""
        length = request.headers.get("content-length", "")
        if length.isdigit() and int(length) > MAX_SETTINGS_IMPORT_BYTES:
            return _too_large()
        data = bytearray()
        async for chunk in request.stream():
            data += chunk
            if len(data) > MAX_SETTINGS_IMPORT_BYTES:
                return _too_large()
        try:
            text = bytes(data).decode("utf-8-sig")  # Notepad อาจใส่ BOM
        except UnicodeDecodeError:
            return _invalid("not UTF-8")
        try:
            doc = json.loads(text, parse_constant=_reject_constant)
        except (ValueError, RecursionError):
            return _invalid("not JSON")
        try:
            settings, warnings = await run_in_threadpool(store.import_settings, doc)
        except SettingsError as error:
            return _settings_error(error)
        return {"settings": settings, "warnings": warnings}

    return router
