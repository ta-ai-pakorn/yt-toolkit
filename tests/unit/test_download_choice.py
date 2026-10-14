"""ตัวเลือก format สำหรับงานโหลด (C8, core/download.py): เสียงภาษาไหน วิดีโอแบบไหน ขนาดคาดการณ์"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from yttoolkit.core.download import (
    FFMPEG_KINDS,
    YOUTUBE_KINDS,
    DownloadChoice,
    MediaFacts,
    SharpPick,
    audio_choice,
    media_facts,
    pick_audio,
    pick_sharp_format,
    sharp_choice,
    video_choice,
)
from yttoolkit.core.extractor import FakeExtractor
from yttoolkit.core.yterrors import YtError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
DUB = "8lpOfyoxcvU"
BBB = "aqz-KE-bpKQ"
AUTO = {"maxQuality": False, "noAudio": False, "audioLanguage": "original"}


@pytest.fixture
def fake() -> FakeExtractor:
    return FakeExtractor(FIXTURES)


# ---------- pick_audio ----------


def test_original_audio_is_default(fake: FakeExtractor) -> None:  # AC-VID-03/06 (original)
    info = fake.probe(DUB)
    aud, notes = pick_audio(info["formats"], "original", codec_prefix="mp4a")
    assert aud is not None
    assert aud["format_id"] == "140-1" and aud["language"] == "th" and notes == ()


def test_empty_want_means_original(fake: FakeExtractor) -> None:
    aud, notes = pick_audio(fake.probe(DUB)["formats"], "", codec_prefix="mp4a")
    assert aud is not None and aud["format_id"] == "140-1" and notes == ()


def test_dub_language_is_chosen(fake: FakeExtractor) -> None:  # AC-VID-05
    aud, notes = pick_audio(fake.probe(DUB)["formats"], "en", codec_prefix="mp4a")
    assert aud is not None
    assert aud["language"] == "en-US" and aud["format_id"] == "140-0" and notes == ()


def test_language_match_ignores_case_and_accepts_the_full_tag(fake: FakeExtractor) -> None:
    formats = fake.probe(DUB)["formats"]
    for want in ("EN", "en-us", "en-US"):
        aud, notes = pick_audio(formats, want, codec_prefix="mp4a")
        assert aud is not None and aud["format_id"] == "140-0" and notes == ()
    # "e" ไม่ใช่ภาษา en (ต้องตรงทั้งคำหรือตามด้วย "-")
    aud, notes = pick_audio(formats, "e", codec_prefix="mp4a")
    assert aud is not None and aud["language"] == "th" and notes == ("AUDIO_LANG_FALLBACK",)


def test_missing_language_falls_back_with_note(fake: FakeExtractor) -> None:  # AC-VID-06
    aud, notes = pick_audio(fake.probe(DUB)["formats"], "ja", codec_prefix="mp4a")
    assert aud is not None
    assert aud["language"] == "th" and notes == ("AUDIO_LANG_FALLBACK",)


def test_without_codec_prefix_the_highest_bitrate_wins(fake: FakeExtractor) -> None:
    aud, _ = pick_audio(fake.probe(DUB)["formats"], "original", codec_prefix=None)
    assert aud is not None and aud["format_id"] == "251-1"  # opus 134.7 kbps > mp4a 129.5 kbps


def test_codec_prefix_with_no_match_keeps_every_candidate(fake: FakeExtractor) -> None:
    aud, notes = pick_audio(fake.probe(DUB)["formats"], "original", codec_prefix="flac")
    assert aud is not None and aud["format_id"] == "251-1" and notes == ()


def test_drc_and_storyboard_are_never_picked(fake: FakeExtractor) -> None:
    aud, notes = pick_audio(fake.probe(BBB)["formats"], "original", codec_prefix="mp4a")
    assert aud is not None and aud["format_id"] == "140" and notes == ()


def test_no_language_tags_fall_back_to_the_best_track(fake: FakeExtractor) -> None:
    aud, notes = pick_audio(fake.probe(BBB)["formats"], "th", codec_prefix="mp4a")
    assert aud is not None and aud["format_id"] == "140" and notes == ("AUDIO_LANG_FALLBACK",)


def test_no_audio_candidates() -> None:
    video_only = [{"format_id": "137", "vcodec": "avc1.640028", "acodec": "none", "height": 1080}]
    assert pick_audio(video_only, "original", codec_prefix="mp4a") == (None, ())
    assert pick_audio([], "en", codec_prefix=None) == (None, ())


def test_returns_the_raw_format_dict(fake: FakeExtractor) -> None:
    formats = fake.probe(DUB)["formats"]
    aud, _ = pick_audio(formats, "original", codec_prefix="mp4a")
    assert any(aud is f for f in formats)


# ---------- video_choice ----------


def test_compat_default_spec(fake: FakeExtractor) -> None:  # AC-VID-01 selector
    c = video_choice(fake.probe(DUB), AUTO)
    assert c.format_spec == "bv*[vcodec^=avc1][height<=1080]+140-1/b[ext=mp4]"
    assert c.merge_mp4 and c.audio_language == "th" and c.notes == ()


def test_compat_expected_bytes_is_best_avc1_plus_audio(fake: FakeExtractor) -> None:
    c = video_choice(fake.probe(DUB), AUTO)
    assert c.expected_bytes == 36285465 + 6526778  # 298 (avc1 720p) + 140-1


def test_compat_max_height_720(fake: FakeExtractor) -> None:
    info = fake.probe(BBB)
    c = video_choice(info, {**AUTO, "maxHeight": 720})
    assert c.format_spec == "bv*[vcodec^=avc1][height<=720]+140/b[ext=mp4]"
    assert c.expected_bytes == 150524867 + 10271496  # 298 (avc1 720p60) + 140


def test_dub_and_fallback_notes_in_video(fake: FakeExtractor) -> None:
    info = fake.probe(DUB)
    dub = video_choice(info, {**AUTO, "audioLanguage": "en-US"})
    assert dub.format_spec.endswith("+140-0/b[ext=mp4]") and dub.audio_language == "en-US"
    missing = video_choice(info, {**AUTO, "audioLanguage": "ja"})
    assert missing.notes == ("AUDIO_LANG_FALLBACK",) and missing.audio_language == "th"


def test_no_audio_has_no_audio_part(fake: FakeExtractor) -> None:  # AC-VID-08 (U)
    c = video_choice(fake.probe(BBB), {**AUTO, "noAudio": True})
    assert c.format_spec == "bv*[vcodec^=avc1][height<=1080]"
    assert "+" not in c.format_spec and "ba" not in c.format_spec
    assert c.audio_language is None and c.merge_mp4
    assert c.expected_bytes == 257619653  # 299 (avc1 1080p60)


def test_no_audio_ignores_the_language(fake: FakeExtractor) -> None:
    c = video_choice(fake.probe(DUB), {**AUTO, "noAudio": True, "audioLanguage": "ja"})
    assert c.notes == () and c.audio_language is None


def test_max_quality_and_format_id(fake: FakeExtractor) -> None:
    info = fake.probe(BBB)
    assert video_choice(info, {**AUTO, "maxQuality": True}).format_spec.startswith("bv*+")
    fid = next(f["format_id"] for f in info["formats"] if (f.get("vcodec") or "").startswith("avc1"))
    c = video_choice(info, {**AUTO, "formatId": fid})
    assert c.format_spec.startswith(f"{fid}+") and "/" not in c.format_spec
    gone = video_choice(info, {**AUTO, "formatId": "999999"})
    assert "QUALITY_FALLBACK" in gone.notes and gone.format_spec.startswith("bv*[vcodec^=avc1]")


def test_max_quality_spec_and_size(fake: FakeExtractor) -> None:
    c = video_choice(fake.probe(BBB), {**AUTO, "maxQuality": True})
    assert c.format_spec == "bv*+140/b"  # 140 (129.48) > 251 (128.61), no language tags
    assert c.expected_bytes == 1362269481 + 10271496  # 315 (vp9 2160p60) + 140
    dub = video_choice(fake.probe(DUB), {**AUTO, "maxQuality": True})
    assert dub.format_spec == "bv*+251-1/b" and dub.audio_language == "th"


def test_format_id_spec_and_size(fake: FakeExtractor) -> None:
    c = video_choice(fake.probe(BBB), {**AUTO, "formatId": "299"})
    assert c.format_spec == "299+140" and c.notes == ()
    assert c.expected_bytes == 257619653 + 10271496
    unknown = video_choice(fake.probe(BBB), {**AUTO, "formatId": "312"})
    assert unknown.format_spec == "312+140" and unknown.expected_bytes is None  # 312 has no size


def test_missing_format_id_with_max_quality_falls_back_to_max(fake: FakeExtractor) -> None:
    c = video_choice(fake.probe(BBB), {**AUTO, "formatId": "999999", "maxQuality": True})
    assert c.format_spec == "bv*+140/b" and c.notes == ("QUALITY_FALLBACK",)


@pytest.mark.parametrize("fid", ["140", "sb0"])
def test_format_id_must_name_a_video_format(fake: FakeExtractor, fid: str) -> None:
    # review M-4: เสียงล้วน (140) หรือ storyboard (sb0) ไม่ใช่ format วิดีโอ = เหมือนไม่มีแล้ว
    c = video_choice(fake.probe(BBB), {**AUTO, "formatId": fid})
    assert c.format_spec == "bv*[vcodec^=avc1][height<=1080]+140/b[ext=mp4]"
    assert c.notes == ("QUALITY_FALLBACK",)


def test_storyboard_with_a_vcodec_is_still_not_a_video(fake: FakeExtractor) -> None:
    info = copy.deepcopy(fake.probe(BBB))
    for fmt in info["formats"]:
        if fmt["format_id"] == "sb0":
            fmt["vcodec"], fmt["height"] = "mjpeg", 4000
    c = video_choice(info, {**AUTO, "formatId": "sb0", "maxQuality": True})
    assert c.format_spec == "bv*+140/b" and c.notes == ("QUALITY_FALLBACK",)
    assert c.expected_bytes == 1362269481 + 10271496  # storyboard never counts as the best video


def test_muxed_format_id_is_accepted(fake: FakeExtractor) -> None:
    c = video_choice(fake.probe(BBB), {**AUTO, "formatId": "18"})
    assert c.format_spec == "18+140" and c.notes == ()


def test_notes_keep_the_order_quality_then_audio(fake: FakeExtractor) -> None:
    c = video_choice(fake.probe(DUB), {**AUTO, "formatId": "nope", "audioLanguage": "ja"})
    assert c.notes == ("QUALITY_FALLBACK", "AUDIO_LANG_FALLBACK")


def test_audio_size_from_bitrate_when_no_filesize(fake: FakeExtractor) -> None:
    info = copy.deepcopy(fake.probe(DUB))
    for fmt in info["formats"]:
        if fmt["format_id"] == "140-1":
            fmt.pop("filesize")
            fmt.pop("filesize_approx")
    c = video_choice(info, AUTO)
    assert c.expected_bytes == 36285465 + round(129.487 * 1000 / 8 * 403)


def test_clip_without_audio_formats_uses_generic_audio(fake: FakeExtractor) -> None:
    info = copy.deepcopy(fake.probe(BBB))
    info["formats"] = [f for f in info["formats"] if f.get("vcodec") != "none" or f.get("format_note") == "storyboard"]
    c = video_choice(info, AUTO)
    assert c.format_spec == "bv*[vcodec^=avc1][height<=1080]+ba[acodec^=mp4a]/b[ext=mp4]"
    assert c.audio_language is None and c.expected_bytes is None
    assert video_choice(info, {**AUTO, "maxQuality": True}).format_spec == "bv*+ba/b"


# ---------- คลิปแนวตั้ง (Shorts): ความละเอียด = ด้านสั้นของภาพ ----------

SHORT_AUDIO = {
    "format_id": "140",
    "vcodec": "none",
    "acodec": "mp4a.40.2",
    "abr": 129.0,
    "filesize": 500_000,
    "ext": "m4a",
}


def _short_info(*, widths: bool = True) -> dict:
    """Shorts แบบสังเคราะห์: H.264 1080x1920, 720x1280, 480x854 + VP9 1080x1920 + เสียง AAC (เรียงแย่ไปดีแบบ yt-dlp)"""
    rows = [
        ("135", 480, 854, "avc1.4d401e", 3_000_000),
        ("136", 720, 1280, "avc1.4d401f", 6_000_000),
        ("137", 1080, 1920, "avc1.640028", 12_000_000),
        ("248", 1080, 1920, "vp09.00.40.08", 9_000_000),
    ]
    formats = [
        {
            "format_id": format_id,
            **({"width": width} if widths else {}),
            "height": height,
            "fps": 30,
            "vcodec": vcodec,
            "acodec": "none",
            "filesize": size,
            "ext": "mp4" if vcodec.startswith("avc1") else "webm",
        }
        for format_id, width, height, vcodec, size in rows
    ]
    return {"id": "SHORTS00001", "duration": 30, "formats": [SHORT_AUDIO, *formats]}


def test_portrait_compat_cap_uses_the_short_side() -> None:
    c = video_choice(_short_info(), AUTO)
    assert c.format_spec == "bv*[vcodec^=avc1][width<=1080]+140/b[ext=mp4]"
    assert c.expected_bytes == 12_000_000 + 500_000  # 137 (1080x1920) ไม่ใช่ถูกตัดเหลือ 480x854


def test_portrait_compat_720() -> None:
    c = video_choice(_short_info(), {**AUTO, "maxHeight": 720, "noAudio": True})
    assert c.format_spec == "bv*[vcodec^=avc1][width<=720]"
    assert c.expected_bytes == 6_000_000  # 136 (720x1280)


def test_portrait_without_widths_falls_back_to_height() -> None:
    c = video_choice(_short_info(widths=False), AUTO)
    assert c.format_spec == "bv*[vcodec^=avc1][height<=1080]+140/b[ext=mp4]"
    assert c.expected_bytes == 3_000_000 + 500_000  # ไม่รู้ width = นับ height แบบเดิม (854 ผ่านเพดาน)


def test_landscape_with_widths_keeps_the_height_filter(fake: FakeExtractor) -> None:
    info = fake.probe(BBB)
    assert all("width" in f for f in info["formats"] if f.get("vcodec") not in (None, "none"))
    assert video_choice(info, AUTO).format_spec == "bv*[vcodec^=avc1][height<=1080]+140/b[ext=mp4]"


@pytest.mark.parametrize(
    ("info", "picked"),
    [
        (_short_info(), "137"),  # แนวตั้ง 1080x1920 = 1080p
        (
            {
                "formats": [
                    {**f, "width": f["height"], "height": f["width"]} if f["vcodec"] != "none" else f
                    for f in _short_info()["formats"]
                ]
            },
            "137",  # แนวนอน 1920x1080 = 1080p (เพดานเดิม)
        ),
    ],
)
def test_yt_dlp_selects_the_short_side_cap(info: dict, picked: str) -> None:
    """สตริง format ที่ส่งให้ yt-dlp เลือก format ที่ด้านสั้นไม่เกินเพดานจริง (ตัวเลือก format ของ yt-dlp เอง ไม่ต่อเน็ต)"""
    import yt_dlp

    spec = video_choice(info, {**AUTO, "noAudio": True}).format_spec
    formats = [f for f in info["formats"] if f["vcodec"] != "none"]
    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        # _select_formats เป็น API ภายในของ yt-dlp (ไม่มีทางสาธารณะให้รันตัวเลือก format โดยไม่ต่อเน็ต) อัปเดต yt-dlp แล้วพัง = แก้ที่นี่
        selected = ydl._select_formats(formats, ydl.build_format_selector(spec))
    assert [f["format_id"] for f in selected] == [picked]


def test_choice_is_frozen(fake: FakeExtractor) -> None:
    c = video_choice(fake.probe(DUB), AUTO)
    assert isinstance(c, DownloadChoice)
    with pytest.raises(AttributeError):
        c.format_spec = "x"  # type: ignore[misc]


# ---------- audio_choice ----------


def test_audio_m4a_spec(fake: FakeExtractor) -> None:
    c = audio_choice(fake.probe(DUB), {"format": "m4a", "audioLanguage": "original"})
    assert c.format_spec == "140-1" and not c.merge_mp4
    assert c.audio_language == "th" and c.notes == () and c.expected_bytes == 6526778


def test_audio_dub_and_fallback(fake: FakeExtractor) -> None:
    info = fake.probe(DUB)
    assert audio_choice(info, {"format": "mp3", "audioLanguage": "en"}).format_spec == "140-0"
    c = audio_choice(info, {"format": "mp3", "audioLanguage": "ko"})
    assert c.format_spec == "140-1" and c.notes == ("AUDIO_LANG_FALLBACK",)


def test_audio_wav_adds_pcm_size(fake: FakeExtractor) -> None:
    c = audio_choice(fake.probe(DUB), {"format": "wav", "audioLanguage": "original"})
    assert c.expected_bytes == 6526778 + 403 * 44100 * 2 * 2


def test_audio_without_tracks_uses_generic_spec(fake: FakeExtractor) -> None:
    info = {"id": BBB, "duration": 10, "formats": []}
    c = audio_choice(info, {"format": "m4a", "audioLanguage": "original"})
    assert c.format_spec == "ba[acodec^=mp4a]/ba" and c.expected_bytes is None and c.audio_language is None


# ---------- job kinds ----------


def test_kind_sets() -> None:
    assert YOUTUBE_KINDS == {"video", "audio", "subtitle", "note", "frames_sharp"}
    assert FFMPEG_KINDS == {"video", "audio", "frames_sharp"}
    assert isinstance(YOUTUBE_KINDS, frozenset) and isinstance(FFMPEG_KINDS, frozenset)


# ---------- ภาพคม (M5 รอบ B spec 3.3) ----------


def _v(fid: str, w: int, h: int, vcodec: str = "avc1.4d401f", *, acodec: str = "none", size: int | None = None,
       dr: str | None = None) -> dict:
    fmt = {"format_id": fid, "width": w, "height": h, "vcodec": vcodec, "acodec": acodec}
    if size is not None:
        fmt["filesize"] = size
    if dr is not None:
        fmt["dynamic_range"] = dr
    return fmt


def _pick(*formats: dict) -> SharpPick | None:
    return pick_sharp_format({"formats": list(formats), "duration": 60})


def test_sharp_pick_on_the_bbb_fixture(fake: FakeExtractor) -> None:
    pick = pick_sharp_format(fake.probe(BBB))
    assert pick == SharpPick("298", 1280, 720, "SDR", False, 150_524_867)
    assert pick.short_side == 720 and pick.hdr is False


def test_sharp_prefers_sdr_over_a_larger_hdr_format() -> None:
    pick = _pick(_v("hdr", 1280, 720, "vp09.02.40.10", dr="HDR10"), _v("sdr", 854, 480))
    assert pick is not None and pick.format_id == "sdr"


def test_sharp_takes_the_largest_short_side_up_to_720() -> None:
    assert _pick(_v("1080", 1920, 1080), _v("720", 1280, 720), _v("480", 854, 480)).format_id == "720"
    portrait = _pick(_v("p1080", 1080, 1920), _v("p720", 720, 1280), _v("p480", 480, 854))
    assert portrait.format_id == "p720" and portrait.short_side == 720


def test_sharp_codec_order_then_smallest_size() -> None:
    assert _pick(_v("av1", 1280, 720, "av01.0.08M.08", size=10), _v("vp9", 1280, 720, "vp9", size=20),
                 _v("h264", 1280, 720, size=30)).format_id == "h264"  # fmt: skip
    assert _pick(_v("av1", 1280, 720, "av01.0.08M.08"), _v("vp9", 1280, 720, "vp09.00.40.08")).format_id == "vp9"
    assert _pick(_v("a", 1280, 720, size=30), _v("b", 1280, 720, size=20), _v("c", 1280, 720)).format_id == "b"


def test_sharp_video_only_before_muxed_and_muxed_fallback() -> None:
    assert _pick(_v("muxed720", 1280, 720, acodec="mp4a.40.2"), _v("vo480", 854, 480)).format_id == "vo480"
    muxed = _pick(_v("18", 640, 360, acodec="mp4a.40.2"))
    assert muxed is not None and muxed.muxed is True and muxed.short_side == 360


def test_sharp_hdr_only_and_nothing_up_to_720() -> None:
    hdr = _pick(_v("hlg", 1280, 720, "vp09.02.40.10", dr="HLG"))
    assert hdr.hdr is True and hdr.dynamic_range == "HLG"
    assert _pick(_v("1440", 2560, 1440, "vp9"), _v("1080", 1920, 1080)).format_id == "1080"


def test_sharp_no_video_format() -> None:
    assert _pick({"format_id": "140", "vcodec": "none", "acodec": "mp4a.40.2"}) is None
    with pytest.raises(YtError) as err:
        sharp_choice({"formats": [], "duration": 60})
    assert err.value.code == "E_UNKNOWN"


def test_sharp_choice_is_a_video_only_download(fake: FakeExtractor) -> None:
    choice, pick = sharp_choice(fake.probe(BBB))
    assert choice.format_spec == "298" and choice.merge_mp4 is True
    assert choice.audio_language is None and choice.notes == () and choice.expected_bytes == 150_524_867
    assert pick.format_id == "298"


def test_media_facts() -> None:
    assert media_facts({"width": 1280, "height": 720, "dynamic_range": "SDR"}) == MediaFacts(1280, 720, "SDR")
    facts = media_facts({"width": 1080.0, "height": 1920, "dynamic_range": "HDR10"})
    assert facts.short_side == 1080 and facts.hdr is True
    unknown = media_facts({"filepath": "x"})
    assert unknown == MediaFacts(None, None, None) and unknown.short_side is None and unknown.hdr is None
    assert media_facts({"height": 720}).short_side == 720
    # M6 รอบ A: bitrate เสียงตามที่ yt-dlp บอก (ยังไม่ปัด) ค่าที่ไม่ใช่ตัวเลขบวก = ไม่รู้
    assert media_facts({"abr": 129.478}).abr_kbps == 129.478
    assert media_facts({"abr": 0}).abr_kbps is None and media_facts({"abr": "x"}).abr_kbps is None
    assert MediaFacts(1280, 720, "SDR").abr_kbps is None
