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

SCHEMA_VERSION = 1

_SCHEMA = """
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

CREATE TABLE jobs (
  id            TEXT PRIMARY KEY,
  video_id      TEXT NOT NULL REFERENCES videos(video_id),
  kind          TEXT NOT NULL,
  params_json   TEXT NOT NULL,
  status        TEXT NOT NULL,
  stage         TEXT,
  progress      REAL,
  speed_bps     INTEGER,
  eta_s         INTEGER,
  position      INTEGER NOT NULL,
  error_code    TEXT,
  error_detail  TEXT,
  outputs_json  TEXT,
  created_at    TEXT NOT NULL,
  started_at    TEXT,
  finished_at   TEXT
);
CREATE INDEX jobs_status_position ON jobs(status, position);

CREATE TABLE settings (key TEXT PRIMARY KEY, value_json TEXT NOT NULL);
"""


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


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def purge_stale_cache(db: Database, cache_root: Path, now: datetime, days: int = 30) -> int:
    """ลบคลิปที่ไม่ได้เปิดเกิน `days` วัน พร้อมโฟลเดอร์ cache คลิปที่ยังมีงานอ้างอิงอยู่จะไม่ถูกลบ
    ลบโฟลเดอร์ก่อนแล้วค่อยลบแถว ถ้าลบโฟลเดอร์ไม่ได้จะเก็บแถวไว้ให้รอบหน้าลองใหม่"""
    cutoff = _parse_time(now.isoformat()) - timedelta(days=days)
    root = cache_root.resolve()
    rows = db.execute(
        "SELECT video_id, opened_at FROM videos "
        "WHERE NOT EXISTS (SELECT 1 FROM jobs WHERE jobs.video_id = videos.video_id)"
    )
    removed = 0
    for row in rows:
        video_id = row["video_id"]
        try:
            opened = _parse_time(row["opened_at"])
        except ValueError:
            continue  # เวลาอ่านไม่ออก ไม่เสี่ยงลบ
        if opened >= cutoff:
            continue
        if not _remove_cache_folder(root, video_id):
            continue
        deleted = db.execute(
            "DELETE FROM videos WHERE video_id = ? "
            "AND NOT EXISTS (SELECT 1 FROM jobs WHERE jobs.video_id = videos.video_id) "
            "RETURNING video_id",
            (video_id,),
        )
        removed += len(deleted)
    return removed


def _remove_cache_folder(root: Path, video_id: str) -> bool:
    """คืน True เมื่อไม่มีโฟลเดอร์เหลือค้าง (ลบแล้ว ไม่มี หรือ id ผิดรูปจึงไม่แตะดิสก์)"""
    if not VIDEO_ID.fullmatch(video_id):
        log.warning("ข้ามการลบโฟลเดอร์ cache: video_id รูปแบบไม่ถูกต้อง %r", video_id)
        return True
    folder = (root / video_id).resolve()
    if folder == root or not folder.is_relative_to(root):
        log.warning("ข้ามการลบโฟลเดอร์ cache: %s อยู่นอก %s", folder, root)
        return True
    if not folder.exists():
        return True
    try:
        shutil.rmtree(folder)
    except OSError as e:
        log.warning("ลบโฟลเดอร์ cache ไม่ได้ %s: %s", folder, e)
        return False
    return True
