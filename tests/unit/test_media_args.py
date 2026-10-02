from __future__ import annotations

import sys
from pathlib import Path

import pytest

from yttoolkit.core.cancel import JobCancelled
from yttoolkit.core.media import (
    FakeMediaTools,
    FfmpegTools,
    MediaMeta,
    SubtitleInput,
    iso639_2,
    m4a_args,
    mp3_args,
    mp4_args,
    run_ffmpeg,
    wav_args,
)
from yttoolkit.core.yterrors import YtError

FF = "ffmpeg"
HEAD = [FF, "-hide_banner", "-nostdin", "-y", "-progress", "pipe:1", "-nostats", "-i"]
SRC = Path("in.mp4")
DST = Path("out.mp4")
META = MediaMeta(
    title="ชื่อคลิป",
    artist="ช่อง",
    comment="https://www.youtube.com/watch?v=aqz-KE-bpKQ",
    date="2026-09-30",
    duration_s=2.0,
)
M = [
    "-metadata", "title=ชื่อคลิป",
    "-metadata", "artist=ช่อง",
    "-metadata", "comment=https://www.youtube.com/watch?v=aqz-KE-bpKQ",
    "-metadata", "date=2026-09-30",
]  # fmt: skip
COVER = Path("cover.jpg")
SUB = SubtitleInput(path=Path("subs.srt"), language="tha")


def _contains(args: list[str], seq: list[str]) -> bool:
    return any(args[i : i + len(seq)] == seq for i in range(len(args) - len(seq) + 1))


def test_iso639_2() -> None:
    assert [iso639_2(x) for x in ("th", "en-US", "tha", "xx", None)] == ["tha", "eng", "tha", "und", "und"]
    assert iso639_2("zh") == "chi"
    assert iso639_2("FR") == "fre"
    assert iso639_2("") == "und"


def test_mp4_full_args_exact() -> None:
    args = mp4_args(FF, SRC, DST, META, cover=COVER, subtitle=SUB, audio_language="th")
    assert args == (
        HEAD + [str(SRC), "-i", str(COVER), "-i", str(SUB.path)]
        + ["-map", "0:v:0", "-map", "0:a?", "-map", "2:0", "-map", "1:0"]
        + ["-c", "copy"]
        + ["-c:s", "mov_text", "-metadata:s:s:0", "language=tha", "-disposition:s:0", "default"]
        + ["-disposition:v:1", "attached_pic"]
        + M
        + ["-metadata:s:a:0", "language=tha"]
        + ["-movflags", "+faststart", str(DST)]
    )  # fmt: skip


def test_mp4_subtitle_only_indexes() -> None:
    args = mp4_args(FF, SRC, DST, META, cover=None, subtitle=SUB, audio_language=None)
    assert _contains(args, ["-i", str(SUB.path), "-map", "0:v:0", "-map", "0:a?", "-map", "1:0"])
    assert "attached_pic" not in args
    assert not any(a.startswith("-metadata:s:a") for a in args)
    assert args[-3:] == ["-movflags", "+faststart", str(DST)]


def test_mp4_cover_only_and_bare() -> None:
    args = mp4_args(FF, SRC, DST, META, cover=COVER, subtitle=None, audio_language=None)
    assert _contains(args, ["-map", "0:v:0", "-map", "0:a?", "-map", "1:0"])
    assert "-c:s" not in args
    assert _contains(args, ["-disposition:v:1", "attached_pic"])
    bare = mp4_args(FF, SRC, DST, MediaMeta("t", "a", "c", None, None), cover=None, subtitle=None, audio_language=None)
    assert bare == (
        HEAD + [str(SRC), "-map", "0:v:0", "-map", "0:a?", "-c", "copy"]
        + ["-metadata", "title=t", "-metadata", "artist=a", "-metadata", "comment=c"]
        + ["-movflags", "+faststart", str(DST)]
    )  # fmt: skip


def test_mp4_no_audio_drops_every_audio_stream() -> None:
    # noAudio: format bv* อาจได้ไฟล์ที่มีเสียงติดมา ไฟล์ "(ไม่มีเสียง)" ต้องไม่มีเสียงจริงๆ
    args = mp4_args(FF, SRC, DST, META, cover=COVER, subtitle=SUB, audio_language="th", no_audio=True)
    assert "0:a?" not in args
    assert _contains(args, ["-map", "0:v:0", "-map", "2:0", "-map", "1:0"])
    assert "-an" in args
    assert not any(a.startswith("-metadata:s:a") for a in args)
    assert args[-3:] == ["-movflags", "+faststart", str(DST)]


