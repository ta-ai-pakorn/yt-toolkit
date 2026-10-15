from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from yttoolkit.config import Paths
from yttoolkit.core import db as db_module
from yttoolkit.core.db import PEEK_SENTINEL, SCHEMA_VERSION, Database, purge_stale_cache

NOW = datetime(2026, 9, 29, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def db(tmp_path: Path):
    database = Database(tmp_path / "app.db")
    database.migrate()
    yield database
    database.close()


def add_video(db: Database, video_id: str, opened_at: datetime | str) -> None:
    stamp = opened_at if isinstance(opened_at, str) else opened_at.isoformat()
    db.execute(
        "INSERT INTO videos (video_id, title, probe_json, probed_at, opened_at) VALUES (?, ?, ?, ?, ?)",
        (video_id, f"title {video_id}", "{}", stamp, stamp),
    )


def add_job(db: Database, job_id: str, video_id: str) -> None:
    db.execute(
        "INSERT INTO jobs (id, video_id, kind, params_json, status, position, created_at) "
        "VALUES (?, ?, 'video', '{}', 'done', 1, ?)",
        (job_id, video_id, NOW.isoformat()),
    )


def make_cache(cache_root: Path, video_id: str) -> Path:
    folder = cache_root / video_id / "storyboard"
    folder.mkdir(parents=True)
    (folder / "0.jpg").write_bytes(b"x")
    return cache_root / video_id


def test_paths_db_and_cache(tmp_path: Path):
    p = Paths(data_root=tmp_path)
    assert p.db == tmp_path / "data" / "app.db"
    assert p.cache == tmp_path / "data" / "cache"
    p.ensure()
    assert p.cache.is_dir()


def test_fresh_database_migrates(db: Database):
    rows = db.execute("SELECT version FROM schema_version")
    assert [r["version"] for r in rows] == [SCHEMA_VERSION]
    tables = {r["name"] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"schema_version", "videos", "jobs", "settings"} <= tables
    indexes = {r["name"] for r in db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "jobs_status_position" in indexes


def test_pragmas(db: Database):
    assert db.execute("PRAGMA journal_mode")[0][0] == "wal"
    assert db.execute("PRAGMA foreign_keys")[0][0] == 1
    assert db.execute("PRAGMA synchronous")[0][0] == 1  # NORMAL


def test_migrate_twice_is_noop(db: Database):
    add_video(db, "aaaaaaaaaaa", NOW)
    db.migrate()
    assert len(db.execute("SELECT version FROM schema_version")) == 1
    assert len(db.execute("SELECT video_id FROM videos")) == 1


def test_newer_database_refuses_to_open(tmp_path: Path):
    first = Database(tmp_path / "app.db")
    first.migrate()
    first.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION + 1,))
    first.close()
    second = Database(tmp_path / "app.db")
    try:
        with pytest.raises(RuntimeError):
            second.migrate()
    finally:
        second.close()


def test_state_survives_reopen(tmp_path: Path):
    first = Database(tmp_path / "app.db")
    first.migrate()
    try:
        first.execute("INSERT INTO settings (key, value_json) VALUES ('k', '1')")
    finally:
        first.close()
    second = Database(tmp_path / "app.db")
    second.migrate()
    try:
        assert second.execute("SELECT value_json FROM settings WHERE key='k'")[0]["value_json"] == "1"
    finally:
        second.close()


def test_concurrent_execute_from_threads(db: Database):
    errors: list[BaseException] = []

    def worker(n: int) -> None:
        try:
            for i in range(25):
                db.execute(
                    "INSERT INTO settings (key, value_json) VALUES (?, ?)", (f"k{n}-{i}", str(i))
                )
                db.execute("SELECT count(*) FROM settings")
        except BaseException as e:  # noqa: BLE001 - เก็บไว้ตรวจนอก thread
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert db.execute("SELECT count(*) FROM settings")[0][0] == 8 * 25


def test_purge_removes_old_rows_and_folders(db: Database, tmp_path: Path):
    cache = tmp_path / "cache"
    add_video(db, "oldvideo001", NOW - timedelta(days=31))
    folder = make_cache(cache, "oldvideo001")
    assert purge_stale_cache(db, cache, NOW) == 1
    assert db.execute("SELECT video_id FROM videos") == []
    assert not folder.exists()


