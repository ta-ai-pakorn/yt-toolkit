"""API สถิติ (M6 รอบ C spec §2.2, AC-STAT-02 ฝั่ง server, AC-STAT-03)"""

from __future__ import annotations

import json
import socket

import pytest

from yttoolkit.core.db import Database
from yttoolkit.core.settings import SettingsStore

# ค่าเดียวกับ tests/api/conftest.py (import conftest ตรง ๆ ไม่ได้)
BASE = "http://127.0.0.1:8787"
AUTH = {"X-Toolkit-Token": "test-token", "Origin": BASE}


@pytest.fixture
def env(make_client, tmp_path):
    db = Database(tmp_path / "stats.db")
    db.migrate()
    settings = SettingsStore(db, tmp_path / "out")
    client = make_client(db=db, settings=settings)
    counter = {"n": 0}

    def add_job(video: str, finished: str, *, status: str = "done", size: int = 100, raw: str | None = None) -> None:
        counter["n"] += 1
        outputs = raw if raw is not None else json.dumps(
            [{"root": "C:/secret-root", "rel": "ชื่อคลิปลับ/a.mp4", "sizeBytes": size, "kind": "video"}]
        )
        db.execute(
            "INSERT INTO jobs (id, video_id, title, kind, params_json, status, position, outputs_json, created_at, finished_at) "
            "VALUES (?, ?, 'ชื่อคลิปลับ', 'video', '{}', ?, ?, ?, '2026-01-01T00:00:00+00:00', ?)",
            (f"job-{counter['n']}", video, status, counter["n"], outputs, finished),
        )

    yield client, db, settings, add_job
    db.close()


def recent(days_ago: int = 0) -> str:
    from datetime import UTC, datetime, timedelta

    return (datetime.now(UTC) - timedelta(days=days_ago)).isoformat(timespec="microseconds")


def test_no_stats_router_without_settings(make_client, tmp_path):
    db = Database(tmp_path / "x.db")
    db.migrate()
    try:
        assert make_client(db=db).get("/api/stats").status_code == 404
    finally:
        db.close()


def test_get_stats_shape_and_no_store(env):
    client, _, _, add_job = env
    add_job("A", recent(), size=1000)
    add_job("B", recent(), size=24)
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-store"
    body = resp.json()
    assert set(body) == {"since", "clips", "files", "totalBytes", "byKind", "byMonth"}
    assert (body["since"], body["clips"], body["files"], body["totalBytes"]) == (None, 2, 2, 1024)
    assert body["byKind"] == [{"kind": "video", "files": 2, "bytes": 1024}]
    assert len(body["byMonth"]) == 1


def test_get_stats_needs_no_token(env):
    client = env[0]
    assert client.get("/api/stats", headers={"Origin": BASE}).status_code == 200


def test_ac_stat_02_answers_with_the_network_cut(env, monkeypatch):
    client, _, _, add_job = env
    add_job("A", recent())

    real_connect = socket.socket.connect

    def refuse_outside(self, address, *args, **kwargs):
        # Windows asyncio ใช้ loopback socketpair ภายใน (self-pipe) จึงตัดเฉพาะปลายทางนอกเครื่อง
        if not (isinstance(address, tuple) and address and address[0] in ("127.0.0.1", "::1", "localhost")):
            raise OSError("network cut")
        return real_connect(self, address, *args, **kwargs)

    def refuse(*_args, **_kwargs):
        raise OSError("network cut")

    monkeypatch.setattr(socket.socket, "connect", refuse_outside)
    monkeypatch.setattr(socket, "create_connection", refuse)
    resp = client.get("/api/stats")
    assert resp.status_code == 200 and resp.json()["clips"] == 1


def test_ac_stat_03_reset_zeroes_and_keeps_everything_else(env, tmp_path):
    client, db, _, add_job = env
    add_job("A", recent(1))
    add_job("B", recent(1), status="failed")
    output = tmp_path / "out" / "a.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"x" * 10)
    jobs_before = [dict(r) for r in db.execute("SELECT * FROM jobs ORDER BY id")]
    resp = client.post("/api/stats/reset", headers=AUTH)
    assert resp.status_code == 200
    since = resp.json()["since"]
    assert isinstance(since, str) and since
    stats = client.get("/api/stats").json()
    assert stats == {"since": since, "clips": 0, "files": 0, "totalBytes": 0, "byKind": [], "byMonth": []}
    assert [dict(r) for r in db.execute("SELECT * FROM jobs ORDER BY id")] == jobs_before
    assert output.read_bytes() == b"x" * 10
    add_job("C", recent())  # เสร็จหลังล้าง = นับ
    assert client.get("/api/stats").json()["clips"] == 1


def test_reset_counts_from_the_click_at_sub_second_precision(env, monkeypatch):
    """final review I1: งานที่เสร็จก่อนกดล้างไม่ถึงวินาที ต้องไม่ถูกนับหลังล้าง"""
    from datetime import UTC, datetime

    client, _, _, add_job = env
    clock = datetime(2099, 1, 1, 5, 0, 0, 900000, tzinfo=UTC)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock

    monkeypatch.setattr("yttoolkit.api.stats.datetime", FrozenDatetime)
    add_job("A", "2099-01-01T05:00:00.400000+00:00")
    resp = client.post("/api/stats/reset", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["since"] == "2099-01-01T05:00:00.900000+00:00"
    assert client.get("/api/stats").json()["clips"] == 0


def test_reset_changes_only_stats_reset_at(env):
    client, _, settings, _ = env
    before = settings.get()
    client.post("/api/stats/reset", headers=AUTH)
    after = settings.get()
    assert {k: v for k, v in after.items() if k != "statsResetAt"} == {
        k: v for k, v in before.items() if k != "statsResetAt"
    }


def test_reset_needs_the_token(env):
    client, _, settings, _ = env
    resp = client.post("/api/stats/reset", headers={"Origin": BASE})
    assert resp.status_code == 403
    assert settings.get()["statsResetAt"] is None


def test_patch_still_rejects_stats_reset_at(env):
    client = env[0]
    resp = client.patch("/api/settings", headers=AUTH, json={"statsResetAt": None})
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "E_BAD_REQUEST"


def test_one_broken_row_does_not_break_the_endpoint(env):
    client, _, _, add_job = env
    add_job("A", recent(), size=7)
    add_job("B", recent(), raw='"oops"')
    add_job("C", recent(), raw='[{"kind": "video", "sizeBytes": "12"}]')
    add_job("D", "yesterday")
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert (body["clips"], body["files"], body["totalBytes"]) == (3, 2, 7)


def test_response_has_no_title_or_path(env):
    client, _, _, add_job = env
    add_job("A", recent())
    text = client.get("/api/stats").text
    for leak in ("ชื่อคลิปลับ", "secret-root", "C:/", "a.mp4", "test-token"):
        assert leak not in text
