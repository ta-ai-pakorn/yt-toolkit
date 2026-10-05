"""งานในคิว (jobs): โมเดล กฎการเปลี่ยนสถานะ และที่เก็บในตาราง jobs ของ SQLite

ทุกการเขียนผ่าน `db.transaction()` จึงไม่มีงานไหนเห็นสถานะครึ่งๆ กลางๆ
เวลาเก็บเป็น ISO 8601 UTC (`+00:00`) แบบมีไมโครวินาทีเสมอ จึงเรียงตามตัวอักษรได้ตรงกับเวลา
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from .db import Database, Transaction
from .yterrors import MESSAGES

JOB_KINDS = ("video", "audio", "subtitle", "note", "frames_sharp", "contact_sheet", "frames_zip")
STATUSES = ("queued", "running", "done", "failed", "cancelled", "interrupted")
STAGES = (
    "probing", "downloading_video", "downloading_audio", "merging", "converting", "writing",
    "cutting", "cutting_ads",
)  # fmt: skip
# "splitting:<i>/<n>" = กำลังแยก chapter ที่ i จาก n (M5 รอบ A) หน้าเว็บแสดง "กำลังแยก chapter i/n"
SPLIT_STAGE = re.compile(r"splitting:(\d{1,4})/(\d{1,4})")
# M5 รอบ B: "extracting_frames:<i>/<n>" = กำลังดึงภาพคม (งาน frames_sharp) · "sharp_frames:<i>/<n>" = ภาพคมอัตโนมัติหลังโหลดวิดีโอ
COUNT_STAGES = ("extracting_frames", "sharp_frames")
COUNT_STAGE = re.compile(r"(extracting_frames|sharp_frames):(\d{1,4})/(\d{1,4})")
TERMINAL = frozenset({"done", "failed", "cancelled", "interrupted"})
# PRD 6.1 บวก running -> queued (Q1: เจอเช็กบอทครั้งแรก กลับไปหัวคิว)
# ทุกคู่ที่ไปเป็น "queued" ทำได้ผ่าน JobStore.requeue() เท่านั้น (ล้างผลรอบก่อนและจัดตำแหน่งคิว)
# transition(..., "queued") จึงถูกปฏิเสธเสมอ
TRANSITIONS = frozenset({
    ("queued", "running"), ("queued", "cancelled"),
    ("running", "done"), ("running", "failed"), ("running", "cancelled"),
    ("running", "interrupted"), ("running", "queued"),
    ("failed", "queued"), ("interrupted", "queued"),
})
NOTES = {
    "AUDIO_LANG_FALLBACK": "คลิปนี้ไม่มีเสียงภาษาที่เลือก ใช้เสียงต้นฉบับแทน",
    "NO_SUBTITLES": "คลิปนี้ไม่มีซับ",
    "EMBED_SUBS_SKIPPED": "ฝังซับไม่สำเร็จ ได้ไฟล์วิดีโอที่ไม่มีซับ",
    "QUALITY_FALLBACK": "คุณภาพที่เลือกไม่มีแล้ว ใช้คุณภาพที่ใกล้ที่สุดแทน",
    "SPONSORBLOCK_EMPTY": "ไม่มีข้อมูลจากชุมชน ไม่ได้ตัดโฆษณา",
    "SPONSORBLOCK_UNREACHABLE": "ติดต่อ SponsorBlock ไม่ได้ ไม่ได้ตัดโฆษณา",
    "NO_CHAPTERS": "คลิปนี้ไม่มี chapter ได้ไฟล์เต็ม",
    "SHARP_LOW_RES": "คลิปนี้มีภาพสูงสุด {h}p ภาพจึงเล็กกว่าปกติ",
    "SHARP_INTERVAL_RAISED": "ปรับเป็นทุก {n} วินาทีเพื่อไม่ให้เกิน 200 ภาพ",
}
# โน้ตที่ข้อความมีค่าเติม (M5 รอบ B) เก็บเป็น "<รหัส>:<ตัวเลข>" เช่น "SHARP_LOW_RES:480" ค่า = ชื่อช่องในข้อความ
NOTE_VALUES = {"SHARP_LOW_RES": "h", "SHARP_INTERVAL_RAISED": "n"}
# ตัวเลือกขั้นสูงของงานโหลด (M5 รอบ A) ที่ API ตรวจและตัวทำงานใช้ร่วมกัน
SPONSORBLOCK_CATEGORIES = (
    "sponsor", "selfpromo", "interaction", "intro", "outro", "preview", "filler", "music_offtopic",
)  # fmt: skip
MIN_RANGE_MS = 1000  # ช่วงเวลาต้องยาวอย่างน้อย 1 วินาที
RANGE_TOLERANCE_MS = 500  # ความยาวคลิปเก็บเป็นวินาทีปัดเศษ ปลายช่วงจึงเกินได้ไม่เกินครึ่งวินาที


def split_stage(index: int, total: int) -> str:
    """ขั้นของการแยกไฟล์ตาม chapter: "splitting:<i>/<n>" (1 <= i <= n <= 9999)"""
    if not 1 <= index <= total <= 9999:
        raise ValueError(f"split stage out of range: {index}/{total}")
    return f"splitting:{index}/{total}"


def count_stage(name: str, index: int, total: int) -> str:
    """ขั้นที่นับทีละภาพของภาพคม: "extracting_frames:<i>/<n>" หรือ "sharp_frames:<i>/<n>" (1 <= i <= n <= 9999)"""
    if name not in COUNT_STAGES or not 1 <= index <= total <= 9999:
        raise ValueError(f"count stage out of range: {name}:{index}/{total}")
    return f"{name}:{index}/{total}"


def is_stage(value: str) -> bool:
    return (
        value in STAGES
        or SPLIT_STAGE.fullmatch(value) is not None
        or COUNT_STAGE.fullmatch(value) is not None
    )


def valued_note(code: str, value: int) -> str:
    """โน้ตที่มีค่าเติม: "<รหัส>:<ค่า>" (รหัสต้องอยู่ใน NOTE_VALUES ค่าเป็นจำนวนเต็มไม่ติดลบ)"""
    if code not in NOTE_VALUES or isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"bad valued note: {code}:{value!r}")
    return f"{code}:{value}"


def note_api(raw: str) -> dict | None:
    """โน้ตที่เก็บไว้ -> {"code", "message"} ของ API (เติมค่าให้โน้ตที่มีค่า) รหัสไม่รู้จักหรือรูปผิด = None (ไม่แสดง)"""
    code, sep, value = raw.partition(":")
    template = NOTES.get(code)
    if template is None:
        return None
    field = NOTE_VALUES.get(code)
    if field is None:
        return None if sep else {"code": code, "message": template}
    if not sep or not value.isdigit():
        return None
    return {"code": code, "message": template.format(**{field: int(value)})}


# ชื่อช่องฝั่ง Python -> คอลัมน์ ที่ transition() เขียนได้
_FIELD_COLUMNS = {
    "title": "title",
    "stage": "stage",
    "progress": "progress",
    "speed_bps": "speed_bps",
    "eta_s": "eta_s",
    "attempt": "attempt",
    "bot_checks": "bot_checks",
    "error_code": "error_code",
    "error_message": "error_message",
    "error_detail": "error_detail",
    "notes": "notes_json",
    "outputs": "outputs_json",
}
# update() แก้ได้เฉพาะค่าระหว่างรัน (งานต้องอยู่ในสถานะ running)
_UPDATE_FIELDS = frozenset({"stage", "progress", "speed_bps", "eta_s", "attempt", "title"})
# requeue() ล้างผลของรอบก่อนทิ้งทั้งหมด ยกเว้น bot_checks (Q1 นับข้ามรอบ ลองใหม่เองค่อยรีเซ็ต)
_REQUEUE_CLEARS = (
    "stage = NULL, progress = NULL, speed_bps = NULL, eta_s = NULL, attempt = 0, "
    "error_code = NULL, error_message = NULL, error_detail = NULL, notes_json = NULL, "
    "outputs_json = NULL, started_at = NULL, finished_at = NULL"
)
# ค่าระหว่างรันที่ไม่มีความหมายแล้วเมื่องานหยุด (ผู้เรียกส่งค่าเองได้ ค่าที่ส่งมาชนะ)
_STOP_CLEARS = {"stage": None, "speed_bps": None, "eta_s": None, "attempt": 0}
_DEFAULT_FINISHED_LIMIT = 20


class InvalidTransition(Exception):
    """เปลี่ยนสถานะแบบนี้ไม่ได้ (API ตอบ 409 E_JOB_STATE)"""


# ---------- uuid7 ----------

_uuid_lock = threading.Lock()
_uuid_last_ms = 0
_uuid_counter = 0


def uuid7() -> str:
    """UUID เวอร์ชัน 7 (RFC 9562) เป็นข้อความ 36 ตัว เรียงตามตัวอักษรได้ตามเวลาที่สร้าง
    ในมิลลิวินาทีเดียวกันใช้ 12 บิต rand_a เป็นตัวนับ จึงเรียงต่อกันได้แม้สร้างถี่ๆ"""
    global _uuid_last_ms, _uuid_counter
    with _uuid_lock:
        ms = time.time_ns() // 1_000_000
        if ms > _uuid_last_ms:
            _uuid_last_ms = ms
            _uuid_counter = int.from_bytes(os.urandom(2)) & 0x7FF  # เว้นที่ให้นับต่อ
        else:
            _uuid_counter += 1
            if _uuid_counter > 0xFFF:  # ตัวนับเต็ม ขยับเวลาไป 1 ms เพื่อให้ยังเรียงได้
                _uuid_last_ms += 1
                _uuid_counter = 0
        ms, counter = _uuid_last_ms, _uuid_counter
    rand_b = int.from_bytes(os.urandom(8)) & ((1 << 62) - 1)
    value = (ms & ((1 << 48) - 1)) << 80 | 0x7 << 76 | counter << 64 | 0b10 << 62 | rand_b
    text = f"{value:032x}"
    return f"{text[:8]}-{text[8:12]}-{text[12:16]}-{text[16:20]}-{text[20:]}"


# ---------- model ----------

@dataclass(frozen=True)
class OutputFile:
    root: str        # โฟลเดอร์ผลลัพธ์ (absolute) ตอนทำงาน ไม่ส่งให้เบราว์เซอร์
    rel: str         # "<folder>/<file>" ใช้ "/" คั่น (kind "folder" = ตัวโฟลเดอร์)
    size_bytes: int
    kind: str        # "video" | "audio" | "subtitle" | "note" | "image" | "archive" | "folder" (M5 รอบ B ภาพคม)
    files: int | None = None  # kind "folder": จำนวนไฟล์ในโฟลเดอร์


@dataclass(frozen=True)
class NewJob:
    video_id: str
    kind: str
    params: dict
    title: str = ""


@dataclass(frozen=True)
class JobResult:
    outputs: tuple[OutputFile, ...] = ()
    notes: tuple[str, ...] = ()
    title: str | None = None


class JobContext(Protocol):
    job_id: str
    workdir: Path        # work/<jobId>/ ตัวรันคิวสร้างให้ และลบทิ้งหลังงานจบ
    output_root: Path    # outputDir ณ ตอนเริ่มงาน

    def stage(self, stage: str) -> None: ...
    def progress(self, fraction: float | None, speed_bps: int | None = None, eta_s: int | None = None) -> None: ...
    def set_title(self, title: str) -> None: ...
    def cancelled(self) -> bool: ...
    def check_cancelled(self) -> None: ...      # raise JobCancelled
    def wait(self, seconds: float) -> None: ... # หลับแบบยกเลิกได้ raise JobCancelled


@dataclass
class Job:
    id: str
    video_id: str
    title: str
    kind: str
    params: dict
    status: str
    stage: str | None
    progress: float | None
    speed_bps: int | None
    eta_s: int | None
    attempt: int
    bot_checks: int
    position: int
    error_code: str | None
    error_message: str | None
    error_detail: str | None
    notes: tuple[str, ...]
    outputs: tuple[OutputFile, ...]
    created_at: str
    started_at: str | None
    finished_at: str | None

    def to_api(self) -> dict:
        """รูป Job ของ API/SSE (C2) ไม่มี "cancelling" (ชั้น API เติมเอง) และไม่มี path เต็มของไฟล์"""
        data: dict[str, Any] = {
            "id": self.id,
            "videoId": self.video_id,
            "title": self.title,
            "kind": self.kind,
            "params": self.params,
            "status": self.status,
            "position": self.position,
            "createdAt": self.created_at,
        }
        optional = {
            "stage": self.stage,
            "progress": self.progress,
            "speedBps": self.speed_bps,
            "etaS": self.eta_s,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
        }
        data.update({k: v for k, v in optional.items() if v is not None})
        if self.attempt:
            data["attempt"] = self.attempt
        if self.error_code is not None:
            data["error"] = {
                "code": self.error_code,
                "message": self.error_message or MESSAGES.get(self.error_code, MESSAGES["E_UNKNOWN"]),
                "detail": self.error_detail,
            }
        notes = [note for note in (note_api(raw) for raw in self.notes) if note is not None]
        if notes:
            data["notes"] = notes
        if self.outputs:
            data["outputs"] = [_output_api(i, out) for i, out in enumerate(self.outputs)]
        return data


def _output_api(index: int, out: OutputFile) -> dict:
    item: dict[str, Any] = {"index": index, "name": PurePosixPath(out.rel).name, "sizeBytes": out.size_bytes}
    if out.files is not None:
        item["files"] = out.files
    return item


Handler = Callable[[Job, JobContext], JobResult]


def _dump_outputs(outputs: Sequence[OutputFile] | None) -> str | None:
    if not outputs:
        return None
    rows: list[dict[str, Any]] = []
    for o in outputs:
        row: dict[str, Any] = {"root": o.root, "rel": o.rel, "sizeBytes": o.size_bytes, "kind": o.kind}
        if o.files is not None:
            row["files"] = o.files
        rows.append(row)
    return json.dumps(rows, ensure_ascii=False)


def _load_outputs(text: str | None) -> tuple[OutputFile, ...]:
    if not text:
        return ()
    return tuple(
        OutputFile(
            str(o["root"]), str(o["rel"]), int(o["sizeBytes"]), str(o["kind"]),
            int(o["files"]) if o.get("files") is not None else None,
        )
        for o in json.loads(text)
    )  # fmt: skip


def _dump_notes(notes: Sequence[str] | None) -> str | None:
    return json.dumps(list(notes), ensure_ascii=False) if notes else None


def _from_row(row: Any) -> Job:
    return Job(
        id=row["id"],
        video_id=row["video_id"],
        title=row["title"],
        kind=row["kind"],
        params=json.loads(row["params_json"]),
        status=row["status"],
        stage=row["stage"],
        progress=row["progress"],
        speed_bps=row["speed_bps"],
        eta_s=row["eta_s"],
        attempt=row["attempt"],
        bot_checks=row["bot_checks"],
        position=row["position"],
        error_code=row["error_code"],
        error_message=row["error_message"],
        error_detail=row["error_detail"],
        notes=tuple(json.loads(row["notes_json"])) if row["notes_json"] else (),
        outputs=_load_outputs(row["outputs_json"]),
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )


def _encode(field: str, value: Any) -> Any:
    if field == "notes":
        return _dump_notes(value)
    if field == "outputs":
        return _dump_outputs(value)
    if field == "stage" and value is not None and not is_stage(value):
        raise ValueError(f"stage ไม่รู้จัก: {value!r}")
    if field == "title":
        return value
    if field in ("attempt", "bot_checks"):
        return int(value or 0)
    return value


def _assignments(fields: dict[str, Any]) -> tuple[list[str], list[Any]]:
    sets: list[str] = []
    values: list[Any] = []
    for field, value in fields.items():
        if field == "title" and value is None:
            continue  # title=None = ไม่แก้ชื่อเดิม
        sets.append(f"{_FIELD_COLUMNS[field]} = ?")
        values.append(_encode(field, value))
    return sets, values


def _check_fields(fields: dict[str, Any], allowed: Collection[str]) -> None:
    unknown = sorted(set(fields) - set(allowed))
    if unknown:
        raise ValueError(f"แก้ช่องเหล่านี้ไม่ได้: {', '.join(unknown)}")


# ---------- store ----------

class JobStore:
    def __init__(
        self,
        db: Database,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        new_id: Callable[[], str] = uuid7,
    ) -> None:
        self._db = db
        self._now = now
        self._new_id = new_id

    def _stamp(self, moment: datetime | None = None) -> str:
        return (moment or self._now()).astimezone(UTC).isoformat(timespec="microseconds")

    @staticmethod
    def _row(tx: Transaction, job_id: str) -> Any:
        rows = tx.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        if not rows:
            raise KeyError(job_id)
        return rows[0]

    def add(self, items: Sequence[NewJob]) -> list[Job]:
        for item in items:
            if item.kind not in JOB_KINDS:
                raise ValueError(f"ชนิดงานไม่รู้จัก: {item.kind!r}")
        created = self._stamp()
        with self._db.transaction() as tx:
            base = tx.execute("SELECT COALESCE(MAX(position), 0) AS p FROM jobs")[0]["p"]
            ids: list[str] = []
            for offset, item in enumerate(items, start=1):
                job_id = self._new_id()
                tx.execute(
                    "INSERT INTO jobs (id, video_id, title, kind, params_json, status, position, created_at) "
                    "VALUES (?, ?, ?, ?, ?, 'queued', ?, ?)",
                    (job_id, item.video_id, item.title or "", item.kind,
                     json.dumps(item.params, ensure_ascii=False), base + offset, created),
                )
                ids.append(job_id)
            return [_from_row(self._row(tx, job_id)) for job_id in ids]

    def get(self, job_id: str) -> Job | None:
        rows = self._db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        return _from_row(rows[0]) if rows else None

    def queued(self) -> list[Job]:
        return self.list_status("queued", -1)

    def running(self) -> list[Job]:
        return self.list_status("running", -1)

    def list_status(self, status: str, limit: int) -> list[Job]:
        """queued เรียงตามลำดับคิว running ตามเวลาเริ่ม สถานะอื่นตามเวลาจบ ใหม่สุดก่อน
        limit < 0 = ไม่จำกัด"""
        if status not in STATUSES:
            raise ValueError(f"สถานะไม่รู้จัก: {status!r}")
        order = {
            "queued": "position ASC, created_at ASC",
            "running": "started_at ASC, position ASC",
        }.get(status, "finished_at DESC, position DESC")
        rows = self._db.execute(
            f"SELECT * FROM jobs WHERE status = ? ORDER BY {order} LIMIT ?", (status, int(limit))
        )
        return [_from_row(r) for r in rows]

    def list_default(self) -> list[Job]:
        """running ทั้งหมด, queued ทั้งหมด, failed/interrupted 20 งานล่าสุดใน 7 วัน
        และ done 20 งานล่าสุดใน 24 ชม. (สองกลุ่มหลังรวมกันเรียงตามเวลาจบ ใหม่สุดก่อน) ไม่มี cancelled"""
        now = self._now()
        with self._db.transaction() as tx:  # อ่านทั้งชุดจากภาพเดียวกัน
            running = tx.execute("SELECT * FROM jobs WHERE status = 'running' ORDER BY started_at, position")
            queued = tx.execute("SELECT * FROM jobs WHERE status = 'queued' ORDER BY position, created_at")
            failed = tx.execute(
                "SELECT * FROM jobs WHERE status IN ('failed', 'interrupted') AND finished_at >= ? "
                "ORDER BY finished_at DESC LIMIT ?",
                (self._stamp(now - timedelta(days=7)), _DEFAULT_FINISHED_LIMIT),
            )
            done = tx.execute(
                "SELECT * FROM jobs WHERE status = 'done' AND finished_at >= ? ORDER BY finished_at DESC LIMIT ?",
                (self._stamp(now - timedelta(hours=24)), _DEFAULT_FINISHED_LIMIT),
            )
        finished = sorted([*failed, *done], key=lambda r: r["finished_at"], reverse=True)
        return [_from_row(r) for r in [*running, *queued, *finished]]

    def transition(self, job_id: str, to: str, **fields: Any) -> Job:
        """เปลี่ยนสถานะตาม TRANSITIONS และเขียนช่องที่ส่งมาพร้อมกัน
        ->running ตั้ง started_at, ->สถานะจบ ตั้ง finished_at และล้าง stage/speed_bps/eta_s/attempt
        (ค่าที่ส่งมาเองชนะ) ส่วน ->queued ต้องใช้ requeue()"""
        _check_fields(fields, _FIELD_COLUMNS.keys())
        if to not in STATUSES:
            raise ValueError(f"สถานะไม่รู้จัก: {to!r}")
        if to == "queued":
            raise InvalidTransition("ใช้ requeue() เพื่อส่งงานกลับเข้าคิว ไม่ใช่ transition(..., 'queued')")
        if to in TERMINAL:
            fields = {**_STOP_CLEARS, **fields}
        sets, values = _assignments(fields)
        stamp = self._stamp()
        with self._db.transaction() as tx:
            current = self._row(tx, job_id)["status"]
            if (current, to) not in TRANSITIONS:
                raise InvalidTransition(f"{current} -> {to}")
            sets.insert(0, "status = ?")
            values.insert(0, to)
            if to == "running":
                sets += ["started_at = ?", "finished_at = NULL"]
            else:
                sets.append("finished_at = ?")
            values.append(stamp)
            tx.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id = ?", (*values, job_id))
            return _from_row(self._row(tx, job_id))

    def update(self, job_id: str, **fields: Any) -> Job:
        """แก้ค่าระหว่างรัน (stage, progress, speed_bps, eta_s, attempt, title) ของงานที่ running
        title=None = ไม่แก้ชื่อ bot_checks ตั้งผ่าน requeue(..., bot_checks=n) เท่านั้น"""
        _check_fields(fields, _UPDATE_FIELDS)
        sets, values = _assignments(fields)
        with self._db.transaction() as tx:
            current = self._row(tx, job_id)["status"]
            if current != "running":
                raise InvalidTransition(f"แก้งานที่ไม่ได้รันอยู่ไม่ได้ ({current})")
            if sets:
                tx.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id = ?", (*values, job_id))
            return _from_row(self._row(tx, job_id))

    def requeue(
        self,
        job_id: str,
        *,
        front: bool = False,
        bot_checks: int | None = None,
        reset_bot_checks: bool = False,
    ) -> Job:
        """failed/interrupted/running -> queued ต่อท้ายคิว (front=True ไปหัวคิว) ทางเดียวที่ส่งงานกลับเข้าคิว
        ล้างผลของรอบก่อน (error, progress, outputs, notes, attempt, stage, เวลา)
        bot_checks: ปกติเก็บค่าเดิม; bot_checks=n ตั้งค่าใน transaction เดียวกัน (Q1 เจอเช็กบอท)
        reset_bot_checks=True ตั้งเป็น 0 (ผู้ใช้กดลองใหม่เอง)"""
        if bot_checks is not None and reset_bot_checks:
            raise ValueError("ส่ง bot_checks กับ reset_bot_checks พร้อมกันไม่ได้")
        new_checks = 0 if reset_bot_checks else bot_checks
        with self._db.transaction() as tx:
            current = self._row(tx, job_id)["status"]
            if (current, "queued") not in TRANSITIONS:
                raise InvalidTransition(f"{current} -> queued")
            if front:
                first = tx.execute("SELECT MIN(position) AS p FROM jobs WHERE status = 'queued'")[0]["p"]
                if first is not None:
                    position = first - 1
                else:
                    position = tx.execute("SELECT COALESCE(MAX(position), 0) AS p FROM jobs")[0]["p"] + 1
            else:
                position = tx.execute("SELECT COALESCE(MAX(position), 0) AS p FROM jobs")[0]["p"] + 1
            tx.execute(
                f"UPDATE jobs SET status = 'queued', position = ?, {_REQUEUE_CLEARS}, "
                "bot_checks = COALESCE(?, bot_checks) WHERE id = ?",
                (position, None if new_checks is None else int(new_checks), job_id),
            )
            return _from_row(self._row(tx, job_id))

    def reorder(self, ids: Sequence[str]) -> None:
        """id ที่ไม่ได้ queued อยู่จะถูกข้าม ที่เหลือได้ตำแหน่งเดิมของกลุ่มตัวเองเรียงจากน้อยไปมาก
        ตามลำดับที่ส่งมา งาน queued อื่นอยู่ที่เดิม"""
        with self._db.transaction() as tx:
            queued = {r["id"]: r["position"] for r in tx.execute(
                "SELECT id, position FROM jobs WHERE status = 'queued'")}
            wanted = [job_id for job_id in dict.fromkeys(ids) if job_id in queued]
            slots = sorted(queued[job_id] for job_id in wanted)
            for job_id, position in zip(wanted, slots, strict=True):
                if queued[job_id] != position:
                    tx.execute("UPDATE jobs SET position = ? WHERE id = ?", (position, job_id))

    def interrupt_running(self, message: str) -> int:
        """ทุกงาน running -> interrupted (E_INTERRUPTED) ใช้ตอนเปิดโปรแกรมใหม่และตอนปิดโปรแกรม"""
        stamp = self._stamp()
        with self._db.transaction() as tx:
            rows = tx.execute(
                "UPDATE jobs SET status = 'interrupted', error_code = 'E_INTERRUPTED', error_message = ?, "
                "finished_at = ?, stage = NULL, speed_bps = NULL, eta_s = NULL, attempt = 0 "
                "WHERE status = 'running' RETURNING id",
                (message, stamp),
            )
        return len(rows)

    def pending_count(self) -> int:
        rows = self._db.execute("SELECT count(*) AS n FROM jobs WHERE status IN ('queued', 'running')")
        return int(rows[0]["n"])
