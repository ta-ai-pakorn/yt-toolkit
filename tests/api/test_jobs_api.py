from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import pytest

from yttoolkit.api.errors import redact_home
from yttoolkit.api.jobs import ITEMS_MAX, ORDER_IDS_MAX
from yttoolkit.core.db import Database
from yttoolkit.core.events import Event, EventBus
from yttoolkit.core.extractor import FakeExtractor
from yttoolkit.core.jobs import JobResult, JobStore, NewJob, OutputFile
from yttoolkit.core.media import FakeMediaTools
from yttoolkit.core.queue import QueueRunner
from yttoolkit.core.settings import SettingsStore
from yttoolkit.core.videos import VideoService
from yttoolkit.core.yterrors import MESSAGES

AUTH = {"X-Toolkit-Token": "test-token", "Origin": "http://127.0.0.1:8787"}

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
MISSING_ID = "00000000-0000-7000-8000-000000000000"
SUB_OPTIONS = {"maxChars": 42, "lines": 2, "minMs": 1000, "maxMs": 7000, "mode": "chars"}
VALID_ITEMS = [
    {"videoId": "aqz-KE-bpKQ", "kind": "video", "params": {"maxQuality": False, "splitChapters": False,
                                                           "noAudio": False, "audioLanguage": "original"},
     "title": "บิ๊กบัค"},
    {"videoId": "aqz-KE-bpKQ", "kind": "audio", "params": {"format": "mp3", "splitChapters": False,
                                                           "audioLanguage": "th"}},
    {"videoId": "88o5Sk8_m1Y", "kind": "subtitle", "params": {"trackId": "o.th-orig", "format": "srt",
                                                              "options": SUB_OPTIONS}},
    {"videoId": "aqz-KE-bpKQ", "kind": "contact_sheet", "params": {"source": "fast", "columns": 5}},
    {"videoId": "aqz-KE-bpKQ", "kind": "frames_zip", "params": {"source": "fast"}},
]


class ManualSpawn:
    def __init__(self) -> None:
        self.pending: list = []

    def __call__(self, fn) -> None:
        self.pending.append(fn)

    def run_all(self) -> None:
        while self.pending:
            self.pending.pop(0)()


class NoFfmpeg:
    def available(self) -> bool:
        return False


def finished_handler(job, ctx) -> JobResult:
    return JobResult(title="จบ")


