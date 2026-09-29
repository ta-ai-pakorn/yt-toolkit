"""API ของ M2: resolve, ข้อมูลคลิป, storyboard, contact sheet, zip, เพลย์ลิสต์, ประวัติ และ /cache

ใช้ FakeExtractor + ฐานข้อมูลและโฟลเดอร์ cache ชั่วคราว ไม่แตะเครือข่าย
"""

from __future__ import annotations

import io
import json
import logging
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import pytest
from PIL import Image

from yttoolkit.core.db import Database
from yttoolkit.core.extractor import FakeExtractor
from yttoolkit.core.videos import VideoService
from yttoolkit.core.yterrors import MESSAGES, YtError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
BBB = "aqz-KE-bpKQ"
ZOO = "jNQXAC9IVRw"  # ไม่มี storyboard
LIVE = "UPCOMINGLV1"
PRIVATE = "PRIVATEVID1"
MISSING = "zzzzzzzzzzz"
PLAYLIST = "PLfakeplaylist250"
THAI_TITLE = 'คลิป: สอน/ทำ "ภาพ" *ใหม่*?  <ตอน|1>'

# ค่าเดียวกับ tests/api/conftest.py (import conftest ตรง ๆ ไม่ได้)
BASE = "http://127.0.0.1:8787"
AUTH = {"X-Toolkit-Token": "test-token", "Origin": BASE}


class ThaiTitleExtractor(FakeExtractor):
    """คลิป BBB แต่ชื่อเป็นภาษาไทยและมีอักขระต้องห้ามของชื่อไฟล์"""

    def probe(self, video_id: str) -> dict:
        info = super().probe(video_id)
        info["title"] = THAI_TITLE
        return info


class BrokenExtractor(FakeExtractor):
    def __init__(self, root: Path, code: str) -> None:
        super().__init__(root)
        self.code = code

    def probe(self, video_id: str) -> dict:
        self.calls.append(("probe", video_id))
        raise YtError(self.code, f"ERROR: เทส {self.code} ที่ {Path.home() / 'x'}")


@pytest.fixture
def services(tmp_path):
    made: list[Database] = []

    def _make(extractor: FakeExtractor | None = None):
        db = Database(tmp_path / f"app{len(made)}.db")
        db.migrate()
        made.append(db)
        fake = extractor or FakeExtractor(FIXTURES)
        videos = VideoService(db, fake, now=lambda: datetime(2026, 9, 29, 12, tzinfo=UTC))
        return {"db": db, "videos": videos, "extractor": fake, "cache_root": tmp_path / "cache"}

    yield _make
    for db in made:
        db.close()


@pytest.fixture
def api(make_client, services):
    def _api(extractor: FakeExtractor | None = None):
        parts = services(extractor)
        client = make_client(**parts)
        client.fake = parts["extractor"]  # type: ignore[attr-defined]
        client.cache_root = parts["cache_root"]  # type: ignore[attr-defined]
        return client

    return _api


def _probes(fake: FakeExtractor) -> int:
    return sum(1 for name, _ in fake.calls if name == "probe")


def _error(resp) -> dict:
    return resp.json()["error"]


# ---------- ไม่มีบริการ = route เดิมยังทำงาน ----------


def test_health_and_ping_still_work_with_services(api):
    client = api()
    fake = {"tools": {}, "disk": {}, "output": {}, "network": {}}
    client.app.state.ctx.health = lambda: fake
    assert client.get("/api/ping").status_code == 200
    assert client.get("/api/health").json()["version"] == "0.1.0"


def test_video_routes_absent_without_services(make_client):
    resp = make_client().get(f"/api/videos/{BBB}")
    assert resp.status_code == 404
    assert _error(resp)["code"] == "E_NOT_FOUND"


# ---------- /resolve ----------


def test_resolve_needs_token(api):  # NFR-SEC-3
    resp = api().post("/api/resolve", json={"text": "https://youtu.be/aqz-KE-bpKQ"})
    assert resp.status_code == 403
    assert _error(resp)["code"] == "E_FORBIDDEN"


