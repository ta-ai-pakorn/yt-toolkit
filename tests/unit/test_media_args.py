from __future__ import annotations

import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

from yttoolkit.core import media as media_module
from yttoolkit.core.cancel import JobCancelled
from yttoolkit.core.media import (
    CutCall,
    FakeMediaTools,
    FfmpegTools,
    FrameCall,
    MediaMeta,
    SubtitleInput,
    cut_args,
    frame_args,
    iso639_2,
    m4a_args,
    mp3_args,
    mp4_args,
    run_ffmpeg,
    scale_filter,
    tonemap_filter,
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
MEDIA_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "media"


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


def test_run_ffmpeg_returns_as_soon_as_the_process_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(media_module, "_POLL_SECONDS", 5.0)  # ถ้ายังหลับเต็มรอบ จะช้ากว่า 5 วินาที
    started = time.monotonic()
    run_ffmpeg(_stub("pass"), duration_s=None, cancel=_never, on_progress=_ignore)
    assert time.monotonic() - started < 3


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


CUT_HEAD = [FF, "-hide_banner", "-nostdin", "-y", "-progress", "pipe:1", "-nostats"]
X264 = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]


def test_cut_exact_mp4_one_interval() -> None:
    args = cut_args(FF, SRC, DST, [(90_000, 300_000)], mode="exact", target="mp4", has_audio=True)
    assert args == CUT_HEAD + [
        "-ss", "90.000", "-t", "210.000", "-i", str(SRC),
        "-filter_complex",
        "[0:v:0]setpts=PTS-STARTPTS[v0];[0:a:0]asetpts=PTS-STARTPTS[a0];[v0][a0]concat=n=1:v=1:a=1[v][a]",
        "-map", "[v]", "-map", "[a]", *X264, "-c:a", "aac", "-b:a", "192k", "-f", "mp4", str(DST),
    ]  # fmt: skip


def test_cut_exact_mp4_two_intervals_without_audio() -> None:
    args = cut_args(FF, SRC, DST, [(0, 60_000), (90_000, 635_000)], mode="exact", target="mp4", has_audio=False)
    assert args == CUT_HEAD + [
        "-ss", "0.000", "-t", "60.000", "-i", str(SRC),
        "-ss", "90.000", "-t", "545.000", "-i", str(SRC),
        "-filter_complex", "[0:v:0]setpts=PTS-STARTPTS[v0];[1:v:0]setpts=PTS-STARTPTS[v1];[v0][v1]concat=n=2:v=1:a=0[v]",
        "-map", "[v]", *X264, "-an", "-f", "mp4", str(DST),
    ]  # fmt: skip


def test_cut_fast_mp4_is_a_stream_copy() -> None:
    args = cut_args(FF, SRC, DST, [(5_000, 17_000)], mode="fast", target="mp4", has_audio=True)
    assert args == CUT_HEAD + [
        "-ss", "5.000", "-t", "12.000", "-i", str(SRC), "-map", "0:v:0", "-map", "0:a?",
        "-c", "copy", "-avoid_negative_ts", "make_zero", "-f", "mp4", str(DST),
    ]  # fmt: skip
    silent = cut_args(FF, SRC, DST, [(5_000, 17_000)], mode="fast", target="mp4", has_audio=False)
    assert "0:a?" not in silent


def test_cut_m4a_one_interval_copies_two_intervals_reencode() -> None:
    m4a = Path("in.m4a")
    one = cut_args(FF, m4a, DST, [(9_500, 11_500)], mode="exact", target="m4a", has_audio=True)
    assert one == CUT_HEAD + ["-ss", "9.500", "-t", "2.000", "-i", str(m4a), "-map", "0:a:0", "-c", "copy",
                              "-f", "mp4", str(DST)]
    two = cut_args(FF, m4a, DST, [(9_500, 11_500), (19_000, 22_000)], mode="exact", target="m4a", has_audio=True)
    assert two[-9:] == ["-map", "[a]", "-c:a", "aac", "-b:a", "192k", "-f", "mp4", str(DST)]
    assert "[a0][a1]concat=n=2:v=0:a=1[a]" in two[two.index("-filter_complex") + 1]


def test_cut_wav_is_pcm() -> None:
    args = cut_args(FF, SRC, Path("cut.wav"), [(1_000, 3_000)], mode="exact", target="wav", has_audio=True)
    assert args[-7:] == ["-map", "[a]", "-c:a", "pcm_s16le", "-f", "wav", "cut.wav"]
    assert args[args.index("-filter_complex") + 1] == "[0:a:0]asetpts=PTS-STARTPTS[a0];[a0]concat=n=1:v=0:a=1[a]"


@pytest.mark.parametrize(
    ("intervals", "mode", "target"),
    [([], "exact", "mp4"), ([(5, 5)], "exact", "mp4"), ([(-1000, 0)], "exact", "wav"),
     ([(0, 1000), (2000, 3000)], "fast", "mp4"), ([(0, 1000)], "fast", "m4a")],
)
def test_cut_rejects_bad_requests(intervals, mode, target) -> None:
    with pytest.raises(ValueError):
        cut_args(FF, SRC, DST, intervals, mode=mode, target=target, has_audio=True)


