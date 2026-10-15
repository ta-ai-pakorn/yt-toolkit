"""ฐานข้อมูล SQLite (data/app.db) และการล้าง cache ของคลิปที่ไม่ได้เปิดนาน"""

from __future__ import annotations

import logging
import shutil
import sqlite3
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .inputs import VIDEO_ID

log = logging.getLogger("yttoolkit")

SCHEMA_VERSION = 3

# v2: ไม่มี foreign key ไป videos (W3 เข้าคิวคลิปที่ยังไม่เคย probe ได้) และมีช่องของงาน M4 เพิ่ม
# แช่แข็งไว้ตามที่เป็นตอน v2: _MIGRATIONS[2] ต้องสร้างตารางแบบ v2 เสมอ ไม่งั้นอัปเกรด v1 -> v2 -> v3
# จะได้คอลัมน์ของ v3 ตั้งแต่ขั้น 2 แล้ว ALTER ของขั้น 3 ล้ม (duplicate column)
_JOBS_V2 = """
CREATE TABLE jobs (
  id            TEXT PRIMARY KEY,
  video_id      TEXT NOT NULL,
  title         TEXT NOT NULL DEFAULT '',
  kind          TEXT NOT NULL,
  params_json   TEXT NOT NULL,
  status        TEXT NOT NULL,
  stage         TEXT,
  progress      REAL,
  speed_bps     INTEGER,
  eta_s         INTEGER,
  attempt       INTEGER NOT NULL DEFAULT 0,
  bot_checks    INTEGER NOT NULL DEFAULT 0,
  position      INTEGER NOT NULL,
  error_code    TEXT,
  error_message TEXT,
  error_detail  TEXT,
  notes_json    TEXT,
  outputs_json  TEXT,
  created_at    TEXT NOT NULL,
  started_at    TEXT,
  finished_at   TEXT
);
CREATE INDEX jobs_status_position ON jobs(status, position);
CREATE INDEX IF NOT EXISTS jobs_video ON jobs(video_id, status);
"""

# v3 (M6 รอบ A): filename_style = รูปแบบชื่อไฟล์ ณ ตอนเริ่มงานครั้งแรก (NULL = ยังไม่เริ่ม หรืองานก่อน M6 = "title")
_JOBS = """
CREATE TABLE jobs (
  id            TEXT PRIMARY KEY,
  video_id      TEXT NOT NULL,
  title         TEXT NOT NULL DEFAULT '',
  kind          TEXT NOT NULL,
  params_json   TEXT NOT NULL,
  status        TEXT NOT NULL,
  stage         TEXT,
  progress      REAL,
  speed_bps     INTEGER,
  eta_s         INTEGER,
  attempt       INTEGER NOT NULL DEFAULT 0,
  bot_checks    INTEGER NOT NULL DEFAULT 0,
  position      INTEGER NOT NULL,
  error_code    TEXT,
  error_message TEXT,
  error_detail  TEXT,
  notes_json    TEXT,
  outputs_json  TEXT,
  created_at    TEXT NOT NULL,
  started_at    TEXT,
  finished_at   TEXT,
  filename_style TEXT
);
CREATE INDEX jobs_status_position ON jobs(status, position);
CREATE INDEX IF NOT EXISTS jobs_video ON jobs(video_id, status);
"""

_SCHEMA = f"""
CREATE TABLE schema_version (version INTEGER NOT NULL);

CREATE TABLE videos (
  video_id      TEXT PRIMARY KEY,
  title         TEXT NOT NULL,
  channel       TEXT,
  duration_s    INTEGER,
  thumbnail_url TEXT,
  chapters_json TEXT,
  probe_json    TEXT NOT NULL,
  probed_at     TEXT NOT NULL,
  opened_at     TEXT NOT NULL
);

{_JOBS}CREATE TABLE settings (key TEXT PRIMARY KEY, value_json TEXT NOT NULL);
"""

_V1_JOB_COLUMNS = (
    "id, video_id, kind, params_json, status, stage, progress, speed_bps, eta_s, position, "
    "error_code, error_detail, outputs_json, created_at, started_at, finished_at"
)

