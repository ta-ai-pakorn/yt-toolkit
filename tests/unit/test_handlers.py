"""ตัวทำงานของงานในคิว (core/handlers.py): video, audio, subtitle, contact_sheet, frames_zip

ใช้บริการจริงบนฐานข้อมูลชั่วคราว (VideoService + SubtitleService บน FakeExtractor) ตัวโหลดแบบ stub
ตามสัญญา C8 (FakeExtractor.download เป็นของ T9) FakeMediaTools (ไม่ใช้ ffmpeg) และ context ที่จดทุกอย่างไว้
ไม่แตะเครือข่าย เทสที่ใช้ ffmpeg จริงข้ามเองเมื่อเครื่องไม่มี ffmpeg
"""

from __future__ import annotations

import io
import logging
import shutil
import zipfile
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from helpers_ffmpeg import ffprobe_json, find_test_ffmpeg, requires_ffmpeg
from yttoolkit.core import files
from yttoolkit.core.cancel import JobCancelled
from yttoolkit.core.db import Database
from yttoolkit.core.advanced import ADS_SUFFIX
from yttoolkit.core.download import (
    DownloadChoice,
    Downloader,
    DownloadHooks,
    DownloadResult,
    SponsorBlockError,
    audio_choice,
    video_choice,
)
from yttoolkit.core.extractor import FakeExtractor
from yttoolkit.core.handlers import HandlerDeps, build_handlers
from yttoolkit.core.jobs import Job, JobResult
from yttoolkit.core.media import CutCall, FakeMediaTools, FfmpegTools
from yttoolkit.core.srt_builder import PRESETS, options_from_dict
from yttoolkit.core.subtitles import SubtitleService
from yttoolkit.core.videos import VideoService
from yttoolkit.core.yterrors import YtError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
MEDIA = FIXTURES / "media"
BBB = "aqz-KE-bpKQ"  # ไม่มีซับ มี storyboard เสียงไม่ระบุภาษา
BBB_TITLE = "Big Buck Bunny 60fps 4K - Official Blender Foundation Short Film"
ZOO = "jNQXAC9IVRw"  # เสียงไม่ระบุภาษา
THAI = "88o5Sk8_m1Y"  # ซับ a.th-orig, license Creative Commons
THAI_TITLE = "Thai Listening Practice | EP.1 | Beginner"
NOW = datetime(2026, 10, 2, 5, 30, tzinfo=UTC)
MEDIUM = {"maxChars": 25, "lines": 1, "minMs": 1200, "maxMs": 5000}
PLENTY = 10**13


# ---------- ตัวช่วยเทส ----------


class RecordingContext:
    """JobContext ที่จดขั้นตอน ความคืบหน้า ชื่องาน และการรอ `cancel_on` = ตั้งธงยกเลิกเมื่อถึงขั้นนี้"""

    def __init__(self, workdir: Path, output_root: Path, cancel_on: str | None = None) -> None:
        self.job_id = "01900000-0000-7000-8000-000000000001"
        self.workdir = workdir
        self.output_root = output_root
        self.cancel_on = cancel_on
        self.stages: list[str] = []
        self.progresses: list[tuple[float | None, int | None, int | None]] = []
        self.titles: list[str] = []
        self.waits: list[float] = []
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
        self.waits.append(seconds)
        self.check_cancelled()


class StubDownloader:
    """Downloader ตามสัญญา C8 แบบ "Fake": เลือก format จาก probe ของ FakeExtractor แล้วคัดลอกไฟล์สื่อจริงขนาดเล็ก"""

    def __init__(self, fake: FakeExtractor, cover: bytes | None = None) -> None:
        self.fake = fake
        self.cover = cover
        self.choices: list[DownloadChoice] = []
        self.hooks: list[DownloadHooks] = []
        self.fetched: list[str] = []

    def download(
        self, video_id: str, choose: Callable[[dict], DownloadChoice], workdir: Path, hooks: DownloadHooks
    ) -> DownloadResult:
        info = self.fake.probe(video_id)
        choice = choose(info)
        self.choices.append(choice)
        self.hooks.append(hooks)
        merged = choice.merge_mp4 and "+" in choice.format_spec
        if merged:
            stages = ["downloading_video", "downloading_audio"]
        else:
            stages = ["downloading_video"] if choice.merge_mp4 else ["downloading_audio"]
        for stage in stages:
            hooks.on_stage(stage)
            for step in (1, 2):
                if hooks.is_cancelled():
                    raise JobCancelled()
                hooks.on_progress(step / 2, 1_000_000, 2 - step)
        if choice.merge_mp4:
            hooks.on_stage("merging")
            source = MEDIA / ("video.mp4" if merged else "video-noaudio.mp4")
            target = workdir / "media.mp4"
        else:
            source = MEDIA / "audio.m4a"
            target = workdir / "media.m4a"
        shutil.copyfile(source, target)
        return DownloadResult(target, info, choice)

    def fetch(self, url: str) -> bytes:
        self.fetched.append(url)
        if url.startswith(FakeExtractor.STORYBOARD_PREFIX):
            return self.fake.fetch(url)
        if self.cover is None:
            raise YtError("E_NETWORK", "fake: ไม่มีภาพปก")
        return self.cover


class RecordingMedia(FakeMediaTools):
    """FakeMediaTools ที่จดอาร์กิวเมนต์ของแต่ละคำสั่ง และรายงานความคืบหน้าซ้ำแบบ ffmpeg"""

    def __init__(self, media_root: Path) -> None:
        super().__init__(media_root)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _record(self, name: str, kwargs: dict[str, Any]) -> None:
        cover = kwargs.get("cover")
        sub = kwargs.get("subtitle")
        self.calls.append(
            (
                name,
                {
                    **kwargs,
                    "cover_bytes": cover.read_bytes() if cover is not None else None,
                    "sub_text": sub.path.read_bytes() if sub is not None else None,
                },
            )
        )
        on_progress = kwargs["on_progress"]
        for value in (0.5, 0.5, 0.5):
            on_progress(value)

    def finalize_mp4(self, src, dst, meta, **kwargs):
        self._record("finalize_mp4", {"meta": meta, **kwargs})
        super().finalize_mp4(src, dst, meta, **kwargs)

    def finalize_m4a(self, src, dst, meta, **kwargs):
        self._record("finalize_m4a", {"meta": meta, **kwargs})
        super().finalize_m4a(src, dst, meta, **kwargs)

    def to_mp3(self, src, dst, meta, **kwargs):
        self._record("to_mp3", {"meta": meta, **kwargs})
        super().to_mp3(src, dst, meta, **kwargs)

    def to_wav(self, src, dst, meta, **kwargs):
        self._record("to_wav", {"meta": meta, **kwargs})
        super().to_wav(src, dst, meta, **kwargs)


class Env:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.db = Database(tmp_path / "app.db")
        self.db.migrate()
        self.fake = FakeExtractor(FIXTURES)
        self.videos = VideoService(self.db, self.fake, now=lambda: NOW)
        self.subtitles = SubtitleService(self.videos, self.fake.fetch_subtitle, tmp_path / "cache")
        self.downloader = StubDownloader(self.fake)
        self.media = RecordingMedia(MEDIA)
        self.out = tmp_path / "out"
        self.free = PLENTY
        self.free_asked: list[Path] = []
        self.deps = HandlerDeps(
            videos=self.videos,
            downloader=self.downloader,
            media=self.media,
            subtitles=self.subtitles,
            cache_root=tmp_path / "cache",
            now=lambda: NOW,
            disk_free=self._disk_free,
        )
        self._runs = 0

    def planned(self, video_id: str, title: str, suffix: str, ext: str) -> Path:
        return files.plan_output(self.out.resolve(), title, video_id, suffix, ext)

    def _disk_free(self, path: Path) -> int:
        self.free_asked.append(path)
        return self.free

    def run(
        self, kind: str, video_id: str, params: dict, *, cancel_on: str | None = None, deps: HandlerDeps | None = None
    ) -> tuple[JobResult, RecordingContext]:
        self._runs += 1
        workdir = self.tmp / "work" / str(self._runs)
        workdir.mkdir(parents=True)
        ctx = RecordingContext(workdir, self.out, cancel_on=cancel_on)
        handler = build_handlers(deps or self.deps)[kind]
        return handler(make_job(kind, video_id, params), ctx), ctx


