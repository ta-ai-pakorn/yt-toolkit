from __future__ import annotations

import copy
import json
import re
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from yttoolkit.core.db import Database, purge_stale_cache
from yttoolkit.core.extractor import FakeExtractor
from yttoolkit.core.videos import VideoService, to_video_info
from yttoolkit.core.yterrors import YtError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SRC = Path(__file__).resolve().parents[2] / "src" / "yttoolkit"
BBB = "aqz-KE-bpKQ"
ZOO = "jNQXAC9IVRw"
PLAYLIST = "PLfakeplaylist250"
T0 = datetime(2026, 9, 29, 12, 0, 0, tzinfo=UTC)


def stamp(value: datetime) -> str:
    return value.isoformat(timespec="microseconds")


def load(name: str) -> dict:
    return json.loads((FIXTURES / "probe" / f"{name}.json").read_text(encoding="utf-8"))


class Clock:
    def __init__(self, start: datetime = T0) -> None:
        self.current = start

    def __call__(self) -> datetime:
        return self.current

    def advance(self, **kwargs: float) -> None:
        self.current += timedelta(**kwargs)


class CountingExtractor:
    """ห่อ FakeExtractor แล้วนับจำนวนครั้งที่เรียก probe/playlist"""

    def __init__(self) -> None:
        self.inner = FakeExtractor(FIXTURES)
        self.count = {"probe": 0, "playlist": 0}

    def probe(self, video_id: str) -> dict:
        self.count["probe"] += 1
        return self.inner.probe(video_id)

    def playlist(self, playlist_id: str, limit: int) -> dict:
        self.count["playlist"] += 1
        return self.inner.playlist(playlist_id, limit)

    def fetch(self, url: str) -> bytes:
        return self.inner.fetch(url)


class StubPlaylist:
    def __init__(self, info: dict) -> None:
        self.info = info

    def probe(self, video_id: str) -> dict:
        raise AssertionError("ไม่ควรเรียก probe")

    def playlist(self, playlist_id: str, limit: int) -> dict:
        return self.info

    def fetch(self, url: str) -> bytes:
        raise AssertionError("ไม่ควรเรียก fetch")


class StubProbe:
    def __init__(self, info: dict) -> None:
        self.info = info

    def probe(self, video_id: str) -> dict:
        return copy.deepcopy(self.info)


@pytest.fixture
def db(tmp_path: Path):
    database = Database(tmp_path / "app.db")
    database.migrate()
    yield database
    database.close()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def ext() -> CountingExtractor:
    return CountingExtractor()


@pytest.fixture
def svc(db: Database, ext: CountingExtractor, clock: Clock) -> VideoService:
    return VideoService(db, ext, now=clock)


# ---------- to_video_info ----------


def test_maps_basic_fields_of_bbb() -> None:
    info = to_video_info(load(BBB))
    assert info["videoId"] == BBB
    assert info["title"].startswith("Big Buck Bunny")
    assert info["channel"] == "Blender"
    assert info["durationS"] == 635
    assert info["publishedAt"] == "2014-11-10"
    assert info["thumbnailUrl"].startswith("https://i.ytimg.com/")
    assert info["chapters"] == []
    assert info["hasStoryboard"] is True
    assert info["isLive"] is False


def test_output_has_exactly_the_prd_keys() -> None:
    info = to_video_info(load(BBB))
    assert set(info) == {
        "videoId", "title", "channel", "durationS", "publishedAt", "thumbnailUrl",
        "chapters", "video", "audio", "hasStoryboard", "isLive",
    }  # fmt: skip
    assert set(info["video"][0]) <= {
        "formatId",
        "height",
        "fps",
        "vcodec",
        "compat",
        "sizeBytes",
    }
    assert set(info["audio"][0]) == {
        "formatId",
        "language",
        "isOriginal",
        "acodec",
        "abrKbps",
    }


