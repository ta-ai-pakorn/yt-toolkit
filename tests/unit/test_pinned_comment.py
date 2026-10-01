"""คอมเมนต์ปักหมุดของเจ้าของช่อง (C-A2): ตัวกรอง, ตัวจริง (yt-dlp ถูกแทน ไม่ต่อเน็ต), ตัวปลอม และบริการ cache"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import ClassVar, Self

import pytest
import yt_dlp
from yt_dlp.utils import DownloadError, ExtractorError

from yttoolkit.core import comments as comments_mod
from yttoolkit.core.comments import CACHE_FILE, CACHE_VERSION, PinnedCommentService, clean_comment
from yttoolkit.core.db import Database
from yttoolkit.core.extractor import FakeExtractor, YtDlpExtractor, pinned_from_comment
from yttoolkit.core.videos import VideoService
from yttoolkit.core.yterrors import YtError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
THAI = "88o5Sk8_m1Y"
BBB = "aqz-KE-bpKQ"
ERRORED = "OWNERTHSUB1"
NO_COMMENTS = "NOORIGSUB01"
ZOO = "jNQXAC9IVRw"
VIEWER = "VIEWERPIN01"
ALLOWED = {"text", "likes", "publishedText", "byUploader"}

UPLOADER_PIN = {
    "id": "Ugx1",
    "text": "สวัสดีครับ\nลิงก์อยู่ในคำอธิบาย",
    "like_count": 12,
    "author": "เจ้าของช่อง",
    "author_id": "UC123",
    "author_url": "https://www.youtube.com/@owner",
    "author_thumbnail": "https://yt3.ggpht.com/x",
    "author_is_uploader": True,
    "author_is_verified": False,
    "is_favorited": False,
    "is_pinned": True,
    "_time_text": " 2 weeks ago ",
    "timestamp": 1,
    "parent": "root",
}


# ---------- pinned_from_comment ----------


def test_uploader_pin_keeps_only_text_likes_and_time() -> None:
    assert pinned_from_comment(UPLOADER_PIN) == {
        "text": "สวัสดีครับ\nลิงก์อยู่ในคำอธิบาย",
        "likes": 12,
        "publishedText": "2 weeks ago",
        "byUploader": True,
    }


def test_viewer_pin_is_kept_with_by_uploader_false() -> None:
    """C-A2 v2: ปักหมุดของผู้ชมก็นับ ส่งออกแค่ byUploader (ไม่มีชื่อ/id ของผู้เขียน)"""
    for change in ({"author_is_uploader": False}, {"author_is_uploader": None}, {"author_is_uploader": "yes"}):
        out = pinned_from_comment({**UPLOADER_PIN, **change})
        assert out is not None and out["byUploader"] is False
        assert set(out) <= ALLOWED
        assert "author" not in out and "UC123" not in str(out)
    out = pinned_from_comment({k: v for k, v in UPLOADER_PIN.items() if k != "author_is_uploader"})
    assert out is not None and out["byUploader"] is False


@pytest.mark.parametrize(
    "change",
    [
        {"is_pinned": False},  # เจ้าของช่องเขียนแต่ไม่ได้ปักหมุด
        {"is_pinned": None},
        {"text": "   "},
        {"text": None},
    ],
)
def test_other_comments_are_not_returned(change: dict) -> None:
    assert pinned_from_comment({**UPLOADER_PIN, **change}) is None


@pytest.mark.parametrize("value", [None, "x", [], 3])
def test_non_dict_is_none(value: object) -> None:
    assert pinned_from_comment(value) is None


def test_optional_fields_are_dropped_when_unusable() -> None:
    out = pinned_from_comment({**UPLOADER_PIN, "like_count": True, "_time_text": ""})
    assert out == {"text": UPLOADER_PIN["text"], "byUploader": True}
    assert "likes" not in pinned_from_comment({**UPLOADER_PIN, "like_count": -1})


# ---------- YtDlpExtractor.pinned_comment (yt-dlp ถูกแทน) ----------


class FakeIE:
    comments: ClassVar[list] = []
    error: ClassVar[BaseException | None] = None
    calls: ClassVar[list] = []

    def initialize(self) -> None:
        FakeIE.calls.append("initialize")

    def _get_default_ytcfg(self, client: str) -> dict:
        FakeIE.calls.append(("ytcfg", client))
        return {"client": client}

    def _get_comments(self, ytcfg: dict, video_id: str, contents: list, webpage: object):
        FakeIE.calls.append(("comments", ytcfg, video_id, contents, webpage))
        if FakeIE.error is not None:
            raise FakeIE.error
        return iter(FakeIE.comments)


class FakeYDL:
    instances: ClassVar[list[FakeYDL]] = []
    ie: ClassVar[object] = FakeIE()
    probe_result: ClassVar[dict] = {}
    probe_error: ClassVar[BaseException | None] = None

    def __init__(self, params: dict) -> None:
        self.params = dict(params)
        self.urls: list[str] = []
        FakeYDL.instances.append(self)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def get_info_extractor(self, key: str) -> object:
        assert key == "Youtube"
        return FakeYDL.ie

    def extract_info(self, url: str, download: bool = True) -> dict:
        assert download is False
        assert self.params.get("getcomments") is True
        self.urls.append(url)
        if FakeYDL.probe_error is not None:
            raise FakeYDL.probe_error
        return FakeYDL.probe_result


@pytest.fixture
def ydl(monkeypatch: pytest.MonkeyPatch) -> type[FakeYDL]:
    FakeYDL.instances = []
    FakeYDL.ie = FakeIE()
    FakeYDL.probe_result = {}
    FakeYDL.probe_error = None
    FakeIE.comments = [UPLOADER_PIN]
    FakeIE.error = None
    FakeIE.calls = []
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    return FakeYDL


def test_direct_path_asks_for_one_top_comment(ydl: type[FakeYDL]) -> None:
    assert YtDlpExtractor().pinned_comment(THAI) == pinned_from_comment(UPLOADER_PIN)
    (inst,) = ydl.instances
    assert inst.params["extractor_args"] == {
        "youtube": {"comment_sort": ["top"], "max_comments": ["1", "1", "0", "0", "1"]}
    }
    assert inst.params["skip_download"] is True and "getcomments" not in inst.params
    assert FakeIE.calls == ["initialize", ("ytcfg", "web"), ("comments", {"client": "web"}, THAI, [], None)]
    assert inst.urls == []  # ไม่ probe ซ้ำ


@pytest.mark.parametrize("first", [[], [None], [{**UPLOADER_PIN, "is_pinned": False}]])
def test_direct_path_without_a_pinned_comment_is_none(ydl: type[FakeYDL], first: list) -> None:
    FakeIE.comments = first
    assert YtDlpExtractor().pinned_comment(THAI) is None


def test_direct_path_returns_a_viewer_pin_with_by_uploader_false(ydl: type[FakeYDL]) -> None:
    FakeIE.comments = [{**UPLOADER_PIN, "author_is_uploader": False}]
    out = YtDlpExtractor().pinned_comment(THAI)
    assert out is not None and out["byUploader"] is False


@pytest.mark.parametrize("error", [AttributeError("no _get_comments"), TypeError("signature changed")])
def test_private_api_change_falls_back_to_a_public_probe(ydl: type[FakeYDL], error: Exception) -> None:
    FakeIE.error = error
    FakeYDL.probe_result = {"id": THAI, "comments": [UPLOADER_PIN]}
    assert YtDlpExtractor().pinned_comment(THAI) == pinned_from_comment(UPLOADER_PIN)
    (inst,) = ydl.instances
    assert inst.urls == [f"https://www.youtube.com/watch?v={THAI}"]
    assert inst.params["extractor_args"]["youtube"]["max_comments"] == ["1", "1", "0", "0", "1"]


def test_public_probe_without_comments_is_none(ydl: type[FakeYDL]) -> None:
    FakeYDL.ie = object()  # ไม่มีเมธอดภายในเลย -> AttributeError
    FakeYDL.probe_result = {"id": THAI, "comments": None}
    assert YtDlpExtractor().pinned_comment(THAI) is None


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (ExtractorError("Unable to download API page: HTTP Error 429: Too Many Requests"), "E_BOT_CHECK"),
        (DownloadError("ERROR: Unable to download API page: timed out"), "E_NETWORK"),
    ],
)
def test_network_and_bot_errors_are_raised_without_fallback(
    ydl: type[FakeYDL], error: Exception, code: str
) -> None:
    FakeIE.error = error
    with pytest.raises(YtError) as exc:
        YtDlpExtractor().pinned_comment(THAI)
    assert exc.value.code == code
    assert ydl.instances[0].urls == []  # ไม่ probe ทางสำรอง


@pytest.mark.parametrize(
    "error",
    [ExtractorError("something odd"), RuntimeError("boom"), KeyError("contents"), IndexError("0"), ValueError("x")],
)
def test_other_direct_path_errors_fall_back_to_the_public_probe(ydl: type[FakeYDL], error: Exception) -> None:
    # review M-1: yt-dlp เปลี่ยนภายในได้หลายแบบ ไม่ใช่แค่ AttributeError/TypeError
    FakeIE.error = error
    FakeYDL.probe_result = {"id": THAI, "comments": [UPLOADER_PIN]}
    assert YtDlpExtractor().pinned_comment(THAI) == pinned_from_comment(UPLOADER_PIN)
    assert ydl.instances[0].urls == [f"https://www.youtube.com/watch?v={THAI}"]


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (ExtractorError("Unable to download API page: HTTP Error 429: Too Many Requests"), "E_BOT_CHECK"),
        (ExtractorError("something odd"), "E_UNKNOWN"),
        (RuntimeError("boom"), "E_UNKNOWN"),
    ],
)
def test_public_probe_errors_become_yt_errors(ydl: type[FakeYDL], error: Exception, code: str) -> None:
    FakeIE.error = KeyError("contents")
    FakeYDL.probe_error = error
    with pytest.raises(YtError) as exc:
        YtDlpExtractor().pinned_comment(THAI)
    assert exc.value.code == code


def test_bad_id_never_reaches_yt_dlp(ydl: type[FakeYDL]) -> None:
    with pytest.raises(YtError) as exc:
        YtDlpExtractor().pinned_comment("../etc")
    assert exc.value.code == "E_INVALID_INPUT"
    assert ydl.instances == []


# ---------- FakeExtractor.pinned_comment ----------


def test_fake_reads_fixtures() -> None:
    fake = FakeExtractor(FIXTURES)
    found = fake.pinned_comment(THAI)
    assert found is not None and set(found) <= ALLOWED and "\n" in found["text"]
    assert found["byUploader"] is True
    viewer = fake.pinned_comment(VIEWER)
    assert viewer is not None and viewer["byUploader"] is False
    assert fake.pinned_comment(BBB) is None
    assert fake.pinned_comment(ZOO) is None  # ไม่มีไฟล์ = ไม่มีคอมเมนต์ปักหมุด
    with pytest.raises(YtError) as exc:
        fake.pinned_comment(ERRORED)
    assert exc.value.code == "E_NETWORK"
    with pytest.raises(YtError) as exc:
        fake.pinned_comment("bad id!")
    assert exc.value.code == "E_INVALID_INPUT"
    assert ("pinned_comment", THAI) in fake.calls


@pytest.mark.parametrize("path", sorted((FIXTURES / "comments").glob("*.json")), ids=lambda p: p.stem)
def test_comment_fixtures_have_no_author_data(path: Path) -> None:
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert set(doc) in ({"comment"}, {"error"})
    if isinstance(doc.get("comment"), dict):
        assert set(doc["comment"]) <= ALLOWED
    assert (FIXTURES / "probe" / f"{path.stem}.json").is_file()  # มีคลิปจริงในชุดทดสอบ


# ---------- PinnedCommentService ----------


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 1, 9, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


class Counting(FakeExtractor):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.result: dict | None = None
        self.error: YtError | None = None
        self.count = 0

    def pinned_comment(self, video_id: str) -> dict | None:
        self.count += 1
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture
def env(tmp_path: Path):
    db = Database(tmp_path / "app.db")
    db.migrate()
    clock = Clock()
    ext = Counting(FIXTURES)
    videos = VideoService(db, ext, now=clock)
    svc = PinnedCommentService(videos, ext.pinned_comment, tmp_path / "cache", now=clock)
    yield svc, ext, clock, tmp_path / "cache"
    db.close()


def test_found_comment_is_cached_on_disk_for_24_hours(env) -> None:
    svc, ext, clock, cache = env
    ext.result = {**UPLOADER_PIN, "text": "หนึ่ง", "likes": 3, "byUploader": True, "author": "x", "authorId": "UC1"}
    assert svc.get(THAI) == {"text": "หนึ่ง", "likes": 3, "byUploader": True}  # ฟิลด์อื่นถูกทิ้ง
    doc = json.loads((cache / THAI / CACHE_FILE).read_text(encoding="utf-8"))
    assert doc["comment"] == {"text": "หนึ่ง", "likes": 3, "byUploader": True} and doc["videoId"] == THAI
    assert doc["v"] == CACHE_VERSION == 2
    ext.result = {"text": "สอง"}
    clock.now += timedelta(hours=23)
    assert svc.get(THAI) == {"text": "หนึ่ง", "likes": 3, "byUploader": True}
    assert ext.count == 1
    clock.now += timedelta(hours=1)
    assert svc.get(THAI) == {"text": "สอง", "byUploader": False}
    assert ext.count == 2


def test_none_is_cached_too(env) -> None:
    svc, ext, clock, _ = env
    assert svc.get(BBB) is None
    assert svc.get(BBB) is None
    assert ext.count == 1


def test_zero_comments_skips_the_network(env) -> None:
    svc, ext, _, cache = env
    ext.result = {"text": "ไม่ควรถูกดึง"}
    assert svc.get(NO_COMMENTS) is None
    assert ext.count == 0
    assert not (cache / NO_COMMENTS / CACHE_FILE).exists()


def test_errors_are_remembered_for_five_minutes(env) -> None:
    svc, ext, clock, cache = env
    ext.error = YtError("E_BOT_CHECK", "HTTP Error 429")
    for _ in range(3):
        with pytest.raises(YtError) as exc:
            svc.get(THAI)
        assert exc.value.code == "E_BOT_CHECK" and exc.value.detail == "HTTP Error 429"
    assert ext.count == 1
    assert not (cache / THAI / CACHE_FILE).exists()
    clock.now += timedelta(minutes=5)
    ext.error = None
    ext.result = {"text": "กลับมาแล้ว"}
    assert svc.get(THAI) == {"text": "กลับมาแล้ว", "byUploader": False}
    assert ext.count == 2


@pytest.mark.parametrize("code", ["E_NETWORK", "E_UNKNOWN"])
def test_retryable_errors_are_not_remembered(env, code: str) -> None:
    # review I-1: ปุ่ม "ลองใหม่" ต้องดึงใหม่จริง (error ที่ลองแล้วช่วยได้ไม่จำ)
    svc, ext, _, _ = env
    ext.error = YtError(code, "x")
    for _ in range(2):
        with pytest.raises(YtError) as exc:
            svc.get(THAI)
        assert exc.value.code == code
    assert ext.count == 2
    ext.error = None
    ext.result = {"text": "ได้แล้ว"}
    assert svc.get(THAI) == {"text": "ได้แล้ว", "byUploader": False}
    assert ext.count == 3


def test_expired_errors_are_pruned(env) -> None:
    # review M-7: error ที่หมดอายุของทุกคลิปถูกล้างทิ้ง ไม่สะสมในหน่วยความจำ
    svc, ext, clock, _ = env
    ext.error = YtError("E_BOT_CHECK", "x")
    for video in (THAI, BBB):
        with pytest.raises(YtError):
            svc.get(video)
    assert set(svc._errors) == {THAI, BBB}
    clock.now += timedelta(minutes=5)
    ext.error = None
    svc.get(ZOO)
    assert svc._errors == {}


def test_clock_going_back_does_not_keep_an_error_forever(env) -> None:
    svc, ext, clock, _ = env
    ext.error = YtError("E_BOT_CHECK", "x")
    with pytest.raises(YtError):
        svc.get(THAI)
    clock.now -= timedelta(minutes=1)
    ext.error = None
    assert svc.get(THAI) is None
    assert ext.count == 2


def test_video_errors_are_not_cached_and_do_not_fetch(env) -> None:
    svc, ext, _, _ = env
    for _ in range(2):
        with pytest.raises(YtError) as exc:
            svc.get("PRIVATEVID1")
        assert exc.value.code == "E_VIDEO_PRIVATE"
    assert ext.count == 0


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        json.dumps({"v": 2, "videoId": "aqz-ke-bpkq", "fetchedAt": "2026-10-01T09:00:00+00:00", "comment": None}),
        json.dumps({"v": 1, "videoId": BBB, "fetchedAt": "2026-10-01T09:00:00+00:00", "comment": None}),  # รุ่นเก่า (กรองเฉพาะเจ้าของช่อง)
        json.dumps({"v": 99, "videoId": BBB, "fetchedAt": "2026-10-01T09:00:00+00:00", "comment": None}),
        json.dumps({"v": 2, "videoId": BBB, "fetchedAt": "yesterday", "comment": None}),
        json.dumps({"v": 2, "videoId": BBB, "comment": None}),
        json.dumps({"v": 2, "videoId": BBB, "fetchedAt": "2026-10-01T09:30:00+00:00", "comment": None}),
        json.dumps({"v": 2, "videoId": BBB, "fetchedAt": "2026-10-01T09:00:00+00:00", "comment": {"text": ""}}),
        json.dumps([1, 2]),
    ],
)
def test_bad_or_foreign_cache_files_are_refetched(env, content: str) -> None:
    svc, ext, _, cache = env
    (cache / BBB).mkdir(parents=True)
    (cache / BBB / CACHE_FILE).write_text(content, encoding="utf-8")
    ext.result = {"text": "ใหม่"}
    assert svc.get(BBB) == {"text": "ใหม่", "byUploader": False}
    assert ext.count == 1


def test_v1_cache_with_a_comment_is_a_miss_and_refetched_as_v2(env) -> None:
    """ไฟล์ที่เขียนด้วยกฎเก่า (เฉพาะเจ้าของช่อง) ห้ามเชื่อ: คลิปแบบ WUKONG ดึงใหม่หนึ่งครั้งแล้วได้ปักหมุดของผู้ชม"""
    svc, ext, _, cache = env
    (cache / THAI).mkdir(parents=True)
    old = {"v": 1, "videoId": THAI, "fetchedAt": "2026-10-01T09:00:00+00:00", "comment": None}
    (cache / THAI / CACHE_FILE).write_text(json.dumps(old), encoding="utf-8")
    ext.result = {"text": "ผู้ชมปักหมุด", "byUploader": False}
    assert svc.get(THAI) == {"text": "ผู้ชมปักหมุด", "byUploader": False}
    assert ext.count == 1
    assert json.loads((cache / THAI / CACHE_FILE).read_text(encoding="utf-8"))["v"] == 2
    assert svc.get(THAI) == {"text": "ผู้ชมปักหมุด", "byUploader": False}
    assert ext.count == 1  # v2 อ่านจาก cache ได้


def test_by_uploader_survives_a_cache_read(env) -> None:
    svc, ext, _, _ = env
    ext.result = {"text": "ของเจ้าของ", "byUploader": True}
    assert svc.get(THAI) == {"text": "ของเจ้าของ", "byUploader": True}
    ext.result = None
    assert svc.get(THAI) == {"text": "ของเจ้าของ", "byUploader": True}  # จาก cache
    assert ext.count == 1


def test_naive_timestamp_in_cache_counts_as_utc(env) -> None:
    svc, ext, _, cache = env
    (cache / BBB).mkdir(parents=True)
    doc = {"v": 2, "videoId": BBB, "fetchedAt": "2026-10-01T08:00:00", "comment": {"text": "เก่า", "x": 1}}
    (cache / BBB / CACHE_FILE).write_text(json.dumps(doc), encoding="utf-8")
    assert svc.get(BBB) == {"text": "เก่า", "byUploader": False}
    assert ext.count == 0


def test_cache_write_failure_still_answers(env, monkeypatch: pytest.MonkeyPatch, caplog) -> None:
    svc, ext, _, _ = env

    def broken(target: Path, data: bytes) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(comments_mod, "_atomic_write", broken)
    ext.result = {"text": "ยังได้"}
    assert svc.get(THAI) == {"text": "ยังได้", "byUploader": False}
    assert "cache" in caplog.text


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            {"text": "a", "likes": 0, "publishedText": " now ", "byUploader": True},
            {"text": "a", "likes": 0, "publishedText": "now", "byUploader": True},
        ),
        ({"text": "a", "likes": "3", "publishedText": 5}, {"text": "a", "byUploader": False}),
        ({"text": "a", "byUploader": "yes", "author": "x"}, {"text": "a", "byUploader": False}),
        ({"text": " "}, None),
        ("text", None),
    ],
)
def test_clean_comment(value: object, expected: object) -> None:
    assert clean_comment(value) == expected
