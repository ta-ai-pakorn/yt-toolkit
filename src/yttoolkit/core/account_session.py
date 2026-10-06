"""บัญชียูทูปชั่วคราว (M5 รอบ C spec 2.1-2.2): ถือการเข้าสู่ระบบได้ครั้งละหนึ่งบัญชี ในหน่วยความจำเท่านั้น

- import_text: ตรวจขนาด (≤ 1 MB) แล้วให้ parse (core/extractor.parse_account_cookies) อ่านเป็น jar ของ yt-dlp
  แทนบัญชีเดิม (ถ้ามี) และเริ่มนับเวลาใหม่ · ไม่มีอะไรลงดิสก์ ไม่ว่ารูปไหน (C8)
- ลบเองเมื่อ (C6): ครบ 2 ชั่วโมงหลังนำเข้า · ปิดโปรแกรม · งานในคิวที่ใช้บัญชีจบแล้วคิวว่างครบ 10 นาที (grace)
  การดึงข้อมูลคลิปหรือถ่ายภาพคมที่ใช้บัญชี (mark_used(None)) ไม่เริ่ม grace
- ทุกครั้งที่สถานะเปลี่ยนประกาศข่าว "account" ทาง publish: {active, expiresAt?, reason?} ไม่มีชื่อหรือค่าคุกกี้
- เธรดไหนเรียกก็ได้ (ล็อกเดียว) · publish / on_clear เรียกนอกล็อก
- ลำดับล็อก: busy() ถูกเรียก *ในล็อกของบัญชี* (job_ended ต้องเช็กคิวว่างกับตั้ง grace ในจังหวะเดียวกัน) จึงห้ามแตะล็อกของบัญชี
  หรือเรียกกลับเข้า AccountService และฝั่งคิวห้ามถือล็อกคิวหรือล็อกฐานข้อมูลค้างไว้ตอนเรียกเข้ามาที่นี่ (busy ใช้แค่ pending_count)
- timer ที่ตั้งไว้ยกเลิกไม่ได้ ใช้ generation / token เทียบ *ในล็อกเดียวกับที่ล้างสถานะ* (ไม่มีช่องว่างให้ re-import หรือ job_queued แทรก)
- เวลาลบเองยึดนาฬิกาจริง: timer ของ Windows ไม่นับเวลาที่เครื่องหลับ จึงให้ jar / status / mark_used / job_ended / job_queued
  เทียบ now() กับเวลาลบเองทุกครั้ง เลยแล้ว = ลบในล็อกเดียวกันนั้นเลย (timer ยังเป็นตัวปลุกให้ประกาศข่าวตรงเวลา)
  ลบแล้ว generation เปลี่ยน timer ที่ครบทีหลังจึงไม่ลบซ้ำ ไม่ประกาศซ้ำ
- ลบแล้ว jar เดิมถูกปล่อยให้ GC เก็บ (ไม่ได้ลบค่าในหน่วยความจำทิ้ง: ภัยที่กันคือไฟล์บนดิสก์และ log ไม่ใช่การอ่านหน่วยความจำ)
core ไม่ import api/ หรือ platform/ และโมดูลนี้ไม่ import yt_dlp (ตัวอ่านไฟล์ส่งมาจากผู้สร้าง)
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from .yterrors import YtError

log = logging.getLogger("yttoolkit")

MAX_IMPORT_BYTES = 1_048_576  # spec 1.2 / 2.1: ไฟล์ cookies.txt ไม่เกิน 1 MB
EXPIRY_S = 2 * 60 * 60  # C6 (c): ลบเองเมื่อครบ 2 ชั่วโมงหลังนำเข้า
GRACE_S = 10 * 60  # C6 (a): คิวว่างครบ 10 นาทีหลังงานที่ใช้บัญชีจบ (planner ruling spec 2.2)
CLEAR_REASONS = frozenset({"manual", "queue_done", "expired", "shutdown"})

Schedule = Callable[[float, Callable[[], None]], None]
Publish = Callable[[str, dict], None]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _timer_schedule(delay: float, fn: Callable[[], None]) -> None:
    timer = threading.Timer(max(delay, 0.0), fn)
    timer.daemon = True  # timer ที่ค้างอยู่ไม่ขวางการปิดโปรแกรม (ปิดโปรแกรม = clear("shutdown") อยู่แล้ว)
    timer.start()


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds")


class AccountService:
    """C3: import_text / clear / status / jar / mark_used และ job_queued / job_ended (QueueListener ของคิว)"""

    def __init__(
        self,
        parse: Callable[[str], Any],
        *,
        publish: Publish | None = None,
        busy: Callable[[], bool] = lambda: False,
        on_clear: Callable[[], None] | None = None,
        now: Callable[[], datetime] = _utcnow,
        schedule: Schedule = _timer_schedule,
        expiry_s: float = EXPIRY_S,
        grace_s: float = GRACE_S,
    ) -> None:
        """parse(text) -> jar (YtError E_COOKIES_INVALID เมื่ออ่านไม่ได้) · busy() = คิวมีงานรอหรือกำลังทำ
        on_clear() = ทิ้งข้อมูลที่ได้มาด้วยบัญชีนี้ (VideoService.forget_signed_in) เรียกเมื่อลบหรือแทนบัญชี"""
        self._parse = parse
        self._publish = publish
        self._busy = busy
        self._on_clear = on_clear
        self._now = now
        self._schedule = schedule
        self._expiry_s = expiry_s
        self._grace_s = grace_s
        self._lock = threading.Lock()
        self._jar: Any | None = None
        self._imported_at: datetime | None = None
        self._expires_at: datetime | None = None
        self._generation = 0  # เพิ่มทุกครั้งที่นำเข้าหรือลบ timer ที่ค้างจากรุ่นก่อนจึงไม่มีผล
        self._grace_seq = 0
        self._grace_token: int | None = None  # grace ที่กำลังนับ (None = ไม่ได้นับ)
        self._grace_until: datetime | None = None
        self._used = False
        self._job_used = False  # spec 2.2 (a): งานในคิวที่ใช้บัญชีจบไปแล้วอย่างน้อยหนึ่งงาน
        self._jobs: set[str] = set()  # งานที่กำลังใช้บัญชีอยู่ (job id)

    # ---------- อ่านสถานะ ----------

    def jar(self) -> Any | None:
        with self._lock:
            cleared = self._expire_due_locked()
            jar = self._jar
        self._after_clear(cleared)
        return jar

    def status(self) -> dict:
        with self._lock:
            cleared = self._expire_due_locked()
            status = self._status_locked()
        self._after_clear(cleared)
        return status

    def _status_locked(self) -> dict:
        if self._jar is None or self._imported_at is None:
            return {"active": False, "used": False}
        return {
            "active": True,
            "importedAt": _iso(self._imported_at),
            "expiresAt": _iso(self._deadline_locked()),
            "used": self._used,
        }

    def _deadline_locked(self) -> datetime:
        """เวลาที่จะลบเองเร็วที่สุด: ครบ 2 ชั่วโมง หรือ grace ที่กำลังนับ"""
        assert self._expires_at is not None
        if self._grace_until is not None and self._grace_until < self._expires_at:
            return self._grace_until
        return self._expires_at

    # ---------- นำเข้า / ลบ ----------

    def import_text(self, text: str) -> dict:
        """นำเข้า cookies.txt (ข้อความ) แทนบัญชีเดิม คืน status() · ใช้ไม่ได้ = YtError E_COOKIES_INVALID บัญชีเดิมไม่เปลี่ยน
        ตั้ง timer ลบเองไม่ได้ (schedule พัง) = ถอยสถานะกลับเป็นก่อนนำเข้าแล้วส่ง error ต่อ"""
        if not isinstance(text, str):
            raise YtError("E_COOKIES_INVALID", f"expected text, got {type(text).__name__}")
        if len(text.encode("utf-8")) > MAX_IMPORT_BYTES:
            raise YtError("E_COOKIES_INVALID", f"file larger than {MAX_IMPORT_BYTES} bytes")
        jar = self._parse(text)  # ตรวจก่อนแตะสถานะ: ไฟล์เสีย = บัญชีเดิมยังอยู่ครบ
        with self._lock:
            snapshot = self._snapshot_locked()
            replaced = self._jar is not None
            self._generation += 1
            generation = self._generation
            self._jar = jar
            self._imported_at = self._now()
            self._expires_at = self._imported_at + timedelta(seconds=self._expiry_s)
            self._grace_token = None
            self._grace_until = None
            self._used = False
            self._job_used = False
            self._jobs = set()
            status = self._status_locked()
        try:
            self._schedule(self._expiry_s, lambda: self._expire(generation))
        except Exception:
            with self._lock:
                if self._generation == generation:  # ยังเป็นรุ่นของเรา (ไม่มีใครนำเข้าหรือลบแทรก): คืนสถานะเดิม
                    self._restore_locked(snapshot)
            raise
        if replaced:
            self._forget_signed_in()
        log.info("นำเข้าบัญชียูทูปชั่วคราวแล้ว ลบเองภายใน %s", status["expiresAt"])
        self._announce({"active": True, "expiresAt": status["expiresAt"]})
        return status

    def clear(self, reason: str) -> dict:
        """ลบบัญชีที่ถืออยู่ (ไม่มี = ไม่ทำอะไร ไม่ประกาศ) คืน status() · งานที่กำลังโหลดด้วยบัญชีนี้ใช้ต่อจนจบ"""
        return self._clear(reason)

    # ---------- การใช้งาน ----------

    def mark_used(self, job_id: str | None) -> None:
        """มีคำขอที่ต้องใช้บัญชี: job_id = งานในคิว (นับเข้ากฎคิวว่าง) · None = หน้าเว็บ/ถ่ายภาพคม (ไม่นับ)"""
        with self._lock:
            cleared = self._expire_due_locked()
            if self._jar is not None:
                self._used = True
                if job_id is not None:
                    self._jobs.add(job_id)
        self._after_clear(cleared)

    # ---------- QueueListener (core/queue.py เรียก) ----------

    def job_queued(self) -> None:
        """มีงานเข้าคิว (ใหม่หรือกดลองใหม่): ยกเลิก grace ที่กำลังนับ"""
        with self._lock:
            cleared = self._expire_due_locked()
            event = None
            if self._grace_token is not None:
                self._grace_token = None
                self._grace_until = None
                event = {"active": True, "expiresAt": _iso(self._deadline_locked())}
        self._after_clear(cleared)
        if event is not None:
            self._announce(event)

    def job_ended(self, job_id: str) -> None:
        """งานจบ (เสร็จ พลาด ยกเลิก หยุดกลางคัน): งานที่ใช้บัญชีจบแล้ว + คิวว่าง = เริ่ม grace"""
        with self._lock:
            cleared = self._expire_due_locked()
            token = self._start_grace_locked(job_id)
            event = None if token is None else {"active": True, "expiresAt": _iso(self._deadline_locked())}
        self._after_clear(cleared)
        if token is None or event is None:
            return
        try:
            self._schedule(self._grace_s, lambda: self._grace_due(token))
        except Exception:
            with self._lock:
                if self._grace_token == token:  # ไม่มี timer = ไม่มี grace: ถอน token ให้ job_ended ครั้งหน้าลองเริ่มใหม่ได้
                    self._grace_token = None
                    self._grace_until = None
            raise
        log.info("คิวว่างแล้ว ลบบัญชียูทูปชั่วคราวในอีก %d วินาที", int(self._grace_s))
        self._announce(event)

    # ---------- ภายใน ----------

    def _start_grace_locked(self, job_id: str) -> int | None:
        """เรียกในล็อก: นับงานที่ใช้บัญชีที่จบ แล้วเริ่ม grace ถ้าครบเงื่อนไข คืน token ของ grace ใหม่ (None = ไม่เริ่ม)"""
        if job_id in self._jobs:
            self._jobs.discard(job_id)
            if self._jar is not None:
                self._job_used = True
        if self._jar is None or not self._job_used or self._grace_token is not None:
            return None
        if self._busy():
            return None
        self._grace_seq += 1
        token = self._grace_seq
        self._grace_token = token
        self._grace_until = self._now() + timedelta(seconds=self._grace_s)
        return token

    def _expire(self, generation: int) -> None:
        self._clear("expired", generation=generation)

    def _grace_due(self, token: int) -> None:
        self._clear("queue_done", token=token)

    def _clear(self, reason: str, *, generation: int | None = None, token: int | None = None) -> dict:
        """ล้างสถานะ: generation / token (ถ้าให้มา) ต้องยังตรงในล็อกเดียวกับที่ล้าง ไม่ตรง = timer เก่า ไม่ทำอะไร
        เลยเวลาลบเองตามนาฬิกาจริงไปแล้ว = ลบด้วยเหตุผลของเวลานั้น (expired / queue_done) แทน · ประกาศนอกล็อกครั้งเดียว"""
        if reason not in CLEAR_REASONS:
            raise ValueError(f"reason ไม่รู้จัก: {reason!r}")
        with self._lock:
            cleared = self._expire_due_locked()
            if cleared is None and self._jar is not None:
                stale = generation is not None and generation != self._generation
                stale = stale or (token is not None and token != self._grace_token)
                if not stale:
                    cleared = self._clear_locked(reason)
            status = self._status_locked()
        self._after_clear(cleared)
        return status

    def _expire_due_locked(self) -> str | None:
        """เรียกในล็อก: เลยเวลาลบเองตามนาฬิกาจริงแล้ว = ล้างเลย คืนเหตุผล (expired / queue_done) ให้ประกาศนอกล็อก"""
        if self._jar is None or self._expires_at is None or self._now() < self._deadline_locked():
            return None
        grace_first = self._grace_until is not None and self._grace_until < self._expires_at
        return self._clear_locked("queue_done" if grace_first else "expired")

    def _clear_locked(self, reason: str) -> str:
        """เรียกในล็อก: ทิ้ง jar และสถานะทั้งหมด เปลี่ยน generation (timer ที่ค้างอยู่จึงไม่มีผล) คืนเหตุผลให้ _after_clear"""
        self._generation += 1
        self._jar = None
        self._imported_at = None
        self._expires_at = None
        self._grace_token = None
        self._grace_until = None
        self._used = False
        self._job_used = False
        self._jobs = set()
        return reason

    def _after_clear(self, reason: str | None) -> None:
        """นอกล็อก: หลังล้างสถานะหนึ่งครั้ง (reason ไม่ใช่ None) ทิ้งข้อมูลที่ได้ด้วยบัญชีแล้วประกาศหนึ่งครั้ง"""
        if reason is None:
            return
        self._forget_signed_in()
        log.info("ลบบัญชียูทูปชั่วคราวออกจากแอพแล้ว (%s)", reason)
        self._announce({"active": False, "reason": reason})

    def _snapshot_locked(self) -> tuple:
        return (
            self._generation, self._jar, self._imported_at, self._expires_at, self._grace_token,
            self._grace_until, self._used, self._job_used, set(self._jobs),
        )

    def _restore_locked(self, snapshot: tuple) -> None:
        (self._generation, self._jar, self._imported_at, self._expires_at, self._grace_token,
         self._grace_until, self._used, self._job_used, self._jobs) = snapshot

    def _forget_signed_in(self) -> None:
        if self._on_clear is None:
            return
        try:
            self._on_clear()
        except Exception:
            log.exception("ล้างข้อมูลคลิปที่ได้มาด้วยบัญชีไม่สำเร็จ")

    def _announce(self, data: dict) -> None:
        if self._publish is None:
            return
        try:
            self._publish("account", data)
        except Exception:
            log.exception("ประกาศสถานะบัญชียูทูปไม่สำเร็จ")