def test_chapters_are_mapped_to_camel_case() -> None:
    info = to_video_info(load(ZOO))
    assert info["chapters"] == [
        {"startS": 0, "endS": 5, "title": "Intro"},
        {"startS": 5, "endS": 17, "title": "The cool thing"},
        {"startS": 17, "endS": 19, "title": "End"},
    ]
    assert info["hasStoryboard"] is False


def test_chapter_without_end_time_ends_at_next_start_or_duration() -> None:
    raw = load(ZOO)
    raw["chapters"] = [
        {"start_time": 0, "title": "a"},
        {"start_time": 7.5, "title": "b"},
    ]
    chapters = to_video_info(raw)["chapters"]
    assert chapters[0]["endS"] == 7.5
    assert chapters[1]["endS"] == 19


def test_video_list_sorted_by_height_then_fps_desc() -> None:
    video = to_video_info(load(BBB))["video"]
    keys = [(v["height"], v["fps"]) for v in video]
    assert keys == sorted(keys, reverse=True)
    assert video[0]["height"] == 2160


def test_video_list_has_no_muxed_audio_or_storyboard_formats() -> None:
    ids = {v["formatId"] for v in to_video_info(load(BBB))["video"]}
    assert "18" not in ids  # มีเสียงในตัว
    assert not ids & {"sb0", "sb1", "sb2", "sb3"}


def test_video_list_dedupes_same_height_fps_codec_family_keeping_largest() -> None:
    video = to_video_info(load(BBB))["video"]
    combos = [
        (v["height"], v["fps"], v["vcodec"].split(".")[0].replace("vp09", "vp9"))
        for v in video
    ]
    assert len(combos) == len(set(combos))
    at_144_30_avc = [
        v
        for v in video
        if v["height"] == 144 and v["fps"] == 30 and v["vcodec"].startswith("avc1")
    ]
    assert [v["formatId"] for v in at_144_30_avc] == [
        "160"
    ]  # ตัวที่มีขนาดไฟล์ ชนะตัว 269 ที่ไม่มี
    assert at_144_30_avc[0]["sizeBytes"] == 4323893


def test_compat_is_true_only_for_h264() -> None:
    video = to_video_info(load(BBB))["video"]
    for entry in video:
        assert entry["compat"] is entry["vcodec"].startswith("avc1")
    assert any(e["compat"] for e in video)
    assert any(not e["compat"] for e in video)


def test_size_bytes_falls_back_to_approx_and_is_omitted_when_unknown() -> None:
    raw = {
        "id": BBB,
        "title": "t",
        "formats": [
            {
                "format_id": "a",
                "vcodec": "avc1.x",
                "acodec": "none",
                "height": 720,
                "fps": 30,
                "filesize_approx": 99,
            },
            {
                "format_id": "b",
                "vcodec": "vp9",
                "acodec": "none",
                "height": 720,
                "fps": 30,
            },
        ],
    }
    by_id = {v["formatId"]: v for v in to_video_info(raw)["video"]}
    assert by_id["a"]["sizeBytes"] == 99
    assert "sizeBytes" not in by_id["b"]


def test_fps_none_does_not_crash_and_sorts_last() -> None:
    raw = {
        "id": BBB,
        "title": "t",
        "formats": [
            {
                "format_id": "a",
                "vcodec": "avc1.x",
                "acodec": "none",
                "height": 720,
                "fps": None,
            },
            {
                "format_id": "b",
                "vcodec": "vp9",
                "acodec": "none",
                "height": 720,
                "fps": 30.0,
            },
        ],
    }
    video = to_video_info(raw)["video"]
    assert [v["formatId"] for v in video] == ["b", "a"]
    assert video[0]["fps"] == 30
    assert video[1]["fps"] == 0


def test_audio_drops_drc_variants() -> None:
    ids = {a["formatId"] for a in to_video_info(load(BBB))["audio"]}
    assert not any(i.endswith("-drc") for i in ids)
    assert {"139", "140", "249", "250", "251"} <= ids


