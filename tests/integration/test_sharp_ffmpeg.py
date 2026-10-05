"""ภาพคม (M5 รอบ B) กับ ffmpeg จริง: ด้านยาว 1280 (แนวนอน/แนวตั้ง) ไม่ขยายภาพเล็ก ภาพตรงเวลา ภาพท้ายคลิปไม่มี และ tone-map"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from helpers_ffmpeg import find_test_ffmpeg, requires_ffmpeg
from PIL import Image

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


def _clip(folder: Path, name: str, size: str, *extra: str) -> Path:
    out = folder / name
    subprocess.run(
        [_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=10",
         "-t", "6", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", *extra, str(out)],
        check=True,
    )  # fmt: skip
    return out


@pytest.fixture(scope="module")
def clips(tmp_path_factory) -> dict[str, Path]:
    folder = tmp_path_factory.mktemp("sharp")
    return {
        "wide": _clip(folder, "wide.mp4", "1920x1080"),
        "portrait": _clip(folder, "portrait.mp4", "1080x1920"),
        "hdr": _clip(folder, "hdr.mp4", "1280x720", "-color_primaries", "bt2020", "-color_trc", "smpte2084",
                     "-colorspace", "bt2020nc"),
    }  # fmt: skip


def _never() -> bool:
    return False


def _size(path: Path) -> tuple[int, int]:
    with Image.open(path) as img:
        assert img.format == "JPEG"
        return img.size


def _gray(path: Path) -> bytes:
    with Image.open(path) as img:
        return img.convert("L").resize((160, 90)).tobytes()


def _decoded(src: Path, at_s: float, folder: Path) -> Path:
    out = folder / f"ref-{at_s}.png"
    subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{at_s:.3f}", "-i", str(src),
                    "-frames:v", "1", str(out)], check=True)  # fmt: skip
    return out


def test_wide_long_side_is_1280_and_the_picture_is_at_the_timecode(clips, tmp_path: Path) -> None:
    dst = tmp_path / "w.jpg"
    assert _tools().extract_frame(clips["wide"], dst, 3000, long_side=1280, dynamic_range=None, cancel=_never) is True
    assert _size(dst) == (1280, 720)
    here, other = _gray(dst), _gray(_decoded(clips["wide"], 3.0, tmp_path))
    later = _gray(_decoded(clips["wide"], 4.5, tmp_path))
    diff = sum(abs(a - b) for a, b in zip(here, other, strict=True)) / len(here)
    far = sum(abs(a - b) for a, b in zip(here, later, strict=True)) / len(here)
    assert diff < far and diff < 8


def test_portrait_becomes_720_by_1280(clips, tmp_path: Path) -> None:  # D4
    dst = tmp_path / "p.jpg"
    assert _tools().extract_frame(clips["portrait"], dst, 1000, long_side=1280, dynamic_range=None, cancel=_never)
    assert _size(dst) == (720, 1280)


def test_small_video_is_never_upscaled(tmp_path: Path) -> None:
    dst = tmp_path / "s.jpg"
    assert _tools().extract_frame(MEDIA / "video.mp4", dst, 1000, long_side=1280, dynamic_range=None, cancel=_never)
    assert _size(dst) == (160, 90)


def test_a_timecode_past_the_last_frame_yields_no_image(tmp_path: Path) -> None:
    dst = tmp_path / "late.jpg"
    assert _tools().extract_frame(MEDIA / "video.mp4", dst, 1950, long_side=1280, dynamic_range=None,
                                  cancel=_never) is False  # fmt: skip
    assert not dst.exists()


def test_hdr_tone_map_chain_runs(clips, tmp_path: Path) -> None:
    dst = tmp_path / "h.jpg"
    assert _tools().extract_frame(clips["hdr"], dst, 1000, long_side=1280, dynamic_range="HDR10", cancel=_never)
    assert _size(dst) == (1280, 720)


def test_cancel_stops_the_extraction(clips, tmp_path: Path) -> None:
    with pytest.raises(JobCancelled):
        _tools().extract_frame(clips["wide"], tmp_path / "c.jpg", 0, long_side=1280, dynamic_range=None,
                               cancel=lambda: True)  # fmt: skip
