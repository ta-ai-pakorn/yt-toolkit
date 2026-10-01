"""เทสกับ ffmpeg จริง (ข้ามเมื่อเครื่องไม่มี ffmpeg)"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from helpers_ffmpeg import ffprobe_json, find_test_ffmpeg, requires_ffmpeg

from yttoolkit.core.cancel import JobCancelled
from yttoolkit.core.media import FfmpegTools, MediaMeta, SubtitleInput, run_ffmpeg
from yttoolkit.core.yterrors import YtError

MEDIA = Path(__file__).resolve().parents[1] / "fixtures" / "media"
META = MediaMeta("ทดสอบ; & | $(x)", "ช่องทดสอบ", "https://www.youtube.com/watch?v=aqz-KE-bpKQ", "2026-09-30", 2.0)

pytestmark = requires_ffmpeg


def _tools() -> FfmpegTools:
    found = find_test_ffmpeg()
    assert found is not None
    return FfmpegTools(lambda: Path(found))


def _never() -> bool:
    return False


def _ignore(_p: float | None) -> None:
    return None


def _streams(info: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [s for s in info["streams"] if s["codec_type"] == kind]


def _srt(tmp_path: Path) -> Path:
    path = tmp_path / "subs.srt"
    path.write_text("1\r\n00:00:00,000 --> 00:00:01,000\r\nสวัสดี\r\n\r\n", encoding="utf-8")
    return path


def test_finalize_mp4_copies_video_and_adds_everything(tmp_path: Path) -> None:
    src = MEDIA / "video.mp4"
    dst = tmp_path / "out.mp4"
    _tools().finalize_mp4(
        src, dst, META, cover=MEDIA / "cover.jpg", subtitle=SubtitleInput(_srt(tmp_path), "tha"),
        audio_language="th", cancel=_never, on_progress=_ignore,
    )  # fmt: skip
    info = ffprobe_json(dst)
    subs = _streams(info, "subtitle")
    assert len(subs) == 1
    assert subs[0]["codec_name"] == "mov_text"
    assert subs[0]["tags"]["language"] == "tha"
    assert subs[0]["disposition"]["default"] == 1
    videos = _streams(info, "video")
    assert [v["disposition"]["attached_pic"] for v in videos] == [0, 1]
    audio = _streams(info, "audio")
    assert audio[0]["tags"]["language"] == "tha"
    assert info["format"]["tags"]["title"] == META.title
    assert info["format"]["tags"]["artist"] == META.artist
    # AC-VID-09: ภาพหลักไม่ถูกเข้ารหัสใหม่
    original = _streams(ffprobe_json(src), "video")[0]
    assert videos[0]["codec_name"] == original["codec_name"]
    assert videos[0]["bit_rate"] == original["bit_rate"]
    assert videos[0]["width"] == original["width"]


def test_finalize_mp4_without_extras(tmp_path: Path) -> None:
    dst = tmp_path / "out.mp4"
    _tools().finalize_mp4(
        MEDIA / "video-noaudio.mp4", dst, META, cover=None, subtitle=None, audio_language="th",
        cancel=_never, on_progress=_ignore,
    )  # fmt: skip
    info = ffprobe_json(dst)
    assert len(_streams(info, "video")) == 1
    assert _streams(info, "audio") == []


def test_finalize_m4a_keeps_aac_and_has_cover_and_title(tmp_path: Path) -> None:
    dst = tmp_path / "out.m4a"
    _tools().finalize_m4a(
        MEDIA / "audio.m4a", dst, META, cover=MEDIA / "cover.jpg", audio_language="th",
        cancel=_never, on_progress=_ignore,
    )  # fmt: skip
    info = ffprobe_json(dst)
    assert _streams(info, "audio")[0]["codec_name"] == "aac"
    assert info["format"]["tags"]["title"] == META.title
    cover = _streams(info, "video")
    assert len(cover) == 1
    assert cover[0]["disposition"]["attached_pic"] == 1


def test_to_mp3_bitrate_within_five_percent(tmp_path: Path) -> None:
    dst = tmp_path / "out.mp3"
    _tools().to_mp3(
        MEDIA / "audio.m4a", dst, META, kbps=192, cover=MEDIA / "cover.jpg", audio_language="th",
        cancel=_never, on_progress=_ignore,
    )  # fmt: skip
    info = ffprobe_json(dst)
    audio = _streams(info, "audio")[0]
    assert audio["codec_name"] == "mp3"
    assert abs(int(audio["bit_rate"]) - 192_000) <= 192_000 * 0.05
    assert info["format"]["tags"]["title"] == META.title


def test_to_wav_is_pcm_with_tags(tmp_path: Path) -> None:
    dst = tmp_path / "out.wav"
    src = MEDIA / "audio.m4a"
    _tools().to_wav(src, dst, META, audio_language="th", cancel=_never, on_progress=_ignore)
    info = ffprobe_json(dst)
    audio = _streams(info, "audio")[0]
    assert audio["codec_name"] == "pcm_s16le"
    assert int(audio["sample_rate"]) == 44100
    assert abs(float(info["format"]["duration"]) - float(ffprobe_json(src)["format"]["duration"])) <= 0.1
    tags = {k.lower(): v for k, v in info["format"]["tags"].items()}
    assert tags["title"] == META.title
    assert tags["artist"] == META.artist


def test_progress_reaches_the_end(tmp_path: Path) -> None:
    seen: list[float | None] = []
    _tools().to_wav(
        MEDIA / "audio.m4a", tmp_path / "o.wav", META, audio_language=None, cancel=_never, on_progress=seen.append
    )
    values = [v for v in seen if v is not None]
    assert values
    assert all(0.0 <= v <= 1.0 for v in values)
    assert max(values) > 0.9


def test_bad_input_raises_unknown(tmp_path: Path) -> None:
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not media")
    with pytest.raises(YtError) as info:
        _tools().to_wav(bad, tmp_path / "o.wav", META, audio_language=None, cancel=_never, on_progress=_ignore)
    assert info.value.code == "E_UNKNOWN"


def test_cancel_kills_process_quickly() -> None:
    ffmpeg = find_test_ffmpeg()
    assert ffmpeg is not None
    start = time.monotonic()
    args = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-re", "-f", "lavfi", "-i", "sine=duration=30", "-f", "null", "-"]
    with pytest.raises(JobCancelled):
        run_ffmpeg(args, duration_s=30, cancel=lambda: time.monotonic() - start > 0.3, on_progress=_ignore)
    assert time.monotonic() - start < 1.5
