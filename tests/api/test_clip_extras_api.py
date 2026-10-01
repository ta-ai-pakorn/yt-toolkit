"""API ของ owner round 2: ข้อมูลคลิปใน VideoInfo (C-A1), คอมเมนต์ปักหมุด (C-A2), โน้ต .md (C-A3)

ใช้ FakeExtractor + ฐานข้อมูลและโฟลเดอร์ cache ชั่วคราว ไม่แตะเครือข่าย
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import pytest
import yaml

from yttoolkit.core.db import Database
from yttoolkit.core.extractor import FakeExtractor
from yttoolkit.core.subtitles import SubtitleService
from yttoolkit.core.videos import VideoService
from yttoolkit.core.yterrors import MESSAGES, YtError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
THAI = "88o5Sk8_m1Y"
ZOO = "jNQXAC9IVRw"
BBB = "aqz-KE-bpKQ"
OWNER = "OWNERTHSUB1"
NO_COMMENTS = "NOORIGSUB01"
NO_STATS = "VTTFALLBAK1"
WORD = "maxChars=15&lines=1&minMs=800&maxMs=3000&mode=tokens&tokensPerCue=1"


class Counting(FakeExtractor):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.pinned_calls = 0

    def pinned_comment(self, video_id: str) -> dict | None:
        self.pinned_calls += 1
        return super().pinned_comment(video_id)


def _client(make_client, tmp_path: Path, fetch=None):
    db = Database(tmp_path / "app.db")
    db.migrate()
    fake = Counting(FIXTURES)
    videos = VideoService(db, fake, now=lambda: datetime(2026, 10, 1, 12, tzinfo=UTC))
    cache_root = tmp_path / "cache"
    subtitles = SubtitleService(videos, fetch or fake.fetch_subtitle, cache_root)
    client = make_client(videos=videos, extractor=fake, cache_root=cache_root, subtitles=subtitles)
    return client, fake, db


@pytest.fixture
def env(make_client, tmp_path):
    client, fake, db = _client(make_client, tmp_path)
    yield client, fake
    db.close()


@pytest.fixture
def client(env):
    return env[0]


def _error(resp) -> dict:
    return resp.json()["error"]


# ---------- C-A1 ----------


def test_video_info_has_clip_stats(client):
    body = client.get(f"/api/videos/{ZOO}").json()
    assert body["stats"] == {"views": 438721846, "likes": 19966949, "comments": 10000000, "channelFollowers": 6640000}
    assert body["tags"] == ["me at the zoo", "jawed karim", "first youtube video"]
    assert body["categories"] == ["Film & Animation"]
    assert body["mostReplayed"] == [{"startMs": 0, "endMs": 190}, {"startMs": 10260, "endMs": 12160}]


def test_missing_clip_stats_are_omitted(client):
    body = client.get(f"/api/videos/{NO_STATS}").json()
    assert not {"stats", "tags", "categories", "mostReplayed"} & set(body)
    thai = client.get(f"/api/videos/{THAI}").json()
    assert "mostReplayed" not in thai and thai["stats"]["comments"] == 120


# ---------- C-A2 ----------


def test_pinned_comment_found(env):
    client, fake = env
    resp = client.get(f"/api/videos/{THAI}/pinned-comment")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"comment"}
    assert set(body["comment"]) == {"text", "likes", "publishedText"}
    assert body["comment"]["text"].startswith("ขอบคุณที่ดูคลิปนี้")
    assert client.get(f"/api/videos/{THAI}/pinned-comment").json() == body
    assert fake.pinned_calls == 1  # ครั้งที่สองมาจาก cache


def test_pinned_comment_null(env):
    client, fake = env
    assert client.get(f"/api/videos/{BBB}/pinned-comment").json() == {"comment": None}
    assert client.get(f"/api/videos/{NO_COMMENTS}/pinned-comment").json() == {"comment": None}
    assert fake.pinned_calls == 1  # คลิปที่คอมเมนต์ = 0 ไม่ต่อยูทูป


def test_pinned_comment_network_error_is_502_and_remembered(env):
    client, fake = env
    for _ in range(2):
        resp = client.get(f"/api/videos/{OWNER}/pinned-comment")
        assert resp.status_code == 502
        assert _error(resp)["code"] == "E_NETWORK"
        assert _error(resp)["message"] == MESSAGES["E_NETWORK"]
    assert fake.pinned_calls == 1


@pytest.mark.parametrize(
    ("video", "status", "code"),
    [("PRIVATEVID1", 404, "E_VIDEO_PRIVATE"), ("not-an-id", 422, "E_INVALID_INPUT"), ("UPCOMINGLV1", 409, "E_LIVE_NOT_READY")],
)
def test_pinned_comment_video_errors(client, video, status, code):
    resp = client.get(f"/api/videos/{video}/pinned-comment")
    assert resp.status_code == status
    assert _error(resp)["code"] == code


def test_pinned_comment_bot_check_is_429(make_client, tmp_path):
    client, fake, db = _client(make_client, tmp_path)

    def blocked(video_id: str) -> dict | None:
        raise YtError("E_BOT_CHECK", "HTTP Error 429")

    fake.pinned_comment = blocked
    try:
        resp = client.get(f"/api/videos/{THAI}/pinned-comment")
        assert resp.status_code == 429
        assert _error(resp)["code"] == "E_BOT_CHECK"
    finally:
        db.close()


# ---------- C-A3 ----------


def _note(client, video: str, query: str = ""):
    return client.get(f"/api/videos/{video}/note" + (f"?{query}" if query else ""))


def _front(text: str) -> dict:
    assert text.startswith("---\n")
    head, _, _ = text[4:].partition("\n---\n")
    return yaml.safe_load(head)


def test_note_of_the_thai_clip_with_the_default_track(client):
    resp = _note(client, THAI, WORD)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/markdown; charset=utf-8"
    disposition = resp.headers["content-disposition"]
    assert f'filename="{THAI}.note.md"' in disposition
    assert quote("Thai Listening Practice EP.1 Beginner.note.md", safe="") in disposition  # ตัด | (ห้ามใช้ใน Windows)
    raw = resp.content
    assert b"\r" not in raw and not raw.startswith(b"\xef\xbb\xbf") and raw.endswith(b"\n")
    text = raw.decode("utf-8")
    front = _front(text)
    assert front == {
        "title": "Thai Listening Practice | EP.1 | Beginner",
        "url": f"https://www.youtube.com/watch?v={THAI}",
        "channel": "KOD THAI",
        "published": datetime(2025, 5, 20).date(),
        "duration": "0:06:12",
        "tags": front["tags"],
        "views": 38764,
        "source": "YT Toolkit",
    }
    assert len(front["tags"]) == 10
    assert "\n# Thai Listening Practice | EP.1 | Beginner\n" in text
    assert "\n## คำอธิบาย\nIf you enjoy the videos" in text
    assert "## Chapter" not in text  # คลิปนี้ไม่มี chapter
    assert "\n## ทรานสคริปต์\n\n### [00:00]\n\n" in text
    assert "\n### [02:00]\n" in text


def test_note_uses_chapters_and_the_chosen_track(client):
    text = _note(client, ZOO, "trackId=o.de").text
    assert "\n## Chapter\n- [00:00] Intro\n- [00:05] The cool thing\n- [00:17] End\n" in text
    assert "\n## ทรานสคริปต์\n\n### [00:00] Intro\n" in text
    assert text != _note(client, ZOO).text  # ไม่ส่งแทร็ก = แทร็กที่เลือกให้เอง (o.en)


def test_note_without_any_track_has_no_transcript(client):
    resp = _note(client, BBB)
    assert resp.status_code == 200
    text = resp.text
    assert "## ทรานสคริปต์" not in text and "## Chapter" not in text
    assert "\n## คำอธิบาย\nUHD High Frame rate version" in text


def test_note_yaml_survives_tricky_tags(client):
    front = _front(_note(client, OWNER).text)
    assert front["tags"] == ["ซับไทย", 'test: "quotes"', "#hashtag", "back\\slash", "padded tag"]
    assert front["channel"] == "ชุดทดสอบ"


def test_note_omits_unknown_front_matter(client):
    front = _front(_note(client, NO_STATS).text)
    assert "views" not in front and "tags" not in front


@pytest.mark.parametrize(
    ("query", "status", "code"),
    [
        ("trackId=o.xx", 404, "E_NO_SUBTITLES"),
        ("trackId=bad id", 404, "E_NO_SUBTITLES"),
        ("maxChars=5", 422, "E_BAD_REQUEST"),
        ("mode=tokens", 422, "E_BAD_REQUEST"),
        ("minMs=3000&maxMs=3000", 422, "E_BAD_REQUEST"),
    ],
)
def test_note_bad_requests(client, query, status, code):
    resp = _note(client, THAI, query)
    assert resp.status_code == status
    assert _error(resp)["code"] == code


@pytest.mark.parametrize(("video", "status", "code"), [("PRIVATEVID1", 404, "E_VIDEO_PRIVATE"), ("bad", 422, "E_INVALID_INPUT")])
def test_note_video_errors(client, video, status, code):
    resp = _note(client, video)
    assert resp.status_code == status
    assert _error(resp)["code"] == code


def test_note_translated_track_blocked_is_503(make_client, tmp_path):
    fake = FakeExtractor(FIXTURES)

    def fetch(url: str) -> bytes:
        if "tlang=" in url:
            raise YtError("E_BOT_CHECK", "HTTP Error 429: Too Many Requests")
        return fake.fetch_subtitle(url)

    client, _, db = _client(make_client, tmp_path, fetch)
    try:
        resp = _note(client, THAI, "trackId=t.en")
        assert resp.status_code == 503
        assert _error(resp)["code"] == "E_TRANSLATION_BLOCKED"
        assert _note(client, THAI).status_code == 200
    finally:
        db.close()


def test_note_with_an_empty_default_track_still_works(make_client, tmp_path):
    client, _, db = _client(make_client, tmp_path, lambda url: b'{"events": []}')
    try:
        resp = _note(client, THAI)
        assert resp.status_code == 200
        assert "## ทรานสคริปต์" not in resp.text
    finally:
        db.close()