# สคริปต์อัปเกรดจากเวอร์ชัน (key - 1) ไปเป็น key แต่ละตัวรันใน transaction เดียว
_MIGRATIONS: dict[int, str] = {
    2: f"""
DROP INDEX IF EXISTS jobs_status_position;
ALTER TABLE jobs RENAME TO jobs_v1;
{_JOBS_V2}
INSERT INTO jobs ({_V1_JOB_COLUMNS}) SELECT {_V1_JOB_COLUMNS} FROM jobs_v1;
DROP TABLE jobs_v1;
UPDATE schema_version SET version = 2;
""",
    3: """
ALTER TABLE jobs ADD COLUMN filename_style TEXT;
UPDATE schema_version SET version = 3;
""",
}


class Transaction:
    """ใช้ได้เฉพาะในบล็อก `with db.transaction()` ซึ่งถือ lock ไว้ทั้งบล็อกแล้ว"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def execute(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        return self._conn.execute(sql, params).fetchall()


class Database:
    """SQLite connection เดียว ใช้ร่วมกันได้ทุก thread โดยทุกการเข้าถึงผ่าน lock"""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()  # reentrant: db.execute ในบล็อก transaction ใช้ได้ ไม่ค้าง
        # isolation_level=None = autocommit: คำสั่งนอก transaction จบในตัว ไม่มี transaction ค้าง
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        # WAL + NORMAL: ไม่ fsync ทุก commit (คิวเขียนบ่อย) ไฟดับอาจเสียแค่ commit ท้ายๆ ไม่ทำให้ไฟล์พัง
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

    def migrate(self) -> None:
        with self._lock:
            try:
                self._migrate_locked()
            except BaseException:
                if self._conn.in_transaction:
                    self._conn.execute("ROLLBACK")
                raise

    def _migrate_locked(self) -> None:
        has_table = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version'"
        ).fetchone()
        if has_table is None:
            # ทำทั้งก้อนใน transaction เดียว ถ้าพังกลางทางจะไม่เหลือตารางครึ่งๆ
            self._conn.executescript(
                f"BEGIN;{_SCHEMA}INSERT INTO schema_version (version) VALUES ({SCHEMA_VERSION});COMMIT;"
            )
            return
        row = self._conn.execute("SELECT max(version) FROM schema_version").fetchone()
        found = row[0] if row and row[0] is not None else 0
        if found > SCHEMA_VERSION:
            raise RuntimeError(
                f"ฐานข้อมูลเป็นเวอร์ชัน {found} ใหม่กว่าโปรแกรมนี้ ({SCHEMA_VERSION}) "
                "ให้อัปเดตโปรแกรมก่อนเปิดใช้"
            )
        if found < 1:
            return  # ตาราง schema_version ว่าง ไม่รู้ว่าเป็นเวอร์ชันไหน จึงไม่แตะ (เหมือนเดิม)
        for version in range(found + 1, SCHEMA_VERSION + 1):
            # แต่ละขั้นทำใน transaction เดียว พังกลางทางแล้วย้อนกลับเป็นเวอร์ชันเดิมทั้งก้อน
            self._conn.executescript(f"BEGIN;{_MIGRATIONS[version]}COMMIT;")

    def execute(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    @contextmanager
    def transaction(self) -> Iterator[Transaction]:
        """ถือ lock ตลอดบล็อก: COMMIT เมื่อจบปกติ ROLLBACK เมื่อเกิด exception
        db.execute ในบล็อกเดียวกันจาก thread เดียวกันจะอยู่ใน transaction นี้ด้วย"""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield Transaction(self._conn)
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            else:
                self._conn.execute("COMMIT")

    def close(self) -> None:
        with self._lock:
            self._conn.close()


# opened_at ของคลิปที่แค่ "แอบดูชื่อ" (peek) ยังไม่เคยเปิดจริง: เก่ามากจึงไม่ขึ้นใน "ล่าสุด"
PEEK_SENTINEL = "1970-01-01T00:00:00+00:00"


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def purge_stale_cache(db: Database, cache_root: Path, now: datetime, days: int = 30) -> int:
    """ลบคลิปที่ไม่ได้เปิดเกิน `days` วัน พร้อมโฟลเดอร์ cache คลิปที่ยังมีงานอ้างอิงอยู่จะไม่ถูกลบ
    ลบโฟลเดอร์ก่อนแล้วค่อยลบแถว ถ้าลบโฟลเดอร์ไม่ได้จะเก็บแถวไว้ให้รอบหน้าลองใหม่"""
    cutoff = _parse_time(now.isoformat()) - timedelta(days=days)
    root = cache_root.resolve()
    rows = db.execute(
        "SELECT video_id, opened_at, probed_at FROM videos "
        "WHERE NOT EXISTS (SELECT 1 FROM jobs WHERE jobs.video_id = videos.video_id)"
    )
    removed = 0
    for row in rows:
        video_id = row["video_id"]
        try:
            # คลิปที่ไม่เคยเปิดจริง (peek อย่างเดียว) นับอายุจากเวลา probe แทน
            opened = _parse_time(row["probed_at"] if row["opened_at"] == PEEK_SENTINEL else row["opened_at"])
        except ValueError:
            continue  # เวลาอ่านไม่ออก ไม่เสี่ยงลบ
        if opened >= cutoff:
            continue
        if not _remove_cache_folder(root, video_id):
            continue
        # ลบเฉพาะเมื่อแถวยังเหมือนตอนอ่าน: ถ้าผู้ใช้เพิ่งเปิดคลิปนี้ระหว่างรอบล้าง (opened_at/probed_at เปลี่ยน) ให้เก็บไว้
        deleted = db.execute(
            "DELETE FROM videos WHERE video_id = ? AND opened_at = ? AND probed_at = ? "
            "AND NOT EXISTS (SELECT 1 FROM jobs WHERE jobs.video_id = videos.video_id) "
            "RETURNING video_id",
            (video_id, row["opened_at"], row["probed_at"]),
        )
        removed += len(deleted)
    return removed


def cache_folder(root: Path, name: str) -> Path | None:
    """โฟลเดอร์ cache ของคลิป `<root>/<name>` (resolve แล้ว) เมื่อ name เป็นรหัสคลิปที่ถูกรูป และยังอยู่ใต้ root
    (ไม่ใช่ root เอง) · ไม่ผ่าน = None ผู้เรียกต้องไม่แตะดิสก์ · root ต้อง resolve มาแล้ว
    ที่เดียวที่ตัดสินว่าชื่อไหนเป็นโฟลเดอร์ cache ที่แอพสร้าง (ล้าง cache เก่า และปุ่มล้างข้อมูลชั่วคราว M6 รอบ A)
    งานในอนาคต (เว็บอื่น C12): เปลี่ยนการตรวจ VIDEO_ID ตรงนี้เป็นตัวตรวจ cache key ที่เดียว"""
    if not VIDEO_ID.fullmatch(name):
        return None
    folder = (root / name).resolve()
    if folder == root or not folder.is_relative_to(root):
        return None
    return folder


def _remove_cache_folder(root: Path, video_id: str) -> bool:
    """คืน True เมื่อไม่มีโฟลเดอร์เหลือค้าง (ลบแล้ว ไม่มี หรือ id ผิดรูปจึงไม่แตะดิสก์)"""
    if not VIDEO_ID.fullmatch(video_id):
        log.warning("ข้ามการลบโฟลเดอร์ cache: video_id รูปแบบไม่ถูกต้อง %r", video_id)
        return True
    folder = cache_folder(root, video_id)
    if folder is None:
        log.warning("cache_skip reason=outside_root")
        return True
    if not folder.exists():
        return True
    try:
        shutil.rmtree(folder)
    except OSError as e:
        log.warning("ลบโฟลเดอร์ cache ไม่ได้ %s: %s", folder, e)
        return False
    return True