def test_resolve_needs_origin(api):
    headers = {"X-Toolkit-Token": "test-token"}
    resp = api().post("/api/resolve", json={"text": "x"}, headers=headers)
    assert resp.status_code == 403


def test_resolve_foreign_host_rejected(api):  # AC-SEC-02
    resp = api().post(
        "/api/resolve", json={"text": "x"}, headers={**AUTH, "host": "evil.example:8787"}
    )
    assert resp.status_code == 421


def test_resolve_items_in_order(api):
    lines = [
        "https://www.youtube.com/watch?v=aqz-KE-bpKQ",
        "ไม่ใช่ลิงก์",
        "https://www.youtube.com/playlist?list=PLfakeplaylist250",
        "https://www.youtube.com/watch?v=jNQXAC9IVRw&list=PLfakeplaylist250",
    ]
    text = "\n".join(lines)
    resp = api().post("/api/resolve", json={"text": text}, headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert re.fullmatch(r"[0-9a-f]{32}", body["resolveId"])
    assert body["items"] == [
        {"input": "https://www.youtube.com/watch?v=aqz-KE-bpKQ", "kind": "video", "videoId": BBB},
        {
            "input": "ไม่ใช่ลิงก์",
            "kind": "invalid",
            "error": {"code": "E_INVALID_INPUT", "message": MESSAGES["E_INVALID_INPUT"]},
        },
        {
            "input": "https://www.youtube.com/playlist?list=PLfakeplaylist250",
            "kind": "playlist",
            "playlistId": PLAYLIST,
        },
        {
            "input": "https://www.youtube.com/watch?v=jNQXAC9IVRw&list=PLfakeplaylist250",
            "kind": "ambiguous",
            "videoId": ZOO,
            "playlistId": PLAYLIST,
        },
    ]


def test_resolve_ids_differ_each_call(api):
    client = api()
    first = client.post("/api/resolve", json={"text": BBB}, headers=AUTH).json()["resolveId"]
    second = client.post("/api/resolve", json={"text": BBB}, headers=AUTH).json()["resolveId"]
    assert first != second


def test_resolve_empty_text_gives_no_items(api):
    body = api().post("/api/resolve", json={"text": ""}, headers=AUTH).json()
    assert body["items"] == []


def test_resolve_rejects_text_over_limit(api):
    resp = api().post("/api/resolve", json={"text": "a" * 20001}, headers=AUTH)
    assert resp.status_code == 422
    assert _error(resp)["code"] == "E_BAD_REQUEST"


def test_resolve_accepts_text_at_limit(api):
    resp = api().post("/api/resolve", json={"text": "a" * 20000}, headers=AUTH)
    assert resp.status_code == 200


def test_resolve_rejects_missing_text(api):
    resp = api().post("/api/resolve", json={}, headers=AUTH)
    assert resp.status_code == 422


def test_resolve_does_not_probe(api):
    client = api()
    client.post("/api/resolve", json={"text": BBB}, headers=AUTH)
    assert client.fake.calls == []


# ---------- /videos/{id} ----------


def test_video_info(api):
    resp = api().get(f"/api/videos/{BBB}")
    assert resp.status_code == 200
    info = resp.json()
    assert info["videoId"] == BBB
    assert info["title"].startswith("Big Buck Bunny")
    assert info["durationS"] == 635
    assert info["hasStoryboard"] is True
    assert info["isLive"] is False
    assert {"channel", "thumbnailUrl", "chapters", "video", "audio"} <= set(info)


def test_video_info_uses_cache_within_24h(api):  # AC-PROBE-01
    client = api()
    client.get(f"/api/videos/{BBB}")
    client.get(f"/api/videos/{BBB}")
    client.get(f"/api/videos/{BBB}/storyboard")
    assert _probes(client.fake) == 1


def test_video_info_peek_returns_info_but_stays_out_of_history(api):
    client = api()
    resp = client.get(f"/api/videos/{BBB}?peek=1")
    assert resp.status_code == 200
    assert resp.json()["videoId"] == BBB
    assert client.get("/api/history").json() == {"items": [], "total": 0}


def test_video_info_peek_then_open_uses_cache_and_enters_history(api):
    client = api()
    client.get(f"/api/videos/{BBB}?peek=1")
    client.get(f"/api/videos/{BBB}")
    assert _probes(client.fake) == 1
    body = client.get("/api/history").json()
    assert [i["videoId"] for i in body["items"]] == [BBB]
    assert body["total"] == 1


def test_video_info_peek_on_opened_video_keeps_history_entry(api):
    client = api()
    client.get(f"/api/videos/{BBB}")
    client.get(f"/api/videos/{BBB}?peek=1")
    assert client.get("/api/history").json()["total"] == 1


def test_video_info_refresh_probes_again(api):
    client = api()
    client.get(f"/api/videos/{BBB}")
    assert client.get(f"/api/videos/{BBB}?refresh=1").status_code == 200
    assert _probes(client.fake) == 2


def test_video_info_live_is_409(api):  # AC-PROBE-02
    resp = api().get(f"/api/videos/{LIVE}")
    assert resp.status_code == 409
    assert _error(resp) == {
        "code": "E_LIVE_NOT_READY",
        "message": MESSAGES["E_LIVE_NOT_READY"],
        "detail": "live_status=is_upcoming",
    }


def test_video_info_private_is_404(api):
    resp = api().get(f"/api/videos/{PRIVATE}")
    assert resp.status_code == 404
    assert _error(resp)["code"] == "E_VIDEO_PRIVATE"
    assert _error(resp)["message"] == MESSAGES["E_VIDEO_PRIVATE"]


def test_video_info_unavailable_is_404(api):
    resp = api().get(f"/api/videos/{MISSING}")
    assert resp.status_code == 404
    assert _error(resp)["code"] == "E_VIDEO_UNAVAILABLE"


@pytest.mark.parametrize("bad", ["short", "aqz-KE-bpKQx", "aqz-KE-bp%21Q", "aqz.KE.bpKQ"])
def test_video_info_bad_id_is_422(api, bad):
    client = api()
    resp = client.get(f"/api/videos/{bad}")
    assert resp.status_code == 422
    assert _error(resp)["code"] == "E_INVALID_INPUT"
    assert client.fake.calls == []


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("E_VIDEO_UNAVAILABLE", 404),
        ("E_AGE_RESTRICTED", 409),
        ("E_GEO_BLOCKED", 409),
        ("E_BOT_CHECK", 429),
        ("E_NETWORK", 502),
        ("E_UNKNOWN", 500),
        ("E_SOMETHING_NEW", 500),
    ],
)
def test_error_status_mapping(api, code, status):
    resp = api(BrokenExtractor(FIXTURES, code)).get(f"/api/videos/{BBB}")
    assert resp.status_code == status
    error = _error(resp)
    assert error["code"] == (code if code in MESSAGES else "E_UNKNOWN")
    assert error["message"] == MESSAGES.get(code, MESSAGES["E_UNKNOWN"])
    assert str(Path.home()) not in error["detail"]  # detail ถูกซ่อนโฟลเดอร์ผู้ใช้
    assert error["detail"].startswith(f"ERROR: เทส {code} ที่ ~")


