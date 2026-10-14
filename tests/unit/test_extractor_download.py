"""งานโหลดไฟล์ของ extractor (C8): ตัวปลอมตาม behaviors.json (C14) และสายไฟของตัวจริง (yt-dlp ถูกแทน ไม่ต่อเน็ต)"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar, Self

import pytest
import yt_dlp
from yt_dlp.utils import DownloadCancelled, DownloadError

from yttoolkit.core import extractor as extractor_mod
from yttoolkit.core.cancel import JobCancelled
from yttoolkit.core.download import (
    DownloadChoice,
    Downloader,
    DownloadHooks,
    DownloadResult,
    MediaFacts,
    audio_choice,
    video_choice,
)
from yttoolkit.core.extractor import FakeExtractor, YtDlpExtractor
from yttoolkit.core.yterrors import YtError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
MEDIA = FIXTURES / "media"
BEHAVIORS = FIXTURES / "downloads" / "behaviors.json"
BBB = "aqz-KE-bpKQ"

# C14 ตามตัวอักษร (ไฟล์ใน tests/fixtures/downloads ต้องตรงกับนี้ e2e ของคิวพึ่งค่าเหล่านี้)
C14 = {
    "default": {"steps": 6, "stepMs": 120},
    "videos": {
        "SLOWDOWNLD1": {"probeAs": BBB, "title": "คลิปโหลดช้า 1", "steps": 40, "stepMs": 250},
        "SLOWDOWNLD2": {"probeAs": BBB, "title": "คลิปโหลดช้า 2", "steps": 40, "stepMs": 250},
        "SLOWDOWNLD3": {"probeAs": BBB, "title": "คลิปโหลดช้า 3", "steps": 40, "stepMs": 250},
        "SLOWDOWNLD4": {"probeAs": BBB, "title": "คลิปโหลดช้า 4", "steps": 40, "stepMs": 250},
        "BOTCHECKDL1": {
            "probeAs": BBB, "title": "คลิปติดบอท", "steps": 6, "stepMs": 120,
            "failAtStep": 2, "error": "E_BOT_CHECK", "failTimes": 1,
        },
        "NETRETRYDL1": {
            "probeAs": BBB, "title": "คลิปเน็ตหลุด", "steps": 6, "stepMs": 120,
            "failAtStep": 1, "error": "E_NETWORK", "failTimes": 1,
        },
        "REFUSEDDL01": {
            "probeAs": BBB, "title": "คลิปที่ยูทูปไม่ส่งไฟล์", "steps": 6, "stepMs": 120,
            "failAtStep": 0, "error": "E_YT_REFUSED", "failTimes": 99,
        },
        "RANGECLIP01": {"probeAs": BBB, "title": "คลิปช่วงเวลา"},
        "ADSCUTCLIP1": {"probeAs": BBB, "title": "คลิปมีช่วงโฆษณา"},
        "ADSNODATA01": {"probeAs": BBB, "title": "คลิปไม่มีข้อมูลโฆษณา"},
        "ADSOFFLINE1": {"probeAs": BBB, "title": "คลิปที่ติดต่อ SponsorBlock ไม่ได้"},
        "CHAPTERS001": {"probeAs": "jNQXAC9IVRw", "title": "คลิปมี 3 chapter"},
        "SHARPCLIP01": {"probeAs": BBB, "title": "คลิปภาพคม"},
        "AUTOSHARP01": {"probeAs": BBB, "title": "คลิปภาพคมอัตโนมัติ",
                        "media": {"width": 1280, "height": 720, "dynamic_range": "SDR"}},
        "CAPTURE0001": {"probeAs": BBB, "title": "คลิปถ่ายภาพคม"},
        "CAPTURENO01": {"probeAs": BBB, "title": "คลิปถ่ายภาพคมไม่ได้", "captureError": "E_CAPTURE_UNSUPPORTED"},
        "CAPTUREBOT1": {"probeAs": BBB, "title": "คลิปถ่ายภาพคมติดบอท", "captureError": "E_BOT_CHECK"},
        "CAPTURENET1": {"probeAs": BBB, "title": "คลิปถ่ายภาพคมเน็ตหลุด", "captureError": "E_NETWORK"},
        "ACCOUNTAGE1": {"probeAs": BBB, "title": "คลิปจำกัดอายุ", "needsAccount": "E_AGE_RESTRICTED"},
        "ACCOUNTMEM1": {"probeAs": BBB, "title": "คลิปเฉพาะสมาชิก", "needsAccount": "E_VIDEO_PRIVATE"},
    },
}


class Recorder:
    """เก็บทุกการเรียก hook · cancel_at = ครั้งที่เท่าไรของ is_cancelled ที่ตอบ True (None = ไม่ยกเลิก)"""

    def __init__(self, cancel_at: int | None = None, ffmpeg: Path | None = None) -> None:
        self.stages: list[str] = []
        self.progress: list[tuple[float | None, int | None, int | None]] = []
        self.cancel_checks = 0
        self.cancel_at = cancel_at
        self.hooks = DownloadHooks(
            on_stage=self.stages.append,
            on_progress=lambda f, s, e: self.progress.append((f, s, e)),
            is_cancelled=self._is_cancelled,
            ffmpeg_location=ffmpeg,
        )

    def _is_cancelled(self) -> bool:
        self.cancel_checks += 1
        return self.cancel_at is not None and self.cancel_checks >= self.cancel_at


def _media_files(workdir: Path) -> list[str]:
    return sorted(p.name for p in workdir.glob("media*")) if workdir.exists() else []


def _video(params: dict | None = None) -> Callable[[dict], DownloadChoice]:
    return lambda info: video_choice(info, params or {})


def _audio(params: dict | None = None) -> Callable[[dict], DownloadChoice]:
    return lambda info: audio_choice(info, params or {})


# ---------- FakeExtractor ----------


@pytest.fixture
def fast(tmp_path: Path) -> FakeExtractor:
    """ตัวปลอมที่อ่าน behaviors ฉบับคัดลอก ตั้ง stepMs เป็น 0 ทุกตัว (เทสไม่ต้องรอ)"""
    doc = json.loads(BEHAVIORS.read_text(encoding="utf-8"))
    doc["default"]["stepMs"] = 0
    for entry in doc["videos"].values():
        entry["stepMs"] = 0
    path = tmp_path / "behaviors.json"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return FakeExtractor(FIXTURES, behaviors=path)


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    path = tmp_path / "work"
    path.mkdir()
    return path


def test_behaviors_file_is_c14_verbatim() -> None:
    assert json.loads(BEHAVIORS.read_text(encoding="utf-8")) == C14


def test_both_extractors_are_downloaders(fast: FakeExtractor) -> None:
    assert isinstance(fast, Downloader)
    assert isinstance(YtDlpExtractor(), Downloader)


def test_fake_video_copies_the_merged_mp4(fast: FakeExtractor, workdir: Path) -> None:
    rec = Recorder()
    result = fast.download(BBB, _video(), workdir, rec.hooks)
    assert isinstance(result, DownloadResult)
    assert result.path == workdir / "media.mp4"
    assert result.path.read_bytes() == (MEDIA / "video.mp4").read_bytes()
    assert "+" in result.choice.format_spec and result.choice.merge_mp4
    assert result.info["id"] == BBB
    assert _media_files(workdir) == ["media.mp4"]


def test_fake_video_stages_and_progress(fast: FakeExtractor, workdir: Path) -> None:
    rec = Recorder()
    fast.download(BBB, _video(), workdir, rec.hooks)
    assert rec.stages == ["downloading_video", "downloading_audio", "merging"]
    fractions = [f for f, _, _ in rec.progress]
    assert len(fractions) == 6
    assert all(a < b for a, b in zip(fractions, fractions[1:], strict=False))
    assert fractions[-1] == 1.0
    assert all(isinstance(s, int) and isinstance(e, int) for _, s, e in rec.progress)


def test_fake_no_audio_copies_the_silent_mp4(fast: FakeExtractor, workdir: Path) -> None:
    rec = Recorder()
    result = fast.download(BBB, _video({"noAudio": True}), workdir, rec.hooks)
    assert "+" not in result.choice.format_spec
    assert result.path == workdir / "media.mp4"
    assert result.path.read_bytes() == (MEDIA / "video-noaudio.mp4").read_bytes()
    assert rec.stages == ["downloading_video", "merging"]


def test_fake_audio_copies_the_m4a(fast: FakeExtractor, workdir: Path) -> None:
    rec = Recorder()
    result = fast.download(BBB, _audio({"format": "m4a"}), workdir, rec.hooks)
    assert result.path == workdir / "media.m4a"
    assert result.path.read_bytes() == (MEDIA / "audio.m4a").read_bytes()
    assert rec.stages == ["downloading_audio"]
    assert rec.progress[-1][0] == 1.0


def test_fake_choose_gets_the_probe_info(fast: FakeExtractor, workdir: Path) -> None:
    seen: list[dict] = []

    def choose(info: dict) -> DownloadChoice:
        seen.append(info)
        return video_choice(info, {})

    fast.download(BBB, choose, workdir, Recorder().hooks)
    assert len(seen) == 1 and seen[0]["id"] == BBB and seen[0]["formats"]


def test_fake_cancel_at_step_three_leaves_no_media(fast: FakeExtractor, workdir: Path) -> None:
    rec = Recorder(cancel_at=3)
    with pytest.raises(JobCancelled):
        fast.download(BBB, _video(), workdir, rec.hooks)
    assert len(rec.progress) == 2  # สองขั้นแรกผ่าน ขั้นที่สามถูกยกเลิกก่อนเริ่ม
    assert "merging" not in rec.stages
    assert _media_files(workdir) == []


def test_fake_choose_error_propagates_unchanged(fast: FakeExtractor, workdir: Path) -> None:
    def choose(info: dict) -> DownloadChoice:
        raise YtError("E_FFMPEG_MISSING", "no ffmpeg")

    with pytest.raises(YtError) as exc:
        fast.download(BBB, choose, workdir, Recorder().hooks)
    assert exc.value.code == "E_FFMPEG_MISSING" and exc.value.detail == "no ffmpeg"


def test_fake_network_failure_once_then_success(fast: FakeExtractor, workdir: Path) -> None:
    rec = Recorder()
    with pytest.raises(YtError) as exc:
        fast.download("NETRETRYDL1", _video(), workdir, rec.hooks)
    assert exc.value.code == "E_NETWORK" and exc.value.detail.startswith("fake: ")
    assert len(rec.progress) == 1  # failAtStep 1: ขั้นที่ 0 ผ่านไปแล้ว
    assert _media_files(workdir) == []
    result = fast.download("NETRETRYDL1", _video(), workdir, Recorder().hooks)
    assert result.path.read_bytes() == (MEDIA / "video.mp4").read_bytes()
    assert result.info["id"] == "NETRETRYDL1"


def test_fake_bot_check_once_then_success(fast: FakeExtractor, workdir: Path) -> None:
    with pytest.raises(YtError) as exc:
        fast.download("BOTCHECKDL1", _audio(), workdir, Recorder().hooks)
    assert exc.value.code == "E_BOT_CHECK"
    assert fast.download("BOTCHECKDL1", _audio(), workdir, Recorder().hooks).path.is_file()


def test_fake_refused_always_fails(fast: FakeExtractor, workdir: Path) -> None:
    for _ in range(5):
        rec = Recorder()
        with pytest.raises(YtError) as exc:
            fast.download("REFUSEDDL01", _video(), workdir, rec.hooks)
        assert exc.value.code == "E_YT_REFUSED"
        assert rec.progress == []  # failAtStep 0
    assert _media_files(workdir) == []


def test_fake_failure_count_belongs_to_one_extractor(fast: FakeExtractor, tmp_path: Path, workdir: Path) -> None:
    with pytest.raises(YtError):
        fast.download("NETRETRYDL1", _video(), workdir, Recorder().hooks)
    fresh = FakeExtractor(FIXTURES, behaviors=fast.behaviors_path)
    with pytest.raises(YtError):
        fresh.download("NETRETRYDL1", _video(), workdir, Recorder().hooks)
    # สองตัวนับแยกกัน ครั้งที่สองของแต่ละตัวผ่าน
    fast.download("NETRETRYDL1", _video(), workdir, Recorder().hooks)
    fresh.download("NETRETRYDL1", _video(), workdir, Recorder().hooks)


def test_fake_steps_follow_the_behaviour(fast: FakeExtractor, workdir: Path) -> None:
    rec = Recorder()
    fast.download("SLOWDOWNLD1", _video(), workdir, rec.hooks)
    assert len(rec.progress) == 40
    assert rec.stages == ["downloading_video", "downloading_audio", "merging"]


def test_fake_waits_step_ms_between_steps(
    fast: FakeExtractor, workdir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(extractor_mod.time, "sleep", sleeps.append)
    FakeExtractor(FIXTURES).download("SLOWDOWNLD2", _video(), workdir, Recorder().hooks)
    assert sleeps == [0.25] * 40
    sleeps.clear()
    FakeExtractor(FIXTURES).download(BBB, _video(), workdir, Recorder().hooks)
    assert sleeps == [0.12] * 6


def test_fake_probe_of_a_behaviour_id_uses_probe_as() -> None:
    fake = FakeExtractor(FIXTURES)
    info = fake.probe("SLOWDOWNLD1")
    assert info["id"] == "SLOWDOWNLD1"
    assert info["title"] == "คลิปโหลดช้า 1"
    assert info["formats"] == fake.probe(BBB)["formats"]
    assert fake.probe("REFUSEDDL01")["title"] == "คลิปที่ยูทูปไม่ส่งไฟล์"


def test_fake_unknown_id_is_still_unavailable(fast: FakeExtractor, workdir: Path) -> None:
    with pytest.raises(YtError) as exc:
        fast.probe("NOSUCHCLIP1")
    assert exc.value.code == "E_VIDEO_UNAVAILABLE"
    with pytest.raises(YtError) as exc:
        fast.download("NOSUCHCLIP1", _video(), workdir, Recorder().hooks)
    assert exc.value.code == "E_VIDEO_UNAVAILABLE"
    assert _media_files(workdir) == []


def test_fake_bad_id_is_invalid_input(fast: FakeExtractor, workdir: Path) -> None:
    with pytest.raises(YtError) as exc:
        fast.download("../../etc", _video(), workdir, Recorder().hooks)
    assert exc.value.code == "E_INVALID_INPUT"


def test_fake_without_a_behaviours_file_uses_the_defaults(
    tmp_path: Path, workdir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(extractor_mod.time, "sleep", lambda s: None)
    fake = FakeExtractor(FIXTURES, behaviors=tmp_path / "missing.json")
    rec = Recorder()
    fake.download(BBB, _video(), workdir, rec.hooks)
    assert len(rec.progress) == 6
    with pytest.raises(YtError) as exc:
        fake.probe("SLOWDOWNLD1")
    assert exc.value.code == "E_VIDEO_UNAVAILABLE"


def test_fake_download_creates_the_workdir(fast: FakeExtractor, tmp_path: Path) -> None:
    target = tmp_path / "new" / "work"
    result = fast.download(BBB, _audio(), target, Recorder().hooks)
    assert result.path == target / "media.m4a"


# ---------- YtDlpExtractor: options and hooks ----------


def _choice(spec: str = "137+140", merge: bool = True) -> DownloadChoice:
    return DownloadChoice(format_spec=spec, merge_mp4=merge, audio_language=None, notes=(), expected_bytes=None)


def test_download_opts_exact(tmp_path: Path) -> None:
    rec = Recorder(ffmpeg=tmp_path / "bin" / "ffmpeg.exe")
    opts = extractor_mod._download_opts(_choice(), tmp_path, rec.hooks)
    progress, pp, logger = opts.pop("progress_hooks"), opts.pop("postprocessor_hooks"), opts.pop("logger")
    assert opts == {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "overwrites": True,
        "socket_timeout": 20,
        "retries": 3,
        "fragment_retries": 3,
        "format": "137+140",
        "outtmpl": {"default": "media.%(ext)s"},
        "paths": {"home": str(tmp_path), "temp": str(tmp_path)},
        "merge_output_format": "mp4",
        "ffmpeg_location": str(tmp_path / "bin" / "ffmpeg.exe"),
    }
    assert len(progress) == 1 and callable(progress[0])
    assert len(pp) == 1 and callable(pp[0])
    assert isinstance(logger, extractor_mod._YtDlpLogger)


def test_download_opts_without_merge_or_ffmpeg(tmp_path: Path) -> None:
    opts = extractor_mod._download_opts(_choice("140", merge=False), tmp_path, Recorder().hooks)
    assert "merge_output_format" not in opts and "ffmpeg_location" not in opts
    assert opts["format"] == "140"


def _d(status: str, vcodec: str, done: int | None = None, **extra: Any) -> dict:
    return {"status": status, "info_dict": {"vcodec": vcodec}, "downloaded_bytes": done, **extra}


def test_progress_hook_maps_stages_and_numbers() -> None:
    rec = Recorder()
    hook = extractor_mod._progress_hook(rec.hooks)
    hook(_d("downloading", "avc1.640028", 500, total_bytes=1000, speed=1234.7, eta=3.6))
    hook(_d("downloading", "avc1.640028", 1000, total_bytes=1000, speed=None, eta=None))
    hook(_d("finished", "avc1.640028", 1000, total_bytes=1000))
    hook(_d("downloading", "none", 100, total_bytes=None, total_bytes_estimate=400.0, speed=50.0, eta=6))
    hook(_d("downloading", "none", 100, speed=50.0, eta=6))
    assert rec.stages == ["downloading_video", "downloading_audio"]
    assert rec.progress == [
        (0.5, 1234, 3),
        (1.0, None, None),
        (0.25, 50, 6),
        (None, 50, 6),
    ]


def test_progress_hook_clamps_an_estimate_that_runs_over() -> None:
    rec = Recorder()
    extractor_mod._progress_hook(rec.hooks)(_d("downloading", "none", 600, total_bytes_estimate=500))
    assert rec.progress == [(1.0, None, None)]


def test_progress_hook_raises_download_cancelled() -> None:
    rec = Recorder(cancel_at=1)
    with pytest.raises(DownloadCancelled):
        extractor_mod._progress_hook(rec.hooks)(_d("downloading", "avc1", 1, total_bytes=10))
    assert rec.progress == [] and rec.stages == []


def test_pp_hook_reports_merging() -> None:
    rec = Recorder()
    hook = extractor_mod._pp_hook(rec.hooks)
    hook({"status": "started", "postprocessor": "Merger", "info_dict": {}})
    hook({"status": "finished", "postprocessor": "Merger", "info_dict": {}})
    hook({"status": "started", "postprocessor": "FixupM4a", "info_dict": {}})
    assert rec.stages == ["merging"]


def test_pp_hook_raises_download_cancelled() -> None:
    rec = Recorder(cancel_at=1)
    with pytest.raises(DownloadCancelled):
        extractor_mod._pp_hook(rec.hooks)({"status": "started", "postprocessor": "Merger", "info_dict": {}})
    assert rec.stages == []


# ---------- YtDlpExtractor.download (yt-dlp is replaced, no network) ----------


class DownloadYDL:
    """แทน yt_dlp.YoutubeDL: ตัวแรกดึงข้อมูล (คืน fixture BBB) ตัวที่สองโหลด (เขียน media.* ลง paths.home)

    process_errors = รายการ error ที่ process_ie_result โยนทีละครั้ง (None = ผ่าน)
    write = ชื่อไฟล์ที่ process_ie_result เขียน · result = ค่าที่ process_ie_result คืน (None = requested_downloads ปกติ)
    hook_events = dict ที่ส่งให้ progress hook ก่อนเขียนไฟล์
    """

    instances: ClassVar[list[DownloadYDL]] = []
    extracted: ClassVar[list[str]] = []
    processed: ClassVar[list[dict]] = []
    extract_result: ClassVar[object] = None
    process_errors: ClassVar[list[BaseException | None]] = []
    write: ClassVar[list[str]] = ["media.mp4"]
    result: ClassVar[dict | None] = None
    hook_events: ClassVar[list[dict]] = []

    def __init__(self, params: dict) -> None:
        self.params = params
        DownloadYDL.instances.append(self)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def extract_info(self, url: str, download: bool = True) -> dict:
        assert download is False
        assert self.params.get("skip_download") is True
        DownloadYDL.extracted.append(url)
        if isinstance(DownloadYDL.extract_result, BaseException):
            raise DownloadYDL.extract_result
        raw = json.loads(json.dumps(DownloadYDL.extract_result))
        # yt-dlp จริงเลือก format ตามค่าตั้งต้นไว้แล้วตอนดึงข้อมูล (ค้างอยู่ระดับบนของ info)
        raw["requested_formats"] = [{"format_id": "stale-video"}, {"format_id": "stale-audio"}]
        raw["__post_extractor"] = None
        return raw

    @staticmethod
    def sanitize_info(info: dict, remove_private_keys: bool = False) -> dict:
        drop = {"requested_formats", "requested_downloads"} if remove_private_keys else set()
        return {
            k: v
            for k, v in json.loads(json.dumps(info)).items()
            if k not in drop and not (remove_private_keys and k.startswith("__"))
        }

    def process_ie_result(self, info: dict, download: bool = True) -> dict:
        assert download is True
        DownloadYDL.processed.append(info)
        home = Path(self.params["paths"]["home"])
        (home / "media.f137.mp4.part").write_bytes(b"partial")
        for event in DownloadYDL.hook_events:
            for hook in self.params["progress_hooks"]:
                hook(event)
        error = DownloadYDL.process_errors.pop(0) if DownloadYDL.process_errors else None
        if error is not None:
            raise error
        (home / "media.f137.mp4.part").unlink()
        for name in DownloadYDL.write:
            (home / name).write_bytes(b"media")
        if DownloadYDL.result is not None:
            return DownloadYDL.result
        return {**info, "requested_downloads": [{"filepath": str(home / DownloadYDL.write[-1])}]}


@pytest.fixture
def dl(monkeypatch: pytest.MonkeyPatch) -> type[DownloadYDL]:
    DownloadYDL.instances = []
    DownloadYDL.extracted = []
    DownloadYDL.processed = []
    DownloadYDL.extract_result = json.loads((FIXTURES / "probe" / f"{BBB}.json").read_text(encoding="utf-8"))
    DownloadYDL.process_errors = []
    DownloadYDL.write = ["media.mp4"]
    DownloadYDL.result = None
    DownloadYDL.hook_events = []
    monkeypatch.setattr(yt_dlp, "YoutubeDL", DownloadYDL)
    return DownloadYDL


class CountingChoose:
    def __init__(self, choose: Callable[[dict], DownloadChoice] | None = None) -> None:
        self.infos: list[dict] = []
        self._choose = choose or _video()

    def __call__(self, info: dict) -> DownloadChoice:
        self.infos.append(info)
        return self._choose(info)


REFUSED = "ERROR: unable to download video data: HTTP Error 403: Forbidden"


def test_real_download_extracts_once_and_downloads_with_the_choice(dl: type[DownloadYDL], workdir: Path) -> None:
    choose = CountingChoose()
    rec = Recorder(ffmpeg=Path("C:/tools/ffmpeg.exe"))
    result = YtDlpExtractor().download(BBB, choose, workdir, rec.hooks)
    assert dl.extracted == [f"https://www.youtube.com/watch?v={BBB}"]
    first, second = dl.instances
    assert first.params["skip_download"] is True
    assert len(choose.infos) == 1 and choose.infos[0]["id"] == BBB
    assert second.params["format"] == result.choice.format_spec == video_choice(choose.infos[0], {}).format_spec
    assert second.params["paths"] == {"home": str(workdir), "temp": str(workdir)}
    assert second.params["merge_output_format"] == "mp4"
    assert second.params["ffmpeg_location"] == str(Path("C:/tools/ffmpeg.exe"))
    assert result.path == workdir / "media.mp4"
    assert result.info["id"] == BBB and result.info == choose.infos[0]
    assert _media_files(workdir) == ["media.mp4"]


def test_real_download_drops_the_stale_format_selection(dl: type[DownloadYDL], workdir: Path) -> None:
    YtDlpExtractor().download(BBB, _audio(), workdir, Recorder().hooks)
    (info,) = dl.processed
    assert "requested_formats" not in info and "__post_extractor" not in info
    assert info["id"] == BBB and info["formats"]


def test_real_refused_download_runs_twice_then_fails(dl: type[DownloadYDL], workdir: Path) -> None:
    dl.process_errors = [DownloadError(REFUSED), DownloadError(REFUSED)]
    choose = CountingChoose()
    with pytest.raises(YtError) as exc:
        YtDlpExtractor().download(BBB, choose, workdir, Recorder().hooks)
    assert exc.value.code == "E_YT_REFUSED"
    assert "403" in exc.value.detail
    assert len(dl.extracted) == 2 and len(dl.processed) == 2 and len(choose.infos) == 2
    assert len(dl.instances) == 4
    assert _media_files(workdir) == []


def test_real_refused_once_then_succeeds(dl: type[DownloadYDL], workdir: Path) -> None:
    dl.process_errors = [DownloadError(REFUSED), None]
    result = YtDlpExtractor().download(BBB, _video(), workdir, Recorder().hooks)
    assert result.path == workdir / "media.mp4"
    assert len(dl.extracted) == 2
    assert _media_files(workdir) == ["media.mp4"]


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (DownloadError("ERROR: unable to download video data: HTTP Error 503: Service Unavailable"), "E_NETWORK"),
        (DownloadError("ERROR: unable to download video data: HTTP Error 429: Too Many Requests"), "E_BOT_CHECK"),
        (RuntimeError("boom"), "E_UNKNOWN"),
    ],
)
def test_real_other_download_errors_are_not_retried(
    dl: type[DownloadYDL], workdir: Path, error: Exception, code: str
) -> None:
    dl.process_errors = [error]
    with pytest.raises(YtError) as exc:
        YtDlpExtractor().download(BBB, _video(), workdir, Recorder().hooks)
    assert exc.value.code == code
    assert len(dl.extracted) == 1
    assert _media_files(workdir) == []


def test_real_cancel_from_the_progress_hook_is_job_cancelled(dl: type[DownloadYDL], workdir: Path) -> None:
    dl.hook_events = [_d("downloading", "avc1", 10, total_bytes=100)]
    rec = Recorder(cancel_at=3)  # ครั้งที่ 1-2 = ก่อนดึงข้อมูล / หลัง choose ครั้งที่ 3 = ใน progress hook
    with pytest.raises(JobCancelled):
        YtDlpExtractor().download(BBB, _video(), workdir, rec.hooks)
    assert len(dl.extracted) == 1 and len(dl.processed) == 1
    assert _media_files(workdir) == []


def test_real_cancel_before_extracting_skips_yt_dlp(dl: type[DownloadYDL], workdir: Path) -> None:
    choose = CountingChoose()
    with pytest.raises(JobCancelled):
        YtDlpExtractor().download(BBB, choose, workdir, Recorder(cancel_at=1).hooks)
    assert dl.instances == [] and choose.infos == []


def test_real_cancel_after_choose_does_not_start_the_download(dl: type[DownloadYDL], workdir: Path) -> None:
    choose = CountingChoose()
    with pytest.raises(JobCancelled):
        YtDlpExtractor().download(BBB, choose, workdir, Recorder(cancel_at=2).hooks)
    assert len(dl.extracted) == 1 and len(choose.infos) == 1
    assert len(dl.instances) == 1 and dl.processed == []


def test_real_cancel_during_a_refused_retry_does_not_re_extract(dl: type[DownloadYDL], workdir: Path) -> None:
    dl.process_errors = [DownloadError(REFUSED)]
    rec = Recorder(cancel_at=3)  # 1 = ก่อนดึงข้อมูล 2 = หลัง choose 3 = ต้นรอบลองซ้ำของ Q2
    with pytest.raises(JobCancelled):
        YtDlpExtractor().download(BBB, _video(), workdir, rec.hooks)
    assert len(dl.extracted) == 1 and len(dl.processed) == 1
    assert _media_files(workdir) == []


def test_download_logger_hides_workdir_and_home(
    workdir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    logger = extractor_mod._download_opts(_choice(), workdir, Recorder().hooks)["logger"]
    assert isinstance(logger, extractor_mod._PathHidingLogger)
    home = Path.home()
    other = home / "Videos" / "clip.mp4"
    with caplog.at_level("DEBUG", logger="yttoolkit"):
        logger.warning(f"Unable to delete file {workdir / 'media.f137.mp4'}")
        logger.error(f"ERROR: unable to open {str(workdir).upper()}{'/'}media.mp4.part")
        logger.debug(f"[download] Destination: {workdir.as_posix()}/media.f140.m4a")
        logger.info(f"wrote {other}")
    text = caplog.text
    assert "<workdir>" in text and "media.f137.mp4" in text
    assert str(workdir).lower() not in text.lower()
    assert workdir.as_posix().lower() not in text.lower()
    assert str(home).lower() not in text.lower()
    assert f"~{other.as_posix()[len(home.as_posix()):]}" in text.replace("\\", "/")


def test_download_youtubedl_gets_the_path_hiding_logger(dl: type[DownloadYDL], workdir: Path) -> None:
    YtDlpExtractor().download(BBB, _video(), workdir, Recorder().hooks)
    first, second = dl.instances
    assert type(first.params["logger"]) is extractor_mod._YtDlpLogger
    assert isinstance(second.params["logger"], extractor_mod._PathHidingLogger)


def test_real_download_reports_progress_through_hooks(dl: type[DownloadYDL], workdir: Path) -> None:
    dl.hook_events = [
        _d("downloading", "avc1", 50, total_bytes=100, speed=10.0, eta=5),
        _d("downloading", "none", 20, total_bytes=40, speed=4.0, eta=5),
    ]
    rec = Recorder()
    YtDlpExtractor().download(BBB, _video(), workdir, rec.hooks)
    assert rec.stages == ["downloading_video", "downloading_audio"]
    assert rec.progress == [(0.5, 10, 5), (0.5, 4, 5)]


def test_real_extraction_error_does_not_download(dl: type[DownloadYDL], workdir: Path) -> None:
    dl.extract_result = DownloadError("ERROR: [youtube] aqz-KE-bpKQ: Private video. Sign in if you've been granted access")
    choose = CountingChoose()
    with pytest.raises(YtError) as exc:
        YtDlpExtractor().download(BBB, choose, workdir, Recorder().hooks)
    assert exc.value.code == "E_VIDEO_PRIVATE"
    assert choose.infos == [] and len(dl.instances) == 1


def test_real_refused_extraction_is_not_repeated(dl: type[DownloadYDL], workdir: Path) -> None:
    dl.extract_result = DownloadError("ERROR: [youtube] x: Unable to download webpage: HTTP Error 403: Forbidden")
    with pytest.raises(YtError) as exc:
        YtDlpExtractor().download(BBB, _video(), workdir, Recorder().hooks)
    assert exc.value.code == "E_YT_REFUSED"
    assert len(dl.extracted) == 1


def test_real_live_clip_is_rejected_before_choosing(dl: type[DownloadYDL], workdir: Path) -> None:
    dl.extract_result = {**dl.extract_result, "live_status": "is_live"}
    choose = CountingChoose()
    with pytest.raises(YtError) as exc:
        YtDlpExtractor().download(BBB, choose, workdir, Recorder().hooks)
    assert exc.value.code == "E_LIVE_NOT_READY"
    assert choose.infos == [] and len(dl.instances) == 1


def test_real_choose_error_propagates_unchanged(dl: type[DownloadYDL], workdir: Path) -> None:
    def choose(info: dict) -> DownloadChoice:
        raise YtError("E_FFMPEG_MISSING", "no ffmpeg")

    with pytest.raises(YtError) as exc:
        YtDlpExtractor().download(BBB, choose, workdir, Recorder().hooks)
    assert exc.value.code == "E_FFMPEG_MISSING" and exc.value.detail == "no ffmpeg"
    assert len(dl.instances) == 1


def test_real_path_falls_back_to_the_single_media_file(dl: type[DownloadYDL], workdir: Path) -> None:
    dl.write = ["media.m4a"]
    dl.result = {"id": BBB}
    (workdir / "media.m4a.ytdl").write_bytes(b"state")
    (workdir / "cover.jpg").write_bytes(b"jpg")
    result = YtDlpExtractor().download(BBB, _audio(), workdir, Recorder().hooks)
    assert result.path == workdir / "media.m4a"


def test_real_missing_media_file_is_unknown(dl: type[DownloadYDL], workdir: Path) -> None:
    dl.write = []
    dl.result = {"id": BBB, "requested_downloads": [{"filepath": str(workdir / "media.mp4")}]}
    with pytest.raises(YtError) as exc:
        YtDlpExtractor().download(BBB, _video(), workdir, Recorder().hooks)
    assert exc.value.code == "E_UNKNOWN"


def test_real_two_candidate_media_files_is_unknown(dl: type[DownloadYDL], workdir: Path) -> None:
    dl.write = ["media.mp4", "media.webm"]
    dl.result = {"id": BBB}
    with pytest.raises(YtError) as exc:
        YtDlpExtractor().download(BBB, _video(), workdir, Recorder().hooks)
    assert exc.value.code == "E_UNKNOWN"
    assert _media_files(workdir) == []


def test_real_failure_keeps_files_that_are_not_media(dl: type[DownloadYDL], workdir: Path) -> None:
    (workdir / "cover.jpg").write_bytes(b"jpg")
    dl.process_errors = [RuntimeError("boom")]
    with pytest.raises(YtError):
        YtDlpExtractor().download(BBB, _video(), workdir, Recorder().hooks)
    assert (workdir / "cover.jpg").is_file()


def test_real_bad_id_never_reaches_yt_dlp(dl: type[DownloadYDL], workdir: Path) -> None:
    with pytest.raises(YtError) as exc:
        YtDlpExtractor().download("bad id", _video(), workdir, Recorder().hooks)
    assert exc.value.code == "E_INVALID_INPUT"
    assert dl.instances == []


def test_fake_reports_media_facts_only_when_the_behaviour_has_them(fast: FakeExtractor, tmp_path: Path) -> None:
    auto = fast.download("AUTOSHARP01", _video(), tmp_path / "a", Recorder().hooks)
    assert auto.media == MediaFacts(1280, 720, "SDR")
    plain = fast.download(BBB, _video(), tmp_path / "b", Recorder().hooks)
    assert plain.media is None


def test_real_download_reports_the_downloaded_format_facts(dl: type[DownloadYDL], workdir: Path) -> None:
    dl.result = {"id": BBB, "requested_downloads": [
        {"filepath": str(workdir / "media.mp4"), "width": 1280, "height": 720, "dynamic_range": "SDR"}]}
    result = YtDlpExtractor().download(BBB, _video(), workdir, Recorder().hooks)
    assert result.media == MediaFacts(1280, 720, "SDR")


def test_real_audio_download_reports_its_bitrate(dl: type[DownloadYDL], workdir: Path) -> None:
    # M6 รอบ A: ไฟล์เสียงอย่างเดียวไม่มีความสูง แต่มี abr (ส่วน "(m4a 128k)" ของชื่อไฟล์)
    dl.result = {"id": BBB, "requested_downloads": [{"filepath": str(workdir / "media.m4a"), "abr": 129.478}]}
    result = YtDlpExtractor().download(BBB, _video(), workdir, Recorder().hooks)
    assert result.media == MediaFacts(None, None, None, 129.478)


def test_real_download_without_facts_reports_none(dl: type[DownloadYDL], workdir: Path) -> None:
    result = YtDlpExtractor().download(BBB, _video(), workdir, Recorder().hooks)
    assert result.media is None
