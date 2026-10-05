"""API ถ่ายภาพคมตรงจุด (M5 รอบ B2 C11): FakeExtractor (ชิ้นจาก fixture) + FakeMediaTools ไม่ต่อเน็ต ไม่ใช้ ffmpeg"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from yttoolkit.core.capture import OUTPUT_DIR, CaptureService
from yttoolkit.core.db import Database
from yttoolkit.core.extractor import FakeExtractor
from yttoolkit.core.media import FakeMediaTools
from yttoolkit.core.settings import SettingsStore
from yttoolkit.core.videos import VideoService
from yttoolkit.core.yterrors import YtError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
BBB = "aqz-KE-bpKQ"
CLIP = "CAPTURE0001"
BASE = "http://127.0.0.1:8787"
AUTH = {"X-Toolkit-Token": "test-token", "Origin": BASE}
URL = re.compile(r"/api/cache/(?P<id>[\w-]{11})/captures/(?P<file>c_\d+\.jpg)\?v=\d+")


@dataclass
class Queue:
    paused_until: datetime | None = None
    brakes: list[str] = field(default_factory=list)

    def pause_state(self) -> SimpleNamespace | None:
        return None if self.paused_until is None else SimpleNamespace(until=self.paused_until, reason="E_BOT_CHECK")

    def brake(self, reason: str = "E_BOT_CHECK") -> None:
        self.brakes.append(reason)


class GatedExtractor(FakeExtractor):
    """ตัวปลอมที่รอ gate ก่อนตัดชิ้น (เทสการถ่ายซ้อน)"""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.gate = threading.Event()
        self.started = threading.Event()

    def fetch_frame_piece(self, video_id, t_ms, max_short_side, dest):  # type: ignore[no-untyped-def]
        self.started.set()
        assert self.gate.wait(10)
        return super().fetch_frame_piece(video_id, t_ms, max_short_side, dest)


@pytest.fixture
def api(make_client, tmp_path):
    made: list[Database] = []

    def _api(extractor: FakeExtractor | None = None):
        db = Database(tmp_path / f"app{len(made)}.db")
        db.migrate()
        made.append(db)
        fake = extractor or FakeExtractor(FIXTURES)
        videos = VideoService(db, fake, now=lambda: datetime(2026, 10, 5, 8, tzinfo=UTC))
        settings = SettingsStore(db, tmp_path / "out")
        queue = Queue()
        cache = tmp_path / "cache"
        service = CaptureService(videos, fake, FakeMediaTools(FIXTURES / "media"), cache, settings, queue,
                                 work_root=tmp_path / "work")  # fmt: skip
        client = make_client(videos=videos, extractor=fake, cache_root=cache, captures=service, settings=settings)
        client.queue = queue  # type: ignore[attr-defined]
        client.out = tmp_path / "out"  # type: ignore[attr-defined]
        return client

    yield _api
    for db in made:
        db.close()


def _error(resp) -> dict:
    return resp.json()["error"]


def test_post_creates_then_returns_the_same_capture(api) -> None:
    client = api()
    resp = client.post(f"/api/videos/{BBB}/captures", json={"tMs": 125_400}, headers=AUTH)
    assert resp.status_code == 201
    body = resp.json()
    assert {k: body[k] for k in ("id", "tMs", "width", "height")} == {"id": "c_125400", "tMs": 125_400, "width": 160, "height": 90}
    assert URL.fullmatch(body["url"]) and URL.fullmatch(body["url"])["file"] == "c_125400.jpg"
    again = client.post(f"/api/videos/{BBB}/captures", json={"tMs": 125_400}, headers=AUTH)
    assert again.status_code == 200 and again.json() == body
    assert client.get(f"/api/videos/{BBB}/captures").json() == {"captures": [body]}
    folder = next(client.out.glob(f"*[[]{BBB}[]]")) / OUTPUT_DIR
    assert [p.name for p in folder.iterdir()] == ["frame_00-02-05.jpg"]


def test_capture_images_are_immutable_and_download_by_timecode(api) -> None:
    client = api()
    url = client.post(f"/api/videos/{BBB}/captures", json={"tMs": 125_400}, headers=AUTH).json()["url"]
    image = client.get(url)
    assert image.status_code == 200 and image.headers["content-type"] == "image/jpeg"
    assert image.headers["cache-control"] == "public, max-age=86400, immutable"
    download = client.get(url.split("?")[0] + "?download=1")
    assert download.headers["content-disposition"] == 'attachment; filename="frame_00-02-05.jpg"'
    assert client.get(f"/api/cache/{BBB}/captures/index.json").status_code == 404


@pytest.mark.parametrize(
    "body",
    [{}, {"tMs": "1000"}, {"tMs": 1.5}, {"tMs": True}, {"tMs": -1}, {"tMs": 1000, "extra": 1}, {"tMs": 172_800_001}],
)
def test_post_body_is_strict(api, body) -> None:
    resp = api().post(f"/api/videos/{BBB}/captures", json=body, headers=AUTH)
    assert resp.status_code == 422 and _error(resp)["code"] == "E_BAD_REQUEST"


def test_out_of_range_and_bad_ids(api) -> None:
    client = api()
    late = client.post(f"/api/videos/{BBB}/captures", json={"tMs": 635_000}, headers=AUTH)
    assert late.status_code == 422 and _error(late)["code"] == "E_BAD_REQUEST"
    assert _error(late)["detail"].startswith(BBB)
    for path in ("/api/videos/bad/captures",):
        assert client.get(path).status_code == 422
        assert client.post(path, json={"tMs": 0}, headers=AUTH).json()["error"]["code"] == "E_INVALID_INPUT"


def test_post_requires_the_token(api) -> None:
    assert api().post(f"/api/videos/{BBB}/captures", json={"tMs": 0}).status_code == 403


@pytest.mark.parametrize(
    ("video_id", "status", "code", "message"),
    [
        ("CAPTURENO01", 422, "E_CAPTURE_UNSUPPORTED", 'คลิปนี้ถ่ายภาพคมเฉพาะจุดไม่ได้ ใช้ "ขอภาพคม" ทั้งคลิปแทนได้'),
        ("CAPTURENET1", 502, "E_NETWORK", "เน็ตหลุด ลองใหม่อีกครั้ง"),
        ("CAPTUREBOT1", 429, "E_BOT_CHECK", "ยูทูปขอให้ยืนยันว่าไม่ใช่บอท พักคิวไว้ 10 นาทีก่อนนะ"),
    ],
)
def test_extractor_failures_map_to_their_status(api, video_id, status, code, message) -> None:
    client = api()
    resp = client.post(f"/api/videos/{video_id}/captures", json={"tMs": 1_000}, headers=AUTH)
    assert resp.status_code == status
    assert (_error(resp)["code"], _error(resp)["message"]) == (code, message)
    assert client.queue.brakes == (["E_BOT_CHECK"] if code == "E_BOT_CHECK" else [])  # พักคิวครั้งเดียว (จาก service)
    assert client.get(f"/api/videos/{video_id}/captures").json() == {"captures": []}


def test_paused_queue_is_409_with_the_time(api) -> None:
    client = api()
    client.queue.paused_until = datetime(2026, 10, 5, 10, 10, tzinfo=UTC)
    resp = client.post(f"/api/videos/{BBB}/captures", json={"tMs": 1_000}, headers=AUTH)
    assert resp.status_code == 409
    assert _error(resp) == {"code": "E_QUEUE_PAUSED", "message": "พักการโหลดอยู่เพราะยูทูปขอตรวจสอบ ลองใหม่หลัง 17:10",
                            "detail": "queue paused by a bot check"}  # fmt: skip


def test_post_while_busy_is_409(api) -> None:
    fake = GatedExtractor(FIXTURES)
    client = api(fake)
    client.get(f"/api/videos/{BBB}")  # probe ก่อน (ให้ VideoService มีข้อมูลคลิป)
    results: dict[str, int] = {}
    worker = threading.Thread(
        target=lambda: results.setdefault(
            "first", client.post(f"/api/videos/{BBB}/captures", json={"tMs": 1_000}, headers=AUTH).status_code))
    worker.start()
    assert fake.started.wait(5)
    busy = client.post(f"/api/videos/{BBB}/captures", json={"tMs": 2_000}, headers=AUTH)
    assert busy.status_code == 409 and _error(busy) == {
        "code": "E_CAPTURE_BUSY", "message": "กำลังถ่ายภาพอื่นอยู่ รอสักครู่", "detail": "another capture is running"}
    fake.gate.set()
    worker.join(10)
    assert results["first"] == 201


def test_delete_then_404(api) -> None:
    client = api()
    capture = client.post(f"/api/videos/{BBB}/captures", json={"tMs": 1_000}, headers=AUTH).json()
    resp = client.delete(f"/api/videos/{BBB}/captures/{capture['id']}", headers=AUTH)
    assert resp.status_code == 204 and resp.content == b""
    assert client.get(f"/api/videos/{BBB}/captures").json() == {"captures": []}
    assert client.delete(f"/api/videos/{BBB}/captures/{capture['id']}", headers=AUTH).status_code == 404
    assert client.delete(f"/api/videos/{BBB}/captures/x", headers=AUTH).status_code == 404
    assert client.delete(f"/api/videos/{BBB}/captures/c_1000").status_code == 403


def test_reveal_opens_the_capture_folder(api, fake_platform) -> None:
    client = api()
    assert client.post(f"/api/videos/{CLIP}/captures/reveal", headers=AUTH).status_code == 404
    client.post(f"/api/videos/{CLIP}/captures", json={"tMs": 1_000}, headers=AUTH)
    resp = client.post(f"/api/videos/{CLIP}/captures/reveal", headers=AUTH)
    assert resp.status_code == 200 and resp.json() == {"ok": True}
    assert fake_platform.opened == [client.out / f"คลิปถ่ายภาพคม [{CLIP}]" / OUTPUT_DIR]
    assert client.post("/api/videos/bad/captures/reveal", headers=AUTH).status_code == 404


def test_no_captures_router_without_the_service(make_client) -> None:
    assert make_client().get(f"/api/videos/{BBB}/captures").status_code == 404


class RaisingService:
    """CaptureService ปลอมที่โยนรหัสที่กำหนด (เทสว่าทุกรหัสของ service มี status ในตาราง ไม่หลุดเป็น 500)"""

    def __init__(self, code: str) -> None:
        self.code = code

    def capture(self, video_id: str, t_ms: int):  # type: ignore[no-untyped-def]
        raise YtError(self.code, "detail")

    def delete(self, video_id: str, capture_id: str) -> None:
        raise YtError(self.code, "detail")


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("E_CAPTURE_UNSUPPORTED", 422),
        ("E_CAPTURE_BUSY", 409),
        ("E_QUEUE_PAUSED", 409),
        ("E_FFMPEG_MISSING", 409),
        ("E_DISK_FULL", 507),
        ("E_OUTPUT_NOT_WRITABLE", 409),
    ],
)
def test_every_capture_error_code_has_its_mapped_status(make_client, tmp_path, caplog, code, status) -> None:
    client = make_client(captures=RaisingService(code), cache_root=tmp_path / "cache")
    with caplog.at_level("WARNING"):
        created = client.post(f"/api/videos/{BBB}/captures", json={"tMs": 1_000}, headers=AUTH)
        deleted = client.delete(f"/api/videos/{BBB}/captures/c_1000", headers=AUTH)
    for resp in (created, deleted):
        assert resp.status_code == status and _error(resp)["code"] == code
    assert all(record.exc_info is None for record in caplog.records)  # ไม่ใช่ 500 = ไม่มี traceback ใน log