def make_job(kind: str, video_id: str, params: dict) -> Job:
    return Job(
        id="01900000-0000-7000-8000-000000000001",
        video_id=video_id,
        title="",
        kind=kind,
        params=params,
        status="running",
        stage=None,
        progress=None,
        speed_bps=None,
        eta_s=None,
        attempt=0,
        bot_checks=0,
        position=1,
        error_code=None,
        error_message=None,
        error_detail=None,
        notes=(),
        outputs=(),
        created_at="2026-10-02T05:00:00.000000+00:00",
        started_at="2026-10-02T05:00:01.000000+00:00",
        finished_at=None,
    )


def video_params(**extra: Any) -> dict:
    return {"maxQuality": False, "splitChapters": False, "noAudio": False, "audioLanguage": "original", **extra}


def audio_params(fmt: str, **extra: Any) -> dict:
    return {"format": fmt, "splitChapters": False, "audioLanguage": "original", **extra}


@pytest.fixture
def env(tmp_path):
    made = Env(tmp_path)
    yield made
    made.db.close()


def output_path(result: JobResult) -> Path:
    (out,) = result.outputs
    return Path(out.root) / out.rel


def folders(root: Path) -> list[Path]:
    return sorted(p for p in root.iterdir() if p.is_dir()) if root.exists() else []