def test_expected_error_logged_without_traceback(api, caplog):
    with caplog.at_level(logging.WARNING, logger="yttoolkit"):
        api(BrokenExtractor(FIXTURES, "E_VIDEO_PRIVATE")).get(f"/api/videos/{BBB}")
    records = [r for r in caplog.records if "E_VIDEO_PRIVATE" in r.getMessage()]
    assert records and records[0].levelno == logging.WARNING
    assert BBB in records[0].getMessage()
    assert records[0].exc_info is None


def test_unknown_error_logged_with_traceback(api, caplog):
    with caplog.at_level(logging.WARNING, logger="yttoolkit"):
        api(BrokenExtractor(FIXTURES, "E_UNKNOWN")).get(f"/api/videos/{BBB}")
    records = [r for r in caplog.records if "E_UNKNOWN" in r.getMessage()]
    assert records and records[0].exc_info is not None


# ---------- storyboard ----------


def test_storyboard(api):
    client = api()
    resp = client.get(f"/api/videos/{BBB}/storyboard")
    assert resp.status_code == 200
    body = resp.json()
    assert body["intervalMs"] == 4961
    assert len(body["frames"]) == 128
    version = (client.cache_root / BBB / "storyboard" / "index.json").stat().st_mtime_ns
    assert body["frames"][1] == {
        "index": 1,
        "tMs": 4961,
        "url": f"/api/cache/{BBB}/storyboard/f_0001.jpg?v={version}",
    }
    assert set(body) == {"intervalMs", "frames"}


