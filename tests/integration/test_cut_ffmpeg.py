"""ตัวตัดของ M5 รอบ A กับ ffmpeg จริง (ข้ามเมื่อเครื่องไม่มี ffmpeg): ความยาว ภาพแรกตรงเฟรม การยกเลิก"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from helpers_ffmpeg import ffprobe_json, find_test_ffmpeg, requires_ffmpeg

from yttoolkit.core.cancel import JobCancelled
from yttoolkit.core.media import FfmpegTools

pytestmark = requires_ffmpeg
MEDIA = Path(__file__).resolve().parents[1] / "fixtures" / "media"


def _ffmpeg() -> str:
    found = find_test_ffmpeg()
    assert found is not None
    return found


def _tools() -> FfmpegTools:
    return FfmpegTools(lambda: Path(_ffmpeg()))


def _durations(path: Path) -> dict[str, float]:
    return {s["codec_type"]: float(s["duration"]) for s in ffprobe_json(path)["streams"]}


@pytest.fixture(scope="module")
def gop_clip(tmp_path_factory) -> Path:
    """คลิป 20 วิ 30 fps keyframe ทุก 4 วิ (เหมือนคลิปยูทูปที่ keyframe ห่าง) ภาพเปลี่ยนทุกเฟรม"""
    out = tmp_path_factory.mktemp("cut") / "src.mp4"
    subprocess.run(
        [_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30",
         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100", "-t", "20", "-c:v", "libx264", "-g", "120",
         "-keyint_min", "120", "-sc_threshold", "0", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out)],
        check=True,
    )  # fmt: skip
    return out


def _gray_frame(path: Path, at_s: float | None) -> bytes:
    seek = ["-ss", f"{at_s:.3f}"] if at_s is not None else []
    return subprocess.run(
        [_ffmpeg(), "-hide_banner", "-loglevel", "error", *seek, "-i", str(path), "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        check=True, capture_output=True,
    ).stdout  # fmt: skip


def _diff(a: bytes, b: bytes) -> float:
    return sum(abs(x - y) for x, y in zip(a, b, strict=True)) / len(a)


def _never() -> bool:
    return False


def test_exact_cut_starts_on_the_requested_frame(gop_clip: Path, tmp_path: Path) -> None:
    out = tmp_path / "cut.mp4"
    seen: list[float | None] = []
    _tools().cut(gop_clip, out, [(10_000, 15_000)], mode="exact", target="mp4", has_audio=True,
                 cancel=_never, on_progress=seen.append)
    durations = _durations(out)
    assert abs(durations["video"] - 5.0) <= 0.05 and abs(durations["audio"] - 5.0) <= 0.05
    first = _gray_frame(out, None)
    assert _diff(first, _gray_frame(gop_clip, 10.0)) < _diff(first, _gray_frame(gop_clip, 10.0 + 1 / 30)) / 3
    assert seen and max(v for v in seen if v is not None) <= 1.0


def test_exact_cut_joins_several_intervals(gop_clip: Path, tmp_path: Path) -> None:
    out = tmp_path / "ads.mp4"
    _tools().cut(gop_clip, out, [(2_000, 7_000), (13_000, 20_000)], mode="exact", target="mp4", has_audio=True,
                 cancel=_never, on_progress=lambda _: None)
    assert abs(_durations(out)["video"] - 12.0) <= 0.05


def test_fast_cut_starts_at_the_keyframe_before(gop_clip: Path, tmp_path: Path) -> None:
    out = tmp_path / "fast.mp4"
    _tools().cut(gop_clip, out, [(10_000, 15_000)], mode="fast", target="mp4", has_audio=True,
                 cancel=_never, on_progress=lambda _: None)
    assert 5.0 <= _durations(out)["video"] <= 7.2  # keyframe at 8 s: up to one GOP earlier (D6)


def test_audio_cuts_are_within_50_ms(tmp_path: Path) -> None:
    tools = _tools()
    one = tmp_path / "one.m4a"
    tools.cut(MEDIA / "audio.m4a", one, [(500, 1_500)], mode="exact", target="m4a", has_audio=True,
              cancel=_never, on_progress=lambda _: None)
    assert abs(_durations(one)["audio"] - 1.0) <= 0.05
    wav = tmp_path / "two.wav"
    tools.cut(MEDIA / "audio.m4a", wav, [(0, 500), (1_000, 1_800)], mode="exact", target="wav", has_audio=True,
              cancel=_never, on_progress=lambda _: None)
    assert abs(_durations(wav)["audio"] - 1.3) <= 0.05


def test_cancel_kills_the_cut(gop_clip: Path, tmp_path: Path) -> None:
    with pytest.raises(JobCancelled):
        _tools().cut(gop_clip, tmp_path / "x.mp4", [(0, 20_000)], mode="exact", target="mp4", has_audio=True,
                     cancel=lambda: True, on_progress=lambda _: None)