def test_track_metadata_only_when_set() -> None:
    assert "track=3/12" not in mp4_args(FF, SRC, DST, META, cover=None, subtitle=None, audio_language=None)
    with_track = replace(META, track="3/12")
    for args in (
        mp4_args(FF, SRC, DST, with_track, cover=None, subtitle=None, audio_language=None),
        m4a_args(FF, SRC, DST, with_track, cover=None, audio_language=None),
        mp3_args(FF, SRC, DST, with_track, kbps=192, cover=None, audio_language=None),
        wav_args(FF, SRC, DST, with_track, audio_language=None),
    ):
        assert _contains(args, ["-metadata", "track=3/12"])


def test_fake_cut_records_and_copies(tmp_path: Path) -> None:
    fake = FakeMediaTools(MEDIA_ROOT)
    src = tmp_path / "media.mp4"
    src.write_bytes(b"video")
    seen: list[float | None] = []
    fake.cut(src, tmp_path / "cut.mp4", [(0, 1000), (2000, 3000)], mode="exact", target="mp4", has_audio=False,
             cancel=lambda: False, on_progress=seen.append)
    fake.cut(src, tmp_path / "cut.wav", [(0, 1000)], mode="exact", target="wav", has_audio=True,
             cancel=lambda: False, on_progress=seen.append)
    assert (tmp_path / "cut.mp4").read_bytes() == b"video"
    assert (tmp_path / "cut.wav").read_bytes() == (MEDIA_ROOT / "audio.wav").read_bytes()
    assert fake.cuts == [
        CutCall("media.mp4", "cut.mp4", ((0, 1000), (2000, 3000)), "exact", "mp4", False),
        CutCall("media.mp4", "cut.wav", ((0, 1000),), "exact", "wav", True),
    ]
    assert seen == [1.0, 1.0]
    with pytest.raises(JobCancelled):
        fake.cut(src, tmp_path / "x.mp4", [(0, 1000)], mode="fast", target="mp4", has_audio=True,
                 cancel=lambda: True, on_progress=seen.append)


@pytest.mark.parametrize(
    ("intervals", "target"),
    [([(0, 1000)], "m4a"), ([(0, 1000)], "wav"), ([(0, 1000), (2000, 3000)], "mp4")],
)
def test_fake_cut_rejects_what_the_real_cutter_rejects(tmp_path: Path, intervals, target) -> None:
    # ตัวปลอมต้องพังเหมือนตัวจริง ไม่งั้น handler ที่เรียกผิดจะผ่านเทสในโหมดปลอม
    with pytest.raises(ValueError) as real:
        cut_args(FF, SRC, DST, intervals, mode="fast", target=target, has_audio=True)
    fake = FakeMediaTools(MEDIA_ROOT)
    src = tmp_path / "media.mp4"
    src.write_bytes(b"video")
    dst = tmp_path / f"cut.{target}"
    with pytest.raises(ValueError) as faked:
        fake.cut(src, dst, intervals, mode="fast", target=target, has_audio=True,
                 cancel=lambda: False, on_progress=lambda _: None)
    assert str(faked.value) == str(real.value) == "fast cut takes exactly one interval of an mp4"
    assert fake.cuts == [] and not dst.exists()


# ---------- ภาพคม (M5 รอบ B spec 3.4) ----------

SCALE = "scale=w='min(1280,iw)':h='min(1280,ih)':force_original_aspect_ratio=decrease"
FRAME_HEAD = [FF, "-hide_banner", "-nostdin", "-y", "-loglevel", "error"]
JPG = Path("f.jpg")


def _no_cancel() -> bool:
    return False


def test_frame_args_sdr_exact() -> None:
    assert scale_filter(1280) == SCALE
    assert frame_args(FF, SRC, JPG, 61_500) == FRAME_HEAD + [
        "-ss", "61.500", "-i", str(SRC), "-frames:v", "1", "-vf", SCALE, "-q:v", "2", str(JPG)]  # fmt: skip


def test_frame_args_hdr_puts_the_tone_map_before_the_scale() -> None:
    args = frame_args(FF, SRC, JPG, 0, dynamic_range="HDR10")
    vf = args[args.index("-vf") + 1]
    assert vf == tonemap_filter("HDR10") + "," + SCALE
    assert vf.startswith("setparams=range=tv:color_primaries=bt2020:color_trc=smpte2084:colorspace=bt2020nc,zscale=t=linear")
    assert "tonemap=tonemap=hable:desat=0" in vf and "format=yuv420p" in vf
    assert "color_trc=arib-std-b67" in tonemap_filter("HLG")