def test_purge_keeps_recent_rows_and_folders(db: Database, tmp_path: Path):
    cache = tmp_path / "cache"
    add_video(db, "newvideo001", NOW - timedelta(days=29))
    folder = make_cache(cache, "newvideo001")
    assert purge_stale_cache(db, cache, NOW) == 0
    assert len(db.execute("SELECT video_id FROM videos")) == 1
    assert folder.is_dir()


def test_purge_keeps_videos_that_have_jobs(db: Database, tmp_path: Path):
    cache = tmp_path / "cache"
    add_video(db, "jobvideo001", NOW - timedelta(days=90))
    add_job(db, "job-1", "jobvideo001")
    folder = make_cache(cache, "jobvideo001")
    assert purge_stale_cache(db, cache, NOW) == 0
    assert len(db.execute("SELECT video_id FROM videos")) == 1
    assert folder.is_dir()


def test_purge_ignores_missing_folder(db: Database, tmp_path: Path):
    add_video(db, "nofolder001", NOW - timedelta(days=40))
    assert purge_stale_cache(db, tmp_path / "cache", NOW) == 1
    assert db.execute("SELECT video_id FROM videos") == []


def test_purge_custom_days(db: Database, tmp_path: Path):
    add_video(db, "midvideo001", NOW - timedelta(days=10))
    assert purge_stale_cache(db, tmp_path / "cache", NOW, days=7) == 1


def test_purge_naive_now_is_treated_as_utc(db: Database, tmp_path: Path):
    add_video(db, "oldvideo001", NOW - timedelta(days=31))
    add_video(db, "newvideo001", NOW - timedelta(days=29))
    assert purge_stale_cache(db, tmp_path / "cache", NOW.replace(tzinfo=None)) == 1
    assert [r["video_id"] for r in db.execute("SELECT video_id FROM videos")] == ["newvideo001"]


def test_purge_naive_opened_at_is_treated_as_utc(db: Database, tmp_path: Path):
    add_video(db, "oldvideo001", (NOW - timedelta(days=31)).replace(tzinfo=None))
    assert purge_stale_cache(db, tmp_path / "cache", NOW) == 1


def test_purge_z_offset(db: Database, tmp_path: Path):
    add_video(db, "oldvideo001", "2026-08-01T00:00:00Z")
    add_video(db, "newvideo001", "2026-09-20T00:00:00Z")
    assert purge_stale_cache(db, tmp_path / "cache", NOW) == 1
    assert [r["video_id"] for r in db.execute("SELECT video_id FROM videos")] == ["newvideo001"]


def test_purge_respects_plus_seven_offset(db: Database, tmp_path: Path):
    # cutoff = 2026-08-30T12:00Z, 18:30+07:00 = 11:30Z (เก่ากว่า), 19:30+07:00 = 12:30Z (ใหม่กว่า)
    add_video(db, "oldvideo001", "2026-08-30T18:30:00+07:00")
    add_video(db, "newvideo001", "2026-08-30T19:30:00+07:00")
    assert purge_stale_cache(db, tmp_path / "cache", NOW) == 1
    assert [r["video_id"] for r in db.execute("SELECT video_id FROM videos")] == ["newvideo001"]


def test_purge_skips_unparseable_opened_at(db: Database, tmp_path: Path):
    add_video(db, "badstamp001", "not a date")
    assert purge_stale_cache(db, tmp_path / "cache", NOW) == 0
    assert len(db.execute("SELECT video_id FROM videos")) == 1


