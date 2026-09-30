from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI

from .api.errors import install_error_handlers
from .api.routes import build_router
from .api.security import LocalOnlyMiddleware
from .api.static import mount_web
from .api.videos import build_videos_router
from .config import APP_NAME, Paths
from .core.db import Database
from .core.extractor import Extractor
from .core.videos import VideoService
from .platform import Platform


def _no_pending_jobs() -> int:
    return 0  # คิวงานมาใน M4


@dataclass
class AppContext:
    paths: Paths
    plat: Platform
    port: int
    token: str
    version: str
    commit: str | None
    output_dir: Path
    request_shutdown: Callable[[], None]
    pending_jobs: Callable[[], int] = _no_pending_jobs
    health: Callable[[], dict] | None = None
    extra_origins: tuple[str, ...] = ()
    # บริการของ M2 (run_app สร้างให้) ไม่มี = ไม่เปิด API ข้อมูลคลิป route เดิมทำงานตามปกติ
    db: Database | None = None
    videos: VideoService | None = None
    extractor: Extractor | None = None
    cache_root: Path | None = None
    fake: bool = False  # โหมดข้อมูลปลอม (serve + YT_TOOLKIT_FAKE=1) หน้าตรวจสุขภาพจะบอกไว้


def create_app(ctx: AppContext) -> FastAPI:
    app = FastAPI(title=APP_NAME, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.ctx = ctx
    install_error_handlers(app)
    app.include_router(build_router(ctx), prefix="/api")
    if ctx.videos is not None:
        app.include_router(build_videos_router(ctx), prefix="/api")
    mount_web(app, ctx.paths.web_dist, ctx.token)
    app.add_middleware(LocalOnlyMiddleware, port=ctx.port, token=ctx.token, extra_origins=ctx.extra_origins)
    return app
