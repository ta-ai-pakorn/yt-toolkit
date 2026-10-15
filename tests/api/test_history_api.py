"""ประวัติคลิป (C15): GET /api/history?scope=all|opened, outputs ของงานที่เสร็จ และ lastAt

ใช้ FakeExtractor + ฐานข้อมูลชั่วคราว แถวงานโหลดใส่ลง DB ตรง ๆ (ยังไม่ผ่านตัวรันคิว)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from yttoolkit.core.db import Database
from yttoolkit.core.extractor import FakeExtractor
from yttoolkit.core.videos import VideoService

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
BBB = "aqz-KE-bpKQ"
ZOO = "jNQXAC9IVRw"
THAI = "88o5Sk8_m1Y"
T0 = datetime(2026, 9, 29, 12, tzinfo=UTC)


def stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


@pytest.fixture
def env(make_client, tmp_path):
    db = Database(tmp_path / "history.db")
    db.migrate()
    fake = FakeExtractor(FIXTURES)
    clock = Clock()
    videos = VideoService(db, fake, now=clock)
    client = make_client(db=db, videos=videos, extractor=fake, cache_root=tmp_path / "cache")
    counter = {"n": 0}

    def add_job(
        video_id: str,
        kind: str,
        finished: datetime | None,
        *,
        status: str = "done",
        outputs: bool = True,
    ) -> None:
        counter["n"] += 1
        files = [{"root": "C:/out", "rel": "x/y.bin", "sizeBytes": 1, "kind": "video"}] if outputs else None
        db.execute(
            "INSERT INTO jobs (id, video_id, kind, params_json, status, position, outputs_json, "
            "created_at, finished_at) VALUES (?, ?, ?, '{}', ?, ?, ?, ?, ?)",
            (
                f"job-{counter['n']}",
                video_id,
                kind,
                status,
                counter["n"],
                json.dumps(files) if files else None,
                stamp(T0),
                stamp(finished) if finished else None,
            ),
        )

    yield client, clock, add_job
    db.close()


def ids(client, **params) -> list[str]:
    resp = client.get("/api/history", params=params)
    assert resp.status_code == 200
    return [item["videoId"] for item in resp.json()["items"]]


# ---------- scope=opened (พฤติกรรมเดิมของ W1 "ล่าสุด") ----------


def test_scope_opened_lists_only_opened_clips_and_excludes_peek(env):
    client, clock, add_job = env
    client.get(f"/api/videos/{BBB}")
    clock.advance(minutes=5)
    client.get(f"/api/videos/{ZOO}?peek=1")  # แค่ดูชื่อ ไม่นับว่าเปิด
    add_job(ZOO, "video", T0 + timedelta(hours=1))  # โหลดแล้วแต่ไม่เคยเปิดจริง
    body = client.get("/api/history", params={"scope": "opened"}).json()
    assert [i["videoId"] for i in body["items"]] == [BBB]
    assert body["total"] == 1
    assert body["items"][0]["lastAt"] == stamp(T0)  # = เวลาเปิด ไม่ใช่เวลางานเสร็จ


def test_scope_opened_still_reports_outputs_of_opened_clip(env):
    client, _, add_job = env
    client.get(f"/api/videos/{BBB}")
    add_job(BBB, "audio", T0 + timedelta(hours=1))
    item = client.get("/api/history", params={"scope": "opened"}).json()["items"][0]
    assert item["outputs"] == ["audio"]
    assert item["lastAt"] == stamp(T0)


# ---------- scope=all ----------


def test_scope_all_includes_never_opened_clip_with_done_job(env):
    client, _, add_job = env
    client.get(f"/api/videos/{BBB}")
    client.get(f"/api/videos/{ZOO}?peek=1")
    add_job(ZOO, "video", T0 + timedelta(hours=2))
    body = client.get("/api/history", params={"scope": "all"}).json()
    assert [i["videoId"] for i in body["items"]] == [ZOO, BBB]
    assert body["total"] == 2
    zoo = body["items"][0]
    assert zoo["outputs"] == ["video"]
    assert zoo["lastAt"] == stamp(T0 + timedelta(hours=2))  # ไม่เคยเปิด = เวลางานเสร็จ
    assert set(zoo) == {"videoId", "title", "channel", "thumbnailUrl", "durationS", "outputs", "lastAt"}


# ---------- M6 รอบ A: ชื่อช่อง (ตัวอย่างชื่อไฟล์แบบ title-channel ในหน้าตั้งค่า) ----------


@pytest.mark.parametrize("scope", ["opened", "all"])
def test_items_carry_the_channel(env, scope):
    client, clock, _ = env
    client.get(f"/api/videos/{BBB}")
    clock.advance(minutes=1)
    client.get(f"/api/videos/{THAI}")
    items = client.get("/api/history", params={"scope": scope}).json()["items"]
    assert [(i["videoId"], i["channel"]) for i in items] == [(THAI, "KOD THAI"), (BBB, "Blender")]


def test_an_unknown_channel_is_an_empty_string(env):
    client, _, _ = env
    client.get(f"/api/videos/{BBB}")
    env_db = client.app.state.ctx.db
    env_db.execute("UPDATE videos SET channel = NULL WHERE video_id = ?", (BBB,))
    (item,) = client.get("/api/history", params={"scope": "opened"}).json()["items"]
    assert item["channel"] == ""


def test_default_scope_is_all(env):
    client, _, add_job = env
    client.get(f"/api/videos/{ZOO}?peek=1")
    add_job(ZOO, "audio", T0)
    assert ids(client) == [ZOO]
    assert ids(client, scope="all") == [ZOO]
    assert ids(client, scope="opened") == []


@pytest.mark.parametrize(
    ("status", "outputs"),
    [("failed", True), ("queued", False), ("running", False), ("cancelled", False), ("done", False)],
)
def test_only_done_jobs_with_files_count(env, status, outputs):
    client, _, add_job = env
    client.get(f"/api/videos/{ZOO}?peek=1")
    add_job(ZOO, "video", T0 + timedelta(hours=1), status=status, outputs=outputs)
    assert ids(client, scope="all") == []
    assert client.get("/api/history").json() == {"items": [], "total": 0}


def test_outputs_are_distinct_and_in_fixed_order(env):
    client, _, add_job = env
    client.get(f"/api/videos/{BBB}")
    kinds = ["frames_zip", "note", "video", "subtitle", "contact_sheet", "audio", "video", "audio", "note"]
    for n, kind in enumerate(kinds):
        add_job(BBB, kind, T0 + timedelta(minutes=n))
    add_job(BBB, "subtitle", T0 + timedelta(hours=9), status="failed")
    for scope in ("all", "opened"):
        item = client.get("/api/history", params={"scope": scope}).json()["items"][0]
        assert item["outputs"] == ["video", "audio", "subtitle", "note", "contact_sheet", "frames_zip"]


def test_last_at_is_the_later_of_open_and_latest_finish(env):
    client, clock, add_job = env
    client.get(f"/api/videos/{BBB}")  # เปิดที่ T0
    client.get(f"/api/videos/{ZOO}")  # เปิดที่ T0
    clock.advance(hours=3)
    client.get(f"/api/videos/{THAI}")  # เปิดที่ T0+3h
    add_job(BBB, "video", T0 + timedelta(hours=5))  # หลังเปิด -> ใช้เวลาเสร็จ
    add_job(BBB, "audio", T0 + timedelta(hours=4))
    add_job(ZOO, "video", T0 - timedelta(hours=1))  # โหลดก่อนเปิดซ้ำ -> ใช้เวลาเปิด
    add_job(THAI, "video", T0 + timedelta(hours=1))
    items = {i["videoId"]: i for i in client.get("/api/history").json()["items"]}
    assert items[BBB]["lastAt"] == stamp(T0 + timedelta(hours=5))
    assert items[ZOO]["lastAt"] == stamp(T0)
    assert items[THAI]["lastAt"] == stamp(T0 + timedelta(hours=3))
    assert ids(client) == [BBB, THAI, ZOO]


def test_equal_last_at_sorts_by_video_id(env):
    client, _, _ = env
    client.get(f"/api/videos/{ZOO}")
    client.get(f"/api/videos/{BBB}")  # เวลาเปิดเท่ากัน
    client.get(f"/api/videos/{THAI}")
    assert ids(client) == sorted([ZOO, BBB, THAI])


def test_search_matches_title_in_every_scope(env):
    client, _, add_job = env
    client.get(f"/api/videos/{BBB}")
    client.get(f"/api/videos/{ZOO}?peek=1")
    add_job(ZOO, "video", T0)
    assert ids(client, q="zoo") == [ZOO]
    assert ids(client, q="BUNNY") == [BBB]
    assert ids(client, q="bunny", scope="opened") == [BBB]
    assert ids(client, q="zoo", scope="opened") == []
    assert client.get("/api/history", params={"q": "zoo"}).json()["total"] == 1
    assert client.get("/api/history", params={"q": "nothing-matches"}).json() == {"items": [], "total": 0}
    assert client.get("/api/history", params={"q": "%"}).json() == {"items": [], "total": 0}


def test_paging_keeps_total(env):
    client, clock, add_job = env
    client.get(f"/api/videos/{BBB}")
    clock.advance(minutes=1)
    client.get(f"/api/videos/{ZOO}")
    add_job(THAI, "audio", T0)  # ไม่มีแถวคลิป (ยังไม่เคย probe) จึงไม่ขึ้นรายการ
    body = client.get("/api/history", params={"limit": 1, "offset": 1}).json()
    assert body["total"] == 2
    assert [i["videoId"] for i in body["items"]] == [BBB]
    assert client.get("/api/history", params={"limit": 5, "offset": 5}).json() == {"items": [], "total": 2}


@pytest.mark.parametrize("scope", ["everything", "ALL", "", "opened,all"])
def test_unknown_scope_is_422(env, scope):
    client, _, _ = env
    resp = client.get("/api/history", params={"scope": scope})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "E_BAD_REQUEST"