def test_audio_language_stays_none_when_unknown() -> None:
    assert all(a["language"] is None for a in to_video_info(load(BBB))["audio"])


def test_audio_abr_is_rounded_and_acodec_present() -> None:
    by_id = {a["formatId"]: a for a in to_video_info(load(BBB))["audio"]}
    assert by_id["140"]["acodec"] == "mp4a.40.2"
    assert by_id["140"]["abrKbps"] == 129
    assert by_id["233"]["acodec"] == "unknown"  # ไม่มี acodec ในข้อมูลดิบ
    assert by_id["233"]["abrKbps"] is None


def _audio_raw(*fmts: dict) -> dict:
    return {
        "id": BBB,
        "title": "t",
        "formats": [
            {"vcodec": "none", "acodec": "opus", "abr": 100, **f} for f in fmts
        ],
    }


def _flags(raw: dict) -> dict[str, bool]:
    return {a["formatId"]: a["isOriginal"] for a in to_video_info(raw)["audio"]}


def test_is_original_from_format_note_original_or_default() -> None:
    raw = _audio_raw(
        {
            "format_id": "a",
            "format_note": "English (US) original, medium",
            "language": "en",
        },
        {"format_id": "b", "format_note": "Thai, medium", "language": "th"},
        {"format_id": "c", "format_note": "Default, low"},
    )
    assert _flags(raw) == {"a": True, "b": False, "c": True}


def test_is_original_is_case_insensitive() -> None:
    raw = _audio_raw(
        {"format_id": "a", "format_note": "ORIGINAL"},
        {"format_id": "b", "format_note": "dub"},
    )
    assert _flags(raw) == {"a": True, "b": False}


def test_is_original_falls_back_to_highest_language_preference_when_it_differs() -> (
    None
):
    raw = _audio_raw(
        {
            "format_id": "a",
            "format_note": "medium",
            "language": "en",
            "language_preference": 10,
        },
        {
            "format_id": "b",
            "format_note": "medium",
            "language": "th",
            "language_preference": -1,
        },
        {
            "format_id": "c",
            "format_note": "low",
            "language": "en",
            "language_preference": 10,
        },
    )
    assert _flags(raw) == {"a": True, "b": False, "c": True}


def test_is_original_all_false_when_inconclusive() -> None:
    same = _audio_raw(
        {"format_id": "a", "format_note": "low", "language_preference": -1},
        {"format_id": "b", "format_note": "medium", "language_preference": -1},
    )
    assert _flags(same) == {"a": False, "b": False}
    missing = _audio_raw(
        {"format_id": "a", "format_note": "low"},
        {"format_id": "b", "format_note": "medium"},
    )
    assert _flags(missing) == {"a": False, "b": False}


def test_drc_variants_are_ignored_even_when_note_says_default() -> None:
    raw = _audio_raw(
        {"format_id": "a-drc", "format_note": "Default, DRC"},
        {"format_id": "b", "format_note": "medium"},
    )
    assert _flags(raw) == {"b": False}


def test_live_status_only_is_live_counts_as_live() -> None:
    raw = load(ZOO)
    for status, expected in [
        ("is_live", True),
        ("was_live", False),
        ("post_live", False),
        ("not_live", False),
    ]:
        raw["live_status"] = status
        assert to_video_info(raw)["isLive"] is expected


def test_duration_float_and_missing_fields() -> None:
    raw = {
        "id": BBB,
        "title": "t",
        "duration": 12.6,
        "uploader": "someone",
        "timestamp": 1415628355,
    }
    info = to_video_info(raw)
    assert info["durationS"] == 13
    assert isinstance(info["durationS"], int)
    assert info["channel"] == "someone"
    assert info["publishedAt"] == "2014-11-10"
    assert info["video"] == [] and info["audio"] == [] and info["chapters"] == []
    assert info["hasStoryboard"] is False