@pytest.mark.parametrize(
    "bad_id", ["..", "../x", "a/b", "a\\b", "short", "toolongvideoid1", "", "abc def ghi"]
)
def test_purge_never_touches_disk_for_invalid_ids(db: Database, tmp_path: Path, caplog, bad_id: str):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "keep.txt").write_text("x")
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    (sibling / "keep.txt").write_text("x")
    add_video(db, bad_id, NOW - timedelta(days=99))
    with caplog.at_level(logging.WARNING, logger="yttoolkit"):
        assert purge_stale_cache(db, cache, NOW) == 1
    assert db.execute("SELECT video_id FROM videos") == []
    assert (cache / "keep.txt").is_file()
    assert (sibling / "keep.txt").is_file()
    assert tmp_path.is_dir()
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_purge_keeps_row_when_folder_removal_fails(db: Database, tmp_path: Path, monkeypatch, caplog):
    cache = tmp_path / "cache"
    add_video(db, "oldvideo001", NOW - timedelta(days=40))
    folder = make_cache(cache, "oldvideo001")

    def boom(path, *args, **kwargs):
        raise PermissionError("locked")

    monkeypatch.setattr(db_module.shutil, "rmtree", boom)
    with caplog.at_level(logging.WARNING, logger="yttoolkit"):
        assert purge_stale_cache(db, cache, NOW) == 0
    assert len(db.execute("SELECT video_id FROM videos")) == 1
    assert folder.is_dir()
    assert any(r.levelno == logging.WARNING for r in caplog.records)
    monkeypatch.undo()
    assert purge_stale_cache(db, cache, NOW) == 1
    assert not folder.exists()


def test_purge_does_not_count_row_that_gained_a_job(db: Database, tmp_path: Path, monkeypatch):
    add_video(db, "oldvideo001", NOW - timedelta(days=40))
    real_rmtree = db_module.shutil.rmtree

    def rmtree_then_job(path, *args, **kwargs):
        real_rmtree(path, *args, **kwargs)
        add_job(db, "job-late", "oldvideo001")

    cache = tmp_path / "cache"
    make_cache(cache, "oldvideo001")
    monkeypatch.setattr(db_module.shutil, "rmtree", rmtree_then_job)
    assert purge_stale_cache(db, cache, NOW) == 0
    assert len(db.execute("SELECT video_id FROM videos")) == 1


def test_failed_migrate_rolls_back_and_can_retry(tmp_path: Path, monkeypatch):
    database = Database(tmp_path / "app.db")
    try:
        with monkeypatch.context() as m:
            m.setattr(
                db_module,
                "_SCHEMA",
                "CREATE TABLE schema_version (version INTEGER NOT NULL); CREATE TABLE broken (;",
            )
            with pytest.raises(sqlite3.Error):
                database.migrate()
        assert database._conn.in_transaction is False
        assert database.execute("SELECT name FROM sqlite_master WHERE type='table'") == []
        database.migrate()
        assert [r["version"] for r in database.execute("SELECT version FROM schema_version")] == [
            SCHEMA_VERSION
        ]
    finally:
        database.close()


def test_transaction_commits(db: Database):
    with db.transaction() as tx:
        tx.execute("INSERT INTO settings (key, value_json) VALUES ('a', '1')")
        tx.execute("INSERT INTO settings (key, value_json) VALUES ('b', '2')")
        assert len(tx.execute("SELECT key FROM settings")) == 2
    assert len(db.execute("SELECT key FROM settings")) == 2
    assert db._conn.in_transaction is False


def test_transaction_rolls_back_on_exception(db: Database):
    with pytest.raises(ValueError), db.transaction() as tx:
        tx.execute("INSERT INTO settings (key, value_json) VALUES ('a', '1')")
        raise ValueError("boom")
    assert db.execute("SELECT key FROM settings") == []
    assert db._conn.in_transaction is False
    db.execute("INSERT INTO settings (key, value_json) VALUES ('b', '2')")
    assert len(db.execute("SELECT key FROM settings")) == 1


def test_transaction_holds_lock_against_other_threads(db: Database):
    inside = threading.Event()
    seen: list[int] = []

    def reader() -> None:
        inside.wait(timeout=5)
        seen.append(len(db.execute("SELECT key FROM settings")))

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    with db.transaction() as tx:
        tx.execute("INSERT INTO settings (key, value_json) VALUES ('a', '1')")
        inside.set()
        t.join(timeout=0.3)
        assert t.is_alive()  # reader ติด lock ระหว่าง transaction
    t.join(timeout=5)
    assert seen == [1]


