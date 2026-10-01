"""API ตั้งค่า (สัญญา C5): ดู แก้ และเปิดโฟลเดอร์ปลายทาง

route เป็น `def` ธรรมดา (แตะดิสก์และฐานข้อมูล) FastAPI จึงส่งไปรันใน threadpool
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from ..core.settings import SettingsError, ensure_writable
from ..core.yterrors import MESSAGES
from .errors import BAD_REQUEST_MESSAGE, error_response

if TYPE_CHECKING:
    from ..app import AppContext

OUTPUT_NOT_WRITABLE_MESSAGE = "บันทึกลงโฟลเดอร์นี้ไม่ได้ ลองเปลี่ยนโฟลเดอร์ในหน้าตั้งค่า"
OUTPUT_DIR_BAD_MESSAGE = "ใส่ที่อยู่โฟลเดอร์แบบเต็ม เช่น C:\\Users\\ชื่อ\\Videos"
_MESSAGES = {
    "E_BAD_REQUEST": BAD_REQUEST_MESSAGE,
    "E_OUTPUT_NOT_WRITABLE": MESSAGES.get("E_OUTPUT_NOT_WRITABLE", OUTPUT_NOT_WRITABLE_MESSAGE),
}


def _settings_error(error: SettingsError) -> JSONResponse:
    if error.code == "E_BAD_REQUEST" and error.key == "outputDir":
        return error_response(422, error.code, OUTPUT_DIR_BAD_MESSAGE, error.detail)
    return error_response(422, error.code, _MESSAGES.get(error.code, BAD_REQUEST_MESSAGE), error.detail)


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

    return router