def test_storyboard_version_changes_when_rebuilt(api):
    client = api()
    first = client.get(f"/api/videos/{BBB}/storyboard").json()["frames"][0]["url"]
    folder = client.cache_root / BBB / "storyboard"
    (folder / "f_0000.jpg").unlink()  # cache ไม่ครบ = สร้างใหม่ทั้งชุด
    second = client.get(f"/api/videos/{BBB}/storyboard").json()["frames"][0]["url"]
    assert first.split("?")[0] == second.split("?")[0]
    assert first != second


def test_versioned_frame_url_downloads_with_timecode(api):
    client = api()
    url = client.get(f"/api/videos/{BBB}/storyboard").json()["frames"][13]["url"]
    assert "?v=" in url
    resp = client.get(f"{url}&download=1")
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "public, max-age=86400, immutable"
    assert resp.headers["content-disposition"] == 'attachment; filename="frame_00-01-04.jpg"'


def test_storyboard_frame_urls_are_served(api):
    client = api()
    frames = client.get(f"/api/videos/{BBB}/storyboard").json()["frames"]
    resp = client.get(frames[5]["url"])
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.headers["cache-control"] == "public, max-age=86400, immutable"
    assert "content-disposition" not in resp.headers
    with Image.open(io.BytesIO(resp.content)) as image:
        assert (image.format, image.size) == ("JPEG", (320, 180))


def test_storyboard_missing_is_404(api):
    resp = api().get(f"/api/videos/{ZOO}/storyboard")
    assert resp.status_code == 404
    assert _error(resp)["code"] == "E_NO_STORYBOARD"
    assert _error(resp)["message"] == MESSAGES["E_NO_STORYBOARD"]


def test_storyboard_live_is_409(api):
    resp = api().get(f"/api/videos/{LIVE}/storyboard")
    assert resp.status_code == 409


def test_storyboard_bad_id_is_422(api):
    resp = api().get("/api/videos/bad/storyboard")
    assert resp.status_code == 422
    assert _error(resp)["code"] == "E_INVALID_INPUT"


# ---------- contact sheet + zip ----------


def _disposition(resp) -> str:
    return resp.headers["content-disposition"]


def test_contact_sheet(api):
    client = api()
    resp = client.get(f"/api/videos/{BBB}/storyboard/contact-sheet.jpg")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    with Image.open(io.BytesIO(resp.content)) as image:
        assert image.format == "JPEG"
        assert image.width == 5 * 320 + 6 * 8  # 5 คอลัมน์ (AC-FRAME-05)
    name = "Big Buck Bunny 60fps 4K - Official Blender Foundation Short Film - contact sheet.jpg"
    assert _disposition(resp) == (
        f"attachment; filename=\"contact-sheet.jpg\"; filename*=UTF-8''{quote(name, safe='')}"
    )
    assert _probes(client.fake) == 1