def test_mp4_keeps_audio_by_default() -> None:
    args = mp4_args(FF, SRC, DST, META, cover=None, subtitle=None, audio_language=None)
    assert "-an" not in args and "0:a?" in args


def test_m4a_args() -> None:
    args = m4a_args(FF, SRC, Path("o.m4a"), META, cover=COVER, audio_language="en")
    assert args == (
        HEAD + [str(SRC), "-i", str(COVER), "-map", "0:a:0", "-map", "1:0", "-disposition:v:0", "attached_pic"]
        + ["-c", "copy"] + M + ["-metadata:s:a:0", "language=eng"]
        + ["-f", "mp4", "-movflags", "+faststart", "o.m4a"]
    )  # fmt: skip
    plain = m4a_args(FF, SRC, Path("o.m4a"), META, cover=None, audio_language=None)
    assert _contains(plain, ["-f", "mp4"])
    assert "attached_pic" not in plain


def test_mp3_args() -> None:
    args = mp3_args(FF, SRC, Path("o.mp3"), META, kbps=192, cover=COVER, audio_language="th")
    assert args == (
        HEAD + [str(SRC), "-i", str(COVER), "-map", "0:a:0", "-map", "1:0"]
        + ["-c:a", "libmp3lame", "-b:a", "192k", "-c:v", "copy", "-disposition:v:0", "attached_pic"]
        + ["-id3v2_version", "3"] + M + ["-metadata:s:a:0", "language=tha", "o.mp3"]
    )  # fmt: skip
    no_cover = mp3_args(FF, SRC, Path("o.mp3"), META, kbps=128, cover=None, audio_language=None)
    assert _contains(no_cover, ["-b:a", "128k"])
    assert "-c:v" not in no_cover


def test_wav_args() -> None:
    args = wav_args(FF, SRC, Path("o.wav"), META, audio_language="th")
    assert args == (
        HEAD + [str(SRC), "-map", "0:a:0", "-c:a", "pcm_s16le"]
        + ["-metadata", "title=ชื่อคลิป", "-metadata", "artist=ช่อง", "o.wav"]
    )  # fmt: skip
    assert "-ar" not in args


def test_title_with_shell_characters_is_one_element() -> None:
    nasty = "ทดสอบ; & | $(rm -rf ~) `x`"
    meta = MediaMeta(nasty, "a", "c", None, None)
    expected = f"title={nasty}"
    for args in (
        mp4_args(FF, SRC, DST, meta, cover=COVER, subtitle=SUB, audio_language="th"),
        m4a_args(FF, SRC, DST, meta, cover=COVER, audio_language="th"),
        mp3_args(FF, SRC, DST, meta, kbps=192, cover=COVER, audio_language="th"),
        wav_args(FF, SRC, DST, meta, audio_language="th"),
    ):
        assert args.count(expected) == 1
        assert sum(nasty in a for a in args) == 1


MEDIA = Path(__file__).resolve().parents[1] / "fixtures" / "media"
FAKE_META = MediaMeta("t", "a", "c", None, 2.0)


def _never() -> bool:
    return False


def _ignore(_p: float | None) -> None:
    return None


def test_fake_is_available_and_copies(tmp_path: Path) -> None:
    fake = FakeMediaTools(MEDIA)
    assert fake.available() is True
    seen: list[float | None] = []
    src = MEDIA / "video.mp4"
    dst = tmp_path / "out.mp4"
    fake.finalize_mp4(
        src, dst, FAKE_META, cover=None, subtitle=None, audio_language=None, cancel=_never, on_progress=seen.append
    )
    assert dst.read_bytes() == src.read_bytes()
    assert 1.0 in seen

    m4a = tmp_path / "o.m4a"
    fake.finalize_m4a(
        MEDIA / "audio.m4a", m4a, FAKE_META, cover=None, audio_language=None, cancel=_never, on_progress=_ignore
    )
    assert m4a.read_bytes() == (MEDIA / "audio.m4a").read_bytes()


