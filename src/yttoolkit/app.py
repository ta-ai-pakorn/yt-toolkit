from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI

from .api.errors import install_error_handlers
from .api.routes import build_router
from .api.security import LocalOnlyMiddleware
from .api.settings import build_settings_router
from .api.static import mount_web
from .api.subtitles import build_subtitles_router
from .api.videos import build_videos_router
from .config import APP_NAME, Paths
from .core.comments import PinnedCommentService
from .core.db import Database
from .core.extractor import Extractor
from .core.subtitles import SubtitleService
from .core.videos import VideoService
from .platform import Platform

if TYPE_CHECKING:  # โมดูลของ M4 ที่ lane อื่นสร้าง ใช้แค่เป็นชนิดของฟิลด์
    from .core.events import EventBus
    from .core.media import MediaTools
    from .core.queue import QueueRunner
    from .core.settings import SettingsStore


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
    # บริการซับของ M3 (run_app สร้างให้) ไม่มี = ไม่เปิด API ซับ
    subtitles: SubtitleService | None = None
    # บริการคอมเมนต์ปักหมุด: router ข้อมูลคลิปสร้างให้ แล้ว router โน้ตใช้ตัวเดียวกัน (ใช้ cache ร่วมกัน)
    pinned: PinnedCommentService | None = None
    # บริการของ M4 (ไม่มี = ไม่เปิด API นั้น) settings = T2, events = T6, media = T5, queue = T11
    settings: SettingsStore | None = None
    queue: QueueRunner | None = None
    events: EventBus | None = None
    media: MediaTools | None = None
    on_bot_check: Callable[[], None] | None = None
    # ตัวแทน platform.reveal / open_folder (โหมดข้อมูลปลอมใช้ตัวที่ไม่เปิดหน้าต่างจริง) None = ใช้ ctx.plat
    reveal: Callable[[Path], None] | None = None
    open_folder: Callable[[Path], None] | None = None


def create_app(ctx: AppContext) -> FastAPI:
    app = FastAPI(title=APP_NAME, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.ctx = ctx
    install_error_handlers(app)
    app.include_router(build_router(ctx), prefix="/api")
    if ctx.videos is not None:
        app.include_router(build_videos_router(ctx), prefix="/api")
    if ctx.subtitles is not None:
        app.include_router(build_subtitles_router(ctx), prefix="/api")
    if ctx.settings is not None:
        app.include_router(build_settings_router(ctx), prefix="/api")
    mount_web(app, ctx.paths.web_dist, ctx.token)
    app.add_middleware(LocalOnlyMiddleware, port=ctx.port, token=ctx.token, extra_origins=ctx.extra_origins)
    return app