def test_db_execute_inside_transaction_joins_it(db: Database):
    db.execute("INSERT INTO settings (key, value_json) VALUES ('a', '1')")
    with pytest.raises(RuntimeError), db.transaction():
        db.execute("UPDATE settings SET value_json = '2' WHERE key = 'a'")  # ไม่ค้าง เพราะ lock เป็น RLock
        raise RuntimeError("boom")
    assert db.execute("SELECT value_json FROM settings WHERE key = 'a'")[0]["value_json"] == "1"


def add_peeked_video(db: Database, video_id: str, probed_at: datetime) -> None:
    db.execute(
        "INSERT INTO videos (video_id, title, probe_json, probed_at, opened_at) VALUES (?, ?, ?, ?, ?)",
        (video_id, f"title {video_id}", "{}", probed_at.isoformat(), PEEK_SENTINEL),
    )


def test_purge_removes_peek_only_rows_30_days_after_probe(db: Database, tmp_path: Path):
    cache = tmp_path / "cache"
    add_peeked_video(db, "peekold0001", NOW - timedelta(days=31))
    folder = make_cache(cache, "peekold0001")
    assert purge_stale_cache(db, cache, NOW) == 1
    assert db.execute("SELECT video_id FROM videos") == []
    assert not folder.exists()


def test_purge_keeps_fresh_peek_only_rows(db: Database, tmp_path: Path):
    add_peeked_video(db, "peeknew0001", NOW - timedelta(days=1))
    assert purge_stale_cache(db, tmp_path / "cache", NOW) == 0
    assert len(db.execute("SELECT video_id FROM videos")) == 1


def test_purge_keeps_row_reopened_during_the_purge(db: Database, tmp_path: Path, monkeypatch):
    cache_root = tmp_path / "cache"
    old = datetime(2026, 1, 1, tzinfo=UTC)
    db.execute(
        "INSERT INTO videos (video_id, title, probe_json, probed_at, opened_at) VALUES (?, ?, ?, ?, ?)",
        ("abcdefghijk", "t", "{}", old.isoformat(), old.isoformat()),
    )
    real_remove = db_module._remove_cache_folder

    def reopen_then_remove(root, video_id):
        # ผู้ใช้เปิดคลิปนี้พอดีระหว่างรอบล้าง
        db.execute("UPDATE videos SET opened_at = ? WHERE video_id = ?", ("2026-03-01T00:00:00+00:00", video_id))
        return real_remove(root, video_id)

    monkeypatch.setattr(db_module, "_remove_cache_folder", reopen_then_remove)
    removed = purge_stale_cache(db, cache_root, datetime(2026, 3, 1, tzinfo=UTC))
    assert removed == 0
    assert len(db.execute("SELECT video_id FROM videos")) == 1


V1_JOBS = """CREATE TABLE schema_version (version INTEGER NOT NULL);
CREATE TABLE videos (video_id TEXT PRIMARY KEY, title TEXT NOT NULL, channel TEXT, duration_s INTEGER,
  thumbnail_url TEXT, chapters_json TEXT, probe_json TEXT NOT NULL, probed_at TEXT NOT NULL, opened_at TEXT NOT NULL);
CREATE TABLE jobs (id TEXT PRIMARY KEY, video_id TEXT NOT NULL REFERENCES videos(video_id), kind TEXT NOT NULL,
  params_json TEXT NOT NULL, status TEXT NOT NULL, stage TEXT, progress REAL, speed_bps INTEGER, eta_s INTEGER,
  position INTEGER NOT NULL, error_code TEXT, error_detail TEXT, outputs_json TEXT, created_at TEXT NOT NULL,
  started_at TEXT, finished_at TEXT);
CREATE INDEX jobs_status_position ON jobs(status, position);
CREATE TABLE settings (key TEXT PRIMARY KEY, value_json TEXT NOT NULL);
INSERT INTO schema_version (version) VALUES (1);"""