def test_frames_zip(api):
    resp = api().get(f"/api/videos/{BBB}/storyboard/frames.zip")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
        names = archive.namelist()
    assert len(names) == 128  # AC-FRAME-06
    assert names[0] == "frame_00-00-00.jpg"
    assert all(re.fullmatch(r"frame_\d\d-\d\d-\d\d(_\d)?\.jpg", n) for n in names)
    disposition = _disposition(resp)
    assert disposition.startswith('attachment; filename="frames.zip"; filename*=UTF-8\'\'')
    assert disposition.endswith(quote(" - frames.zip", safe=""))


def test_thai_title_in_filename_star(api):
    client = api(ThaiTitleExtractor(FIXTURES))
    resp = client.get(f"/api/videos/{BBB}/storyboard/contact-sheet.jpg")
    assert resp.status_code == 200
    disposition = _disposition(resp)
    disposition.encode("latin-1")  # header ต้องเป็น ASCII ล้วน
    assert disposition.isascii()
    encoded = disposition.split("filename*=UTF-8''", 1)[1]
    from urllib.parse import unquote

    assert unquote(encoded) == "คลิป สอนทำ ภาพ ใหม่ ตอน1 - contact sheet.jpg"
    zip_disposition = _disposition(client.get(f"/api/videos/{BBB}/storyboard/frames.zip"))
    assert unquote(zip_disposition.split("''", 1)[1]) == "คลิป สอนทำ ภาพ ใหม่ ตอน1 - frames.zip"


def test_contact_sheet_without_storyboard_is_404(api):
    resp = api().get(f"/api/videos/{ZOO}/storyboard/contact-sheet.jpg")
    assert resp.status_code == 404
    assert _error(resp)["code"] == "E_NO_STORYBOARD"


def test_zip_private_is_404(api):
    resp = api().get(f"/api/videos/{PRIVATE}/storyboard/frames.zip")
    assert resp.status_code == 404
    assert _error(resp)["code"] == "E_VIDEO_PRIVATE"


# ---------- ชื่อไฟล์ ----------


def test_safe_title_rules():
    from yttoolkit.api.videos import attachment_header, safe_title

    assert safe_title('a\\b/c:d*e?f"g<h>i|j') == "abcdefghij"
    assert safe_title("  หนึ่ง \t\n  สอง\x00\x1f\x7f  ") == "หนึ่ง สอง"
    assert safe_title("ก" * 150) == "ก" * 100
    assert safe_title("   ") == ""
    assert attachment_header("x.jpg", "ก.jpg") == (
        "attachment; filename=\"x.jpg\"; filename*=UTF-8''%E0%B8%81.jpg"
    )


def test_empty_title_falls_back_to_video_id(api):
    class Untitled(FakeExtractor):
        def probe(self, video_id: str) -> dict:
            info = super().probe(video_id)
            info["title"] = '???'
            return info

    resp = api(Untitled(FIXTURES)).get(f"/api/videos/{BBB}/storyboard/frames.zip")
    assert _disposition(resp).endswith(quote(f"{BBB} - frames.zip", safe=""))


# ---------- เพลย์ลิสต์ ----------


