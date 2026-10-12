"""ตัวรันคิวงาน (สัญญา C7): เลือกงานถัดไป เริ่มงาน และสรุปผลของแต่ละงาน

หน้าที่ของตัวรันคิวมีแค่ "จัดคิว" ส่วนการโหลดจริงเป็นของ handler แต่ละชนิดงาน (core/handlers.py)
- ทำพร้อมกันได้ไม่เกิน concurrency (1-3 จากหน้าตั้งค่า อ่านใหม่ทุกรอบ)
- งานที่ต้องคุยกับยูทูปเริ่มห่างกันแบบสุ่ม 2-5 วินาที (ไม่ให้ยูทูปมองว่าเป็นบอท)
- เบรกฉุกเฉิน: เจอรหัส E_BOT_CHECK (ดูที่รหัสเท่านั้น ไม่ดู HTTP status) พักทั้งคิว 10 นาที
- เน็ตหลุด (E_NETWORK) ลองใหม่เองสูงสุด 3 ครั้ง รอ 2, 5, 10 วินาที
- ยกเลิกงานที่กำลังรันได้ใน 3 วินาที (handler เช็ก ctx.cancelled() เป็นระยะ)
- เปิดโปรแกรมใหม่: งานที่ค้าง running กลายเป็น interrupted และล้างโฟลเดอร์ work/
"""

from __future__ import annotations

import logging
import math
import random
import shutil
import threading
import time
import traceback
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from ..redact import redact_log_detail
from .cancel import JobCancelled
from .download import YOUTUBE_KINDS
from .events import EventBus
from .jobs import Handler, InvalidTransition, Job, JobResult, JobStore, NewJob, is_stage
from .yterrors import MESSAGES, YtError

log = logging.getLogger("yttoolkit")

# M6 รอบ B (spec 3.2): ความยาวสูงสุดของ detail ในบรรทัด job_failed (หลังซ่อนข้อมูลแล้ว)
JOB_FAILED_DETAIL_MAX = 2000


def job_failed_message(job: Job, code: str, detail: str | None, exc: BaseException | None) -> str:
    """บรรทัด job_failed ของ app.log: ฟิลด์ ASCII key=value (ไม่ต้องมีข้อความไทยใหม่) ตามด้วย traceback (ถ้ามี)

    detail และ traceback ผ่าน redact_log_detail ที่นี่ที่เดียว (C5) พร้อมชื่องาน: ข้อความของ OSError ที่มีชื่อไฟล์
    ของคลิปก็ถูกปิดด้วย · traceback อยู่ในข้อความเอง ไม่ใช้ exc_info จึงผ่านตัวปิดชื่อคลิปด้วย
    """
    titles = (job.title,)
    text = redact_log_detail(detail or "-", titles)
    if len(text) > JOB_FAILED_DETAIL_MAX:
        text = text[: JOB_FAILED_DETAIL_MAX - 1] + "…"
    text = text.replace("\r", "\\r").replace("\n", "\\n")
    line = f"job_failed id={job.id} kind={job.kind} code={code} detail={text}"
    if exc is None:
        return line
    trace = redact_log_detail("".join(traceback.format_exception(exc)), titles)
    return f"{line}\n{trace.rstrip()}"


def log_job_failed(job: Job, code: str, detail: str | None, exc: BaseException | None) -> None:
    """WARNING สำหรับ YtError หรือไม่มี exception · ERROR สำหรับ exception ที่ไม่ได้คาดไว้ (E_UNKNOWN)"""
    level = logging.WARNING if exc is None or isinstance(exc, YtError) else logging.ERROR
    try:
        message = job_failed_message(job, code, detail, exc)
    except Exception:
        # ตัวปิดข้อมูล/จัดรูปแบบพัง: ห้ามขวางการเปลี่ยนสถานะงานเป็น failed · เหลือแค่ id กับรหัส (ไม่มี detail/traceback)
        log.warning("job_failed job=%s code=%s", job.id, code)
        return
    log.log(level, "%s", message)

