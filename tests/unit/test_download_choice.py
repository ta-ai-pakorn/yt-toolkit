"""ตัวเลือก format สำหรับงานโหลด (C8, core/download.py): เสียงภาษาไหน วิดีโอแบบไหน ขนาดคาดการณ์"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from yttoolkit.core.download import (
    FFMPEG_KINDS,
    YOUTUBE_KINDS,
    DownloadChoice,
    audio_choice,
    pick_audio,
    video_choice,
)
from yttoolkit.core.extractor import FakeExtractor

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
    assert YOUTUBE_KINDS == {"video", "audio", "subtitle", "frames_sharp"}
    assert FFMPEG_KINDS == {"video", "audio"}
    assert isinstance(YOUTUBE_KINDS, frozenset) and isinstance(FFMPEG_KINDS, frozenset)
