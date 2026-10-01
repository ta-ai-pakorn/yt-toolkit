"""API ซับของ M3 (C4): รายการแทร็ก, token และโหลดไฟล์ซับ

ใช้ FakeExtractor + ฐานข้อมูลและโฟลเดอร์ cache ชั่วคราว ไม่แตะเครือข่าย
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

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


def _export(client, query: str, track: str = TRACK, video: str = THAI):
    return client.get(f"/api/videos/{video}/subtitles/{track}/export?{query}")


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


@pytest.mark.parametrize(
    ("fmt", "media_type"),
    [
        ("srt", "application/x-subrip; charset=utf-8"),
        ("txt", "text/plain; charset=utf-8"),
        ("md", "text/markdown; charset=utf-8"),
    ],
)
def test_export_file(client, fmt, media_type):
    resp = _export(client, f"format={fmt}&{MEDIUM}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == media_type
    disposition = resp.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert f'filename="subtitles.th.{fmt}"' in disposition
    assert "filename*=UTF-8''" + quote(f"Thai Listening Practice EP.1 Beginner.th.{fmt}", safe="") in disposition
    assert not resp.content.startswith(b"\xef\xbb\xbf")
    assert resp.content.count(b"\n") == resp.content.count(b"\r\n") > 0


def test_export_srt_content(client):
    body = _export(client, f"format=srt&{MEDIUM}").content.decode("utf-8")
    assert body.startswith("1\r\n00:00:")


def test_export_tokens_mode(client):
    resp = _export(client, "format=srt&maxChars=25&lines=1&minMs=1200&maxMs=5000&mode=tokens&tokensPerCue=3")
    assert resp.status_code == 200


def test_export_defaults_to_medium_preset(client):
    assert _export(client, "format=srt").content == _export(client, f"format=srt&{MEDIUM}").content


# ---------- errors ----------


@pytest.mark.parametrize("track", ["zz.bad", "o.xx", "t.nope"])
def test_tokens_unknown_track_is_404(client, track):
    resp = client.get(f"/api/videos/{THAI}/subtitles/{track}/tokens")
    assert resp.status_code == 404
    error = _error(resp)
    assert error["code"] == "E_NO_SUBTITLES"
    assert error["message"] == "คลิปนี้ไม่มีซับ" == MESSAGES["E_NO_SUBTITLES"]


def test_export_unknown_track_is_404(client):
    resp = _export(client, f"format=srt&{MEDIUM}", track="zz.bad")
    assert resp.status_code == 404
    assert _error(resp)["code"] == "E_NO_SUBTITLES"


@pytest.mark.parametrize(
    "query",
    [
        f"format=srt&{MEDIUM}".replace("maxChars=25", "maxChars=5"),
        "format=srt&maxChars=25&lines=1&minMs=5000&maxMs=3000&mode=chars",
        "format=srt&maxChars=25&lines=1&minMs=1200&maxMs=5000&mode=tokens",
        f"format=docx&{MEDIUM}",
        MEDIUM,
        f"format=srt&{MEDIUM}".replace("lines=1", "lines=3"),
        f"format=srt&{MEDIUM}".replace("maxChars=25", "maxChars=25.5"),
        f"format=srt&{MEDIUM}".replace("mode=chars", "mode=words"),
        f"format=srt&{MEDIUM}&tokensPerCue=99",
    ],
)
def test_export_bad_options_are_422(client, query):
    resp = _export(client, query)
    assert resp.status_code == 422
    assert _error(resp)["code"] == "E_BAD_REQUEST"


@pytest.mark.parametrize(
    "path",
    [
        f"/api/videos/{LIVE}/subtitles",
        f"/api/videos/{LIVE}/subtitles/{TRACK}/tokens",
        f"/api/videos/{LIVE}/subtitles/{TRACK}/export?format=srt&{MEDIUM}",
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
        f"/api/videos/{PRIVATE}/subtitles/{TRACK}/export?format=srt&{MEDIUM}",
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
            f"/api/videos/{THAI}/subtitles/t.en/export?format=srt&{MEDIUM}",
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
        f"/api/videos/{THAI}/subtitles/t.en/export?format=srt&{MEDIUM}",
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