def jpeg_bytes(fmt: str = "JPEG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 18), (200, 30, 30)).save(buf, fmt)
    return buf.getvalue()


# ---------- video ----------


def test_video_job_writes_mp4_and_source_note(env):
    result, ctx = env.run("video", BBB, video_params())

    path = output_path(result)
    planned = env.planned(BBB, BBB_TITLE, "", "mp4")
    folder = planned.parent
    assert path == planned
    # ชื่อคลิปยาวถูกตัดตามงบ path (tmp_path ของ Windows ยาว) รูปแบบยังเป็น "<ชื่อ> [<id>]/<ชื่อ>.mp4"
    short = folder.name.removesuffix(f" [{BBB}]")
    assert BBB_TITLE.startswith(short)
    assert planned.name == f"{short}.mp4"
    assert path.read_bytes() == (MEDIA / "video.mp4").read_bytes()
    (out,) = result.outputs
    assert out.root == str(env.out.resolve())
    assert out.rel == f"{folder.name}/{planned.name}"
    assert out.kind == "video"
    assert out.size_bytes == path.stat().st_size
    assert result.title == BBB_TITLE
    assert result.notes == ()
    assert ctx.titles == [BBB_TITLE]
    assert ctx.stages == ["probing", "downloading_video", "downloading_audio", "merging", "writing"]

    note = (folder / files.SOURCE_NOTE_NAME).read_bytes()
    assert not note.startswith(b"\xef\xbb\xbf")
    text = note.decode("utf-8")
    assert f"ลิงก์: https://www.youtube.com/watch?v={BBB}\r\n" in text
    assert "วันที่เผยแพร่: 2014-11-10\r\n" in text
    assert "วันที่โหลด: 2026-10-02 12:30 (+07:00)\r\n" in text
    assert "สัญญาอนุญาต: ไม่ระบุ\r\n" in text


def test_video_job_passes_metadata_and_audio_language(env):
    result, _ = env.run("video", THAI, video_params())

    name, call = env.media.calls[-1]
    assert name == "finalize_mp4"
    meta = call["meta"]
    assert meta.title == THAI_TITLE
    assert meta.artist == "KOD THAI"
    assert meta.comment == f"https://www.youtube.com/watch?v={THAI}"
    assert meta.date == "2025-05-20"
    assert meta.duration_s == 372
    assert call["audio_language"] == "th"
    assert call["subtitle"] is None
    assert output_path(result) == env.planned(THAI, THAI_TITLE, "", "mp4")
    note = (output_path(result).parent / files.SOURCE_NOTE_NAME).read_text(encoding="utf-8")
    assert "สัญญาอนุญาต: Creative Commons Attribution license (reuse allowed)" in note


def test_video_job_hooks_report_progress_and_ffmpeg_location(env):
    _, ctx = env.run("video", BBB, video_params())

    (hooks,) = env.downloader.hooks
    assert hooks.ffmpeg_location is None  # FakeMediaTools
    assert (0.5, 1_000_000, 1) in ctx.progresses
    assert (1.0, 1_000_000, 0) in ctx.progresses


def test_progress_is_deduplicated(env):
    _, ctx = env.run("video", BBB, video_params())

    # ffmpeg (RecordingMedia) รายงาน 0.5 สามครั้งติดกัน ต้องถึง ctx ครั้งเดียว
    assert ctx.progresses.count((0.5, None, None)) == 1
    for before, after in zip(ctx.progresses, ctx.progresses[1:], strict=False):
        assert before != after


def test_no_audio_video_name_suffix(env):
    result, ctx = env.run("video", BBB, video_params(noAudio=True))

    assert output_path(result) == env.planned(BBB, BBB_TITLE, " (ไม่มีเสียง)", "mp4")
    assert output_path(result).name.endswith(" (ไม่มีเสียง).mp4")
    assert output_path(result).read_bytes() == (MEDIA / "video-noaudio.mp4").read_bytes()
    assert ctx.stages == ["probing", "downloading_video", "merging", "writing"]
    assert env.media.calls[-1][1]["audio_language"] is None
    assert env.media.calls[-1][1]["no_audio"] is True


def test_video_with_audio_keeps_audio(env):
    env.run("video", BBB, video_params())

    assert env.media.calls[-1][1]["no_audio"] is False


def test_video_quality_fallback_note(env):
    result, _ = env.run("video", BBB, video_params(formatId="gone999"))

    assert result.notes == ("QUALITY_FALLBACK",)


def test_video_cover_from_thumbnail(env):
    env.downloader.cover = jpeg_bytes()
    env.run("video", BBB, video_params())

    assert env.downloader.fetched == ["https://i.ytimg.com/vi_webp/aqz-KE-bpKQ/maxresdefault.webp"]
    cover = env.media.calls[-1][1]["cover_bytes"]
    assert cover is not None
    with Image.open(io.BytesIO(cover)) as img:
        assert img.format == "JPEG"


def test_video_cover_webp_is_converted_to_jpeg(env):
    env.downloader.cover = jpeg_bytes("WEBP")
    env.run("video", BBB, video_params())

    with Image.open(io.BytesIO(env.media.calls[-1][1]["cover_bytes"])) as img:
        assert img.format == "JPEG"


@pytest.mark.parametrize("cover", [None, b"not an image"])
def test_video_without_cover_still_finishes(env, cover, caplog):
    env.downloader.cover = cover
    caplog.set_level(logging.INFO, logger="yttoolkit")
    result, _ = env.run("video", BBB, video_params())

    assert env.media.calls[-1][1]["cover"] is None
    assert output_path(result).is_file()
    assert "ไม่ใส่ภาพปก" in caplog.text


def test_embed_subs(env):
    result, _ = env.run("video", THAI, video_params(embedSubs="a.th-orig", subOptions=MEDIUM))

    call = env.media.calls[-1][1]
    sub = call["subtitle"]
    assert sub is not None
    assert sub.language == "tha"
    expected = env.subtitles.export(THAI, "a.th-orig", "srt", PRESETS["medium"]).data
    assert call["sub_text"] == expected
    assert result.notes == ()


def test_embed_subs_missing_track_skips_with_note(env):
    result, _ = env.run("video", BBB, video_params(embedSubs="a.en-orig", subOptions=MEDIUM))

    assert result.notes == ("EMBED_SUBS_SKIPPED",)
    assert env.media.calls[-1][1]["subtitle"] is None
    assert output_path(result).is_file()


def test_embed_subs_bad_options_fail_the_job(env):
    # API ตรวจ subOptions แล้ว ค่าเสียถึงตัวทำงาน = ข้อมูลงานเสีย ล้มด้วย E_UNKNOWN (core ไม่มี E_BAD_REQUEST)
    with pytest.raises(YtError) as err:
        env.run("video", THAI, video_params(embedSubs="a.th-orig", subOptions={"maxChars": 1}))

    assert err.value.code == "E_UNKNOWN"
    assert "subOptions" in err.value.detail
    assert env.downloader.choices == []
    assert folders(env.out) == []


@pytest.mark.parametrize("code", ["E_NETWORK", "E_BOT_CHECK"])
def test_embed_subs_network_errors_fail_the_job(env, code):
    def failing(url: str) -> bytes:
        raise YtError(code, "เทส")

    subtitles = SubtitleService(env.videos, failing, env.tmp / "cache2")
    deps = replace(env.deps, subtitles=subtitles)
    with pytest.raises(YtError) as err:
        env.run("video", THAI, video_params(embedSubs="a.th-orig", subOptions=MEDIUM), deps=deps)

    assert err.value.code == code
    assert env.downloader.choices == []  # ไม่โหลดวิดีโอให้เสียเวลา คิวลองใหม่ทั้งงาน
    assert folders(env.out) == []


def test_two_jobs_of_one_clip_share_one_folder(env):
    first, _ = env.run("video", BBB, video_params())
    second, _ = env.run("audio", BBB, audio_params("m4a"))
    third, _ = env.run("video", BBB, video_params())

    (folder,) = folders(env.out)
    assert output_path(first).parent == folder
    assert output_path(second).parent == folder
    mp4 = env.planned(BBB, BBB_TITLE, "", "mp4")
    assert output_path(third) == mp4.with_name(f"{mp4.stem} (2).mp4")
    assert sorted(p.name for p in folder.iterdir()) == sorted(
        [mp4.name, f"{mp4.stem} (2).mp4", f"{mp4.stem}.m4a", files.SOURCE_NOTE_NAME]
    )


# ---------- พื้นที่ว่างและโฟลเดอร์ผลลัพธ์ ----------


def test_disk_full_before_download(env):
    env.free = 10
    with pytest.raises(YtError) as err:
        env.run("video", BBB, video_params())

    assert err.value.code == "E_DISK_FULL"
    assert "พื้นที่ไม่พอ" in err.value.message
    # 2 x 267,891,149 ไบต์ ปัดขึ้นเป็น MB
    assert err.value.params == {"size": "536 MB"}
    assert err.value.message == "พื้นที่ไม่พอ ต้องมีว่างอย่างน้อย 536 MB"
    assert env.media.calls == []
    assert folders(env.out) == []


def test_disk_check_covers_output_and_work_folders(env):
    _, ctx = env.run("audio", BBB, audio_params("wav"))

    assert env.out.resolve() in env.free_asked
    assert ctx.workdir in env.free_asked


def test_disk_check_unreadable_free_space_is_skipped(env):
    def broken(path: Path) -> int:
        raise OSError("no such drive")

    result, _ = env.run("video", BBB, video_params(), deps=replace(env.deps, disk_free=broken))

    assert output_path(result).is_file()


def test_disk_size_in_gigabytes(env):
    env.free = 10
    big = DownloadChoice("x", False, None, (), 1_600_000_000)

    class BigDownloader(StubDownloader):
        def download(self, video_id, choose, workdir, hooks):
            choose({})
            raise AssertionError("ต้องไม่ถึงตรงนี้")

    import yttoolkit.core.handlers as handlers

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(handlers, "audio_choice", lambda info, params: big)
        with pytest.raises(YtError) as err:
            env.run("audio", BBB, audio_params("m4a"), deps=replace(env.deps, downloader=BigDownloader(env.fake)))

    assert err.value.params == {"size": "3.2 GB"}


def test_output_root_is_a_file(env):
    env.out.write_text("not a folder", encoding="utf-8")
    with pytest.raises(YtError) as err:
        env.run("video", BBB, video_params())

    assert err.value.code == "E_OUTPUT_NOT_WRITABLE"
    assert env.downloader.choices == []


def test_cancel_during_download(env):
    with pytest.raises(JobCancelled):
        env.run("video", BBB, video_params(), cancel_on="downloading_video")

    assert env.media.calls == []
    assert folders(env.out) == []


def test_source_note_failure_does_not_fail_the_job(env, monkeypatch, caplog):
    def locked(folder, info, downloaded_at):
        raise YtError("E_OUTPUT_NOT_WRITABLE", f"[WinError 32] {folder}")

    monkeypatch.setattr(files, "write_source_note", locked)
    caplog.set_level(logging.INFO, logger="yttoolkit")
    result, _ = env.run("video", BBB, video_params())

    assert output_path(result).is_file()
    assert not (output_path(result).parent / files.SOURCE_NOTE_NAME).exists()
    assert "แหล่งที่มา.txt" in caplog.text
    assert str(env.tmp) not in caplog.text  # ไม่ log path เต็ม


def test_logs_have_no_absolute_paths(env, caplog):
    caplog.set_level(logging.DEBUG, logger="yttoolkit")
    env.run("video", BBB, video_params())

    planned = env.planned(BBB, BBB_TITLE, "", "mp4")
    assert f"{planned.parent.name}/{planned.name}" in caplog.text
    assert str(env.tmp) not in caplog.text


# ---------- audio ----------


@pytest.mark.parametrize(
    ("fmt", "method", "stages", "source"),
    [
        ("m4a", "finalize_m4a", ["probing", "downloading_audio", "writing"], "audio.m4a"),
        ("mp3", "to_mp3", ["probing", "downloading_audio", "converting", "writing"], "audio.mp3"),
        ("wav", "to_wav", ["probing", "downloading_audio", "converting", "writing"], "audio.wav"),
    ],
)
def test_audio_job(env, fmt, method, stages, source):
    result, ctx = env.run("audio", BBB, audio_params(fmt))

    path = output_path(result)
    assert path == env.planned(BBB, BBB_TITLE, "", fmt)
    assert path.read_bytes() == (MEDIA / source).read_bytes()
    assert result.outputs[0].kind == "audio"
    assert ctx.stages == stages
    assert env.media.calls[-1][0] == method
    assert (path.parent / files.SOURCE_NOTE_NAME).is_file()


def test_mp3_bitrate(env):
    env.run("audio", BBB, audio_params("mp3", mp3Kbps=320))
    assert env.media.calls[-1][1]["kbps"] == 320

    env.run("audio", BBB, audio_params("mp3"))
    assert env.media.calls[-1][1]["kbps"] == 192


def test_audio_cover_for_m4a_and_mp3_not_wav(env):
    env.downloader.cover = jpeg_bytes()
    env.run("audio", BBB, audio_params("m4a"))
    env.run("audio", BBB, audio_params("mp3"))
    env.run("audio", BBB, audio_params("wav"))

    assert env.media.calls[0][1]["cover_bytes"] is not None
    assert env.media.calls[1][1]["cover_bytes"] is not None
    assert "cover" not in env.media.calls[2][1]
    assert len(env.downloader.fetched) == 2


def test_audio_language_fallback_note(env):
    result, _ = env.run("audio", ZOO, audio_params("m4a", audioLanguage="th"))

    assert result.notes == ("AUDIO_LANG_FALLBACK",)
    assert output_path(result).is_file()


def test_audio_language_passed_to_media(env):
    env.run("audio", THAI, audio_params("m4a"))

    assert env.media.calls[-1][1]["audio_language"] == "th"


# ---------- subtitle ----------


@pytest.mark.parametrize("fmt", ["srt", "txt", "md"])
def test_subtitle_job(env, fmt):
    result, ctx = env.run("subtitle", THAI, {"trackId": "a.th-orig", "format": fmt, "options": MEDIUM})

    expected = env.subtitles.export(THAI, "a.th-orig", fmt, PRESETS["medium"])
    path = output_path(result)
    assert path.read_bytes() == expected.data
    assert path.name.endswith(f".{expected.lang}.{fmt}")
    assert path == env.planned(THAI, THAI_TITLE, f".{expected.lang}", fmt)
    assert result.outputs[0].kind == "subtitle"
    assert ctx.stages == ["probing", "writing"]
    assert (path.parent / files.SOURCE_NOTE_NAME).is_file()


def test_subtitle_job_word_preset_matches_the_golden(env):
    """preset "ทีละคำ" ผ่านเส้นทางของงานซับ (handlers → SubtitleService.export → srt_builder) ตรง golden ทุกไบต์"""
    word = {"maxChars": 15, "lines": 1, "minMs": 800, "maxMs": 3000, "mode": "tokens", "tokensPerCue": 1}
    assert options_from_dict(word) == PRESETS["word"]  # ค่าเดียวกับที่หน้าเว็บส่งเมื่อเลือก "ทีละคำ"
    result, _ = env.run("subtitle", THAI, {"trackId": "a.th-orig", "format": "srt", "options": word})

    golden = FIXTURES / "subs" / "golden" / "th-asr.word.srt"  # 88o5Sk8_m1Y th-orig.json3 (test_srt_golden CASES)
    assert output_path(result).read_bytes() == golden.read_bytes()


def test_subtitle_job_uses_default_track(env):
    result, _ = env.run("subtitle", THAI, {"format": "srt", "options": MEDIUM})

    default = env.subtitles.tracks(THAI)["defaultTrackId"]
    assert output_path(result).read_bytes() == env.subtitles.export(THAI, default, "srt", PRESETS["medium"]).data


def test_subtitle_job_on_clip_without_subs(env):
    result, _ = env.run("subtitle", BBB, {"format": "srt", "options": MEDIUM})

    assert result == JobResult(outputs=(), notes=("NO_SUBTITLES",), title=BBB_TITLE)
    assert folders(env.out) == []


def test_subtitle_job_missing_track_is_no_subtitles(env):
    result, _ = env.run("subtitle", BBB, {"trackId": "a.en-orig", "format": "srt", "options": MEDIUM})

    assert result.notes == ("NO_SUBTITLES",)
    assert result.outputs == ()
    assert folders(env.out) == []


def test_subtitle_job_bad_options_fail_the_job(env):
    with pytest.raises(YtError) as err:
        env.run("subtitle", THAI, {"trackId": "a.th-orig", "format": "srt", "options": {"maxChars": 1}})

    assert err.value.code == "E_UNKNOWN"
    assert "options" in err.value.detail
    assert folders(env.out) == []


class WarmingSubtitles:
    """SubtitleService ที่ตอบ E_SESSION_WARMING ในการ export ครั้งแรก"""

    def __init__(self, inner: SubtitleService, retry_after: int | None) -> None:
        self.inner = inner
        self.retry_after = retry_after
        self.exports = 0

    def tracks(self, video_id: str) -> dict:
        return self.inner.tracks(video_id)

    def export(self, *args):
        self.exports += 1
        if self.exports == 1:
            raise YtError("E_SESSION_WARMING", "warming", retry_after=self.retry_after)
        return self.inner.export(*args)


@pytest.mark.parametrize(("retry_after", "waited"), [(7, 7), (None, 5)])
def test_subtitle_job_waits_for_session_warmup(env, retry_after, waited):
    warming = WarmingSubtitles(env.subtitles, retry_after)
    result, ctx = env.run(
        "subtitle", THAI, {"trackId": "a.th-orig", "format": "srt", "options": MEDIUM},
        deps=replace(env.deps, subtitles=warming),
    )  # fmt: skip

    assert ctx.waits == [waited]
    assert warming.exports == 2
    assert output_path(result).is_file()


def test_subtitle_job_warming_twice_fails(env):
    class AlwaysWarming(WarmingSubtitles):
        def export(self, *args):
            self.exports += 1
            raise YtError("E_SESSION_WARMING", "warming", retry_after=3)

    warming = AlwaysWarming(env.subtitles, 3)
    with pytest.raises(YtError) as err:
        env.run(
            "subtitle", THAI, {"trackId": "a.th-orig", "format": "srt", "options": MEDIUM},
            deps=replace(env.deps, subtitles=warming),
        )  # fmt: skip

    assert err.value.code == "E_SESSION_WARMING"
    assert warming.exports == 2


# ---------- contact sheet / zip ----------


def test_contact_sheet_job(env):
    result, ctx = env.run("contact_sheet", BBB, {"source": "fast", "columns": 5})

    path = output_path(result)
    assert path == env.planned(BBB, BBB_TITLE, " - contact sheet", "jpg")
    assert path.name.endswith(" - contact sheet.jpg")
    assert result.outputs[0].kind == "image"
    with Image.open(path) as img:
        assert img.format == "JPEG"
    assert ctx.stages == ["probing", "downloading_video", "converting", "writing"]
    assert (path.parent / files.SOURCE_NOTE_NAME).is_file()


def test_frames_zip_job(env):
    result, _ = env.run("frames_zip", BBB, {"source": "fast"})

    path = output_path(result)
    assert path == env.planned(BBB, BBB_TITLE, " - frames", "zip")
    assert path.name.endswith(" - frames.zip")
    assert result.outputs[0].kind == "archive"
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
    assert "frame_00-00-00.jpg" in names
    assert len(names) == 128


def test_contact_sheet_without_storyboard_fails(env):
    with pytest.raises(YtError) as err:
        env.run("contact_sheet", ZOO, {"source": "fast", "columns": 5})

    assert err.value.code == "E_NO_STORYBOARD"
    assert folders(env.out) == []


# ---------- txt = srt (owner preview round 2) ----------


def test_txt_job_writes_the_srt_bytes_with_a_txt_extension(env):
    srt, _ = env.run("subtitle", THAI, {"trackId": "a.th-orig", "format": "srt", "options": MEDIUM})
    txt, _ = env.run("subtitle", THAI, {"trackId": "a.th-orig", "format": "txt", "options": MEDIUM})

    srt_path, txt_path = output_path(srt), output_path(txt)
    assert txt_path.read_bytes() == srt_path.read_bytes()
    assert txt_path.read_bytes().startswith(b"1\r\n00:")
    assert txt_path.parent == srt_path.parent
    assert txt_path.name == srt_path.name.removesuffix(".srt") + ".txt"


# ---------- โฟลเดอร์กลุ่ม (params.folder) ----------

GROUP = "รวมคลิป ก/ข"
GROUP_DIR = "รวมคลิป กข"  # files.group_folder_name(GROUP)


@pytest.mark.parametrize(
    ("kind", "video_id", "title", "params", "suffix", "ext"),
    [
        ("video", BBB, BBB_TITLE, video_params(), "", "mp4"),
        ("audio", BBB, BBB_TITLE, audio_params("m4a"), "", "m4a"),
        ("subtitle", THAI, THAI_TITLE, {"trackId": "a.th-orig", "format": "srt", "options": MEDIUM}, ".th", "srt"),
        ("note", THAI, THAI_TITLE, {}, ".note", "md"),
        ("contact_sheet", BBB, BBB_TITLE, {"source": "fast", "columns": 5}, " - contact sheet", "jpg"),
        ("frames_zip", BBB, BBB_TITLE, {"source": "fast"}, " - frames", "zip"),
    ],
)
def test_group_folder_layout_for_every_kind(env, kind, video_id, title, params, suffix, ext):
    result, _ = env.run(kind, video_id, {**params, "folder": GROUP})

    (out,) = result.outputs
    path = output_path(result)
    assert out.root == str(env.out.resolve())  # root ยังเป็นโฟลเดอร์ผลลัพธ์
    assert path == files.plan_output(env.out.resolve(), title, video_id, suffix, ext, GROUP)
    assert path.parent.parent == env.out.resolve() / GROUP_DIR
    assert out.rel == f"{GROUP_DIR}/{path.parent.name}/{path.name}"  # rel รวมโฟลเดอร์กลุ่ม
    assert path.parent.name.endswith(f" [{video_id}]")
    assert (path.parent / files.SOURCE_NOTE_NAME).is_file()  # แหล่งที่มา.txt อยู่ในโฟลเดอร์ของคลิป
    assert not (env.out / GROUP_DIR / files.SOURCE_NOTE_NAME).exists()
    assert folders(env.out) == [env.out / GROUP_DIR]


def test_jobs_of_one_batch_share_the_group_and_clip_folders(env):
    a, _ = env.run("subtitle", THAI, {"trackId": "a.th-orig", "format": "srt", "options": MEDIUM, "folder": GROUP})
    b, _ = env.run("note", THAI, {"folder": GROUP})
    c, _ = env.run("contact_sheet", BBB, {"source": "fast", "columns": 5, "folder": GROUP})

    assert output_path(a).parent == output_path(b).parent
    assert output_path(c).parent.parent == output_path(a).parent.parent == env.out.resolve() / GROUP_DIR


@pytest.mark.parametrize("folder", ["", "   ", None, 12])
def test_blank_or_odd_folder_means_no_group(env, folder):
    result, _ = env.run("frames_zip", BBB, {"source": "fast", "folder": folder})

    assert output_path(result) == env.planned(BBB, BBB_TITLE, " - frames", "zip")


def test_dangerous_folder_names_stay_inside_the_output_root(env):
    root = env.out.resolve()
    for raw in ("..", "../../escape", "CON", "a."):
        result, _ = env.run("frames_zip", BBB, {"source": "fast", "folder": raw})
        path = output_path(result)
        assert path.resolve().is_relative_to(root), raw
        assert path.parent.parent.parent == root, raw
        assert result.outputs[0].rel.count("/") == 2, raw
    names = {p.name for p in folders(env.out)}
    assert names == {files.GROUP_FALLBACK, "....escape", "_CON", "a"}


# ---------- note ----------


class PinnedRecorder:
    """ตัวดึงคอมเมนต์ปักหมุดปลอม (แทน PinnedCommentService.get) ตอบตาม `answer` หรือโยน `error`"""

    def __init__(self, answer: dict | None = None, error: BaseException | None = None) -> None:
        self.answer = answer
        self.error = error
        self.calls: list[str] = []

    def __call__(self, video_id: str) -> dict | None:
        self.calls.append(video_id)
        if self.error is not None:
            raise self.error
        return self.answer


PINNED = {"text": "ขอบคุณที่ดูนะ\nกดติดตามด้วย", "byUploader": True, "likes": 3}


def test_note_job_writes_the_same_markdown_as_the_note_endpoint(env):
    pinned = PinnedRecorder(PINNED)
    result, ctx = env.run("note", THAI, {"trackId": "a.th-orig"}, deps=replace(env.deps, pinned=pinned))

    expected = env.subtitles.note(THAI, "a.th-orig", pinned=lambda _vid: PINNED)
    path = output_path(result)
    assert path.read_bytes() == expected.data
    assert path == env.planned(THAI, THAI_TITLE, ".note", "md")
    assert path.name.endswith(".note.md")
    assert result.outputs[0].kind == "note"
    assert result.outputs[0].size_bytes == len(expected.data)
    assert result.notes == ()
    assert result.title == THAI_TITLE
    assert ctx.stages == ["probing", "writing"]
    assert ctx.titles == [THAI_TITLE]
    assert pinned.calls == [THAI]
    text = path.read_text(encoding="utf-8")
    assert "## คอมเมนต์ปักหมุด (เจ้าของช่อง)" in text
    assert "## ทรานสคริปต์" in text
    assert b"\r\n" not in path.read_bytes() and not path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert (path.parent / files.SOURCE_NOTE_NAME).is_file()


def test_note_job_without_track_uses_the_default_track(env):
    result, _ = env.run("note", THAI, {})

    assert output_path(result).read_bytes() == env.subtitles.note(THAI).data
    assert "## ทรานสคริปต์" in output_path(result).read_text(encoding="utf-8")


def test_note_job_without_pinned_getter_has_no_pinned_section(env):
    assert env.deps.pinned is None
    result, _ = env.run("note", THAI, {})

    assert "คอมเมนต์ปักหมุด" not in output_path(result).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "error",
    [YtError("E_BOT_CHECK", "comments"), YtError("E_NETWORK", "x"), RuntimeError("boom"), OSError("disk")],
    ids=lambda e: type(e).__name__ + getattr(e, "code", ""),
)
def test_pinned_failure_never_fails_the_note_job(env, error):
    pinned = PinnedRecorder(error=error)
    result, _ = env.run("note", THAI, {"trackId": "a.th-orig"}, deps=replace(env.deps, pinned=pinned))

    path = output_path(result)
    assert pinned.calls == [THAI]
    assert path.read_bytes() == env.subtitles.note(THAI, "a.th-orig").data
    assert "คอมเมนต์ปักหมุด" not in path.read_text(encoding="utf-8")
    assert result.notes == ()


