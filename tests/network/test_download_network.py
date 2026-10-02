"""โหลดจากยูทูปจริง (M4): handler ของคิว + yt-dlp จริง + ffmpeg จริง แล้วตรวจไฟล์ที่ได้ด้วย ffprobe

ตรวจ AC-VID-01..05, 08, 09 · AC-AUD-01..04 · เพดาน compat ของคลิปแนวตั้ง · ยกเลิกกลางการโหลด (AC-Q-07)
· ไฟล์เซสชันผู้ชมไม่เปลี่ยนหลังโหลด

ต้องได้รับอนุญาตก่อนรัน: เทสนี้โหลดไฟล์วิดีโอจริงจากยูทูป (รวมประมาณ 100-200 MB ใน temp ลบทิ้งเมื่อทุกเทสผ่าน ถ้ามีเทสตกจะเก็บไว้ดูและพิมพ์ path ที่เก็บ)
รันเองด้วย: uv run pytest -m network -q tests/network/test_download_network.py -s
id ของคลิปอยู่ใน tests/network_videos.toml ([downloads]) เทสเก็บไฟล์ใน temp เท่านั้น ไม่มีอะไรลงรีโป
ยูทูปตอบ 429 หรือขอยืนยันว่าไม่ใช่บอท (E_BOT_CHECK) = เทสตก ให้รายงานผล ห้ามแก้เทสให้หลวมลง
(งานแต่ละงานเว้น 2 วินาทีก่อนเริ่ม เหมือนที่คิวทำ)

ยังไม่ครอบคลุม (ต้องใช้คลิปที่หาแบบกำหนดไม่ได้ จดไว้ใน docs/m4-followups.md): 403 จริงที่ดึงข้อมูลใหม่รอบเดียวหาย,
429 จริงที่กลายเป็น E_BOT_CHECK, คลิป post-live, คลิปอายุไม่ถึง 2 วันที่มีแต่ HLS (รวมการยกเลิกบน HLS)
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
import tomllib
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from helpers_ffmpeg import ffprobe_json, requires_ffmpeg

from yttoolkit.core import thai_fallback as tf
from yttoolkit.core.cancel import JobCancelled
from yttoolkit.core.db import Database
from yttoolkit.core.extractor import YtDlpExtractor, visitor_session, ytdlp_version
from yttoolkit.core.files import SOURCE_NOTE_NAME
from yttoolkit.core.handlers import NO_AUDIO_SUFFIX, HandlerDeps, build_handlers
from yttoolkit.core.jobs import Job, JobResult
from yttoolkit.core.media import FfmpegTools, iso639_2
from yttoolkit.core.srt_builder import options_from_dict
from yttoolkit.core.subtitles import SubtitleService
from yttoolkit.core.videos import VideoService
from yttoolkit.core.visitor_session import META_FILE, SESSION_FILE, VISITOR_COOKIE

pytestmark = [pytest.mark.network, requires_ffmpeg]

_TOML = Path(__file__).resolve().parents[1] / "network_videos.toml"
CLIPS: dict[str, str] = tomllib.loads(_TOML.read_text(encoding="utf-8"))["downloads"]

SHORT_4K = CLIPS["short_4k"]
DUB_CLIP = CLIPS["dub_clip"]
THAI_SUBS = CLIPS["thai_subs"]
PORTRAIT = CLIPS["portrait_short"]

MEDIUM = {"maxChars": 25, "lines": 1, "minMs": 1200, "maxMs": 5000}
# เทสที่ไม่ได้ตรวจความละเอียดส่ง maxHeight ต่ำ (240 / 360) ให้ไฟล์เล็กและโหลดเร็ว ลดปริมาณเน็ตของ network test
# maxHeight เป็นตัวเลือกจริงของงาน (compat cap) เส้นทางเลือก format จึงยังเป็นของจริง เทสที่ตรวจ 1080/2160 ไม่ส่ง maxHeight
SMALL = 240
QUEUE_GAP_S = 2  # ช่วงห่างระหว่างงานที่ต่อยูทูป (คิวจริงเว้น 2-5 วินาที)
CANCEL_LIMIT_S = 3.0  # AC-Q-07


# ---------- ตัวช่วย ----------


class JobCtx:
    """JobContext จริงขั้นต่ำสำหรับเรียก handler ตรง ๆ (ไม่ผ่านคิว) · on_progress ตั้งธงยกเลิกได้"""

    def __init__(self, workdir: Path, output_root: Path) -> None:
        self.job_id = "01900000-0000-7000-8000-0000000000aa"
        self.workdir = workdir
        self.output_root = output_root
        self.stages: list[str] = []
        self.titles: list[str] = []
        self.cancel_after_progress = False  # ตั้งธงยกเลิกเมื่อโหลดได้ความคืบหน้าแรก
        self.cancel_set_at: float | None = None
        self._cancelled = False

    def stage(self, stage: str) -> None:
        self.stages.append(stage)

    def progress(self, fraction: float | None, speed_bps: int | None = None, eta_s: int | None = None) -> None:
        if self.cancel_after_progress and fraction and not self._cancelled:
            self._cancelled = True
            self.cancel_set_at = time.monotonic()

    def set_title(self, title: str) -> None:
        self.titles.append(title)

    def cancelled(self) -> bool:
        return self._cancelled

    def check_cancelled(self) -> None:
        if self._cancelled:
            raise JobCancelled()

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)
        self.check_cancelled()


def _say(text: str) -> None:
    """พิมพ์ลงคอนโซลโดยไม่ล้มเมื่อชื่อคลิปมีอักขระที่ code page ของ Windows ไม่มี (เช่นอีโมจิ)"""
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(text.encode(encoding, "replace").decode(encoding))


@dataclass
class Run:
    result: JobResult
    path: Path  # ไฟล์ผลลัพธ์ตัวแรก
    probe: dict  # ผล ffprobe ของไฟล์นั้น
    seconds: float


@dataclass
class Env:
    root: Path
    extractor: YtDlpExtractor
    videos: VideoService
    subs: SubtitleService
    ffmpeg: Path
    handlers: dict[str, Callable[[Job, JobCtx], JobResult]]
    runs: dict[str, Run] = field(default_factory=dict)
    timings: list[str] = field(default_factory=list)
    counter: int = 0
    last_start: float = 0.0

    def info(self, video_id: str) -> dict:
        return self.videos.get(video_id)

    def job(self, kind: str, video_id: str, params: dict[str, Any]) -> Job:
        return Job(
            id="01900000-0000-7000-8000-0000000000aa",
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
            position=0,
            error_code=None,
            error_message=None,
            error_detail=None,
            notes=(),
            outputs=(),
            created_at="2026-10-02T00:00:00Z",
            started_at=None,
            finished_at=None,
        )

    def context(self) -> JobCtx:
        self.counter += 1
        workdir = self.root / "work" / str(self.counter)
        workdir.mkdir(parents=True)
        return JobCtx(workdir, self.root / "output")

    def gap(self) -> None:
        """เว้นช่วงจากงานก่อนหน้า (ไม่ยิงยูทูปถี่กว่าที่คิวจริงทำ)"""
        wait = QUEUE_GAP_S - (time.monotonic() - self.last_start)
        if wait > 0:
            time.sleep(wait)
        self.last_start = time.monotonic()

    def run(self, kind: str, video_id: str, **params: Any) -> Run:
        """รัน handler ของงานนี้หนึ่งครั้ง (จำผลไว้ ชุดพารามิเตอร์เดียวกันไม่โหลดซ้ำ) แล้ว ffprobe ไฟล์ที่ได้"""
        key = f"{kind}:{video_id}:{json.dumps(params, sort_keys=True)}"
        if key not in self.runs:
            self.gap()
            ctx = self.context()
            start = time.monotonic()
            result = self.handlers[kind](self.job(kind, video_id, dict(params)), ctx)
            took = time.monotonic() - start
            assert len(result.outputs) == 1, f"ต้องได้ไฟล์เดียว ได้ {result.outputs}"
            out = result.outputs[0]
            path = Path(out.root) / out.rel
            assert path.is_file()
            assert path.stat().st_size == out.size_bytes
            self.runs[key] = Run(result, path, ffprobe_json(path), took)
            self.timings.append(f"{kind} {video_id} {path.suffix} {took:.1f}s {path.stat().st_size // 1024}KB")
            _say(f"{kind} {video_id} {params}: {took:.1f}s -> {path.name} ({path.stat().st_size // 1024} KB)")
        return self.runs[key]


@pytest.fixture(scope="module")
def env(tmp_path_factory: pytest.TempPathFactory, request: pytest.FixtureRequest) -> Iterator[Env]:
    root = tmp_path_factory.mktemp("download-network")
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg is not None
    ytdlp_version()  # import yt_dlp ก่อน เวลา import จะได้ไม่ปนเข้าไปในเวลางาน
    with pytest.MonkeyPatch.context() as mp:
        # PyThaiNLP สร้างโฟลเดอร์ข้อมูลตอนใช้ครั้งแรก เก็บไว้ใน temp ไม่ใช่ ~/
        mp.setenv(tf.DATA_ENV, str(root / "pythainlp-data"))
        db = Database(root / "app.db")
        db.migrate()
        session = visitor_session(root / "data")  # เซสชันผู้ชมแบบเดียวกับตัวโปรแกรมจริง
        extractor = YtDlpExtractor(session=session)
        videos = VideoService(db, extractor)
        subs = SubtitleService(videos, extractor.fetch_subtitle, root / "cache", session=session)
        media = FfmpegTools(lambda: Path(ffmpeg))
        deps = HandlerDeps(
            videos=videos,
            downloader=extractor,  # type: ignore[arg-type]
            media=media,
            subtitles=subs,
            cache_root=root / "cache",
        )
        state = Env(root, extractor, videos, subs, Path(ffmpeg), build_handlers(deps))  # type: ignore[arg-type]
        try:
            yield state
        finally:
            extractor.close()
            db.close()
            # ASCII ล้วน: คอนโซล Windows ภาษาไทย (cp874) พิมพ์ตัวอักษรพิเศษไม่ได้
            print("\n[timings] " + ", ".join(state.timings))
            if request.session.testsfailed:
                print(f"[kept for inspection] {root}")  # เทสตก = เก็บไฟล์ไว้ดู
            else:
                shutil.rmtree(root, ignore_errors=True)  # ผ่านหมด = ลบไฟล์ที่โหลดมาทิ้ง


def tags(section: dict) -> dict[str, str]:
    """tags ของ ffprobe (stream หรือ format) แบบชื่อตัวพิมพ์เล็ก"""
    return {k.lower(): v for k, v in (section.get("tags") or {}).items()}


def streams(run: Run, kind: str) -> list[dict]:
    return [s for s in run.probe["streams"] if s["codec_type"] == kind]


def main_video(run: Run) -> dict:
    """ภาพหลัก (ไม่ใช่ปก attached_pic)"""
    found = [s for s in streams(run, "video") if not s.get("disposition", {}).get("attached_pic")]
    assert len(found) == 1, f"ต้องมีภาพหลัก 1 สตรีม ได้ {len(found)}"
    return found[0]


def short_side(stream: dict) -> int:
    return min(int(stream["width"]), int(stream["height"]))


def original_audio(info: dict) -> dict:
    """แทร็ก AAC ต้นฉบับที่ bitrate สูงสุด (ตัวที่งานเสียง/วิดีโอเลือกเมื่อไม่ระบุภาษา)"""
    originals = [a for a in info["audio"] if a["isOriginal"]] or info["audio"]
    aac = [a for a in originals if str(a["acodec"]).startswith("mp4a")] or originals
    return max(aac, key=lambda a: a.get("abrKbps", 0))


def audio_md5(ffmpeg: Path, path: Path) -> str:
    """แฮชข้อมูลเสียงแทร็กแรกแบบไม่ถอดรหัส (copy) ใช้เทียบว่าเป็นแทร็กเดียวกันไหม โดยไม่พึ่งแท็กที่ handler เขียนเอง"""
    out = subprocess.run(
        [str(ffmpeg), "-v", "error", "-i", str(path), "-map", "0:a:0", "-c", "copy", "-f", "md5", "-"],
        check=True,
        capture_output=True,
    ).stdout.decode()
    return out.strip()


def srt_texts(text: str) -> list[str]:
    """ข้อความของแต่ละซับใน .srt (ตัดเลขลำดับกับบรรทัดเวลา) ไว้เทียบข้อความอย่างเดียว"""
    cues = []
    for block in re.split(r"\r?\n\r?\n", text.strip()):
        lines = block.strip().splitlines()
        body = [ln.strip() for ln in lines if ln.strip() and not ln.strip().isdigit() and "-->" not in ln]
        cues.append("\n".join(body))
    return cues


# ---------- วิดีโอ: ค่าเริ่มต้น (AC-VID-01, AC-VID-04) ----------


def test_default_is_h264_aac_at_most_1080(env: Env) -> None:
    """AC-VID-01: ค่าเริ่มต้น = H.264 + AAC ความสูง ≤ 1080 (คลิปนี้มี avc1 ถึง 1080 จึงต้องได้ 1080 พอดี ไม่ต่ำกว่า)"""
    run = env.run("video", SHORT_4K)
    video = main_video(run)
    assert video["codec_name"] == "h264"
    assert int(video["height"]) == 1080
    audio = streams(run, "audio")
    assert len(audio) == 1 and audio[0]["codec_name"] == "aac"
    assert run.path.suffix == ".mp4"
    assert NO_AUDIO_SUFFIX not in run.path.name


def test_cover_and_metadata(env: Env) -> None:
    """AC-VID-04: มีภาพปก (attached_pic) และ metadata ชื่อคลิป ช่อง ลิงก์ต้นทาง"""
    run = env.run("video", SHORT_4K)
    info = env.info(SHORT_4K)
    covers = [s for s in streams(run, "video") if s.get("disposition", {}).get("attached_pic")]
    assert len(covers) == 1
    meta = tags(run.probe["format"])
    assert meta["title"] == info["title"]
    assert meta["artist"] == info["channel"]
    assert meta["comment"] == f"https://www.youtube.com/watch?v={SHORT_4K}"


def test_source_note_beside_the_file(env: Env) -> None:
    """AC-OUT-06/07 กับคลิปจริง: มี แหล่งที่มา.txt ข้างไฟล์ และบรรทัดสัญญาอนุญาตเป็นค่าที่ probe ได้"""
    run = env.run("video", SHORT_4K)
    note = (run.path.parent / SOURCE_NOTE_NAME).read_bytes()
    assert not note.startswith(b"\xef\xbb\xbf")
    text = note.decode("utf-8")
    assert f"https://www.youtube.com/watch?v={SHORT_4K}" in text
    license_text = env.info(SHORT_4K).get("license")
    assert license_text
    assert license_text in text


# ---------- วิดีโอ: ความละเอียดสูงสุด (AC-VID-02) ----------


def test_max_quality_with_chosen_2160p(env: Env) -> None:
    """AC-VID-02: เปิด "ความละเอียดสูงสุด" + เลือก 2160p → ไฟล์ mp4 ความสูง 2160"""
    info = env.info(SHORT_4K)
    top = max(info["video"], key=lambda v: v["height"])
    assert top["height"] == 2160, "คลิปนี้ต้องมี 4K (ตรวจ 2026-10-02) ถ้าไม่มีแล้วให้เปลี่ยนคลิปใน toml"
    run = env.run("video", SHORT_4K, maxQuality=True, formatId=top["formatId"])
    assert int(main_video(run)["height"]) == 2160
    assert run.path.suffix == ".mp4"
    assert len(streams(run, "audio")) == 1


def test_max_quality_auto_picks_the_best_video(env: Env) -> None:
    """รายการ smoke ของ T9: maxQuality ไม่ระบุ formatId → bv*+ba ได้ไฟล์ mp4 ที่ถูกต้องและมีเสียง"""
    run = env.run("video", SHORT_4K, maxQuality=True)
    assert int(main_video(run)["height"]) == 2160
    assert run.path.suffix == ".mp4"
    assert len(streams(run, "audio")) == 1


# ---------- วิดีโอ: ภาษาเสียง (AC-VID-03, AC-VID-05) ----------


def test_original_audio_is_the_default_track(env: Env) -> None:
    """AC-VID-03: คลิปหลายภาษา → แทร็กเสียงในไฟล์คือ original (เทียบ language กับข้อมูลจาก probe)"""
    info = env.info(DUB_CLIP)
    assert len(info["audio"]) > 1 and len({a.get("language") for a in info["audio"]}) > 1
    original = original_audio(info)
    run = env.run("video", DUB_CLIP, maxHeight=SMALL)
    audio = streams(run, "audio")
    assert len(audio) == 1
    assert tags(audio[0])["language"] == iso639_2(original["language"])
    assert tags(audio[0])["language"] == "tha"


def test_dub_language_is_chosen_not_the_original(env: Env) -> None:
    """AC-VID-05 (กลับด้าน): ยังไม่มีคลิปอังกฤษที่พากย์ไทย จึงเลือก "en" ในคลิปไทยที่มีพากย์ en-US
    → แทร็กในไฟล์เป็นภาษาอังกฤษ และไม่ใช่แทร็ก original"""
    info = env.info(DUB_CLIP)
    original = original_audio(info)
    assert not str(original["language"]).lower().startswith("en")
    run = env.run("video", DUB_CLIP, maxHeight=SMALL, audioLanguage="en")
    audio = streams(run, "audio")
    assert len(audio) == 1
    assert tags(audio[0])["language"] == "eng"
    assert tags(audio[0])["language"] != iso639_2(original["language"])
    assert not run.result.notes  # มีแทร็กนี้จริง จึงไม่มีหมายเหตุว่าใช้เสียงต้นฉบับแทน
    # ตรวจอิสระจากแท็กที่ handler เขียนเอง: ข้อมูลเสียงของสองไฟล์ต้องต่างกันจริง (คนละแทร็ก)
    original_run = env.run("video", DUB_CLIP, maxHeight=SMALL)
    assert audio_md5(env.ffmpeg, run.path) != audio_md5(env.ffmpeg, original_run.path)


def test_dub_language_in_m4a(env: Env) -> None:
    """AC-VID-05 ส่วน m4a: เสียงพากย์ในไฟล์ m4a ก็เป็นภาษาที่เลือก"""
    run = env.run("audio", DUB_CLIP, format="m4a", audioLanguage="en")
    audio = streams(run, "audio")
    assert len(audio) == 1
    assert tags(audio[0])["language"] == "eng"


# ---------- วิดีโอ: ไม่เอาเสียง (AC-VID-08) ----------


def test_no_audio_has_no_audio_stream(env: Env) -> None:
    """AC-VID-08: เปิด "ไม่เอาเสียง" → ไม่มี audio stream และชื่อไฟล์ลงท้าย " (ไม่มีเสียง).mp4" """
    run = env.run("video", SHORT_4K, noAudio=True, maxHeight=360)  # 360 = ให้ไฟล์เล็ก (ดูหมายเหตุที่ SMALL)
    assert streams(run, "audio") == []
    assert run.path.name.endswith(f"{NO_AUDIO_SUFFIX}.mp4")
    assert main_video(run)["codec_name"] == "h264"
    assert int(main_video(run)["height"]) == 360


# ---------- วิดีโอ: ฝังซับ (AC-VID-09) ----------


def test_embedded_subtitle_is_mov_text_without_reencoding(env: Env) -> None:
    """AC-VID-09: ฝังซับ th-orig → mov_text 1 แทร็ก language tha · ภาพไม่ถูกเข้ารหัสใหม่ · ข้อความตรงกับ .srt preset เดียวกัน"""
    plain = env.run("video", THAI_SUBS, maxHeight=SMALL)
    embedded = env.run("video", THAI_SUBS, maxHeight=SMALL, embedSubs="a.th-orig", subOptions=MEDIUM)
    assert not embedded.result.notes, f"ฝังซับไม่สำเร็จ: {embedded.result.notes}"

    subs = streams(embedded, "subtitle")
    assert len(subs) == 1
    assert subs[0]["codec_name"] == "mov_text"
    assert tags(subs[0])["language"] == "tha"
    assert streams(plain, "subtitle") == []

    # ภาพไม่ถูกเข้ารหัสใหม่: codec และ bitrate เท่ากับกรณีไม่ฝังซับ (copy สตรีมเดิม)
    a, b = main_video(plain), main_video(embedded)
    assert a["codec_name"] == b["codec_name"]
    assert (a["width"], a["height"]) == (b["width"], b["height"])
    # bit_rate ต้องมีทั้งคู่ ไม่ปล่อยผ่านเงียบ ๆ ถ้า ffprobe ไม่ให้ค่า
    assert a.get("bit_rate") and b.get("bit_rate"), "ffprobe ไม่ให้ bit_rate ของภาพหลัก"
    assert abs(int(a["bit_rate"]) - int(b["bit_rate"])) <= 0.01 * int(a["bit_rate"])

    # ข้อความซับตรงกับ .srt ที่สร้างด้วย preset เดียวกัน
    expected = env.subs.export(THAI_SUBS, "a.th-orig", "srt", options_from_dict(MEDIUM)).data.decode("utf-8")
    out_srt = env.root / "embedded-out.srt"
    subprocess.run(
        [str(env.ffmpeg), "-v", "error", "-y", "-i", str(embedded.path), "-map", "0:s:0", str(out_srt)],
        check=True,
        capture_output=True,
    )
    assert srt_texts(out_srt.read_text(encoding="utf-8")) == srt_texts(expected)


# ---------- เสียงอย่างเดียว (AC-AUD-01..04) ----------


def test_m4a_is_not_reencoded(env: Env) -> None:
    """AC-AUD-01: m4a → codec AAC ตรงกับต้นฉบับ (bitrate เท่าแทร็กที่โหลด ไม่ผ่านการเข้ารหัสใหม่) มีปกและ metadata"""
    run = env.run("audio", SHORT_4K, format="m4a")
    audio = streams(run, "audio")
    assert len(audio) == 1 and audio[0]["codec_name"] == "aac"
    source = original_audio(env.info(SHORT_4K))
    assert source["acodec"].startswith("mp4a")
    assert abs(int(audio[0]["bit_rate"]) - source["abrKbps"] * 1000) <= 0.1 * source["abrKbps"] * 1000
    assert run.path.suffix == ".m4a"
    covers = [s for s in streams(run, "video") if s.get("disposition", {}).get("attached_pic")]
    assert len(covers) == 1
    meta = tags(run.probe["format"])
    assert meta["title"] == env.info(SHORT_4K)["title"]
    assert meta["artist"] == env.info(SHORT_4K)["channel"]


def test_mp3_192_bitrate(env: Env) -> None:
    """AC-AUD-02: mp3 192 → bitrate 192 kbps ± 5%"""
    run = env.run("audio", SHORT_4K, format="mp3", mp3Kbps=192)
    audio = streams(run, "audio")
    assert len(audio) == 1 and audio[0]["codec_name"] == "mp3"
    kbps = int(audio[0]["bit_rate"]) / 1000
    assert 192 * 0.95 <= kbps <= 192 * 1.05
    assert tags(run.probe["format"])["title"] == env.info(SHORT_4K)["title"]


def test_wav_matches_the_source_track(env: Env) -> None:
    """AC-AUD-03: wav → pcm_s16le, sample rate เท่าแทร็กต้นฉบับ, ความยาวเท่า ± 0.1 วิ, มี metadata ชื่อคลิปและช่อง"""
    wav = env.run("audio", SHORT_4K, format="wav")
    m4a = env.run("audio", SHORT_4K, format="m4a")  # แทร็กเดียวกัน (ต้นฉบับ AAC) ใช้เป็นต้นฉบับเทียบ
    stream = streams(wav, "audio")[0]
    source = streams(m4a, "audio")[0]
    assert stream["codec_name"] == "pcm_s16le"
    assert stream["sample_rate"] == source["sample_rate"]
    assert stream["channels"] == source["channels"]
    assert abs(float(wav.probe["format"]["duration"]) - float(m4a.probe["format"]["duration"])) <= 0.1
    meta = tags(wav.probe["format"])
    assert meta["title"] == env.info(SHORT_4K)["title"]
    assert meta["artist"] == env.info(SHORT_4K)["channel"]
    assert wav.path.suffix == ".wav"


def test_wav_size_within_5_percent_of_the_estimate(env: Env) -> None:
    """AC-AUD-04: ขนาด wav ที่ W2 บอก (ความยาว x sample rate x ช่อง x 2 ไบต์ ตามค่าที่ probe ได้) คลาดไม่เกิน 5% จากไฟล์จริง

    ฝั่งเว็บใช้ sampleRate/channels จริงของแทร็ก (ไม่รู้ = 44100 Hz 2 ช่อง) ตัวเลขนี้ตรงกับที่ฝั่งเว็บคำนวณ
    ฝั่งหลังบ้านใช้ 44100 Hz 2 ช่องตายตัวสำหรับตรวจพื้นที่ว่างเท่านั้น (ไม่ใช่ตัวเลขที่ผู้ใช้เห็น)
    """
    info = env.info(SHORT_4K)
    source = original_audio(info)
    estimate = info["durationS"] * source.get("sampleRate", 44100) * source.get("channels", 2) * 2
    actual = env.run("audio", SHORT_4K, format="wav").path.stat().st_size
    assert abs(actual - estimate) <= 0.05 * estimate, f"ประมาณ {estimate} ไบต์ ได้จริง {actual} ไบต์"


# ---------- คลิปแนวตั้ง: เพดาน compat นับที่ด้านสั้น ----------


def test_portrait_short_gets_1080_on_the_short_side(env: Env) -> None:
    """คลิปแนวตั้ง 1080x1920 ต้องไม่ถูกตัดเหลือ 480p-class (เพดาน 1080 นับที่ด้านสั้น)"""
    info = env.info(PORTRAIT)
    compat = [v for v in info["video"] if v["compat"]]
    assert any(min(v.get("width", v["height"]), v["height"]) == 1080 for v in compat), "คลิปต้องมี avc1 1080 ด้านสั้น"
    run = env.run("video", PORTRAIT)
    video = main_video(run)
    assert video["codec_name"] == "h264"
    assert int(video["width"]) < int(video["height"])  # ยังเป็นแนวตั้ง
    assert short_side(video) == 1080


# ---------- ยกเลิก (AC-Q-07) ----------


def test_cancel_during_download_stops_within_3_seconds(env: Env) -> None:
    """AC-Q-07 บน HTTP แบบแบ่งก้อนจริง: ยกเลิกทันทีที่โหลดได้ความคืบหน้าแรก → หยุดภายใน 3 วิ ไม่มีไฟล์ค้างและไม่มีไฟล์ผลลัพธ์"""
    env.gap()
    ctx = env.context()
    before = {p for p in ctx.output_root.rglob("*") if p.is_file()} if ctx.output_root.exists() else set()
    ctx.cancel_after_progress = True
    with pytest.raises(JobCancelled):
        env.handlers["video"](env.job("video", THAI_SUBS, {}), ctx)
    raised_at = time.monotonic()
    assert ctx.cancel_set_at is not None, "โหลดจบก่อนมีความคืบหน้าแรก (ลองคลิปที่ใหญ่กว่านี้)"
    took = raised_at - ctx.cancel_set_at
    print(f"cancel took {took:.2f}s")
    env.timings.append(f"cancel {took:.2f}s")
    assert took < CANCEL_LIMIT_S
    leftovers = [p.name for p in ctx.workdir.rglob("*") if p.is_file()]
    assert not leftovers, f"ไฟล์ค้างในโฟลเดอร์ทำงาน: {leftovers}"
    after = {p for p in ctx.output_root.rglob("*") if p.is_file()} if ctx.output_root.exists() else set()
    assert after == before, "ห้ามมีไฟล์ใหม่ในโฟลเดอร์ผลลัพธ์จากงานที่ยกเลิก"


# ---------- เซสชันผู้ชม ----------


def _session_state(folder: Path) -> tuple[str | None, object]:
    """(ค่าคุกกี้ผู้เข้าชม, เวลาเกิดของเซสชัน) ไม่แสดงค่าคุกกี้ที่ไหนทั้งสิ้น เทียบกันในหน่วยความจำเท่านั้น"""
    visitor = None
    for line in (folder / SESSION_FILE).read_text(encoding="utf-8").splitlines():
        parts = line.removeprefix("#HttpOnly_").split("\t")
        if len(parts) >= 7 and parts[5] == VISITOR_COOKIE and "youtube" in parts[0]:
            visitor = parts[6]
    created = json.loads((folder / META_FILE).read_text(encoding="utf-8")).get("createdAt")
    return visitor, created


def test_visitor_session_is_unchanged_by_a_download(env: Env) -> None:
    """โหลดไฟล์แล้วเซสชันผู้ชม (ไฟล์คุกกี้ที่ซับแปลใช้) ยังเป็นคนเดิม: ค่าคุกกี้ผู้เข้าชมและเวลาเกิดของเซสชันไม่เปลี่ยน"""
    folder = env.root / "data"
    env.videos.get(SHORT_4K, refresh=True)  # probe สดอย่างน้อย 1 ครั้ง เซสชันจึงมีคุกกี้ผู้เข้าชม
    before_visitor, before_created = _session_state(folder)
    assert before_visitor, "เซสชันยังไม่มีคุกกี้ผู้เข้าชมหลัง probe"
    env.run("audio", SHORT_4K, format="m4a")  # โหลดจริงอย่างน้อย 1 ครั้ง (ถ้าโหลดไว้แล้วในเทสก่อนหน้าก็ยังเทียบได้)
    env.run("audio", SHORT_4K, format="mp3", mp3Kbps=128)  # งานใหม่จริง ๆ อีกหนึ่งงาน
    after_visitor, after_created = _session_state(folder)
    same_visitor = before_visitor == after_visitor  # ไม่ใส่ในข้อความ assert: ห้ามพิมพ์ค่าคุกกี้
    # ค่าเปลี่ยน = ให้ไปตรวจ ไม่ได้แปลว่าบั๊กเสมอไป: ยูทูปอาจหมุนค่าคุกกี้ผู้เข้าชมเอง (ลองรันซ้ำก่อน)
    assert same_visitor, "ค่าคุกกี้ผู้เข้าชมเปลี่ยนหลังโหลด (ตรวจว่าเป็นแอพทำ หรือยูทูปหมุนค่าเอง)"
    assert before_created == after_created, "เวลาเกิดของเซสชันเปลี่ยนหลังโหลด"
    # ไฟล์ยังอ่านได้ทั้งไฟล์ และไม่ทิ้งไฟล์ชั่วคราวข้าง ๆ
    assert [p.name for p in folder.iterdir() if p.name.startswith("visitor-session")] == sorted(
        [META_FILE, SESSION_FILE]
    )


# ---------- ห้ามเหลือไฟล์ค้าง ----------


def test_no_leftovers_in_work_folders(env: Env) -> None:
    """หลังงานสำเร็จ โฟลเดอร์ผลลัพธ์มีแต่ไฟล์สื่อกับ แหล่งที่มา.txt (ไม่มี .part ไม่มีไฟล์ 0 ไบต์)"""
    if not env.runs:
        pytest.skip("ยังไม่มีงานที่โหลดสำเร็จในรอบนี้")
    for path in (env.root / "output").rglob("*"):
        if path.is_file():
            assert ".part" not in path.name and ".ytdl" not in path.name, path.name
            assert path.stat().st_size > 0, f"{path.name} ขนาด 0"
