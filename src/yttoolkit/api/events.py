"""สตรีมข่าวงานในคิวให้หน้าเว็บแบบ Server-Sent Events (สัญญา C6): GET /api/events

เริ่มด้วย `retry: 3000` (หลุดแล้วเบราว์เซอร์ต่อใหม่ใน 3 วินาที) ส่ง `: ping` เมื่อเงียบครบ 15 วินาที
และจบเองเมื่อ bus ปิด (ตอนปิดโปรแกรม) สตรีมที่เปิดค้างจึงไม่ขวางการปิดเซิร์ฟเวอร์
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator, Callable
from typing import TYPE_CHECKING

import anyio
import anyio.to_thread
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..core.events import CLOSED, Event, EventBus

if TYPE_CHECKING:
    from ..app import AppContext

RETRY = "retry: 3000\n\n"
PING = ": ping\n\n"
HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def format_event(e: Event) -> str:
    # json.dumps หนี \n และ \r ในข้อความให้แล้ว ข้อมูลหนึ่งข่าวจึงอยู่บรรทัด data เดียวเสมอ
    return f"event: {e.name}\ndata: {json.dumps(e.data, ensure_ascii=False, separators=(',', ':'))}\n\n"


async def sse_stream(
    bus: EventBus,
    *,
    ping_s: float = 15.0,
    poll_s: float = 1.0,
    monotonic: Callable[[], float] = time.monotonic,
) -> AsyncIterator[str]:
    sub = bus.subscribe()
    # limiter ของสตรีมนี้เอง (ไม่ใช้ตัวกลางของ anyio): สตรีมที่เปิดค้างกินเธรดรอข่าวเกือบตลอดเวลา
    # ถ้าใช้ตัวกลาง (40 เธรด ใช้ร่วมกับ route แบบ def ธรรมดาทุกตัว) แท็บที่เปิดค้างหลายแท็บจะแย่งเธรด
    # จน probe / ซับ / งานอื่นต้องรอคิว หนึ่งสตรีมรอทีละครั้งเดียวอยู่แล้ว จึงให้ 1 เธรดพอ
    limiter = anyio.CapacityLimiter(1)
    try:
        # จดเวลาก่อน yield: generator หยุดรอที่ yield จนผู้อ่านขอชิ้นถัดไป จดหลัง yield จะได้เวลาที่ช้าไป
        last_sent = monotonic()
        yield RETRY
        while True:
            item = await anyio.to_thread.run_sync(sub.get, poll_s, abandon_on_cancel=True, limiter=limiter)
            if item is CLOSED:
                return
            if isinstance(item, Event):
                last_sent = monotonic()
                yield format_event(item)
            elif monotonic() - last_sent >= ping_s:
                last_sent = monotonic()
                yield PING
    finally:
        # ปิดกล่อง = เธรดที่ยังรอ get อยู่ (กรณีผู้ชมปิดหน้าเว็บ) ตื่นและจบทันที
        sub.close()


def build_events_router(ctx: AppContext) -> APIRouter:
    router = APIRouter()

    @router.get("/events")
    async def events() -> StreamingResponse:
        # text/* ได้ "; charset=utf-8" ต่อท้ายจาก Starlette
        return StreamingResponse(sse_stream(ctx.events), media_type="text/event-stream", headers=HEADERS)

    return router