@pytest.mark.parametrize("params", [{"trackId": "a.th-orig"}, {}, {"trackId": "o.xx"}], ids=["track", "default", "gone"])
def test_pinned_bot_check_brakes_the_queue_once_and_still_writes_the_note(env, params):
    """I-3: โน้ตยังเสร็จ (ไม่มีหัวข้อคอมเมนต์) แต่คิวต้องเบรกฉุกเฉินหนึ่งครั้ง งานโน้ตชุดใหญ่จะได้ไม่ยิงยูทูปต่อ"""
    brakes: list[str] = []
    pinned = PinnedRecorder(error=YtError("E_BOT_CHECK", "comments"))
    deps = replace(env.deps, pinned=pinned, on_bot_check=lambda: brakes.append("brake"))
    result, _ = env.run("note", THAI, params, deps=deps)

    assert brakes == ["brake"]
    assert output_path(result).is_file()
    assert "คอมเมนต์ปักหมุด" not in output_path(result).read_text(encoding="utf-8")


@pytest.mark.parametrize("error", [YtError("E_NETWORK", "x"), RuntimeError("boom")], ids=["network", "runtime"])
def test_other_pinned_failures_do_not_brake(env, error):
    brakes: list[str] = []
    deps = replace(env.deps, pinned=PinnedRecorder(error=error), on_bot_check=lambda: brakes.append("brake"))
    result, _ = env.run("note", THAI, {}, deps=deps)

    assert brakes == []
    assert output_path(result).is_file()


