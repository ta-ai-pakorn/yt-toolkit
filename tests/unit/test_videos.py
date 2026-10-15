from __future__ import annotations

import copy
import json
import re
import threading
import time
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from yttoolkit.core.db import PEEK_SENTINEL, Database, purge_stale_cache
from yttoolkit.core.extractor import FakeExtractor
from yttoolkit.core.videos import PROBE_VERSION, VideoService, to_video_info, trim_probe
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

    def playlist(self, playlist_id: str, limit: int, video_id: str | None = None) -> dict:
        self.count["playlist"] += 1
        self.last_video_id = video_id
        return self.inner.playlist(playlist_id, limit, video_id=video_id)

    def fetch(self, url: str) -> bytes:
        return self.inner.fetch(url)


class StubPlaylist:
    def __init__(self, info: dict) -> None:
        self.info = info

    def probe(self, video_id: str) -> dict:
        raise AssertionError("ไม่ควรเรียก probe")

    def playlist(self, playlist_id: str, limit: int, video_id: str | None = None) -> dict:
        self.calls = [*getattr(self, "calls", []), (playlist_id, limit, video_id)]
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
    assert info["description"] == load(BBB)["description"]
    assert info["description"].startswith("UHD High Frame rate version")


def test_description_is_kept_raw_and_omitted_when_blank() -> None:
    raw = {"id": BBB, "title": "t", "description": "  line one\n\nline two  "}
    assert to_video_info(raw)["description"] == "  line one\n\nline two  "
    for blank in ("", "  \n\t ", None, 0):
        raw["description"] = blank
        assert "description" not in to_video_info(raw)
    del raw["description"]
    assert "description" not in to_video_info(raw)


