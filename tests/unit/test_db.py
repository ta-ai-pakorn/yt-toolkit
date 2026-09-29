from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from yttoolkit.config import Paths
from yttoolkit.core import db as db_module
from yttoolkit.core.db import SCHEMA_VERSION, Database, purge_stale_cache

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
