from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from yttoolkit.config import Paths
from yttoolkit.core.db import SCHEMA_VERSION, Database, purge_stale_cache

NOW = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def db(tmp_path: Path):
    database = Database(tmp_path / "app.db")
    database.migrate()
    yield database
    database.close()


def add_video(db: Database, video_id: str, opened_at: datetime) -> None:
    db.execute(
        "INSERT INTO videos (video_id, title, probe_json, probed_at, opened_at) VALUES (?, ?, ?, ?, ?)",
        (video_id, f"title {video_id}", "{}", opened_at.isoformat(), opened_at.isoformat()),
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
    first.execute("INSERT INTO settings (key, value_json) VALUES ('k', '1')")
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
    add_video(db, "oldvideo0001", NOW - timedelta(days=31))
    folder = make_cache(cache, "oldvideo0001")
    assert purge_stale_cache(db, cache, NOW) == 1
    assert db.execute("SELECT video_id FROM videos") == []
    assert not folder.exists()


def test_purge_keeps_recent_rows_and_folders(db: Database, tmp_path: Path):
    cache = tmp_path / "cache"
    add_video(db, "newvideo0001", NOW - timedelta(days=29))
    folder = make_cache(cache, "newvideo0001")
    assert purge_stale_cache(db, cache, NOW) == 0
    assert len(db.execute("SELECT video_id FROM videos")) == 1
    assert folder.is_dir()


def test_purge_keeps_videos_that_have_jobs(db: Database, tmp_path: Path):
    cache = tmp_path / "cache"
    add_video(db, "jobvideo0001", NOW - timedelta(days=90))
    add_job(db, "job-1", "jobvideo0001")
    folder = make_cache(cache, "jobvideo0001")
    assert purge_stale_cache(db, cache, NOW) == 0
    assert len(db.execute("SELECT video_id FROM videos")) == 1
    assert folder.is_dir()


def test_purge_ignores_missing_folder(db: Database, tmp_path: Path):
    add_video(db, "nofolder0001", NOW - timedelta(days=40))
    assert purge_stale_cache(db, tmp_path / "cache", NOW) == 1
    assert db.execute("SELECT video_id FROM videos") == []


def test_purge_custom_days(db: Database, tmp_path: Path):
    add_video(db, "midvideo0001", NOW - timedelta(days=10))
    assert purge_stale_cache(db, tmp_path / "cache", NOW, days=7) == 1
