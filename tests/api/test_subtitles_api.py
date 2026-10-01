"""API ซับ (C4): รายการแทร็ก, token และโน้ต .md (ไฟล์ซับย้ายเข้าคิวงานแล้ว)

ใช้ FakeExtractor + ฐานข้อมูลและโฟลเดอร์ cache ชั่วคราว ไม่แตะเครือข่าย
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from yttoolkit.core.db import Database
from yttoolkit.core.extractor import FakeExtractor
from yttoolkit.core.subtitles import SubtitleService
from yttoolkit.core.videos import VideoService
from yttoolkit.core.yterrors import MESSAGES, YtError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
THAI = "88o5Sk8_m1Y"
BBB = "aqz-KE-bpKQ"
LIVE = "UPCOMINGLV1"
PRIVATE = "PRIVATEVID1"
TRACK = "a.th-orig"
MEDIUM = "maxChars=25&lines=1&minMs=1200&maxMs=5000&mode=chars"


@pytest.fixture
def client(make_client, tmp_path):
    db = Database(tmp_path / "app.db")
    db.migrate()
    fake = FakeExtractor(FIXTURES)
    videos = VideoService(db, fake, now=lambda: datetime(2026, 9, 30, 12, tzinfo=UTC))
    cache_root = tmp_path / "cache"
    subtitles = SubtitleService(videos, fake.fetch_subtitle, cache_root)
    yield make_client(videos=videos, extractor=fake, cache_root=cache_root, subtitles=subtitles)
    db.close()


def _error(resp) -> dict:
    return resp.json()["error"]


# ---------- happy path ----------


def test_tracks_shape(client):
    resp = client.get(f"/api/videos/{THAI}/subtitles")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"tracks", "defaultTrackId"}
    assert body["defaultTrackId"] == TRACK
    assert all(set(track) == {"id", "lang", "name", "group"} for track in body["tracks"])


def test_tracks_empty_is_not_an_error(client):
    resp = client.get(f"/api/videos/{BBB}/subtitles")
    assert resp.status_code == 200
    assert resp.json() == {"tracks": []}


def test_tokens_shape(client):
    resp = client.get(f"/api/videos/{THAI}/subtitles/{TRACK}/tokens")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"hasWordTiming", "tokens"}
    assert isinstance(body["hasWordTiming"], bool)
    assert len(body["tokens"]) >= 200
    for tok in body["tokens"]:
        assert set(tok) == {"t", "s", "e"}
        assert isinstance(tok["t"], str)
        assert type(tok["s"]) is int and type(tok["e"]) is int


def test_removed_export_endpoint_answers_404(client):
    # M4 (Q3): ไฟล์ซับโหลดผ่านคิวงานแล้ว endpoint เดิมถูกถอดออก (โน้ต .md ยังอยู่)
    resp = client.get(f"/api/videos/{THAI}/subtitles/{TRACK}/export?format=srt&{MEDIUM}")
    assert resp.status_code == 404
    assert _error(resp)["code"] == "E_NOT_FOUND"


# ---------- errors ----------


@pytest.mark.parametrize("track", ["zz.bad", "o.xx", "t.nope"])
def test_tokens_unknown_track_is_404(client, track):
    resp = client.get(f"/api/videos/{THAI}/subtitles/{track}/tokens")
    assert resp.status_code == 404
    error = _error(resp)
    assert error["code"] == "E_NO_SUBTITLES"
    assert error["message"] == "คลิปนี้ไม่มีซับ" == MESSAGES["E_NO_SUBTITLES"]


@pytest.mark.parametrize(
    "path",
    [
        f"/api/videos/{LIVE}/subtitles",
        f"/api/videos/{LIVE}/subtitles/{TRACK}/tokens",
        f"/api/videos/{LIVE}/note?{MEDIUM}",
    ],
)
def test_live_not_ready_is_409(client, path):
    resp = client.get(path)
    assert resp.status_code == 409
    assert _error(resp)["code"] == "E_LIVE_NOT_READY"


@pytest.mark.parametrize(
    "path",
    [
        f"/api/videos/{PRIVATE}/subtitles",
        f"/api/videos/{PRIVATE}/subtitles/{TRACK}/tokens",
        f"/api/videos/{PRIVATE}/note?{MEDIUM}",
    ],
)
def test_private_is_404(client, path):
    resp = client.get(path)
    assert resp.status_code == 404
    assert _error(resp)["code"] == "E_VIDEO_PRIVATE"


def test_translated_track_blocked_is_503_not_bot_check(make_client, tmp_path):
    db = Database(tmp_path / "blocked.db")
    db.migrate()
    fake = FakeExtractor(FIXTURES)
    videos = VideoService(db, fake, now=lambda: datetime(2026, 9, 30, 12, tzinfo=UTC))

    def fetch(url: str) -> bytes:
        if "tlang=" in url:
            raise YtError("E_BOT_CHECK", "HTTP Error 429: Too Many Requests")
        return fake.fetch_subtitle(url)

    cache_root = tmp_path / "cache"
    subtitles = SubtitleService(videos, fetch, cache_root, sleep=lambda seconds: None)
    client = make_client(videos=videos, extractor=fake, cache_root=cache_root, subtitles=subtitles)
    try:
        for path in (
            f"/api/videos/{THAI}/subtitles/t.en/tokens",
            f"/api/videos/{THAI}/note?trackId=t.en&{MEDIUM}",
        ):
            resp = client.get(path)
            assert resp.status_code == 503
            error = _error(resp)
            assert error["code"] == "E_TRANSLATION_BLOCKED"
            assert error["message"] == MESSAGES["E_TRANSLATION_BLOCKED"]
        # ซับภาษาต้นฉบับของคลิปเดียวกันยังโหลดได้ตามปกติ
        assert client.get(f"/api/videos/{THAI}/subtitles/{TRACK}/tokens").status_code == 200
    finally:
        db.close()


def test_bad_video_id_is_422(client):
    resp = client.get("/api/videos/not-an-id/subtitles")
    assert resp.status_code == 422
    assert _error(resp)["code"] == "E_INVALID_INPUT"


def test_cross_site_request_is_blocked(client):
    resp = client.get(f"/api/videos/{THAI}/subtitles", headers={"Sec-Fetch-Site": "cross-site"})
    assert resp.status_code == 403


def test_routes_absent_without_subtitle_service(make_client):
    resp = make_client().get(f"/api/videos/{THAI}/subtitles")
    assert resp.status_code == 404
    assert _error(resp)["code"] == "E_NOT_FOUND"


# ---------- owner round 3: E_SESSION_WARMING ----------


class _YoungSession:
    def __init__(self, wait: int) -> None:
        self.wait = wait

    def wait_seconds(self) -> int:
        return self.wait


@pytest.fixture
def warming(make_client, tmp_path):
    db = Database(tmp_path / "warming.db")
    db.migrate()
    fake = FakeExtractor(FIXTURES)
    videos = VideoService(db, fake, now=lambda: datetime(2026, 9, 30, 12, tzinfo=UTC))
    cache_root = tmp_path / "cache"
    session = _YoungSession(37)
    subtitles = SubtitleService(videos, fake.fetch_subtitle, cache_root, session=session)
    yield make_client(videos=videos, extractor=fake, cache_root=cache_root, subtitles=subtitles), session
    db.close()


@pytest.mark.parametrize(
    "path",
    [
        f"/api/videos/{THAI}/subtitles/t.en/tokens",
        f"/api/videos/{THAI}/note?trackId=t.en&{MEDIUM}",
    ],
)
def test_session_warming_is_503_with_retry_after(warming, path):
    client, _ = warming
    resp = client.get(path)
    assert resp.status_code == 503
    assert resp.headers["Retry-After"] == "37"
    error = _error(resp)
    assert error["code"] == "E_SESSION_WARMING"
    assert error["message"] == MESSAGES["E_SESSION_WARMING"]
    assert error["retryAfterSeconds"] == 37
    assert set(error) == {"code", "message", "detail", "retryAfterSeconds"}


def test_session_warming_never_gates_original_tracks(warming):
    client, _ = warming
    resp = client.get(f"/api/videos/{THAI}/subtitles/{TRACK}/tokens")
    assert resp.status_code == 200


def test_session_ready_serves_translated_tokens(warming):
    client, session = warming
    session.wait = 0
    resp = client.get(f"/api/videos/{THAI}/subtitles/t.en/tokens")
    assert resp.status_code == 200
    assert resp.json()["tokens"]


def test_other_errors_have_no_retry_after(client):
    resp = client.get(f"/api/videos/{PRIVATE}/subtitles/{TRACK}/tokens")
    assert "Retry-After" not in resp.headers
    assert "retryAfterSeconds" not in _error(resp)


# ---------- M4: ตัวพักคิว (ctx.on_bot_check) ----------


def test_translation_blocked_does_not_call_brake_but_real_bot_check_does(make_client, tmp_path):
    db = Database(tmp_path / "brake.db")
    db.migrate()
    fake = FakeExtractor(FIXTURES)
    videos = VideoService(db, fake, now=lambda: datetime(2026, 9, 30, 12, tzinfo=UTC))

    def fetch(url: str) -> bytes:
        if "tlang=" in url:
            raise YtError("E_BOT_CHECK", "HTTP Error 429: Too Many Requests")
        return fake.fetch_subtitle(url)

    calls: list[int] = []
    cache_root = tmp_path / "cache"
    subtitles = SubtitleService(videos, fetch, cache_root, sleep=lambda seconds: None)
    client = make_client(
        videos=videos,
        extractor=fake,
        cache_root=cache_root,
        subtitles=subtitles,
        on_bot_check=lambda: calls.append(1),
    )
    try:
        resp = client.get(f"/api/videos/{THAI}/subtitles/t.en/tokens")
        assert resp.status_code == 503
        assert _error(resp)["code"] == "E_TRANSLATION_BLOCKED"
        assert calls == []

        # ยูทูปขอยืนยันบอทตอนอ่านรายการแทร็ก (ดึงข้อมูลคลิป) = พักคิว
        def blocked(video_id: str) -> dict:
            raise YtError("E_BOT_CHECK", "Sign in to confirm you're not a bot")

        fake.probe = blocked  # type: ignore[method-assign]
        resp = client.get(f"/api/videos/{BBB}/subtitles")
        assert resp.status_code == 429
        assert _error(resp)["code"] == "E_BOT_CHECK"
        assert calls == [1]
    finally:
        db.close()