def test_failing_brake_hook_does_not_fail_the_note_job(env, caplog):
    def broken() -> None:
        raise RuntimeError("queue gone")

    deps = replace(env.deps, pinned=PinnedRecorder(error=YtError("E_BOT_CHECK", "x")), on_bot_check=broken)
    with caplog.at_level(logging.WARNING, logger="yttoolkit"):
        result, _ = env.run("note", THAI, {}, deps=deps)

    assert output_path(result).is_file()
    assert "RuntimeError" in caplog.text


def test_note_job_on_clip_without_subtitles_still_writes_the_note(env):
    result, _ = env.run("note", BBB, {}, deps=replace(env.deps, pinned=PinnedRecorder(None)))

    text = output_path(result).read_text(encoding="utf-8")
    assert "ทรานสคริปต์" not in text
    assert f"# {BBB_TITLE}" in text
    assert output_path(result).name.endswith(".note.md")


def test_note_job_missing_track_falls_back_to_default(env):
    result, _ = env.run("note", THAI, {"trackId": "o.xx"})

    assert output_path(result).read_bytes() == env.subtitles.note(THAI).data


def test_note_job_missing_track_on_clip_without_subs_still_writes(env):
    result, _ = env.run("note", BBB, {"trackId": "a.en-orig"})

    assert output_path(result).read_bytes() == env.subtitles.note(BBB).data


class WarmingNotes:
    """SubtitleService ที่ตอบ E_SESSION_WARMING ในการทำโน้ตครั้งแรก (หรือทุกครั้ง)"""

    def __init__(self, inner: SubtitleService, always: bool = False) -> None:
        self.inner = inner
        self.always = always
        self.notes = 0

    def note(self, *args, **kwargs):
        self.notes += 1
        if self.always or self.notes == 1:
            raise YtError("E_SESSION_WARMING", "warming", retry_after=4)
        return self.inner.note(*args, **kwargs)


def test_note_job_waits_for_session_warmup(env):
    warming = WarmingNotes(env.subtitles)
    result, ctx = env.run("note", THAI, {"trackId": "a.th-orig"}, deps=replace(env.deps, subtitles=warming))

    assert ctx.waits == [4]
    assert warming.notes == 2
    assert output_path(result).is_file()