def test_playlist_limited_to_200(api):  # AC-IN-07
    resp = api().get(f"/api/playlists/{PLAYLIST}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "เพลย์ลิสต์ทดสอบ 250 คลิป"
    assert body["total"] == 250
    assert body["truncated"] is True
    assert len(body["entries"]) == 200
    assert set(body["entries"][0]) >= {"videoId", "title", "thumbnailUrl"}


@pytest.mark.parametrize("bad", ["short", "PL" + "x" * 70, "PL-bad!list"])
def test_playlist_bad_id_is_422(api, bad):
    client = api()
    resp = client.get(f"/api/playlists/{bad}")
    assert resp.status_code == 422
    assert _error(resp)["code"] == "E_INVALID_INPUT"
    assert client.fake.calls == []


def test_playlist_missing_is_404(api):
    resp = api().get("/api/playlists/PLdoesnotexist")
    assert resp.status_code == 404
    assert _error(resp)["code"] == "E_VIDEO_UNAVAILABLE"


# ---------- ประวัติ ----------


def test_history_after_two_probes(api):
    client = api()
    assert client.get("/api/history").json() == {"items": [], "total": 0}
    client.get(f"/api/videos/{BBB}")
    client.get(f"/api/videos/{ZOO}")
    body = client.get("/api/history").json()
    assert body["total"] == 2
    assert {item["videoId"] for item in body["items"]} == {BBB, ZOO}
    item = next(i for i in body["items"] if i["videoId"] == BBB)
    assert set(item) == {"videoId", "title", "thumbnailUrl", "durationS", "outputs", "lastAt"}


def test_history_search_and_paging(api):
    client = api()
    client.get(f"/api/videos/{BBB}")
    client.get(f"/api/videos/{ZOO}")
    body = client.get("/api/history", params={"q": "zoo"}).json()
    assert body["total"] == 1 and body["items"][0]["videoId"] == ZOO
    page = client.get("/api/history", params={"limit": 1, "offset": 1}).json()
    assert page["total"] == 2 and len(page["items"]) == 1


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1", "limit=x"])
def test_history_rejects_bad_paging(api, query):
    resp = api().get(f"/api/history?{query}")
    assert resp.status_code == 422
    assert _error(resp)["code"] == "E_BAD_REQUEST"


def test_history_accepts_max_limit(api):
    assert api().get("/api/history?limit=100").status_code == 200


# ---------- /cache ----------


def _built(client) -> Path:
    client.get(f"/api/videos/{BBB}/storyboard")
    return client.cache_root / BBB / "storyboard"


def test_cache_download_names_frame_by_timecode(api):
    client = api()
    _built(client)
    resp = client.get(f"/api/cache/{BBB}/storyboard/f_0013.jpg?download=1")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    # เฟรม 13 = 13 × 4961 ms = 64.493 วิ -> 00:01:04
    assert resp.headers["content-disposition"] == 'attachment; filename="frame_00-01-04.jpg"'


def test_cache_download_zero_means_inline(api):
    client = api()
    _built(client)
    resp = client.get(f"/api/cache/{BBB}/storyboard/f_0000.jpg?download=0")
    assert "content-disposition" not in resp.headers


def test_cache_missing_file_is_404(api):
    client = api()
    _built(client)
    resp = client.get(f"/api/cache/{BBB}/storyboard/f_9999.jpg")
    assert resp.status_code == 404
    assert _error(resp)["code"] == "E_NOT_FOUND"


def test_cache_does_not_serve_index_json(api):
    client = api()
    _built(client)
    assert client.get(f"/api/cache/{BBB}/storyboard/index.json").status_code == 404


def test_cache_does_not_serve_directories(api):
    client = api()
    _built(client)
    assert client.get(f"/api/cache/{BBB}/storyboard").status_code == 404


def test_cache_serves_other_image_under_video_folder(api):
    client = api()
    folder = client.cache_root / BBB
    folder.mkdir(parents=True)
    Image.new("RGB", (4, 4)).save(folder / "thumb.png")
    resp = client.get(f"/api/cache/{BBB}/thumb.png")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert "cache-control" not in resp.headers  # immutable เฉพาะไฟล์เฟรม storyboard


@pytest.mark.parametrize(
    "path",
    [
        f"/api/cache/{BBB}/%2e%2e/{ZOO}/storyboard/f_0000.jpg",  # ไปโฟลเดอร์คลิปอื่น
        f"/api/cache/{BBB}/storyboard/%2e%2e/%2e%2e/secret.jpg",
        f"/api/cache/{BBB}/storyboard/%2E%2E%2F%2E%2E%2Fsecret.jpg",
        f"/api/cache/{BBB}/storyboard%5C..%5C..%5Csecret.jpg",
        f"/api/cache/{BBB}/storyboard%5Cf_0000.jpg",
        f"/api/cache/{BBB}//etc/secret.jpg",  # absolute
        f"/api/cache/{BBB}/%2Fetc%2Fsecret.jpg",
        f"/api/cache/{BBB}/C:/secret.jpg",  # drive letter
        f"/api/cache/{BBB}/C%3A%5Csecret.jpg",
        f"/api/cache/{BBB}/storyboard/f_0000.jpg:stream",  # NTFS stream
        f"/api/cache/{BBB}/storyboard/f_0000.jpg.",  # จุดท้ายชื่อบน Windows
        f"/api/cache/{BBB}/storyboard/f_0000.jpg%00.png",
        "/api/cache/%2e%2e/secret.jpg",
        "/api/cache/..%5Csecret/x.jpg",
        f"/api/cache/{BBB[:10]}/storyboard/f_0000.jpg",  # id สั้นไป
        "/api/cache/%5C%5Cevil%5Cshare/x.jpg",  # UNC
    ],
)
def test_cache_traversal_is_404(api, path):  # AC-SEC-04
    client = api()
    _built(client)
    # ไฟล์ล่อที่อยู่นอกโฟลเดอร์ของคลิป
    (client.cache_root / "secret.jpg").write_bytes(b"secret")
    (client.cache_root.parent / "secret.jpg").write_bytes(b"secret")
    resp = client.get(path)
    assert resp.status_code == 404, path
    assert _error(resp)["code"] == "E_NOT_FOUND"
    assert b"secret" not in resp.content


def test_cache_literal_dotdot_is_404(api):
    """httpx ตัด .. ออกจาก URL เอง จึงส่ง path ดิบผ่าน ASGI scope ตรง ๆ"""
    import asyncio

    client = api()
    _built(client)
    (client.cache_root / "secret.jpg").write_bytes(b"secret")
    app = client.app
    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": f"/api/cache/{BBB}/../secret.jpg",
        "raw_path": f"/api/cache/{BBB}/../secret.jpg".encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"127.0.0.1:8787")],
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 8787),
    }
    asyncio.run(app(scope, receive, send))
    assert sent[0]["status"] == 404
    body = b"".join(m.get("body", b"") for m in sent[1:])
    assert json.loads(body)["error"]["code"] == "E_NOT_FOUND"


