"""M5 รอบ B กับยูทูปจริง: งานภาพคมผ่าน handler ของคิว + yt-dlp จริง + ffmpeg จริง (AC-FRAME-03, D4)

ต้องได้รับอนุญาตจากพิธก่อนรัน: โหลดวิดีโออย่างเดียว 720p ราว 40-70 MB ลง temp ลบทิ้งเมื่อทุกเทสผ่าน
รันเองด้วย: uv run pytest -m network -q tests/network/test_sharp_network.py -s
id ของคลิปอยู่ใน tests/network_videos.toml ([sharp]) · ยูทูปตอบ 429 หรือขอยืนยันว่าไม่ใช่บอท = เทสตก ให้รายงานผล ห้ามแก้เทสให้หลวมลง
"""

from __future__ import annotations

import shutil
import time
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from helpers_ffmpeg import requires_ffmpeg
from PIL import Image

from yttoolkit.core.db import Database
from yttoolkit.core.extractor import YtDlpExtractor, visitor_session, ytdlp_version
from yttoolkit.core.handlers import HandlerDeps, build_handlers
from yttoolkit.core.jobs import Job, JobResult
from yttoolkit.core.media import FfmpegTools
from yttoolkit.core.sharp_store import read_sharp
from yttoolkit.core.subtitles import SubtitleService
from yttoolkit.core.videos import VideoService

pytestmark = [pytest.mark.network, requires_ffmpeg]

_TOML = Path(__file__).resolve().parents[1] / "network_videos.toml"
CLIPS: dict[str, str] = tomllib.loads(_TOML.read_text(encoding="utf-8"))["sharp"]
QUEUE_GAP_S = 2
JOB_ID = "01900000-0000-7000-8000-0000000000bb"


class Ctx:
    """JobContext ขั้นต่ำสำหรับเรียก handler ตรง ๆ (ไม่ผ่านคิว)"""

    def __init__(self, workdir: Path, output_root: Path) -> None:
        self.job_id = JOB_ID
        self.workdir = workdir
        self.output_root = output_root

    def stage(self, stage: str) -> None:
        return None

    def progress(self, fraction: float | None, speed_bps: int | None = None, eta_s: int | None = None) -> None:
        return None

    def set_title(self, title: str) -> None:
        return None

    def cancelled(self) -> bool:
        return False

    def check_cancelled(self) -> None:
        return None

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)


def _job(video_id: str, params: dict[str, Any]) -> Job:
    return Job(
        id=JOB_ID, video_id=video_id, title="", kind="frames_sharp", params=params, status="running", stage=None,
        progress=None, speed_bps=None, eta_s=None, attempt=0, bot_checks=0, position=0, error_code=None,
        error_message=None, error_detail=None, notes=(), outputs=(), created_at="2026-10-05T00:00:00Z",
        started_at=None, finished_at=None,
    )  # fmt: skip


@dataclass
class Env:
    root: Path
    handlers: dict
    counter: int = 0
    last: float = 0.0

    def run(self, video_id: str, params: dict[str, Any]) -> tuple[JobResult, Path]:
        wait = QUEUE_GAP_S - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.monotonic()
        self.counter += 1
        workdir = self.root / "work" / str(self.counter)
        workdir.mkdir(parents=True)
        return self.handlers["frames_sharp"](_job(video_id, params), Ctx(workdir, self.root / "output")), workdir


@pytest.fixture(scope="module")
def env(tmp_path_factory: pytest.TempPathFactory, request: pytest.FixtureRequest) -> Iterator[Env]:
    root = tmp_path_factory.mktemp("sharp-network")
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg is not None
    ytdlp_version()
    db = Database(root / "app.db")
    db.migrate()
    session = visitor_session(root / "data")
    extractor = YtDlpExtractor(session=session)
    videos = VideoService(db, extractor)
    deps = HandlerDeps(
        videos=videos,
        downloader=extractor,  # type: ignore[arg-type]
        media=FfmpegTools(lambda: Path(ffmpeg)),
        subtitles=SubtitleService(videos, extractor.fetch_subtitle, root / "cache", session=session),
        cache_root=root / "cache",
    )
    try:
        yield Env(root, build_handlers(deps))
    finally:
        extractor.close()
        db.close()
        if request.session.testsfailed:
            print(f"[kept for inspection] {root}")
        else:
            shutil.rmtree(root, ignore_errors=True)


def _sizes(folder: Path) -> set[tuple[int, int]]:
    out = set()
    for path in folder.iterdir():
        with Image.open(path) as img:
            assert img.format == "JPEG"
            out.add(img.size)
    return out


def test_ac_frame_03_landscape_1280_and_the_video_is_deleted(env: Env) -> None:
    result, workdir = env.run(CLIPS["clip"], {"intervalS": 60})
    (out,) = result.outputs
    folder = Path(out.root) / out.rel
    assert out.kind == "folder" and out.files == 7  # 372 วิ: 0, 60, ..., 360
    assert _sizes(folder) == {(1280, 720)}
    assert [f["tMs"] for f in read_sharp(env.root / "cache", CLIPS["clip"])["frames"]] == list(range(0, 420_000, 60_000))
    assert not list(workdir.glob("media.*"))


def test_d4_portrait_clip_gives_720_by_1280(env: Env) -> None:
    result, _ = env.run(CLIPS["portrait_clip"], {"intervalS": 10})
    (out,) = result.outputs
    assert _sizes(Path(out.root) / out.rel) == {(720, 1280)}
