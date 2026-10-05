"""ถ่ายภาพคมตรงจุดกับ ffmpeg จริง (M5 รอบ B2 spec 6): ชิ้นจาก sidx ตัวจริง ภาพต้องตรงกับภาพจากไฟล์เต็มที่เวลาเดียวกัน
และได้ความละเอียดต้นฉบับ (1920×1080 ไม่ย่อ) · ไม่ต่อเน็ต"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from helpers_capture import BBB, PIECE, FakeVideos, FixtureFetcher, StubQueue, StubSettings, clip_info
from helpers_ffmpeg import find_test_ffmpeg, requires_ffmpeg
from PIL import Image

from yttoolkit.core.capture import CaptureService
from yttoolkit.core.media import FfmpegTools

pytestmark = requires_ffmpeg


def _ffmpeg() -> str:
    found = find_test_ffmpeg()
    assert found is not None
    return found


def _service(tmp_path: Path) -> CaptureService:
    return CaptureService(FakeVideos({BBB: clip_info(duration_s=4)}), FixtureFetcher(), FfmpegTools(lambda: Path(_ffmpeg())),
                          tmp_path / "cache", StubSettings(tmp_path / "out"), StubQueue(), work_root=tmp_path / "work")  # fmt: skip


def _reference(at_s: float, folder: Path) -> Path:
    """ภาพจากไฟล์เต็ม (ไม่ผ่านการตัดชิ้น) ที่เวลาเดียวกัน คำสั่งแบบเดียวกับตัวทำงาน"""
    out = folder / f"ref-{at_s:.3f}.jpg"
    subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{at_s:.3f}", "-i", str(PIECE),
                    "-frames:v", "1", "-q:v", "2", str(out)], check=True)  # fmt: skip
    return out


def _gray(path: Path) -> bytes:
    with Image.open(path) as img:
        return img.convert("L").resize((480, 270)).tobytes()


def _diff(a: bytes, b: bytes) -> float:
    return sum(abs(x - y) for x, y in zip(a, b, strict=True)) / len(a)


@pytest.mark.parametrize("t_ms", [0, 1_000, 2_550, 3_500])
def test_piece_frame_equals_the_full_file_frame(tmp_path: Path, t_ms: int) -> None:
    service = _service(tmp_path)
    capture, created = service.capture(BBB, t_ms)
    assert created and (capture.width, capture.height) == (1920, 1080)
    here = _gray(service.cache_path(BBB, capture))
    same = _gray(_reference(t_ms / 1000, tmp_path))
    other = _gray(_reference(((t_ms + 1_500) % 4_000) / 1000, tmp_path))
    assert _diff(here, same) < 0.5 < _diff(here, other)


def test_last_fraction_retries_and_still_gets_a_frame(tmp_path: Path) -> None:
    service = _service(tmp_path)
    capture, _ = service.capture(BBB, 3_950)  # ภาพสุดท้ายอยู่ที่ 3.9 วินาที: 3.95 ไม่มีภาพ ถอยไป 3.85 แล้วได้ภาพ 3.9
    assert _diff(_gray(service.cache_path(BBB, capture)), _gray(_reference(3.85, tmp_path))) < 0.5
