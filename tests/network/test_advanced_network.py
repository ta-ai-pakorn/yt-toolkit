"""M5 รอบ A กับยูทูปจริง: ช่วงเวลาตรงเฟรม (AC-ADV-01), แยก chapter (AC-ADV-03), SponsorBlock (AC-ADV-04),
ฝังซับตามช่วงเวลา (AC-VID-10 ส่วนที่ 1) ผ่าน handler ของคิว + yt-dlp จริง + ffmpeg จริง

ต้องได้รับอนุญาตจากพิธก่อนรัน: โหลดไฟล์จริงจากยูทูป (240p) ลง temp ลบทิ้งเมื่อทุกเทสผ่าน
ประมาณการ 30-60 MB รวม: คลิป 372 วิ โหลดเต็ม 3 รอบ (ไฟล์เต็มไว้เทียบเฟรม, ไฟล์ตัดช่วง, ไฟล์ฝังซับ) รอบละราว 8-15 MB
คลิป chapter ของ AC-ADV-03 (วิดีโอ + เสียง ขนาดขึ้นกับคลิปที่พิธเลือก) และคลิป 10 วิ ของ AC-ADV-04 ที่ไม่มีข้อมูล โหลดไม่ถึง 2 MB (ตัวเลขนี้ประมาณ ยังไม่ได้วัดจริง)
รันเองด้วย: uv run pytest -m network -q tests/network/test_advanced_network.py -s
id ของคลิปอยู่ใน tests/network_videos.toml ([advanced]) · sponsor_clip ว่าง = ข้ามกรณีที่มีข้อมูลของ SponsorBlock
chapters_clip ว่าง = ข้าม AC-ADV-03 (พิธต้องเลือกคลิปจริงที่มี chapter ≥ 3 ก่อน)
ยูทูปตอบ 429 หรือขอยืนยันว่าไม่ใช่บอท = เทสตก ให้รายงานผล ห้ามแก้เทสให้หลวมลง
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from helpers_ffmpeg import ffprobe_json, requires_ffmpeg

from yttoolkit.core import thai_fallback as tf
from yttoolkit.core.advanced import merge_intervals
from yttoolkit.core.db import Database
from yttoolkit.core.extractor import YtDlpExtractor, visitor_session, ytdlp_version
from yttoolkit.core.handlers import HandlerDeps, build_handlers
from yttoolkit.core.jobs import Job, JobResult
from yttoolkit.core.media import FfmpegTools
from yttoolkit.core.subtitles import SubtitleService
from yttoolkit.core.videos import VideoService

pytestmark = [pytest.mark.network, requires_ffmpeg]

_TOML = Path(__file__).resolve().parents[1] / "network_videos.toml"
CLIPS: dict[str, str] = tomllib.loads(_TOML.read_text(encoding="utf-8"))["advanced"]
SMALL = 240  # ไฟล์เล็ก โหลดเร็ว (เส้นทางเลือก format ยังเป็นของจริง)
QUEUE_GAP_S = 2
MEDIUM = {"maxChars": 25, "lines": 1, "minMs": 1200, "maxMs": 5000}
VIDEO = {"maxQuality": False, "maxHeight": SMALL, "splitChapters": False, "noAudio": False, "audioLanguage": "original"}
SRT_TIME = re.compile(r"(\d\d):(\d\d):(\d\d),(\d\d\d) --> (\d\d):(\d\d):(\d\d),(\d\d\d)")


class Ctx:
    """JobContext ขั้นต่ำสำหรับเรียก handler ตรง ๆ (ไม่ผ่านคิว)"""

    def __init__(self, workdir: Path, output_root: Path) -> None:
        self.job_id = "01900000-0000-7000-8000-0000000000ab"
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


def _job(kind: str, video_id: str, params: dict[str, Any]) -> Job:
    return Job(
        id="01900000-0000-7000-8000-0000000000ab", video_id=video_id, title="", kind=kind, params=params,
        status="running", stage=None, progress=None, speed_bps=None, eta_s=None, attempt=0, bot_checks=0,
        position=0, error_code=None, error_message=None, error_detail=None, notes=(), outputs=(),
        created_at="2026-10-02T00:00:00Z", started_at=None, finished_at=None,
    )  # fmt: skip


@dataclass
class Env:
    root: Path
    extractor: YtDlpExtractor
    videos: VideoService
    ffmpeg: str
    handlers: dict
    counter: int = 0
    last: float = 0.0

    def run(self, kind: str, video_id: str, params: dict[str, Any]) -> JobResult:
        wait = QUEUE_GAP_S - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.monotonic()
        self.counter += 1
        workdir = self.root / "work" / str(self.counter)
        workdir.mkdir(parents=True)
        return self.handlers[kind](_job(kind, video_id, params), Ctx(workdir, self.root / "output"))


@pytest.fixture(scope="module")
def env(tmp_path_factory: pytest.TempPathFactory, request: pytest.FixtureRequest) -> Iterator[Env]:
    root = tmp_path_factory.mktemp("advanced-network")
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg is not None
    ytdlp_version()
    with pytest.MonkeyPatch.context() as mp:
        # PyThaiNLP สร้างโฟลเดอร์ข้อมูลตอนใช้ครั้งแรก (ซับไทยของเทสฝังซับ) เก็บไว้ใน temp ไม่ใช่ ~/
        mp.setenv(tf.DATA_ENV, str(root / "pythainlp-data"))
        db = Database(root / "app.db")
        db.migrate()
        session = visitor_session(root / "data")
        extractor = YtDlpExtractor(session=session)
        videos = VideoService(db, extractor)
        subs = SubtitleService(videos, extractor.fetch_subtitle, root / "cache", session=session)
        deps = HandlerDeps(
            videos=videos,
            downloader=extractor,  # type: ignore[arg-type]
            media=FfmpegTools(lambda: Path(ffmpeg)),
            subtitles=subs,
            cache_root=root / "cache",
            sponsors=extractor,
        )
        state = Env(root, extractor, videos, ffmpeg, build_handlers(deps))  # type: ignore[arg-type]
        try:
            yield state
        finally:
            extractor.close()
            db.close()
            if request.session.testsfailed:
                print(f"[kept for inspection] {root}")
            else:
                shutil.rmtree(root, ignore_errors=True)


def _path(result: JobResult, index: int = 0) -> Path:
    out = result.outputs[index]
    return Path(out.root) / out.rel


def _duration(path: Path, kind: str) -> float:
    return float(next(s for s in ffprobe_json(path)["streams"] if s["codec_type"] == kind)["duration"])


def _gray(ffmpeg: str, path: Path, at_s: float | None) -> bytes:
    seek = ["-ss", f"{at_s:.3f}"] if at_s is not None else []
    return subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", *seek, "-i", str(path), "-frames:v", "1",
         "-vf", "scale=160:90", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        check=True, capture_output=True,
    ).stdout  # fmt: skip


def _diff(a: bytes, b: bytes) -> float:
    return sum(abs(x - y) for x, y in zip(a, b, strict=True)) / len(a)


def test_ac_adv_01_range_is_frame_exact(env: Env) -> None:
    clip = CLIPS["range_clip"]
    full = env.run("video", clip, dict(VIDEO))
    cut = env.run("video", clip, {**VIDEO, "range": {"startMs": 90_000, "endMs": 300_000}})
    path = _path(cut)
    assert path.name.endswith(" (01.30-05.00).mp4")
    assert abs(_duration(path, "video") - 210.0) <= 0.5
    first = _gray(env.ffmpeg, path, None)
    reference = _path(full)
    at = _diff(first, _gray(env.ffmpeg, reference, 90.0))
    around = min(_diff(first, _gray(env.ffmpeg, reference, 89.0)), _diff(first, _gray(env.ffmpeg, reference, 91.0)))
    assert at < 4.0 and at <= around + 1.0


def test_ac_adv_03_chapter_split_video_and_mp3(env: Env) -> None:
    clip = CLIPS.get("chapters_clip") or ""
    if not clip:
        pytest.skip("พิธเลือกคลิปสาธารณะที่มี chapter อย่างน้อย 3 อัน ใส่ id ใน tests/network_videos.toml [advanced] chapters_clip ก่อนรัน")
    chapters = env.videos.get(clip)["chapters"]
    assert len(chapters) >= 3
    video = env.run("video", clip, {**VIDEO, "splitChapters": True})
    names = [Path(o.rel).name for o in video.outputs]
    assert len(names) == len(chapters)
    assert all(name.startswith(f"{i:02d} - ") and name.endswith(".mp4") for i, name in enumerate(names, start=1))
    assert {Path(o.rel).parent.name for o in video.outputs} == {"แยกตาม chapter (mp4)"}
    for i, chapter in enumerate(chapters):
        length = chapter["endS"] - chapter["startS"]
        assert length - 0.2 <= _duration(_path(video, i), "video") <= length + 3.2  # D6: up to one GOP more
    audio = env.run("audio", clip, {"format": "mp3", "mp3Kbps": 128, "splitChapters": True, "audioLanguage": "original"})
    assert {Path(o.rel).parent.name for o in audio.outputs} == {"แยกตาม chapter (mp3)"}
    for i, chapter in enumerate(chapters):
        assert abs(_duration(_path(audio, i), "audio") - (chapter["endS"] - chapter["startS"])) <= 0.15
    tags = {k.lower(): v for k, v in (ffprobe_json(_path(audio, 0))["format"].get("tags") or {}).items()}
    assert tags.get("track") == f"1/{len(chapters)}"


def test_ac_adv_04_sponsorblock_cuts_the_segments(env: Env) -> None:
    clip = CLIPS.get("sponsor_clip") or ""
    if not clip:
        pytest.skip("ใส่ id คลิปที่มีข้อมูล SponsorBlock ใน tests/network_videos.toml [advanced] sponsor_clip ก่อนรัน")
    info = env.videos.get(clip)
    segments = env.extractor.sponsor_segments(clip, ["sponsor"], float(info["durationS"]))
    assert segments, "คลิปนี้ไม่มีข้อมูล sponsor แล้ว เลือกคลิปใหม่"
    result = env.run("video", clip, {**VIDEO, "sponsorblock": ["sponsor"]})
    path = _path(result)
    assert path.name.endswith(" (ตัดโฆษณา).mp4") and result.notes == ()
    cut_s = sum(e - s for s, e in merge_intervals([(s, e) for s, e, _ in segments])) / 1000
    assert abs(_duration(path, "video") - (info["durationS"] - cut_s)) <= 1.0


def test_ac_adv_04_no_sponsor_data_keeps_the_full_clip(env: Env) -> None:
    result = env.run("video", CLIPS["no_sponsor_clip"], {**VIDEO, "sponsorblock": ["sponsor"]})
    assert result.notes == ("SPONSORBLOCK_EMPTY",)
    assert not _path(result).name.endswith(" (ตัดโฆษณา).mp4")


def test_ac_vid_10_part_1_embedded_subtitles_follow_the_range(env: Env) -> None:
    clip = CLIPS["range_clip"]
    params = {**VIDEO, "embedSubs": "a.th-orig", "subOptions": MEDIUM, "range": {"startMs": 90_000, "endMs": 120_000}}
    path = _path(env.run("video", clip, params))
    srt = subprocess.run(
        [env.ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(path), "-map", "0:s:0", "-f", "srt", "-"],
        check=True, capture_output=True,
    ).stdout.decode("utf-8")  # fmt: skip
    times = [
        (int(a) * 3_600_000 + int(b) * 60_000 + int(c) * 1000 + int(d), int(e) * 3_600_000 + int(f) * 60_000 + int(g) * 1000 + int(h))
        for a, b, c, d, e, f, g, h in SRT_TIME.findall(srt)
    ]
    assert times, "ไม่มีซับในไฟล์"
    assert min(s for s, _ in times) >= 0 and max(e for _, e in times) <= 30_000