def test_note_job_warming_twice_fails(env):
    warming = WarmingNotes(env.subtitles, always=True)
    with pytest.raises(YtError) as err:
        env.run("note", THAI, {"trackId": "a.th-orig"}, deps=replace(env.deps, subtitles=warming))

    assert err.value.code == "E_SESSION_WARMING"
    assert warming.notes == 2
    assert folders(env.out) == []


def test_note_job_other_errors_fail_the_job(env):
    with pytest.raises(YtError) as err:
        env.run("note", "UPCOMINGLV1", {})

    assert err.value.code == "E_LIVE_NOT_READY"
    assert folders(env.out) == []


def test_note_job_cancelled_before_writing_leaves_nothing(env):
    with pytest.raises(JobCancelled):
        env.run("note", THAI, {}, cancel_on="writing")

    assert folders(env.out) == []


def test_build_handlers_keys(env):
    assert set(build_handlers(env.deps)) == {
        "video", "audio", "subtitle", "note", "frames_sharp", "contact_sheet", "frames_zip",
    }  # fmt: skip
    assert isinstance(env.downloader, Downloader)


# ---------- "ล่าสุด" และการยกเลิกช่วงท้าย ----------


@pytest.mark.parametrize(
    ("kind", "video_id", "title", "params"),
    [
        ("video", BBB, BBB_TITLE, video_params()),
        ("audio", BBB, BBB_TITLE, audio_params("mp3")),
        ("subtitle", THAI, THAI_TITLE, {"trackId": "a.th-orig", "format": "srt", "options": MEDIUM}),
        ("contact_sheet", BBB, BBB_TITLE, {"source": "fast", "columns": 5}),
        ("frames_zip", BBB, BBB_TITLE, {"source": "fast"}),
    ],
)
def test_jobs_do_not_mark_clip_opened(env, kind, video_id, title, params):
    env.run(kind, video_id, params)

    # งานโหลดเก็บข้อมูลคลิปแบบ peek: ไม่ขึ้นในประวัติ "เปิดแล้ว" (C15 scope="opened" = ค่าเริ่มต้นของ recent)
    assert env.videos.recent(10) == ([], 0)
    assert env.videos.recent(10, scope="opened") == ([], 0)
    rows = env.db.execute("SELECT title FROM videos WHERE video_id = ?", (video_id,))
    assert [row["title"] for row in rows] == [title]


def test_storyboard_refresh_does_not_mark_clip_opened(env):
    class FlakyDownloader(StubDownloader):
        failed = False

        def fetch(self, url: str) -> bytes:
            if url.startswith(FakeExtractor.STORYBOARD_PREFIX) and not self.failed:
                self.failed = True
                raise YtError("E_NETWORK", "ลิงก์หมดอายุ")
            return super().fetch(url)

    flaky = FlakyDownloader(env.fake)
    result, _ = env.run("frames_zip", BBB, {"source": "fast"}, deps=replace(env.deps, downloader=flaky))

    assert flaky.failed
    assert output_path(result).is_file()
    assert env.videos.recent(10) == ([], 0)
    assert env.videos.recent(10, scope="opened") == ([], 0)


@pytest.mark.parametrize(
    ("kind", "params", "cancel_on"),
    [
        ("video", video_params(), "merging"),
        ("video", video_params(), "writing"),
        ("audio", audio_params("m4a"), "writing"),
        ("audio", audio_params("mp3"), "converting"),
        ("audio", audio_params("wav"), "writing"),
        ("subtitle", {"trackId": "a.th-orig", "format": "srt", "options": MEDIUM}, "writing"),
        ("contact_sheet", {"source": "fast", "columns": 5}, "converting"),
        ("contact_sheet", {"source": "fast", "columns": 5}, "writing"),
        ("frames_zip", {"source": "fast"}, "converting"),
        ("frames_zip", {"source": "fast"}, "writing"),
    ],
)
def test_late_cancel_leaves_no_output(env, kind, params, cancel_on):
    video_id = THAI if kind == "subtitle" else BBB
    with pytest.raises(JobCancelled):
        env.run(kind, video_id, params, cancel_on=cancel_on)

    assert folders(env.out) == []


def test_cover_not_fetched_after_cancel(env, tmp_path):
    from yttoolkit.core.handlers import _Clip, _cover

    env.downloader.cover = jpeg_bytes()
    ctx = RecordingContext(tmp_path, env.out)
    ctx._cancelled = True
    clip = _Clip(BBB, {"thumbnailUrl": "https://i.ytimg.com/x.jpg"}, BBB_TITLE, env.out)

    assert _cover(env.deps, clip, ctx) is None
    assert env.downloader.fetched == []


# ---------- ffmpeg จริง ----------


@requires_ffmpeg
def test_video_with_real_ffmpeg_embeds_subs_and_cover(env):
    ffmpeg = find_test_ffmpeg()
    assert ffmpeg is not None
    env.downloader.cover = jpeg_bytes("WEBP")
    deps = replace(env.deps, media=FfmpegTools(lambda: Path(ffmpeg)))
    result, _ = env.run("video", THAI, video_params(embedSubs="a.th-orig", subOptions=MEDIUM), deps=deps)

    probe = ffprobe_json(output_path(result))
    streams = probe["streams"]
    subs = [s for s in streams if s["codec_type"] == "subtitle"]
    assert [s["codec_name"] for s in subs] == ["mov_text"]
    assert subs[0]["tags"]["language"] == "tha"
    assert any(s.get("disposition", {}).get("attached_pic") == 1 for s in streams)
    assert probe["format"]["tags"]["title"] == THAI_TITLE
    audio = [s for s in streams if s["codec_type"] == "audio"]
    assert audio[0]["tags"]["language"] == "tha"


# ---------- M5 รอบ A: ช่วงเวลา ตัดโฆษณา ซับตามช่วง ----------

RANGE = {"startMs": 90_000, "endMs": 300_000}
ADS = [(60_000, 90_000, "sponsor"), (100_000, 101_000, "intro")]


class StubSponsors:
    """SponsorSource ตามสัญญา C4: ช่วงตายตัว หรือ error=True = ติดต่อ SponsorBlock ไม่ได้"""

    def __init__(self, segments=(), error: bool = False) -> None:
        self.segments = list(segments)
        self.error = error
        self.calls: list[tuple[str, tuple[str, ...], float | None]] = []

    def sponsor_segments(self, video_id, categories, duration_s):
        self.calls.append((video_id, tuple(categories), duration_s))
        if self.error:
            raise SponsorBlockError("fake: unreachable")
        return [s for s in self.segments if s[2] in categories]


def run_with(env, sponsors, kind: str, video_id: str, params: dict, **kwargs):
    return env.run(kind, video_id, params, deps=replace(env.deps, sponsors=sponsors), **kwargs)


def test_video_range_is_cut_exactly_and_named(env):
    result, ctx = env.run("video", BBB, video_params(range=RANGE))
    assert env.media.cuts == [CutCall("media.mp4", "cut.mp4", ((90_000, 300_000),), "exact", "mp4", True)]
    assert ctx.stages.index("cutting") < ctx.stages.index("writing")
    name, kwargs = env.media.calls[-1]
    assert name == "finalize_mp4" and kwargs["meta"].duration_s == 210.0
    assert output_path(result) == env.planned(BBB, BBB_TITLE, " (01.30-05.00)", "mp4")
    assert result.notes == ()


def test_range_end_after_the_clip_is_clipped_to_the_real_duration(env):
    result, _ = env.run("video", BBB, video_params(range={"startMs": 600_000, "endMs": 700_000}))
    assert env.media.cuts[-1].intervals == ((600_000, 635_000),)
    assert output_path(result).name.endswith(" (10.00-10.35).mp4")


def test_range_outside_the_clip_fails_the_job(env):
    with pytest.raises(YtError) as info:
        env.run("video", BBB, video_params(range={"startMs": 700_000, "endMs": 710_000}))
    assert info.value.code == "E_UNKNOWN"
    assert folders(env.out) == []