# ความถี่สูงสุดที่เขียนความคืบหน้าลงฐานข้อมูล (หน้าเว็บได้ค่าสดทาง SSE อยู่แล้ว ฐานข้อมูลไว้ใช้ตอนโหลดหน้าใหม่)
PROGRESS_DB_INTERVAL_S = 1.0
# รอบปลุกตัวจัดคิวอย่างน้อยทุกเท่านี้ (นอกจากถูกปลุกตอนมีงานใหม่หรืองานจบ)
DISPATCH_INTERVAL_S = 0.2
# คีย์ของ Job ที่อาจไม่มีค่า ข่าว job.updated ที่เปลี่ยนสถานะส่ง null ให้ทุกคีย์ที่ไม่มีค่าแล้ว
# (หน้าเว็บรวม patch แบบ "คีย์ที่ไม่ส่งมา = เก็บค่าเดิม" null จึงเป็นทางเดียวที่ลบค่าเก่าออก)
_OPTIONAL_KEYS = (
    "stage", "progress", "speedBps", "etaS", "attempt", "error", "notes", "outputs",
    "startedAt", "finishedAt", "cancelling",
)
_USER = "user"
# ผลของ _start
_STARTED, _SKIPPED, _SPAWN_FAILED = "started", "skipped", "spawn_failed"
_SHUTDOWN = "shutdown"


@dataclass(frozen=True)
class PauseState:
    until: datetime
    reason: str


class SettingsView(Protocol):
    def concurrency(self) -> int: ...
    def output_dir(self) -> Path: ...


class QueueListener(Protocol):
    """ผู้ฟังสถานะคิว (M5 รอบ C: AccountService นับ grace ของบัญชีชั่วคราว) เรียกนอกล็อกของคิวเสมอ"""

    def job_queued(self) -> None: ...
    def job_ended(self, job_id: str) -> None: ...


def _thread_spawn(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, daemon=True, name="yt-job").start()