def test_fresh_database_is_v3_without_job_foreign_key(tmp_path):
    db = Database(tmp_path / "app.db")
    db.migrate()
    assert db.execute("SELECT max(version) AS v FROM schema_version")[0]["v"] == 3
    db.execute(
        "INSERT INTO jobs (id, video_id, kind, params_json, status, position, created_at) "
        "VALUES ('j1', 'notprobed01', 'video', '{}', 'queued', 1, '2026-10-01T00:00:00+00:00')"
    )
    cols = {r["name"] for r in db.execute("PRAGMA table_info(jobs)")}
    assert {"title", "attempt", "bot_checks", "error_message", "notes_json", "filename_style"} <= cols
    db.close()


def test_v1_database_migrates_and_keeps_rows(tmp_path):
    raw = sqlite3.connect(tmp_path / "app.db")
    raw.executescript(V1_JOBS)
    raw.execute("INSERT INTO videos VALUES ('aqz-KE-bpKQ','t',NULL,NULL,NULL,NULL,'{}','x','x')")
    raw.execute("INSERT INTO jobs (id, video_id, kind, params_json, status, position, created_at) "
                "VALUES ('old', 'aqz-KE-bpKQ', 'video', '{}', 'done', 3, 'x')")
    raw.commit()
    raw.close()
    db = Database(tmp_path / "app.db")
    db.migrate()
    row = db.execute("SELECT * FROM jobs WHERE id = 'old'")[0]
    assert (row["status"], row["position"], row["title"], row["attempt"]) == ("done", 3, "", 0)
    assert row["filename_style"] is None  # งานก่อน M6 = แบบ "title"
    assert db.execute("SELECT max(version) AS v FROM schema_version")[0]["v"] == 3
    assert not db.execute("SELECT 1 FROM sqlite_master WHERE name = 'jobs_v1'")
    # v2 ไม่มี foreign key แล้ว: งานของคลิปที่ไม่เคย probe ใส่ได้
    db.execute(
        "INSERT INTO jobs (id, video_id, kind, params_json, status, position, created_at) "
        "VALUES ('new', 'notprobed01', 'video', '{}', 'queued', 4, '2026-10-01T00:00:00+00:00')"
    )
    assert db.execute("SELECT video_id FROM jobs WHERE id = 'new'")[0]["video_id"] == "notprobed01"
    assert db.execute("PRAGMA foreign_key_list(jobs)") == []
    db.close()


def _jobs_video_index_columns(db: Database) -> list[str]:
    return [r["name"] for r in db.execute("PRAGMA index_info(jobs_video)")]


def test_fresh_database_has_jobs_video_index(tmp_path):
    # คำค้นงานตามคลิป (หน้าประวัติ ป้ายสถานะ และรอบล้างแคช) ไม่ต้องไล่ทั้งตาราง
    db = Database(tmp_path / "app.db")
    db.migrate()
    assert _jobs_video_index_columns(db) == ["video_id", "status"]
    db.close()


def test_v1_migration_adds_jobs_video_index(tmp_path):
    raw = sqlite3.connect(tmp_path / "app.db")
    raw.executescript(V1_JOBS)
    raw.commit()
    raw.close()
    db = Database(tmp_path / "app.db")
    db.migrate()
    assert _jobs_video_index_columns(db) == ["video_id", "status"]
    db.close()


def test_v1_migration_failure_rolls_back(tmp_path, monkeypatch):
    raw = sqlite3.connect(tmp_path / "app.db")
    raw.executescript(V1_JOBS)
    raw.commit()
    raw.close()
    db = Database(tmp_path / "app.db")
    try:
        with monkeypatch.context() as m:
            m.setitem(db_module._MIGRATIONS, 2, "ALTER TABLE jobs RENAME TO jobs_v1; CREATE TABLE broken (;")
            with pytest.raises(sqlite3.Error):
                db.migrate()
        assert db._conn.in_transaction is False
        assert db.execute("SELECT max(version) AS v FROM schema_version")[0]["v"] == 1
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name = 'jobs_v1'")
        db.migrate()
        assert db.execute("SELECT max(version) AS v FROM schema_version")[0]["v"] == 3
    finally:
        db.close()


# ---------- M6 รอบ A: schema v3 (jobs.filename_style) ----------