def test_fake_conversions_write_fixture_copies(tmp_path: Path) -> None:
    fake = FakeMediaTools(MEDIA)
    seen: list[float | None] = []
    mp3 = tmp_path / "o.mp3"
    wav = tmp_path / "o.wav"
    fake.to_mp3(
        MEDIA / "audio.m4a", mp3, FAKE_META, kbps=192, cover=None, audio_language=None, cancel=_never, on_progress=seen.append
    )
    fake.to_wav(MEDIA / "audio.m4a", wav, FAKE_META, audio_language=None, cancel=_never, on_progress=seen.append)
    assert mp3.read_bytes() == (MEDIA / "audio.mp3").read_bytes()
    assert wav.read_bytes() == (MEDIA / "audio.wav").read_bytes()
    assert seen == [1.0, 1.0]


def test_fake_cancel_raises_and_writes_nothing(tmp_path: Path) -> None:
    fake = FakeMediaTools(MEDIA)
    dst = tmp_path / "out.mp4"
    with pytest.raises(JobCancelled):
        fake.finalize_mp4(
            MEDIA / "video.mp4", dst, FAKE_META, cover=None, subtitle=None, audio_language=None,
            cancel=lambda: True, on_progress=_ignore,
        )  # fmt: skip
    assert not dst.exists()


def test_ffmpeg_tools_missing(tmp_path: Path) -> None:
    tools = FfmpegTools(lambda: None)
    assert tools.available() is False
    assert tools.ffmpeg_path() is None
    a, b = tmp_path / "a", tmp_path / "b"
    calls = [
        lambda: tools.finalize_mp4(a, b, FAKE_META, cover=None, subtitle=None, audio_language=None, cancel=_never, on_progress=_ignore),
        lambda: tools.finalize_m4a(a, b, FAKE_META, cover=None, audio_language=None, cancel=_never, on_progress=_ignore),
        lambda: tools.to_mp3(a, b, FAKE_META, kbps=192, cover=None, audio_language=None, cancel=_never, on_progress=_ignore),
        lambda: tools.to_wav(a, b, FAKE_META, audio_language=None, cancel=_never, on_progress=_ignore),
    ]  # fmt: skip
    for call in calls:
        with pytest.raises(YtError) as info:
            call()
        assert info.value.code == "E_FFMPEG_MISSING"


def _stub(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def test_run_ffmpeg_disk_full_maps_to_e_disk_full() -> None:
    args = _stub("import sys; sys.stderr.write('x: No space left on device'); sys.exit(1)")
    with pytest.raises(YtError) as info:
        run_ffmpeg(args, duration_s=None, cancel=_never, on_progress=_ignore)
    assert info.value.code == "E_DISK_FULL"


def test_run_ffmpeg_other_failure_maps_to_e_unknown() -> None:
    args = _stub("import sys; sys.stderr.write('boom'); sys.exit(3)")
    with pytest.raises(YtError) as info:
        run_ffmpeg(args, duration_s=None, cancel=_never, on_progress=_ignore)
    assert info.value.code == "E_UNKNOWN"
    assert "ffmpeg exit 3" in info.value.detail
    assert "boom" in info.value.detail


def test_run_ffmpeg_reports_progress_from_out_time_lines() -> None:
    code = "print('out_time_us=500000'); print('out_time_ms=1500000'); print('out_time_us=9000000'); print('progress=end')"
    seen: list[float | None] = []
    run_ffmpeg(_stub(code), duration_s=2.0, cancel=_never, on_progress=seen.append)
    assert seen == [0.25, 0.75, 1.0]


def test_run_ffmpeg_progress_is_none_without_duration() -> None:
    seen: list[float | None] = []
    run_ffmpeg(_stub("print('out_time_us=500000')"), duration_s=None, cancel=_never, on_progress=seen.append)
    assert seen == [None]


def test_run_ffmpeg_survives_a_failing_progress_callback() -> None:
    # ถ้าตัวอ่าน stdout ตาย pipe จะเต็มแล้วโปรเซสค้าง: สคริปต์นี้พิมพ์เยอะพอจะอุดท่อ
    code = "for i in range(20000): print('out_time_us=%d' % i)"
    calls: list[float | None] = []

    def broken(value: float | None) -> None:
        calls.append(value)
        raise RuntimeError("callback พัง")

    run_ffmpeg(_stub(code), duration_s=1.0, cancel=_never, on_progress=broken)
    assert len(calls) == 20000


def test_run_ffmpeg_missing_executable_is_ffmpeg_missing(tmp_path: Path) -> None:
    with pytest.raises(YtError) as info:
        run_ffmpeg([str(tmp_path / "nope.exe")], duration_s=None, cancel=_never, on_progress=_ignore)
    assert info.value.code == "E_FFMPEG_MISSING"
