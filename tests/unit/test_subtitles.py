"""บริการซับ (core/subtitles.py): รายการแทร็ก, token + cache, vtt สำรอง, ลิงก์หมดอายุ, ไฟล์ export
และการต่อสายใน lifecycle

ใช้ FakeExtractor + ฐานข้อมูลและ cache ชั่วคราว ไม่แตะเครือข่าย โหลดเฉพาะไฟล์ซับที่มีอยู่จริงใน fixtures
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from yttoolkit import lifecycle
from yttoolkit.core.db import Database
from yttoolkit.core.extractor import FakeExtractor
from yttoolkit.core.srt_builder import PRESETS, SubOptions
from yttoolkit.core.subparse import PARSER_VERSION
from yttoolkit.core.subtitles import SubtitleService
from yttoolkit.core.videos import VideoService
from yttoolkit.core.yterrors import YtError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
THAI = "88o5Sk8_m1Y"
THAI_TITLE = "Thai Listening Practice | EP.1 | Beginner"
BBB = "aqz-KE-bpKQ"  # ไม่มีซับ
ZOO = "jNQXAC9IVRw"  # ซับเจ้าของคลิป en/de, มี chapter
VTT_FALLBACK = "VTTFALLBAK1"
LIVE = "UPCOMINGLV1"
TRACK = "a.th-orig"
SRT_TIME = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})")


class Fetcher:
    """ห่อ fetch_subtitle ของตัวปลอม: `fail` = รหัส error ที่โยนใน `times` ครั้งแรก (None = ไม่พลาด)"""

    def __init__(self, fake: FakeExtractor, fail: str | None = None, times: int = 0) -> None:
        self.fake = fake
        self.fail = fail
        self.times = times
        self.urls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        if self.fail is not None and len(self.urls) <= self.times:
            raise YtError(self.fail, f"เทส {self.fail}")
        return self.fake.fetch_subtitle(url)


@pytest.fixture
def make(tmp_path):
    made: list[Database] = []

    def _make(fail: str | None = None, times: int = 0, session=None):
        db = Database(tmp_path / f"app{len(made)}.db")
        db.migrate()
        made.append(db)
        fake = FakeExtractor(FIXTURES)
        videos = VideoService(db, fake, now=lambda: datetime(2026, 9, 30, 12, tzinfo=UTC))
        fetch = Fetcher(fake, fail, times)
        # รอก่อนลองซับแปลซ้ำ (20 วินาที) บันทึกไว้แทนการหลับจริง
        fetch.sleeps = []
        service = SubtitleService(videos, fetch, tmp_path / "cache", session=session, sleep=fetch.sleeps.append)
        return service, fake, fetch, db, videos

    yield _make
    for db in made:
        db.close()


def probes(fake: FakeExtractor) -> int:
    return sum(1 for name, _ in fake.calls if name == "probe")


def joined(tokens) -> str:
    return "".join(tok.t for tok in tokens).replace(" ", "")


def cache_file(tmp_path: Path, video_id: str, track_id: str) -> Path:
    return tmp_path / "cache" / video_id / "subs" / f"{track_id}.tokens.json"


# ---------- รายการแทร็ก ----------


def test_tracks_thai_default_is_th_orig(make):
    service, *_ = make()
    payload = service.tracks(THAI)
    assert payload["defaultTrackId"] == TRACK
    assert payload["tracks"][0] == {"id": TRACK, "lang": "th", "name": "Thai (Original)", "group": "original"}


def test_tracks_without_subtitles_is_empty(make):
    service, *_ = make()
    assert service.tracks(BBB) == {"tracks": []}


def test_tracks_errors_propagate(make):
    service, *_ = make()
    with pytest.raises(YtError) as info:
        service.tracks(LIVE)
    assert info.value.code == "E_LIVE_NOT_READY"


def _strip_to_m2_row(db: Database, video_id: str) -> None:
    row = db.execute("SELECT probe_json FROM videos WHERE video_id = ?", (video_id,))[0]
    data = json.loads(row["probe_json"])
    data.pop("captions")
    data.pop("probeVersion")
    db.execute("UPDATE videos SET probe_json = ? WHERE video_id = ?", (json.dumps(data), video_id))


def test_m2_row_without_captions_refreshes_once_and_persists(make):
    service, fake, _, db, videos = make()
    videos.get(THAI)
    _strip_to_m2_row(db, THAI)
    before = probes(fake)
    assert service.tracks(THAI)["defaultTrackId"] == TRACK
    assert probes(fake) == before + 1
    # probe ใหม่ถูกเขียนลงแถวแล้ว เปิดหน้าคลิปครั้งถัดไป (หน้าเว็บเรียก /subtitles ทุกครั้ง) ไม่ probe ซ้ำ
    assert service.tracks(THAI)["defaultTrackId"] == TRACK
    assert service.tokens(THAI, TRACK).tokens
    assert probes(fake) == before + 1


# ---------- token ----------


def test_tokens_json3_and_cache(make, tmp_path):
    service, _, fetch, *_ = make()
    parsed = service.tokens(THAI, TRACK)
    assert parsed.source == "json3"
    assert len(parsed.tokens) >= 200
    assert len(fetch.urls) == 1
    # ครั้งที่สองอ่านจาก cache ไม่โหลดซ้ำ ได้ผลเท่าเดิม
    again = service.tokens(THAI, TRACK)
    assert len(fetch.urls) == 1
    assert again == parsed
    folder = tmp_path / "cache" / THAI / "subs"
    assert (folder / f"{TRACK}.json3").read_bytes() == (FIXTURES / "subs" / THAI / "th-orig.json3").read_bytes()
    doc = json.loads(cache_file(tmp_path, THAI, TRACK).read_text(encoding="utf-8"))
    assert doc["v"] == PARSER_VERSION
    assert doc["source"] == "json3"
    assert doc["hasWordTiming"] is parsed.has_word_timing
    assert doc["tokens"][0] == [parsed.tokens[0].t, parsed.tokens[0].s, parsed.tokens[0].e]
    assert not list(folder.glob("*.tmp"))


def test_tokens_cache_from_old_parser_is_rebuilt(make, tmp_path):
    service, _, fetch, *_ = make()
    parsed = service.tokens(THAI, TRACK)
    path = cache_file(tmp_path, THAI, TRACK)
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["v"] = 0
    doc["tokens"] = [["เก่า", 0, 10]]
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert service.tokens(THAI, TRACK) == parsed
    assert len(fetch.urls) == 2
    assert json.loads(path.read_text(encoding="utf-8"))["v"] == PARSER_VERSION


@pytest.mark.parametrize("content", ["{", "[]", '{"v": 1, "tokens": [["x", 0]]}'])
def test_tokens_broken_cache_is_rebuilt(make, tmp_path, content):
    service, _, fetch, *_ = make()
    parsed = service.tokens(THAI, TRACK)
    cache_file(tmp_path, THAI, TRACK).write_text(content, encoding="utf-8")
    assert service.tokens(THAI, TRACK) == parsed
    assert len(fetch.urls) == 2


def test_tokens_cache_of_other_video_is_ignored(make, tmp_path):
    """NTFS ไม่สนตัวพิมพ์: ไฟล์ของ id ที่ต่างแค่ตัวพิมพ์ต้องไม่ถูกหยิบมาใช้"""
    service, _, fetch, *_ = make()
    service.tokens(THAI, TRACK)
    path = cache_file(tmp_path, THAI, TRACK)
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["videoId"] = THAI.upper()
    path.write_text(json.dumps(doc), encoding="utf-8")
    service.tokens(THAI, TRACK)
    assert len(fetch.urls) == 2


def test_tokens_vtt_fallback_for_truncated_json3(make):
    """AC-SUB-11: json3 เสีย (ตัดกลางไฟล์) -> ใช้ vtt ของแทร็กเดียวกันเอง ข้อความตรงกับ json3"""
    service, _, fetch, *_ = make()
    parsed = service.tokens(VTT_FALLBACK, TRACK)
    assert parsed.source == "vtt"
    assert [u.rsplit("/", 1)[-1] for u in fetch.urls] == ["broken.json3", "th-orig.vtt"]
    assert joined(parsed.tokens) == joined(service.tokens(THAI, TRACK).tokens)


def test_tokens_expired_link_reprobes_once_then_succeeds(make):
    service, fake, fetch, *_ = make(fail="E_NETWORK", times=1)
    service.tracks(THAI)
    before = probes(fake)
    parsed = service.tokens(THAI, TRACK)
    assert parsed.source == "json3"
    assert probes(fake) == before + 1
    assert len(fetch.urls) == 2


def test_tokens_network_error_propagates_after_one_reprobe(make, tmp_path):
    service, fake, fetch, *_ = make(fail="E_NETWORK", times=99)
    service.tracks(THAI)
    before = probes(fake)
    with pytest.raises(YtError) as info:
        service.tokens(THAI, TRACK)
    assert info.value.code == "E_NETWORK"
    assert probes(fake) == before + 1
    assert len(fetch.urls) == 2  # json3 รอบแรก + json3 หลัง probe ใหม่ (ไม่ลอง vtt)
    assert not cache_file(tmp_path, THAI, TRACK).exists()


def test_tokens_bot_check_propagates_without_reprobe_or_fallback(make, tmp_path):
    service, fake, fetch, *_ = make(fail="E_BOT_CHECK", times=99)
    service.tracks(THAI)
    before = probes(fake)
    with pytest.raises(YtError) as info:
        service.tokens(THAI, TRACK)
    assert info.value.code == "E_BOT_CHECK"
    assert probes(fake) == before
    assert len(fetch.urls) == 1
    assert not cache_file(tmp_path, THAI, TRACK).exists()


def test_tokens_translated_track_bot_check_is_translation_blocked(make, tmp_path):
    # ยูทูปตอบ 429 เฉพาะคำขอซับแปล (tlang): ไม่ใช่การขอยืนยันว่าไม่ใช่บอท จึงไม่ใช้ E_BOT_CHECK (M4 พักคิวด้วยรหัสนั้น)
    service, fake, fetch, *_ = make(fail="E_BOT_CHECK", times=99)
    service.tracks(THAI)
    before = probes(fake)
    with pytest.raises(YtError) as info:
        service.tokens(THAI, "t.en")
    assert info.value.code == "E_TRANSLATION_BLOCKED"
    assert info.value.message == "ยูทูปยังไม่ให้โหลดซับแปลอัตโนมัติในตอนนี้ เลือกซับภาษาต้นฉบับแทน"
    assert isinstance(info.value.__cause__, YtError)
    assert info.value.__cause__.code == "E_BOT_CHECK"
    assert probes(fake) == before
    # owner round 3: ลองซ้ำครั้งเดียวหลังรอ 20 วินาที แล้วจึงยอมแพ้
    assert len(fetch.urls) == 2
    assert fetch.sleeps == [20]
    assert not cache_file(tmp_path, THAI, "t.en").exists()


def test_export_translated_track_bot_check_is_translation_blocked(make):
    service, *_ = make(fail="E_BOT_CHECK", times=99)
    with pytest.raises(YtError) as info:
        service.export(THAI, "t.en", "srt", PRESETS["medium"])
    assert info.value.code == "E_TRANSLATION_BLOCKED"


def test_tokens_owner_track_bot_check_stays_bot_check(make):
    service, _, fetch, *_ = make(fail="E_BOT_CHECK", times=99)
    with pytest.raises(YtError) as info:
        service.tokens(ZOO, "o.en")
    assert info.value.code == "E_BOT_CHECK"
    assert len(fetch.urls) == 1  # ไม่ลองซ้ำ ไม่รอ (เฉพาะซับแปล)
    assert fetch.sleeps == []


def test_tokens_translated_track_other_errors_keep_their_code(make):
    service, _, fetch, *_ = make(fail="E_NETWORK", times=99)
    with pytest.raises(YtError) as info:
        service.tokens(THAI, "t.en")
    assert info.value.code == "E_NETWORK"
    assert len(fetch.urls) == 2  # ลิงก์หมดอายุ: probe ใหม่แล้วลองอีกรอบเดียวเหมือนแทร็กอื่น


@pytest.mark.parametrize("track_id", ["o.th", "t.xx", "zz.bad", "a.th-orig\n", "", "a." + "x" * 65])
def test_tokens_unknown_track(make, track_id):
    service, _, fetch, *_ = make()
    with pytest.raises(YtError) as info:
        service.tokens(THAI, track_id)
    assert info.value.code == "E_NO_SUBTITLES"
    assert fetch.urls == []


def test_tokens_malformed_track_id_does_not_probe(make):
    service, fake, *_ = make()
    with pytest.raises(YtError) as info:
        service.tokens(THAI, "../../x")
    assert info.value.code == "E_NO_SUBTITLES"
    assert probes(fake) == 0


def test_tokens_track_without_text_is_no_subtitles(make, tmp_path, monkeypatch):
    service, _, fetch, *_ = make()
    empty = {"events": [{"tStartMs": 0, "dDurationMs": 10, "segs": [{"utf8": "\n"}]}]}
    fetch.fake.fetch_subtitle = lambda url: (  # type: ignore[method-assign]
        json.dumps(empty).encode() if url.endswith(".json3") else b"WEBVTT\n\n"
    )
    with pytest.raises(YtError) as info:
        service.tokens(THAI, TRACK)
    assert info.value.code == "E_NO_SUBTITLES"
    assert len(fetch.urls) == 2  # json3 ว่าง -> ลอง vtt แล้วก็ว่าง
    assert not cache_file(tmp_path, THAI, TRACK).exists()


def test_tokens_translated_track_uses_tlang_url(make):
    service, _, fetch, *_ = make()
    parsed = service.tokens(THAI, "t.en")
    assert parsed.tokens
    assert fetch.urls == ["https://fake.invalid/subs/88o5Sk8_m1Y/th-orig.json3?tlang=en"]


def test_tokens_cache_write_failure_still_returns(make, tmp_path, caplog):
    service, *_ = make()
    (tmp_path / "cache" / THAI).mkdir(parents=True)
    (tmp_path / "cache" / THAI / "subs").write_text("ไม่ใช่โฟลเดอร์", encoding="utf-8")
    assert service.tokens(THAI, TRACK).tokens
    assert "เก็บซับ" in caplog.text


# ---------- export ----------


def _ms(h: str, m: str, s: str, ms: str) -> int:
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + int(ms)


def test_export_srt_bytes(make):
    service, *_ = make()
    result = service.export(THAI, TRACK, "srt", PRESETS["medium"])
    data = result.data
    assert not data.startswith(b"\xef\xbb\xbf")
    assert data.count(b"\n") == data.count(b"\r\n") > 0
    blocks = data.decode("utf-8").split("\r\n\r\n")
    numbers, times = [], []
    for block in blocks:
        if not block.strip():
            continue
        lines = block.strip("\r\n").split("\r\n")
        numbers.append(int(lines[0]))
        m = SRT_TIME.fullmatch(lines[1])
        assert m is not None, lines[1]
        times.append((_ms(*m.groups()[:4]), _ms(*m.groups()[4:])))
        assert lines[2:]
    assert numbers == list(range(1, len(numbers) + 1))
    assert all(s <= e for s, e in times)
    assert all(a[1] <= b[0] for a, b in zip(times, times[1:], strict=False))


def test_export_result_carries_title_and_lang(make):
    service, *_ = make()
    result = service.export(THAI, TRACK, "srt", PRESETS["medium"])
    assert (result.title, result.lang) == (THAI_TITLE, "th")


def test_export_txt_and_md(make):
    service, *_ = make()
    txt = service.export(THAI, TRACK, "txt", PRESETS["medium"]).data
    md = service.export(THAI, TRACK, "md", PRESETS["medium"]).data.decode("utf-8")
    assert not txt.startswith(b"\xef\xbb\xbf")
    assert txt.count(b"\n") == txt.count(b"\r\n") > 0
    assert f"# {THAI_TITLE}" in md
    assert "https://www.youtube.com/watch?v=88o5Sk8_m1Y" in md
    assert md.count("\n") == md.count("\r\n")


def test_export_md_uses_chapters(make):
    service, _, _, _, videos = make()
    chapters = videos.get(ZOO)["chapters"]
    assert chapters
    md = service.export(ZOO, "o.en", "md", PRESETS["medium"]).data.decode("utf-8")
    assert f"] {chapters[0]['title']}" in md


def test_export_md_accepts_fractional_chapter_starts(make):
    service, fake, _, db, videos = make()
    original = fake.probe

    def probe(video_id: str) -> dict:
        info = original(video_id)
        info["chapters"] = [{"start_time": 0.0, "title": "เปิด"}, {"start_time": 12.345, "title": "สอง"}]
        return info

    fake.probe = probe  # type: ignore[method-assign]
    md = service.export(THAI, TRACK, "md", PRESETS["medium"]).data.decode("utf-8")
    assert "## [00:12] สอง" in md


def test_export_tokens_mode(make):
    service, *_ = make()
    opts = SubOptions(max_chars=25, lines=1, min_ms=1200, max_ms=5000, mode="tokens", tokens_per_cue=3)
    assert service.export(THAI, TRACK, "srt", opts).data


def test_export_rejects_unknown_format(make):
    service, *_ = make()
    with pytest.raises(ValueError):
        service.export(THAI, TRACK, "docx", PRESETS["medium"])


def test_export_unknown_track(make):
    service, *_ = make()
    with pytest.raises(YtError) as info:
        service.export(THAI, "o.xx", "srt", PRESETS["medium"])
    assert info.value.code == "E_NO_SUBTITLES"


# ---------- lifecycle ----------


@pytest.fixture
def clean_thai_env(monkeypatch):
    for name in ("PYTHAINLP_DATA", "PYTHAINLP_DATA_DIR"):
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)
    return monkeypatch


def test_open_services_builds_subtitle_service_and_thai_dir(paths, fake_platform, clean_thai_env):
    import os

    db, videos, extractor, subtitles, _ = lifecycle.open_services(paths, fake_platform, fake=True)
    try:
        assert isinstance(subtitles, SubtitleService)
        assert subtitles.tracks(THAI)["defaultTrackId"] == TRACK
        assert os.environ["PYTHAINLP_DATA"] == str(paths.data_root / "pythainlp")
    finally:
        db.close()


def test_configure_thai_keeps_user_setting(paths, clean_thai_env):
    import os

    clean_thai_env.setenv("PYTHAINLP_DATA", "D:/mine")
    lifecycle.configure_thai(paths)
    assert os.environ["PYTHAINLP_DATA"] == "D:/mine"


def test_configure_thai_skips_when_legacy_variable_set(paths, clean_thai_env):
    """ตั้งทั้ง PYTHAINLP_DATA_DIR และ PYTHAINLP_DATA = PyThaiNLP โยน ValueError"""
    import os

    clean_thai_env.setenv("PYTHAINLP_DATA_DIR", "D:/legacy")
    lifecycle.configure_thai(paths)
    assert "PYTHAINLP_DATA" not in os.environ


def test_run_app_passes_subtitles_to_context(paths, fake_platform, clean_thai_env):
    captured = []

    class FakeServer:
        def __init__(self, ctx):
            captured.append(ctx)
            self.ctx = ctx

        def start(self):
            self.ctx.request_shutdown()

        def wait_until_ready(self, timeout=15.0):
            return True

        def stop(self):
            pass

        def join(self, timeout=None):
            pass

    clean_thai_env.setattr(lifecycle, "Server", FakeServer)
    clean_thai_env.setattr(lifecycle, "git_commit", lambda root, plat: None)
    code = lifecycle.run_app(
        paths=paths, plat=fake_platform, port=8791, with_tray=False, open_browser=False, auto_ffmpeg=False, fake=True
    )
    assert code == 0
    assert isinstance(captured[0].subtitles, SubtitleService)


# ---------- owner round 3: ประตูอายุเซสชันของซับแปล ----------


class Session:
    """แทน VisitorSession: waits = ค่าที่ wait_seconds คืนทีละครั้ง (ค่าสุดท้ายใช้ซ้ำ)"""

    def __init__(self, *waits: int | None) -> None:
        self.waits = list(waits)
        self.calls = 0

    def wait_seconds(self) -> int | None:
        self.calls += 1
        return self.waits.pop(0) if len(self.waits) > 1 else self.waits[0]


def test_translated_track_waits_for_a_young_session(make, tmp_path):
    service, fake, fetch, *_ = make(session=Session(42))
    service.tracks(THAI)
    before = probes(fake)
    with pytest.raises(YtError) as info:
        service.tokens(THAI, "t.en")
    assert info.value.code == "E_SESSION_WARMING"
    assert info.value.retry_after == 42
    assert info.value.message == "กำลังเตรียมซับแปลจากยูทูป รอสักครู่แล้วโหลดใหม่"
    assert fetch.urls == []  # ไม่ยิงคำขอที่รู้อยู่แล้วว่าได้ 429
    assert probes(fake) == before
    assert not cache_file(tmp_path, THAI, "t.en").exists()


@pytest.mark.parametrize(("video", "track"), [(THAI, TRACK), (ZOO, "o.en")])
def test_original_and_owner_tracks_are_never_gated(make, video, track):
    session = Session(75)
    service, _, fetch, *_ = make(session=session)
    assert service.tokens(video, track).tokens
    assert session.calls == 0
    assert len(fetch.urls) == 1


def test_old_session_fetches_translated_track(make):
    service, _, fetch, *_ = make(session=Session(0))
    parsed = service.tokens(THAI, "t.en")
    assert parsed.tokens
    assert len(fetch.urls) == 1
    assert "tlang=en" in fetch.urls[0]
    assert fetch.sleeps == []


def test_cached_translated_track_skips_the_gate(make):
    session = Session(0)
    service, _, fetch, *_ = make(session=session)
    service.tokens(THAI, "t.en")
    session.waits = [60]
    calls = session.calls
    assert service.tokens(THAI, "t.en").tokens  # cache: ไม่ต้องรอ ไม่โหลดใหม่
    assert session.calls == calls
    assert len(fetch.urls) == 1


def test_missing_session_is_minted_by_one_probe_then_waits(make):
    # ไม่มีเซสชันเลย (ติดตั้งใหม่): probe คลิปนี้ใหม่เพื่อรับคุกกี้ผู้เข้าชม แล้วนับถอยหลังเต็ม 75 วินาที
    service, fake, fetch, *_ = make(session=Session(None, 75))
    service.tracks(THAI)
    before = probes(fake)
    with pytest.raises(YtError) as info:
        service.tokens(THAI, "t.en")
    assert (info.value.code, info.value.retry_after) == ("E_SESSION_WARMING", 75)
    assert probes(fake) == before + 1
    assert fetch.urls == []


def test_no_visitor_after_probe_is_remembered_for_five_minutes(make):
    # review #3: probe แล้วไม่ได้คุกกี้ผู้เข้าชม ไม่ probe ซ้ำทุกครั้งที่ขอซับแปลภายใน 5 นาที
    service, fake, fetch, *_ = make(session=Session(None))
    now = [1000.0]
    service._monotonic = lambda: now[0]
    service.tracks(THAI)
    before = probes(fake)
    calls = []

    def count(url):
        calls.append(url)
        raise YtError("E_NETWORK", "x")

    service._fetch = count
    for _ in range(3):
        with pytest.raises(YtError):
            service.tokens(THAI, "t.en")
        now[0] += 60
    # ครั้งแรก probe ขอเซสชัน 1 ครั้ง (+ probe ใหม่จาก E_NETWORK ของลิงก์หมดอายุทุกครั้ง แบบเดิม)
    session_probes = probes(fake) - before - 3
    assert session_probes == 1
    now[0] += 300
    with pytest.raises(YtError):
        service.tokens(THAI, "t.en")
    assert probes(fake) - before - 4 == 2  # พ้น 5 นาทีแล้ว probe ขอเซสชันอีกครั้ง


def test_session_still_missing_after_probe_fetches_anyway(make):
    service, fake, fetch, *_ = make(session=Session(None))
    service.tracks(THAI)
    before = probes(fake)
    assert service.tokens(THAI, "t.en").tokens
    assert probes(fake) == before + 1
    assert len(fetch.urls) == 1


def test_old_session_429_retries_once_then_succeeds(make):
    service, _, fetch, *_ = make(fail="E_BOT_CHECK", times=1, session=Session(0))
    assert service.tokens(THAI, "t.en").tokens
    assert len(fetch.urls) == 2
    assert fetch.urls[0] == fetch.urls[1]
    assert fetch.sleeps == [20]


def test_old_session_429_twice_is_translation_blocked(make):
    service, _, fetch, *_ = make(fail="E_BOT_CHECK", times=99, session=Session(0))
    with pytest.raises(YtError) as info:
        service.tokens(THAI, "t.en")
    assert info.value.code == "E_TRANSLATION_BLOCKED"
    assert info.value.retry_after is None
    assert len(fetch.urls) == 2
    assert fetch.sleeps == [20]


def test_retry_after_429_with_another_error_keeps_that_error(make):
    service, fake, *_ = make(session=Session(0))
    calls = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        raise YtError("E_BOT_CHECK" if len(calls) == 1 else "E_VIDEO_UNAVAILABLE", "x")

    service._fetch = fetch
    with pytest.raises(YtError) as info:
        service.tokens(THAI, "t.en")
    assert info.value.code == "E_VIDEO_UNAVAILABLE"


def test_warming_export_and_note_use_the_same_gate(make):
    service, *_ = make(session=Session(10))
    with pytest.raises(YtError) as info:
        service.export(THAI, "t.en", "srt", PRESETS["medium"])
    assert info.value.code == "E_SESSION_WARMING"
    with pytest.raises(YtError) as info:
        service.note(THAI, "t.en")
    assert info.value.code == "E_SESSION_WARMING"


def test_open_services_real_mode_shares_one_session(paths, fake_platform, clean_thai_env, monkeypatch):
    from yttoolkit.core.extractor import YtDlpExtractor
    from yttoolkit.core.visitor_session import VisitorSession

    db, videos, extractor, subtitles, _ = lifecycle.open_services(paths, fake_platform, fake=False)
    try:
        assert isinstance(extractor, YtDlpExtractor)
        assert isinstance(extractor.session, VisitorSession)
        assert subtitles._session is extractor.session
        # ไฟล์คุกกี้อยู่ในโฟลเดอร์ข้อมูลของแอพ (data/ ซึ่ง git ไม่เก็บ) ยังไม่ถูกสร้างจนกว่าจะ probe
        assert extractor.session.path == paths.data / "visitor-session.txt"
        assert not extractor.session.path.exists()
    finally:
        db.close()


def test_open_services_fake_mode_has_no_session(paths, fake_platform, clean_thai_env):
    db, _, extractor, subtitles, _ = lifecycle.open_services(paths, fake_platform, fake=True)
    try:
        assert subtitles._session is None
        assert not hasattr(extractor, "session")
    finally:
        db.close()