class _JobContext:
    """JobContext (C1) ของงานหนึ่งรอบ: handler รายงานความคืบหน้าและเช็กการยกเลิกผ่านตัวนี้"""

    def __init__(self, runner: QueueRunner, job: Job, workdir: Path, output_root: Path) -> None:
        self.job_id = job.id
        self.workdir = workdir
        self.output_root = output_root
        self.reason: str | None = None   # "user" | "shutdown" เมื่อถูกขอให้หยุด
        self.done = threading.Event()   # ตั้งเมื่อเธรดงานสรุปผลเสร็จ
        self._runner = runner
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._closed = False             # งานไม่ได้ running แล้ว (เช่นโดนปิดโปรแกรม) ไม่ต้องรายงานอะไรอีก
        self._stage: str | None = None
        self._last: tuple[float | None, int | None, int | None] | None = None
        self._db_at = -math.inf
        self._attempt_shown = False      # หน้าเว็บกำลังโชว์ "กำลังลองใหม่ (ครั้งที่ n/3)" อยู่

    # ---------- ฝั่งตัวรันคิว ----------

    def request_stop(self, reason: str) -> None:
        with self._lock:
            if self.reason is None:
                self.reason = reason
        self._cancel.set()

    def close(self) -> None:
        with self._lock:
            self._closed = True

    # ---------- JobContext ----------

    def stage(self, stage: str) -> None:
        if not is_stage(stage):
            raise ValueError(f"stage ไม่รู้จัก: {stage!r}")
        clear_attempt = self._attempt_shown  # รอบใหม่หลังรอลองใหม่เริ่มเดินแล้ว (เหมือนใน progress)
        if stage == self._stage and not clear_attempt:
            return
        self._stage = stage
        self._last = None
        # ขั้นใหม่เริ่มนับใหม่: ไม่ให้แถบเต็มจากขั้นโหลดค้างไว้ระหว่างรวมไฟล์
        fields: dict[str, Any] = {"stage": stage, "progress": None, "speed_bps": None, "eta_s": None}
        patch: dict[str, Any] = {"stage": stage, "progress": None, "speedBps": None, "etaS": None}
        if clear_attempt:
            fields["attempt"] = 0
            patch["attempt"] = None
        if self._write(**fields):
            self._db_at = self._runner._monotonic()
            if clear_attempt:
                self._attempt_shown = False
            self._publish(patch)

    def progress(self, fraction: float | None, speed_bps: int | None = None, eta_s: int | None = None) -> None:
        values = (
            None if fraction is None else round(min(max(float(fraction), 0.0), 1.0), 4),
            None if speed_bps is None else int(speed_bps),
            None if eta_s is None else int(eta_s),
        )
        if values == self._last:
            return  # ffmpeg ส่งค่าเดิมซ้ำได้ ไม่ต้องส่งข่าวซ้ำ
        self._last = values
        now = self._runner._monotonic()
        fields: dict[str, Any] = {}
        due = now - self._db_at >= PROGRESS_DB_INTERVAL_S
        if due:
            fields.update(progress=values[0], speed_bps=values[1], eta_s=values[2])
        # ความคืบหน้าแรกหลังรอลองใหม่ = รอบใหม่เดินแล้ว เลิกโชว์ข้อความลองใหม่ (ตัวนับจำกัดครั้งอยู่ในตัวรันคิว ไม่รีเซ็ต)
        clear_attempt = self._attempt_shown
        if clear_attempt:
            fields["attempt"] = 0
        if fields:
            if not self._write(**fields):
                return
            if due:
                self._db_at = now
        elif self._is_closed():
            return
        patch: dict[str, Any] = {"progress": values[0], "speedBps": values[1], "etaS": values[2]}
        if clear_attempt:
            self._attempt_shown = False
            patch["attempt"] = None
        self._publish(patch)

    def set_title(self, title: str) -> None:
        if not title:
            return
        if self._write(title=title):
            self._publish({"title": title})

    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def check_cancelled(self) -> None:
        if self._cancel.is_set():
            raise JobCancelled()

    def wait(self, seconds: float) -> None:
        if self._cancel.wait(max(seconds, 0.0)):
            raise JobCancelled()

    # ---------- ภายใน ----------

    def _set_attempt(self, attempt: int) -> None:
        if self._write(attempt=attempt):
            self._attempt_shown = True
            self._last = None  # ความคืบหน้าแรกของรอบใหม่ต้องส่งเสมอ แม้ค่าจะเท่ารอบก่อน
            self._publish({"attempt": attempt})

    def _is_closed(self) -> bool:
        with self._lock:
            return self._closed

    def _write(self, **fields: Any) -> bool:
        """เขียนลงฐานข้อมูล คืน False เมื่องานไม่ได้ running แล้ว (เช่นปิดโปรแกรมไปแล้ว) ซึ่งไม่ใช่ error ของ handler"""
        if self._is_closed():
            return False
        try:
            self._runner.store.update(self.job_id, **fields)
        except (InvalidTransition, KeyError):
            self.close()
            return False
        return True

    def _publish(self, fields: dict) -> None:
        self._runner._bus.job_updated(self.job_id, fields)