def test_cache_other_video_folder_needs_its_own_id(api):
    """ไฟล์ของคลิปอื่นเข้าได้ผ่าน id ของคลิปนั้นเองเท่านั้น"""
    client = api()
    _built(client)
    other = client.cache_root / ZOO
    other.mkdir()
    Image.new("RGB", (4, 4)).save(other / "x.jpg")
    assert client.get(f"/api/cache/{ZOO}/x.jpg").status_code == 200
    assert client.get(f"/api/cache/{BBB}/%2e%2e/{ZOO}/x.jpg").status_code == 404


def test_cache_foreign_host_rejected(api):  # AC-SEC-02
    client = api()
    _built(client)
    resp = client.get(
        f"/api/cache/{BBB}/storyboard/f_0000.jpg", headers={"host": "evil.example:8787"}
    )
    assert resp.status_code == 421


def test_unknown_code_logged_with_original_code(api, caplog):
    with caplog.at_level(logging.WARNING, logger="yttoolkit"):
        resp = api(BrokenExtractor(FIXTURES, "E_SOMETHING_NEW")).get(f"/api/videos/{BBB}")
    assert _error(resp)["code"] == "E_UNKNOWN"
    records = [r for r in caplog.records if "E_SOMETHING_NEW" in r.getMessage()]
    assert records and records[0].exc_info is not None


# ---------- เว็บอื่นยิง GET ที่มีผลข้างเคียงไม่ได้ ----------