def test_published_at_omitted_without_date() -> None:
    assert "publishedAt" not in to_video_info({"id": BBB, "title": "t"})


def test_thumbnail_falls_back_to_thumbnails_list() -> None:
    raw = {
        "id": BBB,
        "title": "t",
        "thumbnails": [{"url": "https://x/a.jpg"}, {"url": "https://x/b.jpg"}],
    }
    assert to_video_info(raw)["thumbnailUrl"] == "https://x/b.jpg"


def test_mapping_does_not_mutate_input() -> None:
    raw = load(BBB)
    before = copy.deepcopy(raw)
    to_video_info(raw)
    assert raw == before


# ---------- VideoService.get ----------


def test_get_probes_maps_and_stores_row(
    svc: VideoService, ext: CountingExtractor, db: Database
) -> None:
    info = svc.get(BBB)
    assert info == to_video_info(load(BBB))
    assert ext.count["probe"] == 1
    row = db.execute("SELECT * FROM videos WHERE video_id = ?", (BBB,))[0]
    assert row["title"] == info["title"]
    assert row["channel"] == "Blender"
    assert row["duration_s"] == 635
    assert row["thumbnail_url"] == info["thumbnailUrl"]
    assert json.loads(row["chapters_json"]) == []
    assert row["probed_at"] == row["opened_at"] == stamp(T0)


def test_chapters_json_uses_prd_keys(svc: VideoService, db: Database) -> None:
    svc.get(ZOO)
    row = db.execute("SELECT chapters_json FROM videos WHERE video_id = ?", (ZOO,))[0]
    assert json.loads(row["chapters_json"])[0] == {
        "start_s": 0,
        "end_s": 5,
        "title": "Intro",
    }


def test_cache_hit_within_24h_makes_no_extractor_call(
    svc: VideoService, ext: CountingExtractor, clock: Clock
) -> None:
    first = svc.get(BBB)
    clock.advance(hours=23, minutes=59)
    second = svc.get(BBB)
    assert ext.count["probe"] == 1
    assert second == first


def test_cache_expires_after_24h(
    svc: VideoService, ext: CountingExtractor, clock: Clock
) -> None:
    svc.get(BBB)
    clock.advance(hours=25)
    svc.get(BBB)
    assert ext.count["probe"] == 2


def test_refresh_forces_a_probe(svc: VideoService, ext: CountingExtractor) -> None:
    svc.get(BBB)
    svc.get(BBB, refresh=True)
    assert ext.count["probe"] == 2


def test_future_probed_at_is_treated_as_stale(
    svc: VideoService, ext: CountingExtractor, clock: Clock
) -> None:
    clock.current = T0 + timedelta(days=3)
    svc.get(BBB)
    clock.current = T0  # นาฬิกาถอยหลัง
    svc.get(BBB)
    assert ext.count["probe"] == 2


def test_opened_at_updates_on_cache_hit_but_probed_at_does_not(
    svc: VideoService, clock: Clock, db: Database
) -> None:
    svc.get(BBB)
    clock.advance(hours=2)
    svc.get(BBB)
    row = db.execute(
        "SELECT probed_at, opened_at FROM videos WHERE video_id = ?", (BBB,)
    )[0]
    assert row["probed_at"] == stamp(T0)
    assert row["opened_at"] == stamp(T0 + timedelta(hours=2))


def test_reprobe_keeps_single_row_and_does_not_break_jobs_reference(
    svc: VideoService, clock: Clock, db: Database
) -> None:
    svc.get(BBB)
    db.execute(
        "INSERT INTO jobs (id, video_id, kind, params_json, status, position, created_at) "
        "VALUES ('j1', ?, 'video', '{}', 'queued', 1, ?)",
        (BBB, T0.isoformat()),
    )
    clock.advance(hours=30)
    svc.get(BBB)
    assert len(db.execute("SELECT 1 FROM videos")) == 1
    assert len(db.execute("SELECT 1 FROM jobs")) == 1