class QueueRunner:
    def __init__(
        self,
        store: JobStore,
        bus: EventBus,
        handlers: Mapping[str, Handler],
        *,
        settings: SettingsView,
        work_root: Path,
        delay_range: tuple[float, float] = (2.0, 5.0),
        brake_s: float = 600.0,
        retry_waits: tuple[float, ...] = (2.0, 5.0, 10.0),
        monotonic: Callable[[], float] = time.monotonic,
        wall: Callable[[], datetime] = lambda: datetime.now(UTC),
        rng: random.Random | None = None,
        spawn: Callable[[Callable[[], None]], None] | None = None,
        redact: Callable[[str], str],
    ) -> None:
        """spawn(fn) รันงานหนึ่งงาน ค่าเริ่มต้นเปิดเธรด daemon (เทสส่งตัวเก็บ fn มาเองได้)
        redact(text) ซ่อนโฟลเดอร์ผู้ใช้ใน error.detail ก่อนส่งข่าว SSE (lifecycle ส่ง api.errors.redact_home)
        บังคับส่งเสมอ จะได้ไม่มีใครลืมต่อสาย"""
        self.store = store
        self._bus = bus
        self._handlers = dict(handlers)
        self._settings = settings
        self._work_root = work_root
        self._delay_range = delay_range
        self._brake_s = brake_s
        self._retry_waits = tuple(retry_waits)
        self._monotonic = monotonic
        self._wall = wall
        self._rng = rng or random.Random()
        self._spawn = spawn or _thread_spawn
        self._redact = redact
        # RLock: tick / cancel / reorder ถือ lock ระหว่างเช็กสถานะกับเปลี่ยนสถานะ จึงไม่มีงานไหนถูกเริ่มกับยกเลิกพร้อมกัน
        self._lock = threading.RLock()
        self._pause: PauseState | None = None
        self._next_youtube_at = -math.inf
        self._active: dict[str, _JobContext] = {}
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._stopping = False
        # ผู้ฟัง (lifecycle ต่อ AccountService ให้หลังสร้าง) None = ไม่มีใครฟัง
        self.listener: QueueListener | None = None

    # ---------- ตัวจัดคิว ----------

    def start(self) -> None:
        with self._lock:
            if self._thread is not None or self._stopping:
                return
            self._thread = threading.Thread(target=self._loop, daemon=True, name="yt-queue")
            self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("จัดคิวรอบนี้ไม่สำเร็จ")
            self._wake.wait(DISPATCH_INTERVAL_S)
            self._wake.clear()

    @property
    def next_youtube_at(self) -> float:
        return self._next_youtube_at

    def concurrency(self) -> int:
        return self._settings.concurrency()

    def tick(self) -> list[str]:
        started: list[str] = []
        spawn_failed: list[str] = []
        with self._lock:
            if self._stopping or self.pause_state() is not None:
                return started
            slots = self._settings.concurrency() - len(self.store.running())
            if slots <= 0:
                return started
            for job in self.store.queued():
                if slots <= 0:
                    break
                youtube = job.kind in YOUTUBE_KINDS
                if youtube and self._monotonic() < self._next_youtube_at:
                    continue  # รอเว้นช่วง งานที่ไม่ต้องคุยกับยูทูปข้างหลังยังเริ่มได้
                outcome = self._start(job)
                if outcome == _SPAWN_FAILED:
                    spawn_failed.append(job.id)
                    break  # เปิดเธรดไม่ได้ อย่าลากงานที่เหลือในคิวให้ล้มตามกันหมดในรอบเดียว รอรอบหน้า
                if outcome == _STARTED:
                    started.append(job.id)
                    slots -= 1
                    if youtube:
                        self._next_youtube_at = self._monotonic() + self._rng.uniform(*self._delay_range)
        for job_id in spawn_failed:
            self._notify_ended(job_id)
        return started

    def _start(self, job: Job) -> str:
        try:
            output_root = self._settings.output_dir()
            job = self.store.transition(job.id, "running")
        except (KeyError, InvalidTransition):
            return _SKIPPED
        workdir = self._work_root / job.id
        ctx = _JobContext(self, job, workdir, output_root)
        self._active[job.id] = ctx
        try:
            workdir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            log.warning("สร้างโฟลเดอร์ทำงานของงาน %s ไม่ได้: %s", job.id, type(exc).__name__)
        self._publish_job(job)
        try:
            self._spawn(lambda: self._work(job, ctx))
        except Exception as exc:
            # เปิดเธรดไม่ได้ (เช่นเครื่องทรัพยากรหมด): งานต้องไม่ค้าง running โดยไม่มีใครทำ
            detail = f"{type(exc).__name__}: {exc}"
            log_job_failed(job, "E_UNKNOWN", detail, exc)
            ctx.close()
            self._forget(job.id, ctx)
            shutil.rmtree(workdir, ignore_errors=True)
            ctx.done.set()
            try:
                failed = self.store.transition(job.id, "failed", error_code="E_UNKNOWN",
                                               error_message=MESSAGES["E_UNKNOWN"],
                                               error_detail=detail)
            except (KeyError, InvalidTransition):
                return _SPAWN_FAILED
            self._publish_job(failed)
            return _SPAWN_FAILED
        return _STARTED

    # ---------- เธรดงาน ----------

    def _work(self, job: Job, ctx: _JobContext) -> None:
        outcome = "?"
        try:
            outcome = self._run_job(job, ctx)
        except Exception:
            log.exception("สรุปผลงาน %s ไม่สำเร็จ", job.id)
        finally:
            ctx.close()
            with self._lock:
                current = self._active.get(job.id)
                # เผื่อทางที่สรุปผลไม่สำเร็จ แต่ถ้างานนี้ถูกลองใหม่และเริ่มรอบใหม่ไปแล้ว ห้ามลบโฟลเดอร์ของรอบใหม่
                # (ถือ lock อยู่ tick จึงสร้างโฟลเดอร์รอบใหม่แทรกกลางไม่ได้)
                if current is None or current is ctx:
                    shutil.rmtree(ctx.workdir, ignore_errors=True)
                if current is ctx:
                    del self._active[job.id]
            ctx.done.set()
            self._wake.set()
            log.info("งาน %s (%s) จบด้วย %s", job.id, job.kind, outcome)

    def _run_job(self, job: Job, ctx: _JobContext) -> str:
        """เรียก handler แล้วเปลี่ยนสถานะตามผล คืนข้อความสั้นสำหรับ log (สถานะหรือรหัส error)"""
        try:
            handler = self._handlers.get(job.kind)
            if handler is None:
                raise LookupError(f"ไม่มี handler ของงานชนิด {job.kind}")
            result = self._call_with_retries(handler, job, ctx)
        except JobCancelled:
            if ctx.reason is None:
                return self._fail(job, ctx, "E_UNKNOWN", MESSAGES["E_UNKNOWN"], "JobCancelled โดยไม่มีใครสั่งยกเลิก")
            return self._stopped(job, ctx)
        except YtError as exc:
            if ctx.reason is not None:
                return self._stopped(job, ctx)  # error ที่เกิดเพราะถูกสั่งหยุด (เช่น ffmpeg ถูก kill)
            if exc.code == "E_BOT_CHECK":
                return self._bot_check(job, ctx, exc)
            if exc.code == "E_QUEUE_PAUSED" and self.pause_state() is not None:
                return self._paused(job, ctx)
            return self._fail(job, ctx, exc.code, exc.message, exc.detail, exc)
        except Exception as exc:
            if ctx.reason is not None:
                return self._stopped(job, ctx)
            # พังแบบไม่คาดคิด: traceback ลง log ครั้งเดียวในบรรทัด job_failed พร้อมรหัส (M6 รอบ B)
            return self._fail(job, ctx, "E_UNKNOWN", MESSAGES["E_UNKNOWN"], f"{type(exc).__name__}: {exc}", exc)
        return self._finish(job, ctx, result)

    def _call_with_retries(self, handler: Handler, job: Job, ctx: _JobContext) -> JobResult:
        attempt = 0
        while True:
            try:
                return handler(job, ctx)
            except YtError as exc:
                if exc.code != "E_NETWORK" or attempt >= len(self._retry_waits) or ctx.cancelled():
                    raise
                attempt += 1
                log.info("งาน %s เน็ตหลุด ลองใหม่ครั้งที่ %d/%d", job.id, attempt, len(self._retry_waits))
                ctx._set_attempt(attempt)
                ctx.wait(self._retry_waits[attempt - 1])

    def _finish(self, job: Job, ctx: _JobContext, result: JobResult) -> str:
        self._clear_workdir(ctx)
        done = self._end(job, ctx, "done", outputs=result.outputs, notes=result.notes,
                         title=result.title, progress=1.0)
        return "done" if done else "done (ไม่ได้บันทึก)"

    def _stopped(self, job: Job, ctx: _JobContext) -> str:
        self._clear_workdir(ctx)
        if ctx.reason == _SHUTDOWN:
            self._end(job, ctx, "interrupted", error_code="E_INTERRUPTED", error_message=MESSAGES["E_INTERRUPTED"])
            return "interrupted"
        self._end(job, ctx, "cancelled")
        return "cancelled"

    def _fail(
        self, job: Job, ctx: _JobContext, code: str, message: str, detail: str | None, exc: BaseException | None = None
    ) -> str:
        """ทุกความล้มเหลวของงานผ่านที่นี่ (ยกเว้นเปิดเธรดไม่ได้ใน _start): บรรทัด job_failed หนึ่งบรรทัดต่อครั้ง (AC-SET-03)"""
        log_job_failed(job, code, detail, exc)
        self._clear_workdir(ctx)
        self._end(job, ctx, "failed", error_code=code, error_message=message, error_detail=detail or None)
        return code

    def _bot_check(self, job: Job, ctx: _JobContext, exc: YtError) -> str:
        # เบรกก่อนส่งงานกลับเข้าคิว ไม่งั้นตัวจัดคิวอาจหยิบงานนี้ไปรันซ้ำก่อนคิวพัก
        self.brake("E_BOT_CHECK")
        self._clear_workdir(ctx)
        with self._lock:
            # เช็กการยกเลิกกับส่งกลับเข้าคิวใน lock เดียวกับ cancel(): คำสั่งยกเลิกที่มาระหว่างนี้จึงไม่หาย
            if ctx.reason is None:
                current = self.store.get(job.id)
                if current is not None and current.bot_checks == 0:
                    ctx.close()
                    try:
                        requeued = self.store.requeue(job.id, front=True, bot_checks=1)  # Q1: ครั้งแรกกลับหัวคิว
                    except (KeyError, InvalidTransition):
                        return "E_BOT_CHECK (สถานะเปลี่ยนไปแล้ว)"
                    self._forget(job.id, ctx)
                    self._publish_job(requeued)
                    return "E_BOT_CHECK (กลับหัวคิว)"
        if ctx.reason is not None:
            return self._stopped(job, ctx)
        return self._fail(job, ctx, "E_BOT_CHECK", exc.message, exc.detail, exc)

    def _paused(self, job: Job, ctx: _JobContext) -> str:
        """E_QUEUE_PAUSED ระหว่างงานรันอยู่ (คำขออื่นเบรกคิวกลางทาง แล้ว with_account_retry ไม่ยอมลองด้วยบัญชี)
        = กลับหัวคิวรหัสงานเดิม รันใหม่เมื่อคิวหายพัก ไม่นับเป็นเช็กบอท (bot_checks คงเดิม ไม่เบรกซ้ำ)
        ผู้เรียกเช็กแล้วว่าคิวยังพักอยู่ คิวไม่พักแล้ว = จบ failed ตามปกติ (ไม่วนลองซ้ำ)"""
        self._clear_workdir(ctx)
        with self._lock:
            # เช็กการยกเลิกกับส่งกลับเข้าคิวใน lock เดียวกับ cancel() เหมือน _bot_check
            if ctx.reason is None:
                ctx.close()
                try:
                    requeued = self.store.requeue(job.id, front=True)
                except (KeyError, InvalidTransition):
                    return "E_QUEUE_PAUSED (สถานะเปลี่ยนไปแล้ว)"
                self._forget(job.id, ctx)
                self._publish_job(requeued)
                return "E_QUEUE_PAUSED (กลับหัวคิว)"
        return self._stopped(job, ctx)

    def _end(self, job: Job, ctx: _JobContext, status: str, **fields: Any) -> bool:
        """running -> สถานะจบ คืน False เมื่องานไม่ได้ running แล้ว (เช่นตอนปิดโปรแกรมถูกตั้ง interrupted ไปก่อน)"""
        ctx.close()
        try:
            ended = self.store.transition(job.id, status, **fields)
        except (KeyError, InvalidTransition):
            return False
        self._forget(job.id, ctx)
        self._publish_job(ended)
        self._notify_ended(job.id)
        return True

    def _forget(self, job_id: str, ctx: _JobContext) -> None:
        with self._lock:
            if self._active.get(job_id) is ctx:
                del self._active[job_id]

    @staticmethod
    def _clear_workdir(ctx: _JobContext) -> None:
        # ลบก่อนเปลี่ยนสถานะ: งานที่กลับเข้าคิวแล้วเริ่มใหม่ทันทีจะไม่โดนลบโฟลเดอร์ของรอบใหม่
        shutil.rmtree(ctx.workdir, ignore_errors=True)

    # ---------- คำสั่งจากหน้าเว็บ ----------

    def enqueue(self, items: Sequence[NewJob]) -> list[Job]:
        # ประกาศ job.created ขณะยังถือ lock: ตัวจัดคิวเริ่มงานได้ต้องรอ lock ข่าว running จึงมาหลัง created เสมอ
        # (เว็บทิ้ง job.updated ของงานที่ยังไม่รู้จัก) ลำดับ lock คิว -> bus เหมือนจุดอื่น
        with self._lock:
            jobs = self.store.add(items)
            for job in jobs:
                self._bus.publish("job.created", self.job_api(job))
        self._wake.set()
        if jobs:
            self._notify_queued()
        return jobs

    def cancel(self, job_id: str) -> Job:
        """queued -> cancelled ทันที, running -> ส่งสัญญาณหยุด (สถานะ cancelled ตามมาทาง SSE)
        ไม่มีงาน = KeyError, งานจบแล้ว = InvalidTransition"""
        with self._lock:
            job = self.store.get(job_id)
            if job is None:
                raise KeyError(job_id)
            if job.status == "queued":
                job = self.store.transition(job_id, "cancelled")
                self._publish_job(job)
            elif job.status != "running":
                raise InvalidTransition(f"{job.status} -> cancelled")
            elif (ctx := self._active.get(job_id)) is None:
                # running ค้างจากที่ไม่มีเธรดไหนทำอยู่แล้ว ยกเลิกในฐานข้อมูลได้เลย
                job = self.store.transition(job_id, "cancelled")
                self._publish_job(job)
            else:
                ctx.request_stop(_USER)
                self._bus.job_updated(job_id, {"cancelling": True})
                return job  # สถานะ cancelled มากับเธรดงาน (_end แจ้งผู้ฟังเอง)
        self._notify_ended(job_id)
        return job

    def retry(self, job_id: str) -> Job:
        """failed / interrupted -> queued ท้ายคิว นับเช็กบอทใหม่ (ลองใหม่ได้อีกครั้งต่อการกดหนึ่งครั้ง)"""
        with self._lock:
            job = self.store.get(job_id)
            if job is None:
                raise KeyError(job_id)
            if job.status not in ("failed", "interrupted"):
                raise InvalidTransition(f"{job.status} -> queued")
            job = self.store.requeue(job_id, reset_bot_checks=True)
            self._publish_job(job)
        self._wake.set()
        self._notify_queued()
        return job

    def reorder(self, ids: Sequence[str]) -> None:
        with self._lock:
            before = {job.id: job.position for job in self.store.queued()}
            self.store.reorder(ids)
            moved = [job for job in self.store.queued() if before.get(job.id) != job.position]
        for job in moved:
            self._bus.job_updated(job.id, {"position": job.position})

    def brake(self, reason: str = "E_BOT_CHECK") -> None:
        with self._lock:
            until = self._wall() + timedelta(seconds=self._brake_s)
            if self._pause is not None and self._pause.until > until:
                until = self._pause.until
            self._pause = PauseState(until, reason)
        log.warning("พักคิวถึง %s เพราะ %s", until.isoformat(timespec="seconds"), reason)
        self._bus.publish("queue.paused", {"until": _iso(until), "reason": reason})

    def resume(self) -> None:
        with self._lock:
            was_paused = self._pause is not None
            self._pause = None
        if was_paused:
            log.info("คิวกลับมาทำงานต่อ")
            self._bus.publish("queue.resumed", {})
        self._wake.set()

    def pause_state(self) -> PauseState | None:
        with self._lock:
            pause = self._pause
            if pause is None or self._wall() < pause.until:
                return pause
            self._pause = None
        log.info("ครบเวลาพักคิวแล้ว ทำงานต่อ")
        self._bus.publish("queue.resumed", {})
        return None

    def is_cancelling(self, job_id: str) -> bool:
        with self._lock:
            ctx = self._active.get(job_id)
            return ctx is not None and ctx.reason is not None

    def pending_count(self) -> int:
        return self.store.pending_count()

    def job_api(self, job: Job) -> dict:
        """Job ในรูป C2 สำหรับ API และ SSE: เติม cancelling และซ่อนโฟลเดอร์ผู้ใช้ใน error.detail"""
        data = job.to_api()
        if job.status == "running" and self.is_cancelling(job.id):
            data["cancelling"] = True
        error = data.get("error")
        if error and error.get("detail"):
            data["error"] = {**error, "detail": self._redact(error["detail"])}
        return data

    def _notify_queued(self) -> None:
        listener = self.listener
        if listener is None:
            return
        try:
            listener.job_queued()
        except Exception:
            log.exception("แจ้งผู้ฟังว่ามีงานเข้าคิวไม่สำเร็จ")

    def _notify_ended(self, job_id: str) -> None:
        listener = self.listener
        if listener is None:
            return
        try:
            listener.job_ended(job_id)
        except Exception:
            log.exception("แจ้งผู้ฟังว่างาน %s จบไม่สำเร็จ", job_id)

    def _publish_job(self, job: Job) -> None:
        """ข่าวเปลี่ยนสถานะ: ส่งทุกคีย์ ค่าที่ไม่มีแล้วส่งเป็น null (เช่น error เก่าหลังลองใหม่)"""
        data = self.job_api(job)
        del data["id"]
        for key in _OPTIONAL_KEYS:
            data.setdefault(key, None)
        self._bus.job_updated(job.id, data)

    # ---------- เปิด / ปิดโปรแกรม ----------

    def recover(self) -> int:
        """ตอนเปิดโปรแกรม: งานที่ค้าง running จากรอบก่อนเป็น interrupted แล้วล้าง work/ (AC-Q-05)"""
        count = self.store.interrupt_running(MESSAGES["E_INTERRUPTED"])
        self._empty_work_root()
        if count:
            log.info("งานที่ค้างจากรอบก่อน %d งาน ถูกตั้งเป็นหยุดกลางคัน", count)
        return count

    def shutdown(self, timeout: float = 5.0) -> None:
        """หยุดตัวจัดคิว สั่งงานที่รันอยู่ให้หยุด (จบเป็น interrupted) รอไม่เกิน timeout แล้วเก็บกวาด"""
        deadline = time.monotonic() + max(timeout, 0.0)
        with self._lock:
            self._stopping = True
            thread = self._thread
            active = list(self._active.values())
        self._stop.set()
        self._wake.set()
        for ctx in active:
            ctx.request_stop(_SHUTDOWN)
        if thread is not None:
            thread.join(max(deadline - time.monotonic(), 0.0))
        for ctx in active:
            ctx.done.wait(max(deadline - time.monotonic(), 0.0))
        for ctx in active:
            ctx.close()  # งานที่ยังไม่ยอมหยุด: ไม่ต้องเขียนความคืบหน้าทับสถานะ interrupted
        leftovers = self.store.interrupt_running(MESSAGES["E_INTERRUPTED"])
        if leftovers:
            log.warning("งาน %d งานไม่หยุดภายใน %.1f วินาที ตั้งเป็นหยุดกลางคัน", leftovers, timeout)
        self._empty_work_root()

    def _empty_work_root(self) -> None:
        try:
            children = list(self._work_root.iterdir())
        except FileNotFoundError:
            return
        except OSError as exc:
            log.warning("อ่านโฟลเดอร์ทำงานไม่ได้: %s", type(exc).__name__)
            return
        for child in children:
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child, ignore_errors=True)
            else:
                try:
                    child.unlink()
                except OSError:
                    pass


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds")