def test_no_audio_range_name_order(env):
    result, _ = env.run("video", BBB, video_params(noAudio=True, range=RANGE))
    assert env.media.cuts[-1].has_audio is False
    assert output_path(result).name.endswith(" (ไม่มีเสียง) (01.30-05.00).mp4")


def test_sponsorblock_cuts_the_ads(env):
    sponsors = StubSponsors(ADS)
    result, ctx = run_with(env, sponsors, "video", BBB, video_params(sponsorblock=["sponsor"]))
    assert sponsors.calls == [(BBB, ("sponsor",), 635.0)]
    assert env.media.cuts[-1].intervals == ((0, 60_000), (90_000, 635_000))
    assert "cutting_ads" in ctx.stages and "cutting" not in ctx.stages
    assert env.media.calls[-1][1]["meta"].duration_s == 605.0
    assert output_path(result) == env.planned(BBB, BBB_TITLE, ADS_SUFFIX, "mp4")
    assert result.notes == ()


def test_sponsorblock_without_data_keeps_the_full_clip_and_name(env):
    result, ctx = run_with(env, StubSponsors(), "video", BBB, video_params(sponsorblock=["sponsor"]))
    assert env.media.cuts == [] and "cutting_ads" not in ctx.stages
    assert output_path(result) == env.planned(BBB, BBB_TITLE, "", "mp4")
    assert result.notes == ("SPONSORBLOCK_EMPTY",)


@pytest.mark.parametrize("sponsors", [StubSponsors(error=True), None], ids=["error", "no-source"])
def test_sponsorblock_unreachable_keeps_the_full_clip(env, sponsors):
    result, _ = run_with(env, sponsors, "video", BBB, video_params(sponsorblock=["sponsor"]))
    assert env.media.cuts == []
    assert output_path(result) == env.planned(BBB, BBB_TITLE, "", "mp4")
    assert result.notes == ("SPONSORBLOCK_UNREACHABLE",)


def test_range_and_ads_together(env):
    params = video_params(range={"startMs": 30_000, "endMs": 120_000}, sponsorblock=["sponsor"])
    result, _ = run_with(env, StubSponsors(ADS), "video", BBB, params)
    assert env.media.cuts[-1].intervals == ((30_000, 60_000), (90_000, 120_000))
    assert output_path(result).name.endswith(" (00.30-02.00) (ตัดโฆษณา).mp4")


def test_ads_outside_the_range_cut_the_range_only(env):
    params = video_params(range={"startMs": 200_000, "endMs": 260_000}, sponsorblock=["sponsor"])
    result, ctx = run_with(env, StubSponsors(ADS), "video", BBB, params)
    assert env.media.cuts[-1].intervals == ((200_000, 260_000),)
    assert "cutting" in ctx.stages and "cutting_ads" not in ctx.stages
    assert output_path(result).name.endswith(" (03.20-04.20).mp4")
    assert result.notes == ("SPONSORBLOCK_EMPTY",)


def test_sponsors_are_not_asked_without_sponsorblock(env):
    sponsors = StubSponsors(ADS)
    run_with(env, sponsors, "video", BBB, video_params(range=RANGE))
    assert sponsors.calls == []


@pytest.mark.parametrize(
    ("fmt", "target", "method"),
    [("m4a", "m4a", "finalize_m4a"), ("mp3", "wav", "to_mp3"), ("wav", "wav", "to_wav")],
)
def test_audio_range(env, fmt, target, method):
    result, ctx = env.run("audio", BBB, audio_params(fmt, range=RANGE))
    assert env.media.cuts == [CutCall("media.m4a", f"cut.{target}", ((90_000, 300_000),), "exact", target, True)]
    name, kwargs = env.media.calls[-1]
    assert name == method and kwargs["meta"].duration_s == 210.0
    assert "cutting" in ctx.stages
    assert output_path(result) == env.planned(BBB, BBB_TITLE, " (01.30-05.00)", fmt)


def test_audio_sponsorblock(env):
    result, _ = run_with(env, StubSponsors(ADS), "audio", BBB, audio_params("m4a", sponsorblock=["sponsor"]))
    assert env.media.cuts[-1] == CutCall("media.m4a", "cut.m4a", ((0, 60_000), (90_000, 635_000)), "exact", "m4a", True)
    assert output_path(result) == env.planned(BBB, BBB_TITLE, ADS_SUFFIX, "m4a")


def test_subtitle_range_file(env):
    params = {"trackId": "a.th-orig", "format": "srt", "options": MEDIUM, "range": {"startMs": 10_000, "endMs": 40_000}}
    result, _ = env.run("subtitle", THAI, params)
    expected = env.subtitles.export(THAI, "a.th-orig", "srt", PRESETS["medium"], (10_000, 40_000))
    assert output_path(result).read_bytes() == expected.data
    assert output_path(result) == env.planned(THAI, THAI_TITLE, f" (00.10-00.40).{expected.lang}", "srt")


def test_embedded_subtitles_follow_the_range(env):
    params = video_params(embedSubs="a.th-orig", subOptions=MEDIUM, range={"startMs": 10_000, "endMs": 40_000})
    env.run("video", THAI, params)
    name, kwargs = env.media.calls[-1]
    expected = env.subtitles.export(THAI, "a.th-orig", "srt", PRESETS["medium"], (10_000, 40_000)).data
    assert name == "finalize_mp4" and kwargs["sub_text"] == expected


def test_cutting_needs_three_times_the_download_size(env):
    expected = video_choice(env.fake.probe(BBB), video_params()).expected_bytes
    assert expected == 267_891_149
    env.free = 600_000_000  # >= 2 x expected, < 3 x expected
    env.run("video", BBB, video_params())
    with pytest.raises(YtError) as info:
        env.run("video", BBB, video_params(range=RANGE))
    assert info.value.code == "E_DISK_FULL" and info.value.params == {"size": "804 MB"}


@pytest.mark.parametrize("kind", ["video", "audio"])
def test_sponsorblock_without_data_needs_only_twice_the_download_size(env, kind):
    params = video_params(sponsorblock=["sponsor"]) if kind == "video" else audio_params("m4a", sponsorblock=["sponsor"])
    choose = video_choice if kind == "video" else audio_choice
    expected = choose(env.fake.probe(BBB), params).expected_bytes
    env.free = expected * 2 + expected // 2  # >= 2 x expected, < 3 x expected
    result, _ = run_with(env, StubSponsors(), kind, BBB, params)
    assert result.notes == ("SPONSORBLOCK_EMPTY",)
    with pytest.raises(YtError) as info:
        run_with(env, StubSponsors(ADS), kind, BBB, params)
    assert info.value.code == "E_DISK_FULL"


def test_cancel_while_cutting_leaves_nothing(env):
    with pytest.raises(JobCancelled):
        env.run("video", BBB, video_params(range=RANGE), cancel_on="cutting")
    assert folders(env.out) == []


# ---------- M5 รอบ A fix round 1: คลิปไม่มีเสียง และช่วงของคลิปที่ยังไม่เคยดึงข้อมูล ----------


class SilentDownloader(StubDownloader):
    """คลิปที่ไม่มีแทร็กเสียงเลย: ทุก format ของการดึงข้อมูลรอบโหลดมี acodec "none" ไฟล์ที่โหลดไม่มีเสียง"""

    def download(self, video_id, choose, workdir, hooks):
        info = dict(self.fake.probe(video_id))
        info["formats"] = [f for f in info["formats"] if f.get("acodec") == "none"]
        choice = choose(info)
        self.choices.append(choice)
        target = workdir / "media.mp4"
        shutil.copyfile(MEDIA / "video-noaudio.mp4", target)
        return DownloadResult(target, info, choice)


def test_range_on_a_clip_without_audio_cuts_without_audio(env):
    deps = replace(env.deps, downloader=SilentDownloader(env.fake))
    result, _ = env.run("video", BBB, video_params(range=RANGE), deps=deps)
    assert env.media.cuts == [CutCall("media.mp4", "cut.mp4", ((90_000, 300_000),), "exact", "mp4", False)]
    assert output_path(result) == env.planned(BBB, BBB_TITLE, " (01.30-05.00)", "mp4")