def test_stored_times_are_parseable_by_purge_stale_cache(
    svc: VideoService, clock: Clock, db: Database, tmp_path: Path
) -> None:
    svc.get(BBB)
    (tmp_path / "cache").mkdir()
    assert (
        purge_stale_cache(db, tmp_path / "cache", clock.current + timedelta(days=31))
        == 1
    )
    svc.get(ZOO)
    assert (
        purge_stale_cache(db, tmp_path / "cache", clock.current + timedelta(days=1))
        == 0
    )


def test_stored_times_are_utc_with_offset_even_for_other_timezone(
    db: Database, ext: CountingExtractor
) -> None:
    bangkok = timezone(timedelta(hours=7))
    service = VideoService(
        db, ext, now=lambda: datetime(2026, 9, 29, 19, 0, tzinfo=bangkok)
    )
    service.get(BBB)
    row = db.execute("SELECT probed_at FROM videos")[0]
    assert row["probed_at"].endswith("+00:00")
    assert datetime.fromisoformat(row["probed_at"]) == T0


def test_live_upcoming_raises_and_stores_nothing(
    svc: VideoService, db: Database
) -> None:
    with pytest.raises(YtError) as exc:
        svc.get("UPCOMINGLV1")
    assert exc.value.code == "E_LIVE_NOT_READY"
    assert db.execute("SELECT 1 FROM videos") == []


def test_private_video_error_propagates(svc: VideoService) -> None:
    with pytest.raises(YtError) as exc:
        svc.get("PRIVATEVID1")
    assert exc.value.code == "E_VIDEO_PRIVATE"


def test_error_on_refresh_keeps_old_row(
    svc: VideoService, db: Database, ext: CountingExtractor
) -> None:
    svc.get(BBB)

    def boom(video_id: str) -> dict:
        raise YtError("E_NETWORK", "down")

    ext.probe = boom  # type: ignore[method-assign]
    with pytest.raises(YtError):
        svc.get(BBB, refresh=True)
    assert len(db.execute("SELECT 1 FROM videos")) == 1


@pytest.mark.parametrize(
    "bad", ["short", "way-too-long-id", "bad id 1234", "", "../../etc/pw"]
)
def test_get_rejects_invalid_video_id_without_probing(
    svc: VideoService, ext: CountingExtractor, bad: str
) -> None:
    with pytest.raises(YtError) as exc:
        svc.get(bad)
    assert exc.value.code == "E_INVALID_INPUT"
    assert ext.count["probe"] == 0


def test_corrupt_cached_probe_json_is_reprobed(
    svc: VideoService, ext: CountingExtractor, db: Database
) -> None:
    svc.get(BBB)
    db.execute("UPDATE videos SET probe_json = 'not json'")
    assert svc.get(BBB)["videoId"] == BBB
    assert ext.count["probe"] == 2


# ---------- probe_json / raw ----------


def test_probe_json_is_trimmed_but_keeps_storyboard_and_mapping_fields(
    svc: VideoService, db: Database
) -> None:
    svc.get(BBB)
    stored = db.execute("SELECT probe_json FROM videos")[0]["probe_json"]
    data = json.loads(stored)
    sb = [f for f in data["formats"] if f.get("format_note") == "storyboard"]
    assert {f["format_id"] for f in sb} == {"sb0", "sb1", "sb2", "sb3"}
    sb0 = next(f for f in sb if f["format_id"] == "sb0")
    assert (sb0["rows"], sb0["columns"], sb0["width"], sb0["height"]) == (
        3,
        3,
        320,
        180,
    )
    assert sb0["fps"] == pytest.approx(0.2015748031)
    assert len(sb0["fragments"]) == 15
    assert set(sb0["fragments"][0]) == {"url", "duration"}
    assert data["duration"] == 635
    assert data["id"] == BBB
    assert "manifest_url" not in data
    assert all(
        "url" not in f for f in data["formats"] if f.get("format_note") != "storyboard"
    )