class Env:
    def __init__(self, make_client, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.db = Database(tmp_path / "app.db")
        self.db.migrate()
        self.clock = {"now": datetime.now(UTC)}
        self.store = JobStore(self.db, now=lambda: self.clock["now"])
        self.bus = EventBus()
        self.sub = self.bus.subscribe()
        self.spawn = ManualSpawn()
        self.settings = SettingsStore(self.db, tmp_path / "out")
        self.revealed: list[Path] = []
        handlers = dict.fromkeys(("video", "audio", "subtitle", "note", "contact_sheet", "frames_zip"),
                                 finished_handler)
        self.runner = QueueRunner(self.store, self.bus, handlers, settings=self.settings, work_root=tmp_path / "work",
                                  rng=random.Random(1), spawn=self.spawn, redact=redact_home)
        self._make = make_client

    def client(self, **overrides):
        values = {"queue": self.runner, "events": self.bus, "settings": self.settings,
                  "media": FakeMediaTools(FIXTURES / "media"), **overrides}
        return self._make(**values)

    def events(self) -> list[Event]:
        out = []
        while (item := self.sub.get(0)) is not None:
            out.append(item)
        return out

    def add(self, n: int = 1, kind: str = "frames_zip") -> list:
        return self.store.add([NewJob(f"vid{i:08d}", kind, {"source": "fast"}) for i in range(n)])

    def finish(self, job_id: str, status: str = "done", at: datetime | None = None, **fields):
        self.clock["now"] = at or datetime.now(UTC)
        self.store.transition(job_id, "running")
        job = self.store.transition(job_id, status, **fields)
        self.clock["now"] = datetime.now(UTC)
        return job


@pytest.fixture
def env(make_client, tmp_path):
    e = Env(make_client, tmp_path)
    yield e
    e.runner.shutdown(timeout=0.1)
    e.bus.close()
    e.db.close()


# ---------- POST /jobs ----------


def test_post_valid_items_creates_jobs_and_events(env):
    client = env.client()
    resp = client.post("/api/jobs", json={"items": VALID_ITEMS}, headers=AUTH)
    assert resp.status_code == 200
    jobs = resp.json()["jobs"]
    assert [j["kind"] for j in jobs] == ["video", "audio", "subtitle", "contact_sheet", "frames_zip"]
    assert all(j["status"] == "queued" for j in jobs)
    assert jobs[0]["title"] == "บิ๊กบัค"
    assert jobs[1]["params"] == {"format": "mp3", "mp3Kbps": 192, "splitChapters": False, "audioLanguage": "th"}
    created = [e for e in env.events() if e.name == "job.created"]
    assert [e.data["id"] for e in created] == [j["id"] for j in jobs]
    assert env.store.pending_count() == 5


def test_post_normalises_defaults(env):
    client = env.client()
    items = [
        {"videoId": "aqz-KE-bpKQ", "kind": "video", "params": {}},
        {"videoId": "aqz-KE-bpKQ", "kind": "audio", "params": {"format": "wav", "mp3Kbps": 320}},
        {"videoId": "aqz-KE-bpKQ", "kind": "video", "params": {"embedSubs": "o.th", "subOptions": SUB_OPTIONS,
                                                              "maxHeight": 720, "formatId": "137"}},
    ]
    jobs = client.post("/api/jobs", json={"items": items}, headers=AUTH).json()["jobs"]
    assert jobs[0]["params"] == {"maxQuality": False, "splitChapters": False, "noAudio": False,
                                 "audioLanguage": "original"}
    assert jobs[1]["params"] == {"format": "wav", "splitChapters": False, "audioLanguage": "original"}
    assert jobs[2]["params"]["subOptions"] == SUB_OPTIONS and jobs[2]["params"]["maxHeight"] == 720


@pytest.mark.parametrize(
    "item",
    [
        {"videoId": "aqz-KE-bpKQ", "kind": "video", "params": {"range": {"startS": 0, "endS": 5}}},
        {"videoId": "aqz-KE-bpKQ", "kind": "video", "params": {"embedSubs": "o.th"}},
        # AC-VID-10 part 2: embedded subtitles together with split by chapter
        {"videoId": "aqz-KE-bpKQ", "kind": "video",
         "params": {"embedSubs": "o.th", "subOptions": SUB_OPTIONS, "splitChapters": True}},
        {"videoId": "aqz-KE-bpKQ", "kind": "video", "params": {"useCookies": True}},
        {"videoId": "aqz-KE-bpKQ", "kind": "video", "params": {"formatId": "137; rm"}},
        {"videoId": "aqz-KE-bpKQ", "kind": "video", "params": {"audioLanguage": "thai language"}},
        {"videoId": "aqz-KE-bpKQ", "kind": "video", "params": {"maxHeight": 480}},
        {"videoId": "aqz-KE-bpKQ", "kind": "audio", "params": {"format": "flac"}},
        {"videoId": "aqz-KE-bpKQ", "kind": "subtitle",
         "params": {"format": "srt", "options": {**SUB_OPTIONS, "minMs": 9000}}},
        {"videoId": "aqz-KE-bpKQ", "kind": "subtitle", "params": {"format": "srt", "options": SUB_OPTIONS,
                                                                  "trackId": "x.th"}},
        {"videoId": "aqz-KE-bpKQ", "kind": "contact_sheet", "params": {"source": "crisp"}},
        {"videoId": "short", "kind": "frames_zip", "params": {}},
        {"videoId": "aqz-KE-bpKQ", "kind": "frames_zip", "params": {}, "extra": 1},
    ],
)
def test_post_rejects_bad_items(env, item):
    client = env.client()
    resp = client.post("/api/jobs", json={"items": [VALID_ITEMS[3], item]}, headers=AUTH)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "E_BAD_REQUEST"
    assert env.store.pending_count() == 0


# ---------- POST /jobs: ตัวเลือกขั้นสูง (M5 รอบ A) ----------

VIDEO = {"maxQuality": False, "splitChapters": False, "noAudio": False, "audioLanguage": "original"}
RANGE = {"startMs": 90_000, "endMs": 300_000}


def video_item(video_id: str = "aqz-KE-bpKQ", **params) -> dict:
    return {"videoId": video_id, "kind": "video", "params": {**VIDEO, **params}}


def test_post_accepts_m5a_advanced_params(env):
    items = [
        video_item(range=RANGE),
        video_item(sponsorblock=["sponsor", "filler"]),
        video_item("jNQXAC9IVRw", splitChapters=True),
        {"videoId": "aqz-KE-bpKQ", "kind": "audio",
         "params": {"format": "mp3", "range": RANGE, "sponsorblock": ["intro"]}},
        {"videoId": "jNQXAC9IVRw", "kind": "audio", "params": {"format": "m4a", "splitChapters": True}},
        {"videoId": "88o5Sk8_m1Y", "kind": "subtitle",
         "params": {"trackId": "a.th-orig", "format": "txt", "options": SUB_OPTIONS, "range": RANGE}},
    ]
    resp = env.client().post("/api/jobs", json={"items": items}, headers=AUTH)
    assert resp.status_code == 200, resp.text
    stored = [job["params"] for job in resp.json()["jobs"]]
    assert stored[0] == {**VIDEO, "range": RANGE}
    assert stored[1] == {**VIDEO, "sponsorblock": ["sponsor", "filler"]}
    assert stored[2] == {**VIDEO, "splitChapters": True}
    assert stored[3] == {"format": "mp3", "mp3Kbps": 192, "splitChapters": False, "audioLanguage": "original",
                         "range": RANGE, "sponsorblock": ["intro"]}
    assert stored[4] == {"format": "m4a", "splitChapters": True, "audioLanguage": "original"}
    assert stored[5]["range"] == RANGE


@pytest.mark.parametrize(
    "params",
    [
        {"range": {"startMs": 90_000}},
        {"range": {**RANGE, "x": 1}},
        {"range": {"startMs": 90_500, "endMs": 300_000}},
        {"range": {"startMs": -1000, "endMs": 3000}},
        {"range": {"startMs": 5000, "endMs": 5000}},
        {"range": {"startMs": 6000, "endMs": 5000}},
        {"range": {"startMs": 1000.0, "endMs": 5000}},
        {"range": {"startMs": True, "endMs": 5000}},
        {"range": {"startMs": "1000", "endMs": 5000}},
        {"sponsorblock": []},
        {"sponsorblock": ["sponsor", "sponsor"]},
        {"sponsorblock": ["poi_highlight"]},
        {"sponsorblock": "sponsor"},
        {"splitChapters": "yes"},
        {"splitChapters": True, "range": RANGE},
        {"splitChapters": True, "sponsorblock": ["sponsor"]},
        {"splitChapters": True, "embedSubs": "o.th", "subOptions": SUB_OPTIONS},
    ],
)
def test_post_rejects_bad_advanced_video_params(env, params):
    resp = env.client().post("/api/jobs", json={"items": [video_item(**params)]}, headers=AUTH)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "E_BAD_REQUEST"
    assert env.store.pending_count() == 0


@pytest.mark.parametrize(
    "item",
    [
        {"videoId": "aqz-KE-bpKQ", "kind": "audio", "params": {"format": "m4a", "splitChapters": True, "range": RANGE}},
        {"videoId": "aqz-KE-bpKQ", "kind": "subtitle", "params": {"format": "md", "options": SUB_OPTIONS, "range": RANGE}},
        {"videoId": "aqz-KE-bpKQ", "kind": "subtitle",
         "params": {"format": "srt", "options": SUB_OPTIONS, "sponsorblock": ["sponsor"]}},
        {"videoId": "aqz-KE-bpKQ", "kind": "subtitle",
         "params": {"format": "srt", "options": SUB_OPTIONS, "splitChapters": True}},
    ],
)
def test_post_rejects_bad_advanced_audio_and_subtitle_params(env, item):
    resp = env.client().post("/api/jobs", json={"items": [item]}, headers=AUTH)
    assert resp.status_code == 422


@pytest.fixture
def cached(env):
    """AppContext overrides with a VideoService whose probe cache holds two clips
    (the videos router also needs extractor and cache_root, see api/videos.build_videos_router)"""
    fake = FakeExtractor(FIXTURES)
    videos = VideoService(env.db, fake)
    videos.get("aqz-KE-bpKQ")  # 635 s, no chapters
    videos.get("jNQXAC9IVRw")  # 19 s, 3 chapters
    return {"videos": videos, "extractor": fake, "cache_root": env.tmp / "cache"}


@pytest.mark.parametrize(
    ("item", "status"),
    [
        (video_item(range={"startMs": 0, "endMs": 635_000}), 200),
        (video_item(range={"startMs": 600_000, "endMs": 636_000}), 422),
        (video_item("jNQXAC9IVRw", range={"startMs": 0, "endMs": 19_000}), 200),
        (video_item("jNQXAC9IVRw", range={"startMs": 0, "endMs": 20_000}), 422),
        (video_item(splitChapters=True), 422),
        (video_item("jNQXAC9IVRw", splitChapters=True), 200),
        ({"videoId": "aqz-KE-bpKQ", "kind": "audio", "params": {"format": "wav", "splitChapters": True}}, 422),
        (video_item("88o5Sk8_m1Y", range={"startMs": 0, "endMs": 999_000}), 200),  # not cached: the handler checks
        (video_item("88o5Sk8_m1Y", splitChapters=True), 200),
    ],
)
def test_post_checks_range_and_chapters_against_a_cached_probe(env, cached, item, status):
    resp = env.client(**cached).post("/api/jobs", json={"items": [item]}, headers=AUTH)
    assert resp.status_code == status, resp.text
    if status == 422:
        assert resp.json()["error"]["code"] == "E_BAD_REQUEST"
        assert item["videoId"] in resp.json()["error"]["detail"]
        assert env.store.pending_count() == 0


def test_post_rejects_a_range_on_a_clip_without_a_known_duration(env, cached, monkeypatch):
    videos = cached["videos"]
    monkeypatch.setattr(videos, "peek_cached", lambda video_id: {"durationS": 0, "isLive": False, "chapters": []})
    resp = env.client(**cached).post("/api/jobs", json={"items": [video_item(range=RANGE)]}, headers=AUTH)
    assert resp.status_code == 422
    monkeypatch.setattr(videos, "peek_cached", lambda video_id: {"durationS": 900, "isLive": True, "chapters": []})
    resp = env.client(**cached).post("/api/jobs", json={"items": [video_item(range=RANGE)]}, headers=AUTH)
    assert resp.status_code == 422


def test_post_rejects_empty_and_oversized_lists(env):
    client = env.client()
    assert ITEMS_MAX == 1200  # owner preview round 2: 200 คลิป x 6 งานจาก W3
    assert client.post("/api/jobs", json={"items": []}, headers=AUTH).status_code == 422
    resp = client.post("/api/jobs", json={"items": [VALID_ITEMS[4]] * (ITEMS_MAX + 1)}, headers=AUTH)
    assert resp.status_code == 422
    assert env.store.pending_count() == 0


def test_post_accepts_items_max(env):
    client = env.client()
    resp = client.post("/api/jobs", json={"items": [VALID_ITEMS[4]] * ITEMS_MAX}, headers=AUTH)
    assert resp.status_code == 200
    assert env.store.pending_count() == ITEMS_MAX


def test_full_batches_do_not_overflow_a_listener(env):
    """job.created ข่าวละงาน: ผู้ฟังที่ยังไม่ได้อ่าน (สตรีมข่าวของหน้าเว็บ) ต้องไม่หลุดแม้มีสองชุดเต็มติดกัน"""
    assert EventBus.MAX_PENDING >= 4 * ITEMS_MAX
    client = env.client()
    for _ in range(2):
        resp = client.post("/api/jobs", json={"items": [VALID_ITEMS[4]] * ITEMS_MAX}, headers=AUTH)
        assert resp.status_code == 200
    assert env.bus.subscriber_count == 1  # ยังไม่ถูกปิดกล่องเพราะค้างข่าวเกิน
    created = [e for e in env.events() if e.name == "job.created"]
    assert len(created) == 2 * ITEMS_MAX


# ---------- params.folder (โฟลเดอร์กลุ่มของ W3) และงานโน้ต ----------

FOLDER_ITEMS = [*VALID_ITEMS, {"videoId": "88o5Sk8_m1Y", "kind": "note", "params": {"trackId": "a.th-orig"}}]


@pytest.mark.parametrize("item", FOLDER_ITEMS, ids=lambda item: item["kind"])
def test_every_kind_accepts_folder_and_stores_it_stripped(env, item):
    client = env.client()
    body = {**item, "params": {**item["params"], "folder": "  คลิปสอน  ภาษาไทย  "}}
    resp = client.post("/api/jobs", json={"items": [body]}, headers=AUTH)
    assert resp.status_code == 200
    job = resp.json()["jobs"][0]
    assert job["params"]["folder"] == "คลิปสอน  ภาษาไทย"  # strip หัวท้ายเท่านั้น ข้างในเก็บตามที่ส่งมา
    assert env.store.get(job["id"]).params["folder"] == "คลิปสอน  ภาษาไทย"


@pytest.mark.parametrize("item", FOLDER_ITEMS, ids=lambda item: item["kind"])
@pytest.mark.parametrize("folder", ["", "   ", "\t\n", None])
def test_blank_folder_is_treated_as_absent(env, item, folder):
    client = env.client()
    body = {**item, "params": {**item["params"], "folder": folder}}
    resp = client.post("/api/jobs", json={"items": [body]}, headers=AUTH)
    assert resp.status_code == 200
    assert "folder" not in resp.json()["jobs"][0]["params"]


def test_folder_length_limit_counts_after_strip(env):
    client = env.client()
    item = VALID_ITEMS[4]
    ok = {**item, "params": {**item["params"], "folder": "  " + "ก" * 80 + "  "}}
    resp = client.post("/api/jobs", json={"items": [ok]}, headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["jobs"][0]["params"]["folder"] == "ก" * 80


@pytest.mark.parametrize("item", FOLDER_ITEMS, ids=lambda item: item["kind"])
def test_folder_longer_than_80_is_422(env, item):
    client = env.client()
    body = {**item, "params": {**item["params"], "folder": "a" * 81}}
    resp = client.post("/api/jobs", json={"items": [VALID_ITEMS[3], body]}, headers=AUTH)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "E_BAD_REQUEST"
    assert env.store.pending_count() == 0


@pytest.mark.parametrize("folder", [12, ["a"], {"a": 1}, True])
def test_folder_must_be_text(env, folder):
    client = env.client()
    item = VALID_ITEMS[4]
    body = {**item, "params": {**item["params"], "folder": folder}}
    resp = client.post("/api/jobs", json={"items": [body]}, headers=AUTH)
    assert resp.status_code == 422


@pytest.mark.parametrize(
    ("params", "stored"),
    [
        ({}, {}),
        ({"trackId": "a.th-orig"}, {"trackId": "a.th-orig"}),
        ({"trackId": None, "folder": "รวมคลิป"}, {"folder": "รวมคลิป"}),
    ],
)
def test_post_note_job(env, params, stored):
    client = env.client(media=NoFfmpeg())  # โน้ตไม่ต้องมี ffmpeg
    resp = client.post("/api/jobs", json={"items": [{"videoId": "88o5Sk8_m1Y", "kind": "note", "params": params}]},
                       headers=AUTH)
    assert resp.status_code == 200
    job = resp.json()["jobs"][0]
    assert job["kind"] == "note"
    assert job["params"] == stored


@pytest.mark.parametrize(
    "params",
    [
        {"trackId": "x.th"},
        {"trackId": "o." + "a" * 65},
        {"format": "md"},
        {"options": SUB_OPTIONS},
        {"folder": "b" * 81},
    ],
)
def test_post_note_rejects_bad_params(env, params):
    client = env.client()
    resp = client.post("/api/jobs", json={"items": [{"videoId": "88o5Sk8_m1Y", "kind": "note", "params": params}]},
                       headers=AUTH)
    assert resp.status_code == 422
    assert env.store.pending_count() == 0


@pytest.mark.parametrize("media", [NoFfmpeg(), None])
def test_post_video_without_ffmpeg_is_409_and_stores_nothing(env, media):
    client = env.client(media=media)
    resp = client.post("/api/jobs", json={"items": [VALID_ITEMS[3], VALID_ITEMS[0]]}, headers=AUTH)
    assert resp.status_code == 409
    assert resp.json()["error"] == {"code": "E_FFMPEG_MISSING", "message": MESSAGES["E_FFMPEG_MISSING"],
                                    "detail": None}
    assert env.store.pending_count() == 0
    assert env.events() == []


def test_post_contact_sheet_does_not_need_ffmpeg(env):
    client = env.client(media=NoFfmpeg())
    resp = client.post("/api/jobs", json={"items": VALID_ITEMS[2:]}, headers=AUTH)
    assert resp.status_code == 200


def test_post_without_token_is_403(env):
    client = env.client()
    resp = client.post("/api/jobs", json={"items": VALID_ITEMS}, headers={"Origin": AUTH["Origin"]})
    assert resp.status_code == 403
    assert env.store.pending_count() == 0


# ---------- GET /jobs and /queue ----------


def test_get_jobs_default_list_rules(env):
    now = datetime.now(UTC)
    (running, queued, done_new, done_old, failed_new, failed_old, interrupted, cancelled) = env.add(8)
    env.finish(done_new.id, "done", now - timedelta(hours=2))
    env.finish(done_old.id, "done", now - timedelta(hours=25))
    env.finish(failed_new.id, "failed", now - timedelta(days=6), error_code="E_NETWORK")
    env.finish(failed_old.id, "failed", now - timedelta(days=8), error_code="E_NETWORK")
    env.finish(interrupted.id, "interrupted", now - timedelta(hours=1), error_code="E_INTERRUPTED")
    env.store.transition(cancelled.id, "cancelled")
    env.store.transition(running.id, "running")
    ids = [j["id"] for j in env.client().get("/api/jobs").json()["jobs"]]
    assert ids == [running.id, queued.id, interrupted.id, done_new.id, failed_new.id]


def test_get_jobs_by_status_and_limit(env):
    now = datetime.now(UTC)
    a, b = env.add(2)
    env.finish(a.id, "done", now - timedelta(minutes=5))
    env.finish(b.id, "done", now - timedelta(minutes=1))
    client = env.client()
    jobs = client.get("/api/jobs", params={"status": "done", "limit": 1}).json()["jobs"]
    assert [j["id"] for j in jobs] == [b.id]
    assert client.get("/api/jobs", params={"status": "bogus"}).status_code == 422
    assert client.get("/api/jobs", params={"limit": 0}).status_code == 422
    assert client.get("/api/jobs", params={"limit": 201}).status_code == 422


def test_failed_detail_is_redacted(env):
    (job,) = env.add(1)
    env.finish(job.id, "failed", error_code="E_UNKNOWN", error_detail=f"cannot open {Path.home() / 'Videos' / 'a.mp4'}")
    error = env.client().get("/api/jobs").json()["jobs"][0]["error"]
    assert error["code"] == "E_UNKNOWN" and error["message"] == MESSAGES["E_UNKNOWN"]
    assert str(Path.home()) not in error["detail"] and error["detail"].startswith("cannot open ~")


def test_get_queue_shape_and_pause(env):
    client = env.client()
    assert client.get("/api/queue").json() == {"pausedUntil": None, "reason": None, "concurrency": 2}
    env.runner.brake()
    body = client.get("/api/queue").json()
    assert body["reason"] == "E_BOT_CHECK" and body["concurrency"] == 2
    until = datetime.fromisoformat(body["pausedUntil"])
    assert timedelta(seconds=590) < until - datetime.now(UTC) <= timedelta(seconds=600)
    resp = client.post("/api/queue/resume", headers=AUTH)
    assert resp.status_code == 200 and resp.json() == {"ok": True}
    assert client.get("/api/queue").json()["pausedUntil"] is None
    names = [e.name for e in env.events()]
    assert names == ["queue.paused", "queue.resumed"]
    assert client.post("/api/queue/resume", headers=AUTH).json() == {"ok": True}  # also when not paused


# ---------- cancel / retry / order ----------


def test_cancel_queued_running_and_terminal(env):
    a, b, c = env.add(3)
    env.finish(c.id, "done")
    env.runner.tick()  # a and b start (concurrency 2), workers held by ManualSpawn
    env.store.add([NewJob("vid99999999", "frames_zip", {"source": "fast"})])
    queued = env.store.queued()[0]
    client = env.client()
    resp = client.post(f"/api/jobs/{queued.id}/cancel", headers=AUTH)
    assert resp.status_code == 200 and resp.json()["status"] == "cancelled"
    resp = client.post(f"/api/jobs/{a.id}/cancel", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["status"] == "running" and resp.json()["cancelling"] is True
    resp = client.post(f"/api/jobs/{c.id}/cancel", headers=AUTH)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "E_JOB_STATE"
    assert resp.json()["error"]["message"] == MESSAGES["E_JOB_STATE"]
    assert client.post(f"/api/jobs/{MISSING_ID}/cancel", headers=AUTH).status_code == 404
    resp = client.post("/api/jobs/not-a-job/cancel", headers=AUTH)
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "E_NOT_FOUND"
    assert client.post(f"/api/jobs/{b.id}/cancel").status_code == 403


def test_retry_rules(env):
    a, b, c = env.add(3)
    env.finish(a.id, "failed", error_code="E_NETWORK")
    env.finish(b.id, "interrupted", error_code="E_INTERRUPTED")
    env.finish(c.id, "done")
    client = env.client()
    for job in (a, b):
        resp = client.post(f"/api/jobs/{job.id}/retry", headers=AUTH)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "queued" and "error" not in body
    resp = client.post(f"/api/jobs/{c.id}/retry", headers=AUTH)
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "E_JOB_STATE"
    resp = client.post(f"/api/jobs/{a.id}/retry", headers=AUTH)  # now queued
    assert resp.status_code == 409
    assert client.post(f"/api/jobs/{MISSING_ID}/retry", headers=AUTH).status_code == 404


def test_put_order_reorders(env):
    a, b, c = env.add(3)
    client = env.client()
    resp = client.put("/api/jobs/order", json={"ids": [c.id, "junk", a.id]}, headers=AUTH)
    assert resp.status_code == 200 and resp.json() == {"ok": True}
    ids = [j["id"] for j in client.get("/api/jobs", params={"status": "queued"}).json()["jobs"]]
    assert ids == [c.id, b.id, a.id]
    assert client.put("/api/jobs/order", json={"ids": []}, headers=AUTH).status_code == 422


def test_put_order_accepts_every_queued_id_of_several_full_batches(env):
    """หน้าเว็บส่ง id queued ทั้งหมดทุกครั้งที่ลาก: สองชุดเต็มจาก W3 (2 x ITEMS_MAX) ต้องเรียงได้"""
    assert ORDER_IDS_MAX >= 10 * ITEMS_MAX
    jobs = env.add(2 * ITEMS_MAX)
    ids = [job.id for job in jobs]
    moved = [ids[-1], *ids[:-1]]  # ลากงานสุดท้ายขึ้นหัวคิว
    client = env.client()
    resp = client.put("/api/jobs/order", json={"ids": moved}, headers=AUTH)
    assert resp.status_code == 200
    assert [job.id for job in env.store.queued()] == moved


def test_put_order_rejects_more_than_the_cap(env):
    client = env.client()
    ids = [MISSING_ID] * (ORDER_IDS_MAX + 1)
    assert client.put("/api/jobs/order", json={"ids": ids}, headers=AUTH).status_code == 422


# ---------- outputs ----------


def _done_with_file(env, name: str = "คลิปทดสอบ.mp4", rel: str | None = None, root: str | None = None):
    out_root = env.tmp / "out"
    folder = out_root / "คลิป [aqz-KE-bpKQ]"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(b"mp4-bytes")
    (job,) = env.add(1)
    output = OutputFile(root or str(out_root), rel or f"คลิป [aqz-KE-bpKQ]/{name}", 9, "video")
    env.finish(job.id, "done", outputs=(output,))
    return job, folder / name


def test_get_output_is_an_attachment_with_the_thai_name(env):
    job, path = _done_with_file(env)
    resp = env.client().get(f"/api/jobs/{job.id}/outputs/0")
    assert resp.status_code == 200
    assert resp.content == b"mp4-bytes"
    assert resp.headers["content-disposition"] == (
        f"attachment; filename=\"download.mp4\"; filename*=UTF-8''{quote('คลิปทดสอบ.mp4', safe='')}"
    )
    listed = env.client().get("/api/jobs").json()["jobs"][0]["outputs"]
    assert listed == [{"index": 0, "name": "คลิปทดสอบ.mp4", "sizeBytes": 9}]


@pytest.mark.parametrize(
    ("name", "media_type"),
    [
        ("frames.zip", "application/zip"),
        ("sheet.jpg", "image/jpeg"),
        ("clip.mp4", "video/mp4"),
        ("song.m4a", "audio/mp4"),
        ("song.mp3", "audio/mpeg"),
        ("song.wav", "audio/wav"),
        ("subs.th.srt", "application/x-subrip"),
        ("subs.th.vtt", "text/vtt; charset=utf-8"),
        ("subs.th.txt", "text/plain; charset=utf-8"),
        ("subs.th.md", "text/markdown; charset=utf-8"),
        ("odd.bin", "application/octet-stream"),
    ],
)
def test_get_output_media_type_by_extension(env, name, media_type):
    job, _ = _done_with_file(env, name=name)
    resp = env.client().get(f"/api/jobs/{job.id}/outputs/0")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == media_type


def test_get_output_404s(env):
    job, path = _done_with_file(env)
    client = env.client()
    assert client.get(f"/api/jobs/{job.id}/outputs/1").status_code == 404
    assert client.get(f"/api/jobs/{job.id}/outputs/-1").status_code == 404
    assert client.get(f"/api/jobs/{MISSING_ID}/outputs/0").status_code == 404
    path.unlink()
    resp = client.get(f"/api/jobs/{job.id}/outputs/0")
    assert resp.status_code == 404 and resp.json()["error"]["code"] == "E_NOT_FOUND"


def test_forged_output_outside_the_root_is_404(env):
    secret = env.tmp / "secret.txt"
    secret.write_text("secret", encoding="utf-8")
    (env.tmp / "out" / "a").mkdir(parents=True)
    (job,) = env.add(1)
    forged = OutputFile(str(env.tmp / "out" / "a"), "../../secret.txt", 6, "video")
    env.finish(job.id, "done", outputs=(forged,))
    client = env.client()
    assert client.get(f"/api/jobs/{job.id}/outputs/0").status_code == 404
    assert client.post(f"/api/jobs/{job.id}/outputs/0/reveal", headers=AUTH).status_code == 404
    assert env.client().app.state.ctx.plat.revealed == []


@pytest.mark.parametrize("root", ["\\\\server\\share", "//server/share", "relative/out"])
def test_output_with_a_network_or_relative_root_is_404(env, root):
    job, _ = _done_with_file(env, root=root)
    assert env.client().get(f"/api/jobs/{job.id}/outputs/0").status_code == 404


def test_reveal_uses_the_override_with_the_absolute_path(env):
    job, path = _done_with_file(env)
    revealed: list[Path] = []
    client = env.client(reveal=revealed.append)
    resp = client.post(f"/api/jobs/{job.id}/outputs/0/reveal", headers=AUTH)
    assert resp.status_code == 200 and resp.json() == {"ok": True}
    assert revealed == [path.resolve()] and revealed[0].is_absolute()
    assert client.post(f"/api/jobs/{job.id}/outputs/3/reveal", headers=AUTH).status_code == 404


def test_reveal_falls_back_to_the_platform(env):
    job, path = _done_with_file(env)
    client = env.client()
    assert client.post(f"/api/jobs/{job.id}/outputs/0/reveal", headers=AUTH).status_code == 200
    assert client.app.state.ctx.plat.revealed == [path.resolve()]


def test_routes_absent_without_a_queue(make_client):
    client = make_client()
    assert client.get("/api/jobs").status_code == 404
    assert client.get("/api/queue").status_code == 404


# ---------- M5 รอบ B ภาพคม ----------


def test_post_accepts_frames_sharp_and_sharp_sources(env):
    items = [
        {"videoId": "aqz-KE-bpKQ", "kind": "frames_sharp", "params": {}},
        {"videoId": "aqz-KE-bpKQ", "kind": "frames_sharp", "params": {"intervalS": 60, "folder": "งานลูกค้า"}},
        {"videoId": "aqz-KE-bpKQ", "kind": "contact_sheet", "params": {"source": "sharp", "columns": 5}},
        {"videoId": "aqz-KE-bpKQ", "kind": "frames_zip", "params": {"source": "sharp"}},
    ]
    resp = env.client().post("/api/jobs", json={"items": items}, headers=AUTH)
    assert resp.status_code == 200, resp.text
    assert [job["params"] for job in resp.json()["jobs"]] == [
        {}, {"intervalS": 60, "folder": "งานลูกค้า"}, {"source": "sharp", "columns": 5}, {"source": "sharp"}]


@pytest.mark.parametrize(
    "params",
    [{"intervalS": 0}, {"intervalS": 3601}, {"intervalS": 1.5}, {"intervalS": True}, {"intervalS": "5"},
     {"interval": 5}, {"source": "sharp"}],
)  # fmt: skip
def test_post_rejects_bad_frames_sharp_params(env, params):
    item = {"videoId": "aqz-KE-bpKQ", "kind": "frames_sharp", "params": params}
    resp = env.client().post("/api/jobs", json={"items": [item]}, headers=AUTH)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "E_BAD_REQUEST"
    assert env.store.pending_count() == 0


def test_post_frames_sharp_checks_a_cached_probe(env, cached, monkeypatch):
    item = {"videoId": "aqz-KE-bpKQ", "kind": "frames_sharp", "params": {"intervalS": 10}}
    assert env.client(**cached).post("/api/jobs", json={"items": [item]}, headers=AUTH).status_code == 200
    uncached = {**item, "videoId": "88o5Sk8_m1Y"}
    assert env.client(**cached).post("/api/jobs", json={"items": [uncached]}, headers=AUTH).status_code == 200
    videos = cached["videos"]
    for info in ({"durationS": 0, "isLive": False}, {"durationS": 900, "isLive": True}):
        monkeypatch.setattr(videos, "peek_cached", lambda video_id, info=info: info)
        resp = env.client(**cached).post("/api/jobs", json={"items": [item]}, headers=AUTH)
        assert resp.status_code == 422
        assert resp.json()["error"]["detail"].startswith("aqz-KE-bpKQ: ")
    assert env.store.pending_count() == 2


def test_post_frames_sharp_without_ffmpeg_is_409(env):
    item = {"videoId": "aqz-KE-bpKQ", "kind": "frames_sharp", "params": {}}
    resp = env.client(media=NoFfmpeg()).post("/api/jobs", json={"items": [item]}, headers=AUTH)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "E_FFMPEG_MISSING"


def _done_with_folder(env):
    out_root = env.tmp / "out"
    folder = out_root / "คลิป [aqz-KE-bpKQ]" / "คลิป - ภาพคม"
    folder.mkdir(parents=True)
    (folder / "frame_00-00-00.jpg").write_bytes(b"jpg")
    (job,) = env.add(1, kind="frames_sharp")
    output = OutputFile(str(out_root), "คลิป [aqz-KE-bpKQ]/คลิป - ภาพคม", 3, "folder", files=1)
    env.finish(job.id, "done", outputs=(output,))
    return job, folder


def test_folder_output_is_listed_but_not_downloadable(env):
    job, _ = _done_with_folder(env)
    client = env.client()
    listed = next(j for j in client.get("/api/jobs").json()["jobs"] if j["id"] == job.id)
    assert listed["outputs"] == [{"index": 0, "name": "คลิป - ภาพคม", "sizeBytes": 3, "files": 1}]
    assert client.get(f"/api/jobs/{job.id}/outputs/0").status_code == 404


def test_reveal_of_a_folder_output_opens_the_folder(env):
    job, folder = _done_with_folder(env)
    opened: list[Path] = []
    client = env.client(open_folder=opened.append)
    assert client.post(f"/api/jobs/{job.id}/outputs/0/reveal", headers=AUTH).status_code == 200
    assert opened == [folder.resolve()]
    assert client.app.state.ctx.plat.revealed == []
    for child in folder.iterdir():
        child.unlink()
    folder.rmdir()
    assert client.post(f"/api/jobs/{job.id}/outputs/0/reveal", headers=AUTH).status_code == 404