@pytest.mark.parametrize("site", ["cross-site", "same-site"])
def test_cross_site_get_does_not_probe(api, site):
    client = api()
    resp = client.get(f"/api/videos/{BBB}?refresh=1", headers={"sec-fetch-site": site})
    assert resp.status_code == 403
    assert _error(resp)["code"] == "E_FORBIDDEN"
    assert client.fake.calls == []


def test_cross_site_contact_sheet_rejected(api):
    client = api()
    resp = client.get(
        f"/api/videos/{BBB}/storyboard/contact-sheet.jpg", headers={"sec-fetch-site": "cross-site"}
    )
    assert resp.status_code == 403
    assert client.fake.calls == []


def test_same_origin_get_allowed(api):
    resp = api().get(f"/api/videos/{BBB}", headers={"sec-fetch-site": "same-origin"})
    assert resp.status_code == 200


# ---------- ตัวพิมพ์เล็ก/ใหญ่ใน /cache ต้องตรงเป๊ะ (NTFS ไม่สนตัวพิมพ์) ----------


@pytest.mark.parametrize(
    "path",
    [
        f"/api/cache/{BBB.upper()}/storyboard/f_0000.jpg",
        f"/api/cache/{BBB.lower()}/storyboard/f_0000.jpg",
        f"/api/cache/{BBB}/STORYBOARD/f_0000.jpg",
        f"/api/cache/{BBB}/storyboard/F_0000.jpg",
        f"/api/cache/{BBB}/storyboard/f_0000.JPG",
        f"/api/cache/{BBB}/storyboard/f_0000.Jpg",
    ],
)
def test_cache_requires_exact_case(api, path):
    client = api()
    _built(client)
    resp = client.get(path)
    assert resp.status_code == 404, path
    assert _error(resp)["code"] == "E_NOT_FOUND"


def test_cache_rejects_uppercase_extension_even_if_file_has_it(api):
    client = api()
    folder = client.cache_root / BBB
    folder.mkdir(parents=True)
    Image.new("RGB", (4, 4)).save(folder / "thumb.PNG", "PNG")
    assert client.get(f"/api/cache/{BBB}/thumb.PNG").status_code == 404


# ---------- ชื่อไฟล์: อักขระกลับทิศ/ขึ้นบรรทัด ----------


def test_safe_title_strips_bidi_override_and_line_breaks():
    from yttoolkit.api.videos import safe_title

    assert safe_title("คลิป\u202egpj.exe") == "คลิปgpj.exe"
    assert safe_title("บรรทัด1\r\nบรรทัด2\rสาม\nสี่") == "บรรทัด1 บรรทัด2 สาม สี่"


# ---------- error อื่นที่ไม่ใช่ YtError ระหว่างทำภาพ ----------


@pytest.mark.parametrize(
    ("func", "path"),
    [("contact_sheet", "contact-sheet.jpg"), ("frames_zip", "frames.zip")],
)
def test_unexpected_error_while_building_file_is_500(api, monkeypatch, func, path):
    from fastapi.testclient import TestClient

    from yttoolkit.api import videos as videos_api

    def boom(*args, **kwargs):
        raise RuntimeError("ภาพพัง")

    monkeypatch.setattr(videos_api, func, boom)
    client = TestClient(api().app, base_url=BASE, raise_server_exceptions=False)
    resp = client.get(f"/api/videos/{BBB}/storyboard/{path}")
    assert resp.status_code == 500
    assert resp.headers["content-type"].startswith("application/json")
    error = _error(resp)
    assert error["code"] == "E_UNKNOWN"
    assert error["message"] == MESSAGES["E_UNKNOWN"]
    assert "Traceback" not in resp.text
    assert "content-disposition" not in resp.headers


# ---------- 422 ไม่สะท้อนข้อความยาว ๆ กลับไป ----------


def test_validation_detail_is_truncated(api):
    resp = api().post("/api/resolve", json={"text": "ก" * 20001}, headers=AUTH)
    assert resp.status_code == 422
    detail = _error(resp)["detail"]
    assert len(detail) <= 500
    assert "ก" * 600 not in resp.text