def test_trim_drops_urls_and_unused_fields_but_keeps_storyboard(db: Database) -> None:
    raw = load(BBB)
    raw["manifest_url"] = "https://manifest.googlevideo.com/x"
    raw["description"] = "long text " * 500
    raw["automatic_captions"] = {
        "th": [{"url": "https://www.youtube.com/api/timedtext?x"}]
    }
    for fmt in raw["formats"]:
        if fmt.get("format_note") != "storyboard":
            fmt["url"] = "https://rr1.googlevideo.com/videoplayback?x"
            fmt["http_headers"] = {"User-Agent": "x" * 200}
    stub = StubProbe(raw)
    VideoService(db, stub).get(BBB)  # type: ignore[arg-type]
    stored = db.execute("SELECT probe_json FROM videos")[0]["probe_json"]
    assert "googlevideo" not in stored
    assert (
        "long text" not in stored
        and "timedtext" not in stored
        and "User-Agent" not in stored
    )
    assert len(stored) < len(json.dumps(raw)) / 2
    assert '"fragments"' in stored


def test_trimmed_raw_maps_to_the_same_video_info(svc: VideoService) -> None:
    for vid in (BBB, ZOO):
        assert to_video_info(svc.raw(vid)) == to_video_info(load(vid))


def test_raw_returns_stored_without_probing_again(
    svc: VideoService, ext: CountingExtractor
) -> None:
    svc.get(BBB)
    raw = svc.raw(BBB)
    assert raw["id"] == BBB
    assert ext.count["probe"] == 1


def test_raw_probes_when_nothing_cached(
    svc: VideoService, ext: CountingExtractor
) -> None:
    raw = svc.raw(ZOO)
    assert raw["id"] == ZOO
    assert ext.count["probe"] == 1


def test_raw_rejects_invalid_id(svc: VideoService) -> None:
    with pytest.raises(YtError) as exc:
        svc.raw("nope")
    assert exc.value.code == "E_INVALID_INPUT"


# ---------- recent ----------


def test_recent_orders_by_opened_at_desc_with_expected_fields(
    svc: VideoService, clock: Clock
) -> None:
    svc.get(BBB)
    clock.advance(minutes=5)
    svc.get(ZOO)
    items, total = svc.recent(10)
    assert total == 2
    assert [i["videoId"] for i in items] == [ZOO, BBB]
    assert items[0] == {
        "videoId": ZOO,
        "title": "Me at the zoo",
        "thumbnailUrl": "https://i.ytimg.com/vi/jNQXAC9IVRw/hqdefault.jpg",
        "durationS": 19,
        "outputs": [],
        "lastAt": stamp(T0 + timedelta(minutes=5)),
    }


def test_reopening_moves_video_to_top(svc: VideoService, clock: Clock) -> None:
    svc.get(BBB)
    clock.advance(minutes=1)
    svc.get(ZOO)
    clock.advance(minutes=1)
    svc.get(BBB)
    assert [i["videoId"] for i in svc.recent(10)[0]] == [BBB, ZOO]


def test_recent_paging(svc: VideoService, clock: Clock) -> None:
    svc.get(BBB)
    clock.advance(minutes=1)
    svc.get(ZOO)
    items, total = svc.recent(1, offset=1)
    assert total == 2
    assert [i["videoId"] for i in items] == [BBB]
    assert svc.recent(5, offset=5) == ([], 2)


def test_recent_search_filters_on_title_case_insensitive(
    svc: VideoService, clock: Clock
) -> None:
    svc.get(BBB)
    clock.advance(minutes=1)
    svc.get(ZOO)
    items, total = svc.recent(10, q="bunny")
    assert total == 1
    assert [i["videoId"] for i in items] == [BBB]
    assert svc.recent(10, q="zzz-nothing") == ([], 0)