def test_output_has_exactly_the_prd_keys() -> None:
    info = to_video_info(load(BBB))
    assert set(info) == {
        "videoId", "title", "channel", "durationS", "publishedAt", "thumbnailUrl",
        "chapters", "video", "audio", "hasStoryboard", "isLive", "description",
        "stats", "tags", "categories", "mostReplayed",
    }  # fmt: skip
    assert set(info["video"][0]) <= {
        "formatId",
        "width",  # M4 gate 2: หน้าเว็บนับความละเอียดที่ด้านสั้น (คลิปแนวตั้ง 1080x1920 = 1080p)
        "height",
        "fps",
        "vcodec",
        "compat",
        "sizeBytes",
    }
    assert {"formatId", "isOriginal", "acodec"} <= set(info["audio"][0])
    assert set(info["audio"][0]) <= {
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


def test_video_width_is_kept_for_short_side_resolution() -> None:
    """width ผ่าน trim_probe ถึง VideoInfo (หน้าเว็บนับความละเอียดที่ด้านสั้น) format ที่ไม่บอก width = ไม่มีคีย์"""
    raw = load(BBB)
    for info in (to_video_info(raw), to_video_info(trim_probe(raw))):
        by_id = {e["formatId"]: e for e in info["video"]}
        assert by_id["299"]["width"] == 1920 and by_id["299"]["height"] == 1080
    raw = copy.deepcopy(raw)
    for fmt in raw["formats"]:
        fmt.pop("width", None)
    assert all("width" not in e for e in to_video_info(raw)["video"])


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


def test_audio_optional_keys_are_omitted_when_unknown() -> None:
    audio = to_video_info(load(BBB))["audio"]
    assert audio
    assert all("language" not in a for a in audio)  # ไม่มีภาษา = ไม่มีคีย์ ไม่ใช่ null
    raw = _audio_raw(
        {"format_id": "a", "language": "th", "abr": 0},
        {"format_id": "b", "abr": None},
    )
    by_id = {a["formatId"]: a for a in to_video_info(raw)["audio"]}
    assert by_id["a"]["language"] == "th"
    assert "abrKbps" not in by_id["a"] and "abrKbps" not in by_id["b"]
    assert "language" not in by_id["b"]
    assert not any(v is None for a in audio for v in a.values())


def test_audio_abr_is_rounded_and_acodec_present() -> None:
    by_id = {a["formatId"]: a for a in to_video_info(load(BBB))["audio"]}
    assert by_id["140"]["acodec"] == "mp4a.40.2"
    assert by_id["140"]["abrKbps"] == 129


def test_audio_without_acodec_is_skipped_so_it_cannot_win_is_original() -> None:
    audio = to_video_info(load(BBB))["audio"]
    ids = {a["formatId"] for a in audio}
    assert not ids & {"233", "234"}  # "Default, low/high" ที่ไม่มี acodec/abr
    assert all(a["acodec"] != "unknown" for a in audio)
    assert ids == {"139", "140", "249", "250", "251"}
    # จากรูปแบบที่เล่นได้จริง: ไม่มีคำว่า original/default และ language_preference เท่ากันหมด
    assert all(a["isOriginal"] is False for a in audio)


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


def test_probed_at_slightly_in_the_future_is_fresh(
    svc: VideoService, ext: CountingExtractor, clock: Clock
) -> None:
    clock.current = T0 + timedelta(minutes=4, seconds=59)
    svc.get(BBB)
    clock.current = T0  # นาฬิกาถอยไม่ถึง 5 นาที
    svc.get(BBB)
    assert ext.count["probe"] == 1


def test_probed_at_more_than_5_minutes_in_the_future_is_stale(
    svc: VideoService, ext: CountingExtractor, clock: Clock
) -> None:
    clock.current = T0 + timedelta(minutes=5, seconds=1)
    svc.get(BBB)
    clock.current = T0
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


# ---------- single-flight ----------


class SlowExtractor(CountingExtractor):
    """probe ช้าพอให้เธรดอื่นเข้ามาซ้ำระหว่างรอ"""

    def __init__(self, delay: float = 0.3) -> None:
        super().__init__()
        self.delay = delay
        self.lock = threading.Lock()

    def probe(self, video_id: str) -> dict:
        with self.lock:
            self.count["probe"] += 1
        time.sleep(self.delay)
        return self.inner.probe(video_id)


def _run_threads(targets: list) -> list:
    results: list = [None] * len(targets)
    errors: list = []
    barrier = threading.Barrier(len(targets))

    def work(i: int) -> None:
        try:
            barrier.wait()
            results[i] = targets[i]()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(len(targets))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not errors
    return results


def test_concurrent_get_for_same_id_probes_once(db: Database, clock: Clock) -> None:
    slow = SlowExtractor()
    service = VideoService(db, slow, now=clock)
    results = _run_threads([lambda: service.get(BBB)] * 6)
    assert slow.count["probe"] == 1
    assert all(r == results[0] for r in results)
    assert len(db.execute("SELECT 1 FROM videos")) == 1


def test_concurrent_get_for_different_ids_is_not_serialised(
    db: Database, clock: Clock
) -> None:
    slow = SlowExtractor(delay=0.4)
    service = VideoService(db, slow, now=clock)
    started = time.monotonic()
    _run_threads([lambda: service.get(BBB), lambda: service.get(ZOO)])
    assert slow.count["probe"] == 2
    assert time.monotonic() - started < 0.75  # ไม่ได้รอกันแบบต่อคิว


def test_concurrent_refresh_probes_once_more_not_once_per_caller(
    db: Database, clock: Clock
) -> None:
    slow = SlowExtractor()
    service = VideoService(db, slow, now=clock)
    service.get(BBB)
    _run_threads([lambda: service.get(BBB, refresh=True)] * 4)
    assert slow.count["probe"] == 2


def test_failed_probe_releases_the_id_and_next_call_retries(
    db: Database, clock: Clock
) -> None:
    slow = SlowExtractor(delay=0.05)
    service = VideoService(db, slow, now=clock)
    for _ in range(2):
        with pytest.raises(YtError):
            service.get("UPCOMINGLV1")
    assert slow.count["probe"] == 2
    assert service.get(BBB)["videoId"] == BBB


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
    assert "timedtext" not in stored and "User-Agent" not in stored
    assert json.loads(stored)["description"] == raw["description"]
    assert len(stored) < len(json.dumps(raw)) / 2
    assert '"fragments"' in stored


def test_trim_probe_adds_probe_version_description_and_captions() -> None:
    data = trim_probe(load("88o5Sk8_m1Y"))
    assert PROBE_VERSION == 6  # M4 gate 2: เก็บความกว้างของ format วิดีโอ (คลิปแนวตั้ง)
    assert data["probeVersion"] == PROBE_VERSION
    assert data["description"] == load("88o5Sk8_m1Y")["description"]
    assert set(data["captions"]) == {"owner", "original", "translated", "translateFrom"}
    assert [o["key"] for o in data["captions"]["original"]] == ["th-orig"]
    assert "subtitles" not in data and "automatic_captions" not in data
    bbb = trim_probe(load(BBB))
    assert bbb["captions"] == {
        "owner": [],
        "original": [],
        "translated": [],
        "translateFrom": None,
    }


def test_trim_probe_omits_blank_description() -> None:
    raw = load(BBB)
    raw["description"] = "   \n  "
    assert "description" not in trim_probe(raw)


def test_stored_probe_json_has_probe_version_and_captions(
    svc: VideoService, db: Database
) -> None:
    svc.get(ZOO)
    data = json.loads(db.execute("SELECT probe_json FROM videos")[0]["probe_json"])
    assert data["probeVersion"] == PROBE_VERSION
    assert [o["key"] for o in data["captions"]["owner"]] == ["en", "de"]


def _make_old_row(db: Database, video_id: str) -> dict:
    """แถวแบบ M2: ไม่มี probeVersion และ captions"""
    data = json.loads(
        db.execute("SELECT probe_json FROM videos WHERE video_id = ?", (video_id,))[0][
            "probe_json"
        ]
    )
    data.pop("probeVersion")
    data.pop("captions")
    db.execute(
        "UPDATE videos SET probe_json = ? WHERE video_id = ?",
        (json.dumps(data, ensure_ascii=False), video_id),
    )
    return data


def test_row_without_probe_version_is_stale_and_reprobed(
    svc: VideoService, ext: CountingExtractor, db: Database
) -> None:
    svc.get(BBB)
    _make_old_row(db, BBB)
    assert svc.get(BBB)["videoId"] == BBB  # ยังไม่ถึง 24 ชม. แต่ probe ใหม่
    assert ext.count["probe"] == 2
    data = json.loads(db.execute("SELECT probe_json FROM videos")[0]["probe_json"])
    assert data["probeVersion"] == PROBE_VERSION and "captions" in data
    svc.get(BBB)
    assert ext.count["probe"] == 2  # เขียนทับแล้ว ใช้ cache ได้ตามปกติ


def test_row_with_other_probe_version_is_stale(
    svc: VideoService, ext: CountingExtractor, db: Database
) -> None:
    svc.get(BBB)
    data = json.loads(db.execute("SELECT probe_json FROM videos")[0]["probe_json"])
    data["probeVersion"] = PROBE_VERSION + 1
    db.execute("UPDATE videos SET probe_json = ?", (json.dumps(data),))
    svc.get(BBB)
    assert ext.count["probe"] == 2


def test_round_two_row_with_old_most_replayed_is_reprobed(
    svc: VideoService, ext: CountingExtractor, db: Database
) -> None:
    # review M-6: แถวรุ่น 3 เก็บ mostReplayed แบบเก่า (มีที่ราบเตี้ยและช่วงกว้าง) ต้อง probe ใหม่ ไม่ใช้ค่าเดิม
    svc.get(ZOO)
    data = json.loads(db.execute("SELECT probe_json FROM videos")[0]["probe_json"])
    data["probeVersion"] = 3
    data["mostReplayed"] = [{"startMs": 0, "endMs": 190}, {"startMs": 10260, "endMs": 12160}]
    db.execute("UPDATE videos SET probe_json = ?", (json.dumps(data),))
    assert svc.get(ZOO)["mostReplayed"] == [{"startMs": 190, "endMs": 570}]
    assert ext.count["probe"] == 2


def test_round_three_row_without_license_is_reprobed(
    svc: VideoService, ext: CountingExtractor, db: Database
) -> None:
    # M4: แถวรุ่น 4 ไม่มี license / asr / audio_channels ต้อง probe ใหม่ (แบบเดียวกับรุ่นก่อน ๆ)
    svc.get("88o5Sk8_m1Y")
    data = json.loads(db.execute("SELECT probe_json FROM videos")[0]["probe_json"])
    data["probeVersion"] = 4
    data.pop("license")
    db.execute("UPDATE videos SET probe_json = ?", (json.dumps(data),))
    assert svc.get("88o5Sk8_m1Y")["license"] == "Creative Commons Attribution license (reuse allowed)"
    assert ext.count["probe"] == 2
    stored = json.loads(db.execute("SELECT probe_json FROM videos")[0]["probe_json"])
    assert stored["probeVersion"] == PROBE_VERSION and "license" in stored


def test_trim_keeps_license_and_audio_sample_rate_and_channels() -> None:
    raw = load(BBB)
    raw["license"] = "Creative Commons Attribution license (reuse allowed)"
    for fmt in raw["formats"]:
        if fmt.get("format_id") == "140":
            fmt["asr"], fmt["audio_channels"] = 44100, 2
        elif fmt.get("format_id") == "299":
            fmt["asr"], fmt["audio_channels"] = None, None
    data = trim_probe(raw)
    assert data["license"] == raw["license"]
    by_id = {f["format_id"]: f for f in data["formats"] if "format_id" in f}
    assert by_id["140"]["asr"] == 44100 and by_id["140"]["audio_channels"] == 2
    assert "asr" not in by_id["299"] and "audio_channels" not in by_id["299"]
    assert "license" not in trim_probe(load(BBB))


def test_row_without_probe_version_is_still_the_offline_fallback(
    svc: VideoService, ext: CountingExtractor, db: Database
) -> None:
    first = svc.get(BBB)
    _make_old_row(db, BBB)
    _go_offline(ext)
    assert svc.get(BBB) == first  # ยังไม่หมด 24 ชม. ก็ probe ใหม่ พลาดแล้วใช้แถวเดิม
    assert ext.count["probe"] == 2


def test_row_without_probe_version_offline_with_peek(
    svc: VideoService, ext: CountingExtractor, db: Database
) -> None:
    svc.get(BBB)
    _make_old_row(db, BBB)
    _go_offline(ext, "E_BOT_CHECK")
    assert svc.get(BBB, peek=True)["videoId"] == BBB


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
        "channel": "jawed",
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
    assert all("durationS" in e for e in result["entries"])
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
    assert "durationS" not in result["entries"][0]  # ไม่รู้ความยาว = ไม่มีคีย์
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


def test_playlist_thumbnail_prefers_last_of_list_then_single_field_then_default(
    db: Database,
) -> None:
    stub = StubPlaylist(
        {
            "title": "p",
            "entries": [
                {
                    "id": "aaaaaaaaaaa",
                    "thumbnails": [
                        {"url": "https://x/small.jpg"},
                        {"url": "https://x/big.jpg"},
                    ],
                    "thumbnail": "https://x/single.jpg",
                },
                {"id": "bbbbbbbbbbb", "thumbnail": "https://x/single.jpg"},
                {"id": "ccccccccccc", "thumbnails": [], "thumbnail": None},
            ],
        }
    )
    entries = VideoService(db, stub).playlist("PLabcdefghij")["entries"]
    assert [e["thumbnailUrl"] for e in entries] == [
        "https://x/big.jpg",
        "https://x/single.jpg",
        "https://i.ytimg.com/vi/ccccccccccc/mqdefault.jpg",
    ]


def _add_titles(db: Database, titles: list[str]) -> None:
    for index, title in enumerate(titles):
        opened = stamp(T0 + timedelta(minutes=index))
        db.execute(
            "INSERT INTO videos (video_id, title, probe_json, probed_at, opened_at)"
            " VALUES (?, ?, '{}', ?, ?)",
            (f"vid{index:08d}", title, opened, opened),
        )


def test_recent_search_with_paging_reports_filtered_total_and_page(
    svc: VideoService, db: Database
) -> None:
    _add_titles(db, ["cat 1", "dog 1", "cat 2", "cat 3", "dog 2"])
    items, total = svc.recent(2, offset=0, q="cat")
    assert total == 3  # จำนวนที่ตรงคำค้นทั้งหมด ไม่ใช่ขนาดหน้า
    assert [i["title"] for i in items] == ["cat 3", "cat 2"]
    items, total = svc.recent(2, offset=2, q="cat")
    assert total == 3
    assert [i["title"] for i in items] == ["cat 1"]
    assert svc.recent(2, offset=4, q="cat") == ([], 3)


def test_recent_search_with_backslash_is_literal(
    svc: VideoService, db: Database
) -> None:
    _add_titles(db, ["plain title", "path C:\\temp", "50% off", "a_b"])
    items, total = svc.recent(10, q="\\")
    assert (total, [i["title"] for i in items]) == (1, ["path C:\\temp"])
    assert svc.recent(10, q="\\t")[1] == 1
    assert svc.recent(10, q="\\%")[1] == 0
    assert svc.recent(10, q="%")[1] == 1  # "50% off" เท่านั้น
    assert svc.recent(10, q="a_b")[1] == 1


# ---------- peek (ดูชื่อคลิปโดยไม่เข้า "ล่าสุด") ----------


def _opened_at(db: Database, video_id: str) -> str:
    return db.execute("SELECT opened_at FROM videos WHERE video_id = ?", (video_id,))[
        0
    ]["opened_at"]


def test_peek_probe_stores_row_with_sentinel_opened_at_and_stays_out_of_recent(
    svc: VideoService, db: Database, ext: CountingExtractor
) -> None:
    info = svc.get(BBB, peek=True)
    assert info == to_video_info(load(BBB))
    assert ext.count["probe"] == 1
    row = db.execute(
        "SELECT probed_at, opened_at FROM videos WHERE video_id = ?", (BBB,)
    )[0]
    assert row["probed_at"] == stamp(T0)
    assert row["opened_at"] == PEEK_SENTINEL
    assert svc.recent(10) == ([], 0)


def test_peek_cache_hit_does_not_change_opened_at(
    svc: VideoService, db: Database, clock: Clock, ext: CountingExtractor
) -> None:
    svc.get(BBB, peek=True)
    clock.advance(hours=2)
    svc.get(BBB, peek=True)
    assert ext.count["probe"] == 1
    assert _opened_at(db, BBB) == PEEK_SENTINEL
    assert svc.recent(10) == ([], 0)


def test_peek_on_a_video_already_opened_keeps_its_place_in_recent(
    svc: VideoService, db: Database, clock: Clock
) -> None:
    svc.get(BBB)
    opened = _opened_at(db, BBB)
    clock.advance(hours=2)
    svc.get(BBB, peek=True)
    assert _opened_at(db, BBB) == opened
    assert [i["videoId"] for i in svc.recent(10)[0]] == [BBB]


def test_peek_reprobe_after_24h_keeps_opened_at_of_an_opened_video(
    svc: VideoService, db: Database, clock: Clock, ext: CountingExtractor
) -> None:
    svc.get(BBB)
    opened = _opened_at(db, BBB)
    clock.advance(hours=25)
    svc.get(BBB, peek=True)
    assert ext.count["probe"] == 2
    assert _opened_at(db, BBB) == opened
    row = db.execute("SELECT probed_at FROM videos WHERE video_id = ?", (BBB,))[0]
    assert row["probed_at"] == stamp(T0 + timedelta(hours=25))


def test_peek_reprobe_keeps_sentinel_for_a_peek_only_video(
    svc: VideoService, db: Database, clock: Clock
) -> None:
    svc.get(BBB, peek=True)
    clock.advance(hours=25)
    svc.get(BBB, peek=True, refresh=True)
    assert _opened_at(db, BBB) == PEEK_SENTINEL


def test_normal_get_after_peek_moves_video_into_recent(
    svc: VideoService, db: Database, clock: Clock, ext: CountingExtractor
) -> None:
    svc.get(BBB, peek=True)
    clock.advance(minutes=3)
    svc.get(BBB)
    assert ext.count["probe"] == 1  # อ่านจาก cache ไม่ probe ซ้ำ
    assert _opened_at(db, BBB) == stamp(T0 + timedelta(minutes=3))
    items, total = svc.recent(10)
    assert total == 1
    assert [i["videoId"] for i in items] == [BBB]


def test_recent_and_its_total_skip_peek_only_rows(
    svc: VideoService, clock: Clock
) -> None:
    svc.get(BBB, peek=True)
    clock.advance(minutes=1)
    svc.get(ZOO)
    items, total = svc.recent(10)
    assert total == 1
    assert [i["videoId"] for i in items] == [ZOO]
    assert svc.recent(10, q="bunny") == ([], 0)


def test_peek_errors_store_nothing(svc: VideoService, db: Database) -> None:
    with pytest.raises(YtError):
        svc.get("UPCOMINGLV1", peek=True)
    assert db.execute("SELECT 1 FROM videos") == []


def test_peek_rejects_invalid_id_without_probing(
    svc: VideoService, ext: CountingExtractor
) -> None:
    with pytest.raises(YtError):
        svc.get("bad", peek=True)
    assert ext.count["probe"] == 0


def test_concurrent_peeks_for_same_id_probe_once(db: Database, clock: Clock) -> None:
    slow = SlowExtractor()
    service = VideoService(db, slow, now=clock)
    results = _run_threads([lambda: service.get(BBB, peek=True)] * 6)
    assert slow.count["probe"] == 1
    assert all(r == results[0] for r in results)
    assert _opened_at(db, BBB) == PEEK_SENTINEL


def test_concurrent_peek_and_open_probe_once_and_end_up_in_recent(
    db: Database, clock: Clock
) -> None:
    slow = SlowExtractor()
    service = VideoService(db, slow, now=clock)
    _run_threads(
        [lambda: service.get(BBB, peek=True), lambda: service.get(BBB)]
        + [lambda: service.get(BBB, peek=True)] * 2
    )
    assert slow.count["probe"] == 1
    assert [i["videoId"] for i in service.recent(10)[0]] == [BBB]


# ---------- final review: ไม่มีเน็ตแต่ cache เก่ากว่า 24 ชม. ใช้ข้อมูลเดิมไปก่อน ----------


def _go_offline(ext: CountingExtractor, code: str = "E_NETWORK") -> None:
    def down(video_id: str) -> dict:
        ext.count["probe"] += 1
        raise YtError(code, f"ERROR: {code} (offline)")

    ext.probe = down  # type: ignore[method-assign]


@pytest.mark.parametrize("code", ["E_NETWORK", "E_BOT_CHECK"])
def test_stale_cache_is_used_when_reprobe_fails_offline(
    svc: VideoService,
    ext: CountingExtractor,
    clock: Clock,
    db: Database,
    code: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    first = svc.get(BBB)
    clock.advance(hours=30)
    _go_offline(ext, code)
    with caplog.at_level("WARNING", logger="yttoolkit"):
        assert svc.get(BBB) == first
    assert ext.count["probe"] == 2  # ลอง probe ใหม่ก่อนจริง ๆ
    row = db.execute("SELECT probed_at, opened_at FROM videos WHERE video_id = ?", (BBB,))[0]
    assert row["probed_at"] == stamp(T0)  # ไม่นับว่า probe ใหม่แล้ว
    assert row["opened_at"] == stamp(T0 + timedelta(hours=30))  # แต่นับว่าเปิดคลิป
    assert code in caplog.text and BBB in caplog.text


def test_stale_fallback_retries_probe_next_time(
    svc: VideoService, ext: CountingExtractor, clock: Clock
) -> None:
    svc.get(BBB)
    clock.advance(hours=30)
    online_probe = ext.probe
    _go_offline(ext)
    svc.get(BBB)
    ext.probe = online_probe  # type: ignore[method-assign]
    svc.get(BBB)
    assert ext.count["probe"] == 3  # probed_at ไม่ขยับ รอบถัดไปจึง probe ใหม่เมื่อเน็ตกลับมา


def test_stale_fallback_with_peek_keeps_opened_at(
    svc: VideoService, ext: CountingExtractor, clock: Clock, db: Database
) -> None:
    svc.get(BBB)
    clock.advance(hours=30)
    _go_offline(ext)
    assert svc.get(BBB, peek=True)["videoId"] == BBB
    row = db.execute("SELECT opened_at FROM videos WHERE video_id = ?", (BBB,))[0]
    assert row["opened_at"] == stamp(T0)


def _refused(ext: CountingExtractor) -> None:
    def refuse(video_id: str) -> dict:
        ext.count["probe"] += 1
        raise YtError("E_YT_REFUSED", "HTTP Error 403")

    ext.probe = refuse  # type: ignore[method-assign]


def test_refused_reprobe_serves_the_stored_row(
    svc: VideoService, ext: CountingExtractor, clock: Clock, db: Database
) -> None:
    # review I-1 (M4): 403/404/410 ตอน probe ใหม่ = ใช้แถวเดิม (ไม่ยิงคำขอเพิ่ม) ทั้งแถวหมดอายุและแถวรุ่นเก่า
    first = svc.get(BBB)
    clock.advance(hours=30)
    _refused(ext)
    assert svc.get(BBB) == first
    assert ext.count["probe"] == 2
    row = db.execute("SELECT probed_at FROM videos WHERE video_id = ?", (BBB,))[0]
    assert row["probed_at"] == stamp(T0)


def test_refused_reprobe_of_a_version_4_row_serves_it(
    svc: VideoService, ext: CountingExtractor, db: Database
) -> None:
    first = svc.get(BBB)
    data = json.loads(db.execute("SELECT probe_json FROM videos")[0]["probe_json"])
    data["probeVersion"] = 4
    db.execute("UPDATE videos SET probe_json = ?", (json.dumps(data),))
    _refused(ext)
    assert svc.get(BBB) == first
    assert ext.count["probe"] == 2


def test_refused_with_refresh_still_raises(
    svc: VideoService, ext: CountingExtractor, clock: Clock
) -> None:
    svc.get(BBB)
    clock.advance(hours=30)
    _refused(ext)
    with pytest.raises(YtError) as exc:
        svc.get(BBB, refresh=True)
    assert exc.value.code == "E_YT_REFUSED"


def test_refused_without_stored_row_raises(svc: VideoService, ext: CountingExtractor) -> None:
    _refused(ext)
    with pytest.raises(YtError) as exc:
        svc.get(BBB)
    assert exc.value.code == "E_YT_REFUSED"


@pytest.mark.parametrize("code", ["E_VIDEO_UNAVAILABLE", "E_VIDEO_PRIVATE", "E_UNKNOWN"])
def test_other_errors_are_not_hidden_by_stale_cache(
    svc: VideoService, ext: CountingExtractor, clock: Clock, code: str
) -> None:
    svc.get(BBB)
    clock.advance(hours=30)
    _go_offline(ext, code)
    with pytest.raises(YtError) as exc:
        svc.get(BBB)
    assert exc.value.code == code


def test_offline_without_stored_row_still_raises(
    svc: VideoService, ext: CountingExtractor
) -> None:
    _go_offline(ext)
    with pytest.raises(YtError) as exc:
        svc.get(BBB)
    assert exc.value.code == "E_NETWORK"


def test_offline_with_corrupt_stored_row_raises(
    svc: VideoService, ext: CountingExtractor, clock: Clock, db: Database
) -> None:
    svc.get(BBB)
    db.execute("UPDATE videos SET probe_json = 'not json'")
    clock.advance(hours=30)
    _go_offline(ext)
    with pytest.raises(YtError) as exc:
        svc.get(BBB)
    assert exc.value.code == "E_NETWORK"


def test_explicit_refresh_offline_still_raises(
    svc: VideoService, ext: CountingExtractor, clock: Clock
) -> None:
    # refresh=True = ผู้เรียกรู้ว่าข้อมูลเดิมใช้ไม่ได้แล้ว (เช่น ลิงก์ storyboard หมดอายุ) ห้ามคืนของเดิม
    svc.get(BBB)
    clock.advance(hours=30)
    _go_offline(ext)
    with pytest.raises(YtError) as exc:
        svc.get(BBB, refresh=True)
    assert exc.value.code == "E_NETWORK"


# ---------- มิกซ์ (list=RD...) ----------

MIX = "RDaqz-KE-bpKQ"


def test_mix_gives_the_first_25_clips(svc: VideoService, ext: CountingExtractor) -> None:
    result = svc.playlist(MIX, video_id=BBB)
    assert result["isMix"] is True
    assert result["title"]
    assert len(result["entries"]) == 25
    # มิกซ์ไม่มีจำนวนจริง (ยูทูปต่อรายการให้เรื่อย ๆ) จำนวนที่บอกจึงเท่ากับที่ได้มา
    assert result["total"] == 25
    assert result["truncated"] is True
    assert result["entries"][0]["videoId"] == BBB
    assert ext.last_video_id == BBB


def test_mix_limit_is_25_even_if_asked_for_more(db: Database) -> None:
    stub = StubPlaylist(
        {"title": "m", "entries": [{"id": f"abcdefghi{n:02d}"} for n in range(40)]}
    )
    result = VideoService(db, stub).playlist("RDabcdefghij", video_id=BBB)
    assert stub.calls == [("RDabcdefghij", 25, BBB)]
    assert len(result["entries"]) == 25


def test_short_mix_is_not_truncated(db: Database) -> None:
    stub = StubPlaylist(
        {"title": "m", "playlist_count": 99, "entries": [{"id": "abcdefghijk"}]}
    )
    result = VideoService(db, stub).playlist("RDabcdefghij", video_id=BBB)
    assert (result["total"], result["truncated"]) == (1, False)


@pytest.mark.parametrize("bad", [None, "", "short", "aqz-KE-bpK!"])
def test_mix_needs_a_valid_starting_clip(
    svc: VideoService, ext: CountingExtractor, bad: str | None
) -> None:
    with pytest.raises(YtError) as exc:
        svc.playlist(MIX, video_id=bad)
    assert exc.value.code == "E_INVALID_INPUT"
    assert ext.count["playlist"] == 0


def test_normal_playlist_ignores_the_video_id(db: Database) -> None:
    stub = StubPlaylist({"title": "p", "entries": [{"id": "abcdefghijk"}]})
    result = VideoService(db, stub).playlist("PLabcdefghij", video_id=BBB)
    assert "isMix" not in result
    assert stub.calls == [("PLabcdefghij", 200, None)]


def test_curated_music_playlist_takes_the_normal_playlist_path(db: Database) -> None:
    # RDCLAK... = เพลย์ลิสต์ของ YouTube Music: ไม่ต้องมีคลิปตั้งต้น ไม่ถูกตัดที่ 25 ไม่มี isMix (D6)
    curated = "RDCLAK5uy_abcdefghij"
    stub = StubPlaylist(
        {
            "title": "c",
            "playlist_count": 30,
            "entries": [{"id": f"abcdefghi{n:02d}"} for n in range(30)],
        }
    )
    result = VideoService(db, stub).playlist(curated)
    assert stub.calls == [(curated, 200, None)]
    assert "isMix" not in result
    assert (result["total"], result["truncated"], len(result["entries"])) == (30, False, 30)


def test_peek_cached_reads_the_stored_row_without_probing_or_opening(
    svc: VideoService, ext: CountingExtractor, db: Database, clock: Clock
) -> None:
    assert svc.peek_cached("aqz-KE-bpKQ") is None
    assert svc.peek_cached("not an id") is None
    svc.get("aqz-KE-bpKQ", peek=True)
    opened = db.execute("SELECT opened_at FROM videos WHERE video_id = 'aqz-KE-bpKQ'")[0]["opened_at"]
    clock.advance(days=3)  # older than the 24 h cache: still returned
    info = svc.peek_cached("aqz-KE-bpKQ")
    assert info is not None and info["durationS"] == 635 and info["chapters"] == []
    assert ext.count["probe"] == 1
    assert db.execute("SELECT opened_at FROM videos WHERE video_id = 'aqz-KE-bpKQ'")[0]["opened_at"] == opened
