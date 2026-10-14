"""API ข้อมูลชั่วคราว (M6 รอบ A spec 3.4, AC-SET-07 / AC-SET-08): GET /api/storage · POST /api/storage/clear"""

from __future__ import annotations

import random
import threading
from pathlib import Path

import pytest

from yttoolkit.core.db import Database
from yttoolkit.core.events import EventBus
from yttoolkit.core.extractor import FakeExtractor
from yttoolkit.core.jobs import JobResult, JobStore, NewJob, OutputFile
from yttoolkit.core.queue import QueueRunner
from yttoolkit.core.settings import SettingsStore
from yttoolkit.core.videos import VideoService

# ค่าเดียวกับ tests/api/conftest.py (import conftest ตรง ๆ ไม่ได้)
BASE = "http://127.0.0.1:8787"
AUTH = {"X-Toolkit-Token": "test-token", "Origin": BASE}
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
BBB = "aqz-KE-bpKQ"
ZOO = "jNQXAC9IVRw"
MB = 1_000_000


def sized(path: Path, size: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.truncate(size)
    return path


@pytest.fixture
def client(make_client, paths):
    return make_client(cache_root=paths.cache)


def test_no_storage_router_without_a_cache_root(make_client):
    assert make_client().get("/api/storage").status_code == 404


def test_get_storage_shape_and_no_store(client, paths):
    sized(paths.cache / BBB / "storyboard" / "f.jpg", 2 * MB)
    sized(paths.work / "ffmpeg-download.zip", MB)
    resp = client.get("/api/storage")
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-store"
    assert resp.json() == {"cacheBytes": 2 * MB, "workBytes": MB, "reclaimableBytes": 2 * MB}


def test_get_storage_needs_no_token(client):
    assert client.get("/api/storage", headers={"Origin": BASE}).status_code == 200


def test_clear_frees_and_reports_the_real_bytes(client, paths):
    sized(paths.cache / BBB / "storyboard" / "f.jpg", 2 * MB)
    sized(paths.cache / ZOO / "pinned.json", 100)
    resp = client.post("/api/storage/clear", headers=AUTH)
    assert resp.status_code == 200 and resp.headers["cache-control"] == "no-store"
    assert resp.json() == {"freedBytes": 2 * MB + 100}
    assert list(paths.cache.iterdir()) == []
    assert client.get("/api/storage").json()["reclaimableBytes"] == 0


def test_clear_ignores_a_body(client, paths):
    assert client.post("/api/storage/clear", json={"everything": True}, headers=AUTH).json() == {"freedBytes": 0}


def test_clear_needs_the_token_and_our_origin(client, paths):
    sized(paths.cache / BBB / "storyboard" / "f.jpg", MB)
    no_token = client.post("/api/storage/clear", headers={"Origin": BASE})
    foreign = client.post("/api/storage/clear", headers={**AUTH, "Origin": "https://evil.example"})
    assert no_token.status_code == 403 and foreign.status_code == 403
    assert no_token.json()["error"]["code"] == "E_FORBIDDEN"
    assert (paths.cache / BBB / "storyboard" / "f.jpg").is_file()


def test_ac_set_08_a_running_job_survives_a_clear_and_finishes(make_client, paths, tmp_path):
    db = Database(paths.db)
    db.migrate()
    started, release = threading.Event(), threading.Event()

    def handler(job, ctx):
        (ctx.workdir / "media.mp4.part").write_bytes(b"x" * 1000)
        sized(paths.cache / job.video_id / "storyboard" / "f.jpg", MB)
        started.set()
        assert release.wait(10)
        assert (ctx.workdir / "media.mp4.part").is_file()  # ยังอยู่หลังล้าง
        assert (paths.cache / job.video_id / "storyboard" / "f.jpg").is_file()
        return JobResult(outputs=(OutputFile(str(ctx.output_root), f"x [{job.video_id}]/x.mp4", 1, "video"),))

    settings = SettingsStore(db, tmp_path / "out")
    runner = QueueRunner(JobStore(db), EventBus(), {"video": handler}, settings=settings, work_root=paths.work,
                         rng=random.Random(1), redact=lambda text: text)  # fmt: skip
    try:
        client = make_client(cache_root=paths.cache, queue=runner, settings=settings, db=db)
        sized(paths.cache / ZOO / "storyboard" / "f.jpg", 3 * MB)
        (job,) = runner.enqueue([NewJob(BBB, "video", {})])
        runner.tick()
        assert started.wait(5)
        usage = client.get("/api/storage").json()
        assert usage["reclaimableBytes"] == 3 * MB  # ของงานที่กำลังทำไม่นับ
        assert client.post("/api/storage/clear", headers=AUTH).json() == {"freedBytes": 3 * MB}
        release.set()
        for _ in range(200):
            if runner.store.get(job.id).status == "done":
                break
            threading.Event().wait(0.02)
        assert runner.store.get(job.id).status == "done"
    finally:
        release.set()
        runner.shutdown(timeout=1)
        db.close()



def test_a_stale_cache_image_url_is_404_after_a_clear(make_client, paths):
    # spec 3.3 แถว api/videos._cache_target: ลิงก์ภาพเก่าที่หน้าเว็บยังถืออยู่ = 404 ไม่ใช่ 500
    db = Database(paths.db)
    db.migrate()
    try:
        fake = FakeExtractor(FIXTURES)
        client = make_client(db=db, videos=VideoService(db, fake), extractor=fake, cache_root=paths.cache)
        assert client.get(f"/api/videos/{BBB}/storyboard").status_code == 200
        assert client.get(f"/api/cache/{BBB}/storyboard/f_0000.jpg").status_code == 200
        assert client.post("/api/storage/clear", headers=AUTH).json()["freedBytes"] > 0
        resp = client.get(f"/api/cache/{BBB}/storyboard/f_0000.jpg")
        assert resp.status_code == 404 and resp.json()["error"]["code"] == "E_NOT_FOUND"
        assert client.get(f"/api/videos/{BBB}/storyboard").status_code == 200  # เปิดคลิปเก่าอีกครั้ง = ดึงภาพใหม่
    finally:
        db.close()