def test_recent_search_treats_like_wildcards_literally(svc: VideoService) -> None:
    svc.get(BBB)
    assert svc.recent(10, q="%") == ([], 0)
    assert svc.recent(10, q="_") == ([], 0)


def test_recent_empty(svc: VideoService) -> None:
    assert svc.recent(10) == ([], 0)


# ---------- playlist ----------


def test_playlist_truncated_at_200_of_250(
    svc: VideoService, ext: CountingExtractor
) -> None:
    result = svc.playlist(PLAYLIST)
    assert set(result) == {"title", "total", "truncated", "entries"}
    assert result["truncated"] is True
    assert result["total"] == 250
    assert len(result["entries"]) == 200
    assert result["entries"][0]["videoId"] == "fake0000001"
    assert set(result["entries"][0]) == {
        "videoId",
        "title",
        "durationS",
        "thumbnailUrl",
    }
    assert result["entries"][0]["durationS"] == 61
    assert (
        result["entries"][0]["thumbnailUrl"]
        == "https://fake.invalid/thumb/fake0000001.jpg"
    )
    assert ext.count["playlist"] == 1


def test_playlist_under_limit_is_not_truncated(svc: VideoService) -> None:
    result = svc.playlist(PLAYLIST, limit=250)
    assert result["truncated"] is False
    assert len(result["entries"]) == 250


def test_playlist_custom_limit(svc: VideoService) -> None:
    result = svc.playlist(PLAYLIST, limit=5)
    assert len(result["entries"]) == 5
    assert result["truncated"] is True


def test_playlist_total_falls_back_to_returned_count(db: Database) -> None:
    stub = StubPlaylist(
        {
            "title": "p",
            "entries": [
                {"id": "abcdefghijk", "title": "a"},
                {"id": "bcdefghijkl", "title": "b"},
            ],
        }
    )
    result = VideoService(db, stub).playlist("PLabcdefghij")
    assert result["total"] == 2
    assert result["truncated"] is False
    assert result["entries"][0]["durationS"] == 0
    assert (
        result["entries"][0]["thumbnailUrl"]
        == "https://i.ytimg.com/vi/abcdefghijk/mqdefault.jpg"
    )


def test_playlist_skips_entries_without_valid_id(db: Database) -> None:
    stub = StubPlaylist(
        {
            "title": "p",
            "entries": [
                {"id": None, "title": "x"},
                {"title": "y"},
                {"id": "abcdefghijk", "title": "ok", "duration": 3.4},
            ],
        }
    )
    result = VideoService(db, stub).playlist("PLabcdefghij")
    assert [e["videoId"] for e in result["entries"]] == ["abcdefghijk"]
    assert result["entries"][0]["durationS"] == 3


@pytest.mark.parametrize("bad", ["short", "has space here", "", "a/b/c/d/e/f/g/h"])
def test_playlist_rejects_invalid_id(
    svc: VideoService, ext: CountingExtractor, bad: str
) -> None:
    with pytest.raises(YtError) as exc:
        svc.playlist(bad)
    assert exc.value.code == "E_INVALID_INPUT"
    assert ext.count["playlist"] == 0


def test_playlist_unavailable_propagates(svc: VideoService) -> None:
    with pytest.raises(YtError) as exc:
        svc.playlist("PLdoesnotexist1")
    assert exc.value.code == "E_VIDEO_UNAVAILABLE"


# ---------- layering ----------


def test_videos_module_respects_core_boundaries() -> None:
    text = (SRC / "core" / "videos.py").read_text(encoding="utf-8")
    assert not re.search(r"^\s*(from|import)\s+yt_dlp", text, re.MULTILINE)
    assert not re.search(r"yttoolkit\.(api|platform)|from\s+\.\.(api|platform)", text)
