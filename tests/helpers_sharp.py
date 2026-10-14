"""ตัวช่วยเทสของภาพคม (M5 รอบ B): บริการจริงบนฐานข้อมูลชั่วคราว (FakeExtractor) ตัวโหลดปลอมที่บอกขนาดไฟล์ได้
และ FakeMediaTools (ภาพคม = สำเนา cover.jpg) · ใช้ใน tests/unit/test_handlers_sharp.py, test_handlers_auto_sharp.py
และ tests/integration/test_sharp_job_ffmpeg.py (import แบบ helpers_ffmpeg)"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from yttoolkit.core.cancel import JobCancelled
from yttoolkit.core.db import Database
from yttoolkit.core.download import DownloadChoice, DownloadHooks, DownloadResult, MediaFacts
from yttoolkit.core.extractor import FakeExtractor
from yttoolkit.core.handlers import HandlerDeps, build_handlers
from yttoolkit.core.jobs import Job, JobResult
from yttoolkit.core.media import FakeMediaTools, MediaTools
from yttoolkit.core.subtitles import SubtitleService
from yttoolkit.core.videos import VideoService
from yttoolkit.core.yterrors import YtError

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MEDIA = FIXTURES / "media"
BBB = "aqz-KE-bpKQ"  # 635 วิ ภาพเร็ว 128 ภาพ format ภาพคม = 298 (avc1 1280x720)
BBB_TITLE = "Big Buck Bunny 60fps 4K - Official Blender Foundation Short Film"
ZOO = "jNQXAC9IVRw"  # 19 วิ ไม่มี storyboard สูงสุด 240p
NOW = datetime(2026, 10, 5, 3, 0, tzinfo=UTC)
JOB_ID = "01900000-0000-7000-8000-000000000001"
PLENTY = 10**13
VIDEO = {"maxQuality": False, "splitChapters": False, "noAudio": False, "audioLanguage": "original"}


class Ctx:
    """JobContext ที่จดขั้น ความคืบหน้า ชื่องาน · cancel_on = ตั้งธงยกเลิกเมื่อถึงขั้นนี้ (เช่น "extracting_frames:2/11")"""

    def __init__(self, workdir: Path, output_root: Path, cancel_on: str | None = None) -> None:
        self.job_id = JOB_ID
        self.workdir = workdir
        self.output_root = output_root
        self.filename_style = "title"  # M6 รอบ A: JobContext.filename_style
        self.cancel_on = cancel_on
        self.stages: list[str] = []
        self.progresses: list[tuple[float | None, int | None, int | None]] = []
        self.titles: list[str] = []
        self._cancelled = False

    def stage(self, stage: str) -> None:
        self.stages.append(stage)
        if stage == self.cancel_on:
            self._cancelled = True

    def progress(self, fraction: float | None, speed_bps: int | None = None, eta_s: int | None = None) -> None:
        self.progresses.append((fraction, speed_bps, eta_s))

    def set_title(self, title: str) -> None:
        self.titles.append(title)

    def cancelled(self) -> bool:
        return self._cancelled

    def check_cancelled(self) -> None:
        if self._cancelled:
            raise JobCancelled()

    def wait(self, seconds: float) -> None:
        self.check_cancelled()


class SharpDownloader:
    """Downloader ปลอม: choose ได้ probe ของ FakeExtractor (formats_hook แก้รายการ format ได้) แล้วคัดลอกไฟล์จิ๋ว
    งานที่ format มี "+" (วิดีโอ + เสียง) ได้ video.mp4 · นอกนั้นได้ source (ค่าเริ่มต้น video-noaudio.mp4) · media = ที่รายงาน"""

    def __init__(self, fake: FakeExtractor) -> None:
        self.fake = fake
        self.source = MEDIA / "video-noaudio.mp4"
        self.media: MediaFacts | None = None
        self.formats_hook: Callable[[list[dict]], list[dict]] | None = None
        self.choices: list[DownloadChoice] = []

    def download(
        self, video_id: str, choose: Callable[[dict], DownloadChoice], workdir: Path, hooks: DownloadHooks
    ) -> DownloadResult:
        info = self.fake.probe(video_id)
        if self.formats_hook is not None:
            info["formats"] = self.formats_hook(info["formats"])
        choice = choose(info)
        self.choices.append(choice)
        hooks.on_stage("downloading_video")
        for step in (1, 2):
            if hooks.is_cancelled():
                raise JobCancelled()
            hooks.on_progress(step / 2, 1_000_000, 2 - step)
        merged = "+" in choice.format_spec
        target = Path(workdir) / "media.mp4"
        shutil.copyfile(MEDIA / "video.mp4" if merged else self.source, target)
        return DownloadResult(target, info, choice, self.media)

    def fetch(self, url: str) -> bytes:
        if url.startswith(FakeExtractor.STORYBOARD_PREFIX):
            return self.fake.fetch(url)
        raise YtError("E_NETWORK", "fake: ไม่มีภาพปก")


def make_job(kind: str, video_id: str, params: dict) -> Job:
    return Job(
        id=JOB_ID, video_id=video_id, title="", kind=kind, params=params, status="running", stage=None,
        progress=None, speed_bps=None, eta_s=None, attempt=0, bot_checks=0, position=1, error_code=None,
        error_message=None, error_detail=None, notes=(), outputs=(), created_at="2026-10-05T03:00:00.000000+00:00",
        started_at="2026-10-05T03:00:01.000000+00:00", finished_at=None,
    )  # fmt: skip


class SharpEnv:
    def __init__(self, tmp_path: Path, media: MediaTools | None = None) -> None:
        self.tmp = tmp_path
        self.db = Database(tmp_path / "app.db")
        self.db.migrate()
        self.fake = FakeExtractor(FIXTURES)
        self.videos = VideoService(self.db, self.fake, now=lambda: NOW)
        self.subtitles = SubtitleService(self.videos, self.fake.fetch_subtitle, tmp_path / "cache")
        self.downloader = SharpDownloader(self.fake)
        self.media = media if media is not None else FakeMediaTools(MEDIA)
        self.out = tmp_path / "out"
        self.cache = tmp_path / "cache"
        self.free = PLENTY
        self.deps = HandlerDeps(
            videos=self.videos,
            downloader=self.downloader,
            media=self.media,
            subtitles=self.subtitles,
            cache_root=self.cache,
            now=lambda: NOW,
            disk_free=lambda _path: self.free,
        )
        self._runs = 0

    def run(
        self,
        kind: str,
        video_id: str,
        params: dict,
        *,
        cancel_on: str | None = None,
        deps: HandlerDeps | None = None,
        style: str = "title",
    ) -> tuple[JobResult, Ctx]:
        self._runs += 1
        workdir = self.tmp / "work" / str(self._runs)
        workdir.mkdir(parents=True)
        ctx = Ctx(workdir, self.out, cancel_on=cancel_on)
        ctx.filename_style = style
        handler = build_handlers(deps or self.deps)[kind]
        return handler(make_job(kind, video_id, params), ctx), ctx

    def close(self) -> None:
        self.db.close()