# สำเนาตาราง jobs ของ v2 ตามที่ M4-M6 รอบ B ส่งจริง (ตัวอักษรต่อตัวอักษร) แยกจากโค้ดที่ทดสอบ (รีวิว T2 M4):
# ถ้า db._JOBS_V2 เพี้ยน เทสข้างล่างจะจับได้ แทนที่ fixture จะเพี้ยนตามไปด้วย
V2_JOBS = """
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


def _v2_database(path: Path) -> None:
    """ฐานข้อมูล v2 ตามที่ M4-M6 รอบ B สร้างจริง (ตาราง jobs แบบ V2_JOBS) พร้อมงานหนึ่งงานและค่าตั้งหนึ่งค่า"""
    raw = sqlite3.connect(path)
    raw.executescript(
        "CREATE TABLE schema_version (version INTEGER NOT NULL);"
        "CREATE TABLE videos (video_id TEXT PRIMARY KEY, title TEXT NOT NULL, channel TEXT, duration_s INTEGER,"
        " thumbnail_url TEXT, chapters_json TEXT, probe_json TEXT NOT NULL, probed_at TEXT NOT NULL,"
        " opened_at TEXT NOT NULL);"
        f"{V2_JOBS}"
        "CREATE TABLE settings (key TEXT PRIMARY KEY, value_json TEXT NOT NULL);"
        "INSERT INTO schema_version (version) VALUES (2);"
    )
    raw.execute("INSERT INTO videos VALUES ('aqz-KE-bpKQ','t','ช่อง',60,NULL,NULL,'{}','x','x')")
    raw.execute(
        "INSERT INTO jobs (id, video_id, title, kind, params_json, status, attempt, bot_checks, position, "
        "error_code, notes_json, outputs_json, created_at, started_at, finished_at) VALUES "
        "('v2job', 'aqz-KE-bpKQ', 'ชื่อ', 'audio', '{\"format\": \"mp3\"}', 'failed', 0, 1, 7, 'E_NETWORK', "
        "'[\"NO_CHAPTERS\"]', NULL, 'c', 's', 'f')"
    )
    raw.execute("INSERT INTO settings VALUES ('concurrency', '3')")
    raw.commit()
    raw.close()


def test_v2_database_migrates_to_v3_and_keeps_every_row(tmp_path):
    _v2_database(tmp_path / "app.db")
    db = Database(tmp_path / "app.db")
    db.migrate()
    assert db.execute("SELECT max(version) AS v FROM schema_version")[0]["v"] == 3
    assert len(db.execute("SELECT version FROM schema_version")) == 1
    row = db.execute("SELECT * FROM jobs WHERE id = 'v2job'")[0]
    assert (row["title"], row["kind"], row["params_json"], row["status"], row["bot_checks"], row["position"]) == (
        "ชื่อ", "audio", '{"format": "mp3"}', "failed", 1, 7,
    )  # fmt: skip
    assert (row["error_code"], row["notes_json"], row["created_at"], row["finished_at"]) == (
        "E_NETWORK", '["NO_CHAPTERS"]', "c", "f",
    )  # fmt: skip
    assert row["filename_style"] is None
    assert db.execute("SELECT channel FROM videos")[0]["channel"] == "ช่อง"
    assert db.execute("SELECT value_json FROM settings WHERE key = 'concurrency'")[0]["value_json"] == "3"
    assert _jobs_video_index_columns(db) == ["video_id", "status"]
    db.migrate()  # ครั้งที่สอง = ไม่ทำอะไร
    assert db.execute("SELECT max(version) AS v FROM schema_version")[0]["v"] == 3
    db.close()


def test_v1_database_migrates_through_v2_to_v3(tmp_path):
    raw = sqlite3.connect(tmp_path / "app.db")
    raw.executescript(V1_JOBS)
    raw.execute("INSERT INTO videos VALUES ('aqz-KE-bpKQ','t',NULL,NULL,NULL,NULL,'{}','x','x')")
    raw.execute("INSERT INTO jobs (id, video_id, kind, params_json, status, position, created_at) "
                "VALUES ('old', 'aqz-KE-bpKQ', 'video', '{}', 'done', 3, 'x')")  # fmt: skip
    raw.commit()
    raw.close()
    db = Database(tmp_path / "app.db")
    db.migrate()
    cols = [r["name"] for r in db.execute("PRAGMA table_info(jobs)")]
    assert cols.count("filename_style") == 1 and cols[-1] == "filename_style"
    row = db.execute("SELECT * FROM jobs WHERE id = 'old'")[0]
    assert (row["status"], row["position"], row["filename_style"]) == ("done", 3, None)
    assert db.execute("SELECT max(version) AS v FROM schema_version")[0]["v"] == 3
    db.close()


def test_migration_2_still_builds_the_frozen_v2_table():
    assert db_module._JOBS_V2 == V2_JOBS  # ตารางที่แช่แข็งไว้ = ตาราง v2 ที่ส่งจริง
    assert "filename_style" not in db_module._JOBS_V2
    assert "filename_style" not in db_module._MIGRATIONS[2]
    assert db_module._JOBS_V2.strip() in db_module._MIGRATIONS[2]
    assert "filename_style" in db_module._JOBS and SCHEMA_VERSION == 3


def test_v3_migration_failure_rolls_back_to_v2(tmp_path, monkeypatch):
    _v2_database(tmp_path / "app.db")
    db = Database(tmp_path / "app.db")
    try:
        with monkeypatch.context() as m:
            m.setitem(db_module._MIGRATIONS, 3, "ALTER TABLE jobs ADD COLUMN filename_style TEXT; CREATE TABLE broken (;")
            with pytest.raises(sqlite3.Error):
                db.migrate()
        assert db.execute("SELECT max(version) AS v FROM schema_version")[0]["v"] == 2
        assert "filename_style" not in {r["name"] for r in db.execute("PRAGMA table_info(jobs)")}
        db.migrate()
        assert db.execute("SELECT max(version) AS v FROM schema_version")[0]["v"] == 3
    finally:
        db.close()


# ---------- M6 รอบ A: cache_folder (ตัวตรวจเดียวกับการล้าง cache เก่า) ----------


def test_cache_folder_accepts_only_video_id_folders_inside_the_root(tmp_path: Path):
    root = (tmp_path / "cache").resolve()
    root.mkdir()
    assert db_module.cache_folder(root, "aqz-KE-bpKQ") == root / "aqz-KE-bpKQ"
    for bad in ("..", "../x", "a/b", "a\\b", "short", "toolongvideoid1", "", ".clear-" + "a" * 32, "storyboard"):
        assert db_module.cache_folder(root, bad) is None, bad


# ---------- M6-A final fix: C4 ----------


def test_purge_skip_for_folder_outside_root_logs_no_path(db: Database, tmp_path: Path, monkeypatch, caplog):
    cache = tmp_path / "cache"
    add_video(db, "oldvideo001", NOW - timedelta(days=40))
    make_cache(cache, "oldvideo001")
    # a symlinked id folder resolves outside data/cache (symlinks need admin on Windows, so fake the check)
    monkeypatch.setattr(db_module, "cache_folder", lambda root, name: None)
    with caplog.at_level(logging.WARNING, logger="yttoolkit"):
        assert purge_stale_cache(db, cache, NOW) == 1
    assert "cache_skip reason=outside_root" in caplog.text
    assert str(tmp_path) not in caplog.text and "oldvideo001" not in caplog.text


def test_purge_failed_delete_logs_no_path(db: Database, tmp_path: Path, monkeypatch, caplog):
    cache = tmp_path / "cache"
    add_video(db, "oldvideo001", NOW - timedelta(days=40))
    make_cache(cache, "oldvideo001")

    def locked(path):
        raise PermissionError(13, "Access is denied", str(path))

    monkeypatch.setattr(db_module.shutil, "rmtree", locked)
    with caplog.at_level(logging.WARNING, logger="yttoolkit"):
        assert purge_stale_cache(db, cache, NOW) == 0
    assert "cache_skip reason=remove_failed" in caplog.text
    assert str(tmp_path) not in caplog.text and "oldvideo001" not in caplog.text
