from __future__ import annotations

import os
from dataclasses import asdict
from typing import TYPE_CHECKING

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..core import tools
from .errors import error_response

if TYPE_CHECKING:
    from ..app import AppContext


class ShutdownBody(BaseModel):
    force: bool = False


def build_router(ctx: AppContext) -> APIRouter:
    router = APIRouter()

    def _health() -> dict:
        if ctx.health is not None:
            return ctx.health()
        return tools.collect_health(ctx.paths, ctx.plat, ctx.output_dir)

    @router.get("/ping")
    def ping() -> dict:
        return {"ok": True, "pid": os.getpid()}

    @router.get("/health")
    def health() -> dict:
        return {"version": ctx.version, "commit": ctx.commit, **_health()}

    @router.post("/tools/ffmpeg/install")
    def install_ffmpeg():
        try:
            tools.install_ffmpeg(ctx.paths, ctx.plat)
        except tools.ToolInstallError as error:
            return error_response(
                502, "E_TOOL_INSTALL_FAILED", "โหลดโปรแกรมที่ต้องใช้ไม่สำเร็จ ตรวจเน็ตแล้วกดลองใหม่", str(error)
            )
        return asdict(tools.ffmpeg_status(ctx.paths, ctx.plat))

    @router.post("/shutdown")
    def shutdown(background: BackgroundTasks, body: ShutdownBody | None = None):
        force = body.force if body else False
        pending = ctx.pending_jobs()
        if pending and not force:
            return JSONResponse(status_code=409, content={"pendingJobs": pending})
        background.add_task(ctx.request_shutdown)
        return {"ok": True}

    return router