@pytest.mark.parametrize(
    ("t_ms", "long_side", "dynamic_range"),
    [(-1, 1280, None), (0, 0, None), (0, 1280, "SDR"), (0, 1280, ""), (True, 1280, None)],
)
def test_frame_args_rejects_bad_input(t_ms, long_side, dynamic_range) -> None:
    with pytest.raises(ValueError):
        frame_args(FF, SRC, JPG, t_ms, long_side=long_side, dynamic_range=dynamic_range)
    with pytest.raises(ValueError):
        FakeMediaTools(MEDIA_ROOT).extract_frame(
            MEDIA_ROOT / "video.mp4", JPG, t_ms, long_side=long_side, dynamic_range=dynamic_range, cancel=_no_cancel)


def test_fake_extract_frame_copies_the_cover_and_records(tmp_path: Path) -> None:
    fake = FakeMediaTools(MEDIA_ROOT)
    dst = tmp_path / "0001.jpg"
    assert fake.extract_frame(MEDIA_ROOT / "video.mp4", dst, 1000, long_side=1280, dynamic_range=None,
                              cancel=_no_cancel) is True  # fmt: skip
    assert dst.read_bytes() == (MEDIA_ROOT / "cover.jpg").read_bytes()
    assert fake.frames == [FrameCall("video.mp4", "0001.jpg", 1000, 1280, None)]


def test_fake_extract_frame_limit_missing_input_and_cancel(tmp_path: Path) -> None:
    fake = FakeMediaTools(MEDIA_ROOT)
    fake.frame_limit_ms = 2000
    late = tmp_path / "late.jpg"
    assert fake.extract_frame(MEDIA_ROOT / "video.mp4", late, 2000, long_side=1280, dynamic_range=None,
                              cancel=_no_cancel) is False  # fmt: skip
    assert not late.exists()
    gone = tmp_path / "gone.jpg"
    assert fake.extract_frame(tmp_path / "missing.mp4", gone, 0, long_side=1280, dynamic_range=None,
                              cancel=_no_cancel) is False  # fmt: skip
    with pytest.raises(JobCancelled):
        fake.extract_frame(MEDIA_ROOT / "video.mp4", tmp_path / "c.jpg", 0, long_side=1280, dynamic_range=None,
                           cancel=lambda: True)  # fmt: skip
    assert not (tmp_path / "c.jpg").exists()


def test_ffmpeg_extract_frame_failure_is_a_dropped_frame(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def failing(args, **kwargs):
        Path(args[-1]).write_bytes(b"half")
        raise YtError("E_UNKNOWN", "ffmpeg exit 234: Nothing was written into output file")

    monkeypatch.setattr(media_module, "run_ffmpeg", failing)
    dst = tmp_path / "x.jpg"
    tools = FfmpegTools(lambda: Path("ffmpeg"))
    assert tools.extract_frame(tmp_path / "in.mp4", dst, 0, long_side=1280, dynamic_range=None, cancel=_no_cancel) is False
    assert not dst.exists()


@pytest.mark.parametrize("code", ["E_DISK_FULL", "E_FFMPEG_MISSING"])
def test_ffmpeg_extract_frame_passes_other_errors_on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: str) -> None:
    def failing(args, **kwargs):
        raise YtError(code, "x")

    monkeypatch.setattr(media_module, "run_ffmpeg", failing)
    with pytest.raises(YtError) as err:
        FfmpegTools(lambda: Path("ffmpeg")).extract_frame(
            tmp_path / "in.mp4", tmp_path / "x.jpg", 0, long_side=1280, dynamic_range=None, cancel=_no_cancel)
    assert err.value.code == code


def test_ffmpeg_extract_frame_success_and_missing_ffmpeg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def writing(args, **kwargs):
        seen.append(args)
        Path(args[-1]).write_bytes(b"\xff\xd8jpeg")

    monkeypatch.setattr(media_module, "run_ffmpeg", writing)
    dst = tmp_path / "ok.jpg"
    assert FfmpegTools(lambda: Path("ffmpeg")).extract_frame(
        tmp_path / "in.mp4", dst, 2500, long_side=1280, dynamic_range="HDR10", cancel=_no_cancel) is True
    assert seen[0][seen[0].index("-ss") + 1] == "2.500" and "setparams" in seen[0][seen[0].index("-vf") + 1]
    with pytest.raises(YtError) as err:
        FfmpegTools(lambda: None).extract_frame(tmp_path / "in.mp4", dst, 0, long_side=1280, dynamic_range=None,
                                                cancel=_no_cancel)  # fmt: skip
    assert err.value.code == "E_FFMPEG_MISSING"


def test_ffmpeg_extract_frame_checks_cancel_before_starting_ffmpeg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """เหมือนตัวปลอม: ยกเลิกแล้วต้องไม่เปิด ffmpeg เลย (ffmpeg ภาพเดียวจบเร็วกว่ารอบเช็กยกเลิกของ run_ffmpeg)"""

    def must_not_run(args, **kwargs):
        raise AssertionError("ffmpeg must not start after a cancel")

    monkeypatch.setattr(media_module, "run_ffmpeg", must_not_run)
    with pytest.raises(JobCancelled):
        FfmpegTools(lambda: Path("ffmpeg")).extract_frame(
            tmp_path / "in.mp4", tmp_path / "c.jpg", 0, long_side=1280, dynamic_range=None, cancel=lambda: True)
