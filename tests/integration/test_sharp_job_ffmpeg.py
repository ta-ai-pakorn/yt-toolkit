"""งานภาพคมทั้งงานกับ ffmpeg จริง (AC-FRAME-03): เวลาตรงตามแผน ภาพกว้าง 1280 และวิดีโอชั่วคราวถูกลบ"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from helpers_ffmpeg import find_test_ffmpeg, requires_ffmpeg
from helpers_sharp import ZOO, SharpEnv
from PIL import Image

from yttoolkit.core.media import FfmpegTools
from yttoolkit.core.sharp_store import read_sharp

pytestmark = requires_ffmpeg


def _ffmpeg() -> str:
    found = find_test_ffmpeg()
    assert found is not None
    return found


@pytest.fixture
def env(tmp_path):
    made = SharpEnv(tmp_path, media=FfmpegTools(lambda: Path(_ffmpeg())))
    clip = tmp_path / "zoo-720.mp4"  # ZOO ยาว 19 วิในข้อมูลคลิป: ภาพที่ 0..18 วิ
    subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", "testsrc2=size=1280x720:rate=5", "-t", "19.5", "-c:v", "libx264", "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p", str(clip)], check=True)  # fmt: skip
    made.downloader.source = clip
    yield made
    made.close()


def test_real_sharp_job_matches_the_plan_and_deletes_the_video(env):
    result, ctx = env.run("frames_sharp", ZOO, {})
    (out,) = result.outputs
    folder = Path(out.root) / out.rel
    files = sorted(folder.iterdir())
    assert out.files == len(files) == 19
    for path in files:
        with Image.open(path) as img:
            assert img.format == "JPEG" and img.size == (1280, 720)
    assert [f["tMs"] for f in read_sharp(env.cache, ZOO)["frames"]] == list(range(0, 19_000, 1000))
    assert not (ctx.workdir / "media.mp4").exists()
    assert result.notes == ("SHARP_LOW_RES:240",)