def test_clip_with_audio_formats_cuts_with_audio(env):
    env.run("video", BBB, video_params(range=RANGE))
    assert env.media.cuts[-1].has_audio is True


@requires_ffmpeg
def test_range_on_a_clip_without_audio_with_real_ffmpeg(env):
    ffmpeg = find_test_ffmpeg()
    assert ffmpeg is not None
    deps = replace(env.deps, downloader=SilentDownloader(env.fake), media=FfmpegTools(lambda: Path(ffmpeg)))
    result, _ = env.run("video", BBB, video_params(range={"startMs": 0, "endMs": 1000}), deps=deps)
    probe = ffprobe_json(output_path(result))
    assert [s["codec_type"] for s in probe["streams"]] == ["video"]
    assert abs(float(probe["format"]["duration"]) - 1.0) < 0.15


def subtitle_range_params(start_ms: int, end_ms: int) -> dict:
    return {"trackId": "a.th-orig", "format": "srt", "options": MEDIUM, "range": {"startMs": start_ms, "endMs": end_ms}}


def test_subtitle_range_past_the_end_is_clipped_to_the_clip(env):
    result, _ = env.run("subtitle", THAI, subtitle_range_params(360_000, 400_000))
    expected = env.subtitles.export(THAI, "a.th-orig", "srt", PRESETS["medium"], (360_000, 372_000))
    assert output_path(result).read_bytes() == expected.data
    assert output_path(result) == env.planned(THAI, THAI_TITLE, f" (06.00-06.12).{expected.lang}", "srt")


@pytest.mark.parametrize("span", [(700_000, 710_000), (371_500, 380_000)], ids=["outside", "under-1s-left"])
def test_subtitle_range_outside_the_clip_fails_the_job(env, span):
    with pytest.raises(YtError) as info:
        env.run("subtitle", THAI, subtitle_range_params(*span))
    assert info.value.code == "E_UNKNOWN"
    assert folders(env.out) == []


def test_embedded_subtitles_and_cut_use_the_same_clipped_range(env):
    params = video_params(embedSubs="a.th-orig", subOptions=MEDIUM, range={"startMs": 360_000, "endMs": 400_000})
    result, _ = env.run("video", THAI, params)
    assert env.media.cuts[-1].intervals == ((360_000, 372_000),)
    expected = env.subtitles.export(THAI, "a.th-orig", "srt", PRESETS["medium"], (360_000, 372_000)).data
    assert env.media.calls[-1][1]["sub_text"] == expected
    assert output_path(result).name.endswith(" (06.00-06.12).mp4")


def test_range_outside_the_clip_fails_before_downloading(env):
    with pytest.raises(YtError) as info:
        env.run("video", BBB, video_params(range={"startMs": 700_000, "endMs": 710_000}))
    assert info.value.code == "E_UNKNOWN"
    assert env.downloader.choices == []


# ---------- M5 รอบ A: แยกไฟล์ตาม chapter ----------

ZOO_TITLE = "Me at the zoo"
ZOO_NAMES = ["01 - Intro", "02 - The cool thing", "03 - End"]


def test_video_chapter_split(env):
    result, ctx = env.run("video", ZOO, video_params(splitChapters=True))
    assert [c.intervals for c in env.media.cuts] == [((0, 5_000),), ((5_000, 17_000),), ((17_000, 19_000),)]
    assert {(c.mode, c.target, c.has_audio) for c in env.media.cuts} == {("fast", "mp4", True)}
    assert [s for s in ctx.stages if s.startswith("splitting")] == ["splitting:1/3", "splitting:2/3", "splitting:3/3"]
    clip_folder = env.planned(ZOO, ZOO_TITLE, "", "mp4").parent
    paths = [Path(o.root) / o.rel for o in result.outputs]
    assert [p.name for p in paths] == [f"{n}.mp4" for n in ZOO_NAMES]
    assert {p.parent for p in paths} == {clip_folder / "แยกตาม chapter (mp4)"}
    assert all(p.is_file() for p in paths) and {o.kind for o in result.outputs} == {"video"}
    assert (clip_folder / files.SOURCE_NOTE_NAME).is_file()
    metas = [kwargs["meta"] for name, kwargs in env.media.calls if name == "finalize_mp4"]
    assert [(m.title, m.track, m.duration_s) for m in metas] == [
        ("Intro", "1/3", 5.0), ("The cool thing", "2/3", 12.0), ("End", "3/3", 2.0)]
    assert result.notes == ()


@pytest.mark.parametrize(
    ("fmt", "target", "method"),
    [("m4a", "m4a", "finalize_m4a"), ("mp3", "wav", "to_mp3"), ("wav", "wav", "to_wav")],
)
def test_audio_chapter_split_is_exact(env, fmt, target, method):
    result, _ = env.run("audio", ZOO, audio_params(fmt, splitChapters=True))
    assert [(c.mode, c.target) for c in env.media.cuts] == [("exact", target)] * 3
    assert [Path(o.rel).name for o in result.outputs] == [f"{n}.{fmt}" for n in ZOO_NAMES]
    assert {Path(o.rel).parent.name for o in result.outputs} == {f"แยกตาม chapter ({fmt})"}
    assert [name for name, _ in env.media.calls] == [method] * 3


def test_chapter_split_on_a_clip_without_chapters_gives_the_full_file(env):
    result, ctx = env.run("video", BBB, video_params(splitChapters=True))
    assert env.media.cuts == [] and not any(s.startswith("splitting") for s in ctx.stages)
    assert output_path(result) == env.planned(BBB, BBB_TITLE, "", "mp4")
    assert result.notes == ("NO_CHAPTERS",)


def test_second_chapter_split_gets_numbered_copies(env):
    env.run("video", ZOO, video_params(splitChapters=True))
    again, _ = env.run("video", ZOO, video_params(splitChapters=True))
    assert Path(again.outputs[0].rel).name == "01 - Intro (2).mp4"


def test_no_audio_chapter_split_goes_to_its_own_folder(env):
    """owner ruling 2026-10-02: ไม่ปนกับไฟล์ chapter ที่มีเสียงของคลิปเดียวกัน ชื่อไฟล์ข้างในเหมือนเดิม"""
    with_sound, _ = env.run("video", ZOO, video_params(splitChapters=True))
    silent, _ = env.run("video", ZOO, video_params(splitChapters=True, noAudio=True))
    clip_folder = env.planned(ZOO, ZOO_TITLE, "", "mp4").parent
    silent_paths = [Path(o.root) / o.rel for o in silent.outputs]
    assert [p.name for p in silent_paths] == [f"{n}.mp4" for n in ZOO_NAMES]
    assert {p.parent for p in silent_paths} == {clip_folder / "แยกตาม chapter (mp4, ไม่มีเสียง)"}
    assert all(p.is_file() for p in silent_paths)
    assert {(Path(o.root) / o.rel).parent for o in with_sound.outputs} == {clip_folder / "แยกตาม chapter (mp4)"}
    assert {c.has_audio for c in env.media.cuts[3:]} == {False}
    assert {kwargs["no_audio"] for name, kwargs in env.media.calls[3:] if name == "finalize_mp4"} == {True}
    assert (clip_folder / files.SOURCE_NOTE_NAME).is_file()


def test_chapters_out_of_order_are_split_by_start_time(env, monkeypatch):
    real = env.videos.get

    def reversed_chapters(video_id: str, **kwargs: Any) -> dict:
        info = dict(real(video_id, **kwargs))
        info["chapters"] = list(reversed(info["chapters"]))
        return info

    monkeypatch.setattr(env.videos, "get", reversed_chapters)
    result, _ = env.run("video", ZOO, video_params(splitChapters=True))
    assert [c.intervals for c in env.media.cuts] == [((0, 5_000),), ((5_000, 17_000),), ((17_000, 19_000),)]
    assert [Path(o.rel).name for o in result.outputs] == [f"{n}.mp4" for n in ZOO_NAMES]


def test_cancel_during_the_chapter_split_leaves_nothing(env):
    with pytest.raises(JobCancelled):
        env.run("video", ZOO, video_params(splitChapters=True), cancel_on="splitting:2/3")
    assert folders(env.out) == []
