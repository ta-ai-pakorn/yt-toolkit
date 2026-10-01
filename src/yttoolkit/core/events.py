"""ตัวกระจายข่าวงานในคิว (สัญญา C6): คิวเรียก publish / job_updated แล้วทุกคนที่ subscribe ได้รับ

ความคืบหน้าของงานหนึ่งตัวส่งได้ไม่เกิน 4 ครั้งต่อวินาที (AC-Q-08): ค่าที่มาถี่กว่านั้นรวมเป็น patch เดียว
แล้วส่งตอนครบ 0.25 วินาที ค่าสุดท้ายจึงไม่หาย ข่าวอื่น (สร้างงาน หยุดคิว ปิดแอพ) ส่งทันที

ใช้ได้จากหลายเธรด: คิวงานรันในเธรดของตัวเอง ส่วนสตรีม SSE รอข่าวผ่าน worker thread ของ anyio
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final


@dataclass(frozen=True)
class Event:
    name: str  # "job.created" | "job.updated" | "queue.paused" | "queue.resumed" | "app.shutdown"
    data: dict


CLOSED: Final = object()  # Subscription.get คืนค่านี้หลังปิด (ทั้งปิดทั้ง bus และปิดเฉพาะตัว)


class Subscription:
    """กล่องข่าวของผู้ฟังหนึ่งคน ข่าวที่ค้างอยู่ตอนปิดยังอ่านได้ครบก่อนได้ CLOSED"""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._cond = threading.Condition()
        self._items: deque[Event] = deque()
        self._closed = False

    def get(self, timeout: float) -> Event | None | object:
        """ข่าวถัดไป, None เมื่อรอครบ timeout แล้วไม่มีข่าว, CLOSED เมื่อปิดแล้วและอ่านข่าวหมดแล้ว"""
        with self._cond:
            self._cond.wait_for(lambda: self._items or self._closed, timeout=max(timeout, 0))
            if self._items:
                return self._items.popleft()
            return CLOSED if self._closed else None

    def close(self) -> None:
        self._mark_closed()
        self._bus._unsubscribe(self)

    def _put(self, event: Event, limit: int) -> bool:
        """คืน False เมื่อกล่องเต็ม (ผู้ฟังอ่านไม่ทัน) กล่องนั้นจะถูกปิด"""
        with self._cond:
            if self._closed:
                return True
            if len(self._items) >= limit:
                self._closed = True
                self._cond.notify_all()
                return False
            self._items.append(event)
            self._cond.notify_all()
            return True

    def _mark_closed(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()


@dataclass
class _JobThrottle:
    last_emit: float | None = None
    pending: dict = field(default_factory=dict)
    scheduled: bool = False


def _timer_schedule(delay: float, fn: Callable[[], None]) -> None:
    timer = threading.Timer(max(delay, 0.0), fn)
    timer.daemon = True  # ไม่ให้ timer ที่ค้างอยู่ขวางการปิดโปรแกรม
    timer.start()


class EventBus:
    MIN_INTERVAL_S = 0.25
    # ผู้ฟังที่ค้างข่าวเกินนี้ถือว่าหลุด ปิดกล่องทิ้ง หน้าเว็บจะต่อใหม่แล้วโหลดรายการงานใหม่เอง (C12)
    MAX_PENDING = 1000
    # จำเวลาส่งล่าสุดของงานไว้ไม่เกินเท่านี้ เกินแล้วล้างงานที่เงียบไปนานพอแล้วออก
    _MAX_TRACKED_JOBS = 256

    def __init__(
        self,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        schedule: Callable[[float, Callable[[], None]], None] | None = None,
    ) -> None:
        self._monotonic = monotonic
        self._schedule = schedule or _timer_schedule
        self._lock = threading.Lock()
        self._subs: list[Subscription] = []
        self._jobs: dict[str, _JobThrottle] = {}
        self._closed = False

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subs)

    def subscribe(self) -> Subscription:
        sub = Subscription(self)
        with self._lock:
            if self._closed:
                sub._mark_closed()
            else:
                self._subs.append(sub)
        return sub

    def publish(self, name: str, data: dict) -> None:
        with self._lock:
            if not self._closed:
                self._broadcast(Event(name, data))

    def job_updated(self, job_id: str, fields: dict) -> None:
        delay: float | None = None
        with self._lock:
            if self._closed:
                return
            now = self._monotonic()
            state = self._jobs.get(job_id)
            if state is None:
                self._forget_quiet_jobs(now)
                state = self._jobs[job_id] = _JobThrottle()
            state.pending.update(fields)
            if state.scheduled:
                return
            if state.last_emit is None or now - state.last_emit >= self.MIN_INTERVAL_S:
                self._emit(job_id, state, now)
                return
            state.scheduled = True
            delay = state.last_emit + self.MIN_INTERVAL_S - now
        # เรียกนอก lock: ตัวตั้งเวลาบางแบบอาจเรียก flush กลับมาทันที
        self._schedule(delay, lambda: self._flush(job_id))

    def close(self) -> None:
        with self._lock:
            self._closed = True
            subs, self._subs = self._subs, []
            self._jobs.clear()
        for sub in subs:
            sub._mark_closed()

    def _flush(self, job_id: str) -> None:
        with self._lock:
            state = self._jobs.get(job_id)
            if self._closed or state is None:
                return
            state.scheduled = False
            if state.pending:
                self._emit(job_id, state, self._monotonic())

    def _emit(self, job_id: str, state: _JobThrottle, now: float) -> None:
        """เรียกขณะถือ lock ส่งข่าวใน lock ทำให้ทุกคนได้ข่าวเรียงลำดับเดียวกัน"""
        data = {"id": job_id, **state.pending}
        state.pending = {}
        state.last_emit = now
        self._broadcast(Event("job.updated", data))

    def _broadcast(self, event: Event) -> None:
        overflowed = [sub for sub in self._subs if not sub._put(event, self.MAX_PENDING)]
        if overflowed:
            self._subs = [sub for sub in self._subs if sub not in overflowed]

    def _forget_quiet_jobs(self, now: float) -> None:
        if len(self._jobs) < self._MAX_TRACKED_JOBS:
            return
        quiet = [
            job_id
            for job_id, state in self._jobs.items()
            if not state.scheduled and (state.last_emit is None or now - state.last_emit >= self.MIN_INTERVAL_S)
        ]
        for job_id in quiet:
            del self._jobs[job_id]

    def _unsubscribe(self, sub: Subscription) -> None:
        with self._lock:
            if sub in self._subs:
                self._subs.remove(sub)
