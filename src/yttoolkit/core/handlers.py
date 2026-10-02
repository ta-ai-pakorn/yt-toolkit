"""ตัวทำงานของแต่ละชนิดงานในคิว (M4): video, audio, subtitle, contact_sheet, frames_zip

ตัวทำงานแค่เรียงขั้นตอน ไม่ตัดสินใจเรื่องคิว (ลองใหม่ พักคิว ยกเลิก เป็นของ core/queue.py):
ดึงข้อมูลคลิป (cache) -> โหลด (extractor) -> จัดไฟล์สื่อ (ffmpeg) -> ย้ายเข้าโฟลเดอร์ผลลัพธ์ -> แหล่งที่มา.txt

- ไฟล์ระหว่างทำทุกไฟล์อยู่ใน ctx.workdir (ตัวรันคิวลบทิ้งหลังงานจบ) ชื่อจริงในโฟลเดอร์ผลลัพธ์
  จองด้วย files.move_into_place เท่านั้น จึงไม่มีไฟล์ครึ่ง ๆ กลาง ๆ ค้างที่ชื่อจริง
- log บอกแค่รหัสงานและ path สัมพัทธ์กับโฟลเดอร์ผลลัพธ์ (path เต็มมีชื่อผู้ใช้ Windows)
core/ ไม่ import api/ หรือ platform/
"""

from __future__ import annotations

import io
import logging
import math
import shutil
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image

from . import files
from .download import DownloadChoice, Downloader, DownloadHooks, audio_choice, video_choice
from .frames import contact_sheet, frames_zip
from .jobs import Handler, Job, JobContext, JobResult, OutputFile
from .media import MediaMeta, MediaTools, SubtitleInput, iso639_2
from .srt_builder import SubOptions, options_from_dict
from .storyboard import FOLDER as STORYBOARD_FOLDER
from .storyboard import get_storyboard
from .yterrors import YtError

if TYPE_CHECKING:
    from .subtitles import SubtitleExport, SubtitleService
    from .videos import VideoService

log = logging.getLogger("yttoolkit")

DISK_FACTOR = 2  # ต้องมีที่ว่างอย่างน้อย 2 เท่าของขนาดคาดการณ์ (ไฟล์โหลด + ไฟล์ที่จัดเสร็จ)
WARMING_WAIT_S = 5  # E_SESSION_WARMING ที่ไม่บอกเวลารอ
DEFAULT_MP3_KBPS = 192
NO_AUDIO_SUFFIX = " (ไม่มีเสียง)"
CONTACT_SHEET_SUFFIX = " - contact sheet"
FRAMES_ZIP_SUFFIX = " - frames"
COVER_JPEG_QUALITY = 90
# ยูทูปมีปัญหาชั่วคราว: ให้คิวลองใหม่ / พักคิว แทนการได้วิดีโอที่ไม่มีซับ
_EMBED_RETRY_CODES = frozenset({"E_NETWORK", "E_BOT_CHECK"})


def _default_disk_free(path: Path) -> int:
    return shutil.disk_usage(path).free


@dataclass
class HandlerDeps:
    videos: VideoService
    downloader: Downloader  # C8 (extractor)
    media: MediaTools  # C9
    subtitles: SubtitleService
    cache_root: Path
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    disk_free: Callable[[Path], int] = _default_disk_free


# ---------- ตัวช่วย ----------


class _Reporter:
    """ส่งขั้นตอน/ความคืบหน้าให้ ctx โดยตัดค่าซ้ำ (ffmpeg รายงานค่าเดิมซ้ำได้)

    เปลี่ยนขั้นตอน = ล้างความคืบหน้า ความเร็ว และเวลาที่เหลือของขั้นก่อน
    """

    def __init__(self, ctx: JobContext) -> None:
        self._ctx = ctx
        self._stage: str | None = None
        self._last: tuple[float | None, int | None, int | None] | None = None

    def stage(self, stage: str) -> None:
        if stage == self._stage:
            return
        self._stage = stage
        self._ctx.stage(stage)
        if self._last is not None and self._last != (None, None, None):
            self._ctx.progress(None)
        self._last = (None, None, None)

    def progress(self, fraction: float | None, speed_bps: int | None = None, eta_s: int | None = None) -> None:
        value = (fraction, speed_bps, eta_s)
        if value == self._last:
            return
        self._last = value
        self._ctx.progress(fraction, speed_bps, eta_s)

    def fraction(self, fraction: float | None) -> None:
        self.progress(fraction)


@dataclass(frozen=True)
class _Clip:
    """ข้อมูลคลิปที่ทุกงานใช้ร่วมกัน"""

    video_id: str
    info: dict  # VideoInfo (camelCase)
    title: str
    root: Path  # โฟลเดอร์ผลลัพธ์แบบ absolute ที่ resolve แล้ว

    @property
    def meta(self) -> MediaMeta:
        duration = self.info.get("durationS")
        return MediaMeta(
            title=self.title,
            artist=str(self.info.get("channel") or ""),
            comment=f"https://www.youtube.com/watch?v={self.video_id}",
            date=_published(self.info),
            duration_s=float(duration) if isinstance(duration, int | float) and duration > 0 else None,
        )


def _published(info: Mapping[str, Any]) -> str | None:
    """วันที่เผยแพร่แบบ YYYY-MM-DD (VideoInfo.publishedAt แปลงจาก 20260901 มาแล้ว) ไม่รู้ = None"""
    text = str(info.get("publishedAt") or "")[:10]
    return text or None


def _start(deps: HandlerDeps, job: Job, ctx: JobContext, report: _Reporter) -> _Clip:
    """ขั้นแรกของทุกงาน: ข้อมูลคลิป (peek: งานในคิวไม่นับว่าเปิดคลิป) ชื่องาน และโฟลเดอร์ผลลัพธ์ที่เขียนได้"""
    report.stage("probing")
    info = deps.videos.get(job.video_id, peek=True)
    title = str(info.get("title") or "")
    if title:
        ctx.set_title(title)
    root = Path(ctx.output_root).resolve()
    files.ensure_output_root(root)
    ctx.check_cancelled()
    return _Clip(job.video_id, info, title, root)


def _human_size(n: int) -> str:
    """ขนาดแบบทศนิยม (1 GB = 10^9 ไบต์) ปัดขึ้น ข้อความจึงไม่บอกน้อยกว่าที่ต้องใช้จริง"""
    if n >= 1_000_000_000:
        return f"{math.ceil(n / 100_000_000) / 10:.1f} GB"
    return f"{max(1, math.ceil(n / 1_000_000))} MB"


def _disk_checked(choice: DownloadChoice, paths: Iterable[Path], disk_free: Callable[[Path], int]) -> DownloadChoice:
    """ไม่เริ่มโหลดถ้าที่ว่างน้อยกว่า 2 เท่าของขนาดคาดการณ์ (ไม่รู้ขนาด หรืออ่านที่ว่างไม่ได้ = ไม่ตรวจ)

    ตรวจทั้งโฟลเดอร์ผลลัพธ์และโฟลเดอร์ทำงาน (อาจอยู่คนละไดรฟ์ ไฟล์โหลดลงโฟลเดอร์ทำงานก่อน)
    ตั้งใจใช้ 2 เท่ากับทั้งสองที่ (รวมโฟลเดอร์ผลลัพธ์ที่อยู่คนละไดรฟ์ซึ่งต้องการจริงแค่ 1 เท่า):
    เผื่อไว้ก่อนดีกว่าให้งานล้มกลางทางหลังโหลดไปนานแล้ว (review T10 minor 1)
    """
    if not choice.expected_bytes:
        return choice
    need = DISK_FACTOR * choice.expected_bytes
    for path in paths:
        try:
            free = disk_free(path)
        except OSError:
            continue
        if free < need:
            raise YtError(
                "E_DISK_FULL",
                f"free {free} bytes < needed {need} bytes",
                params={"size": _human_size(need)},
            )
    return choice


def _hooks(deps: HandlerDeps, ctx: JobContext, report: _Reporter) -> DownloadHooks:
    return DownloadHooks(
        on_stage=report.stage,
        on_progress=report.progress,
        is_cancelled=ctx.cancelled,
        ffmpeg_location=deps.media.ffmpeg_path(),
    )


def _cover(deps: HandlerDeps, clip: _Clip, ctx: JobContext) -> Path | None:
    """ภาพปกเป็น JPEG ใน workdir (ยูทูปส่ง webp ได้) โหลดหรืออ่านไม่ได้ = ไม่มีปก งานยังไปต่อ"""
    url = str(clip.info.get("thumbnailUrl") or "")
    if not url or ctx.cancelled():
        return None
    target = Path(ctx.workdir) / "cover.jpg"
    try:
        data = deps.downloader.fetch(url)
        with Image.open(io.BytesIO(data)) as img:
            img.convert("RGB").save(target, "JPEG", quality=COVER_JPEG_QUALITY)
    except Exception as exc:  # ปกเป็นของแถม พังแบบไหนก็ไม่ทำให้งานล้ม
        log.info("งาน %s ไม่ใส่ภาพปก (%s)", ctx.job_id, type(exc).__name__)
        target.unlink(missing_ok=True)
        return None
    return target


def _sub_options(raw: Any, key: str) -> SubOptions:
    """ค่าซับของงาน (subOptions / options) API ตรวจมาแล้ว ผิดที่นี่ = ข้อมูลงานเสีย งานล้มด้วย E_UNKNOWN

    core ไม่มีรหัส E_BAD_REQUEST (เป็นรหัสของชั้น API) จึงใช้ E_UNKNOWN ทั้งงานซับและการฝังซับ
    """
    try:
        return options_from_dict(raw if isinstance(raw, Mapping) else {})
    except ValueError as exc:
        raise YtError("E_UNKNOWN", f"{key}: {exc}") from exc


def _export_subtitle(
    deps: HandlerDeps, ctx: JobContext, video_id: str, track_id: str, fmt: str, opts: SubOptions
) -> SubtitleExport:
    """SubtitleService.export ถ้าเซสชันผู้ชมยังไม่พร้อม (E_SESSION_WARMING) รอตามที่บอกแล้วลองอีกครั้งเดียว"""
    try:
        return deps.subtitles.export(video_id, track_id, fmt, opts)
    except YtError as exc:
        if exc.code != "E_SESSION_WARMING":
            raise
        ctx.wait(exc.retry_after or WARMING_WAIT_S)
    return deps.subtitles.export(video_id, track_id, fmt, opts)


def _embedded_subtitle(
    deps: HandlerDeps, ctx: JobContext, clip: _Clip, params: Mapping[str, Any]
) -> tuple[SubtitleInput | None, tuple[str, ...]]:
    """ซับ .srt สำหรับฝังใน mp4 ทำไม่ได้ = ข้ามพร้อมโน้ต EMBED_SUBS_SKIPPED

    E_NETWORK / E_BOT_CHECK โยนต่อ (คิวลองใหม่หรือพักคิว ไม่ใช่ปัญหาของซับ)
    subOptions เสีย = งานล้มด้วย E_UNKNOWN เหมือนงานซับ (_sub_options)
    """
    track_id = params.get("embedSubs")
    if not track_id:
        return None, ()
    opts = _sub_options(params.get("subOptions"), "subOptions")  # ค่าเสีย = งานล้ม (ไม่ใช่ข้ามซับ)
    try:
        result = _export_subtitle(deps, ctx, clip.video_id, str(track_id), "srt", opts)
    except YtError as exc:
        if exc.code in _EMBED_RETRY_CODES:
            raise
        log.info("งาน %s ฝังซับไม่ได้ (%s)", ctx.job_id, exc.code)
        return None, ("EMBED_SUBS_SKIPPED",)
    path = Path(ctx.workdir) / "subs.srt"
    path.write_bytes(result.data)
    return SubtitleInput(path=path, language=iso639_2(result.lang)), ()


def _finish(
    deps: HandlerDeps,
    ctx: JobContext,
    clip: _Clip,
    src: Path,
    *,
    suffix: str,
    ext: str,
    kind: str,
    notes: Iterable[str] = (),
) -> JobResult:
    """ย้ายไฟล์ที่เสร็จแล้วเข้าโฟลเดอร์ของคลิป เขียนแหล่งที่มา.txt แล้วคืนผลของงาน"""
    ctx.check_cancelled()
    planned = files.plan_output(clip.root, clip.title, clip.video_id, suffix, ext)
    final = files.move_into_place(src, planned)
    rel = final.relative_to(clip.root).as_posix()
    _write_note(deps, ctx, clip, final.parent)
    log.info("งาน %s บันทึกไฟล์ %s", ctx.job_id, rel)
    output = OutputFile(root=str(clip.root), rel=rel, size_bytes=final.stat().st_size, kind=kind)
    return JobResult(outputs=(output,), notes=_unique(notes), title=clip.title or None)


def _write_note(deps: HandlerDeps, ctx: JobContext, clip: _Clip, folder: Path) -> None:
    """แหล่งที่มา.txt เขียนไม่ได้ (เช่น เปิดค้างใน Word) = บันทึก warning แต่งานไม่ล้ม
    เพราะไฟล์สื่ออยู่ในที่แล้ว ทำงานซ้ำก็ได้ไฟล์ " (2)" เพิ่มโดยไม่จำเป็น"""
    source = files.SourceInfo(
        title=clip.title,
        channel=str(clip.info.get("channel") or ""),
        video_id=clip.video_id,
        published=_published(clip.info),
        license=clip.info.get("license") or None,
    )
    try:
        files.write_source_note(folder, source, deps.now())
    except (YtError, OSError) as exc:
        code = exc.code if isinstance(exc, YtError) else type(exc).__name__
        log.warning("งาน %s เขียน %s ไม่ได้ (%s) ไฟล์งานบันทึกแล้ว", ctx.job_id, files.SOURCE_NOTE_NAME, code)


def _unique(notes: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(notes))


# ---------- ตัวทำงานแต่ละชนิด ----------


def _video(deps: HandlerDeps, job: Job, ctx: JobContext) -> JobResult:
    report = _Reporter(ctx)
    clip = _start(deps, job, ctx, report)
    params = job.params
    workdir = Path(ctx.workdir)
    subtitle, sub_notes = _embedded_subtitle(deps, ctx, clip, params)
    ctx.check_cancelled()

    def choose(raw: dict) -> DownloadChoice:
        return _disk_checked(video_choice(raw, params), (clip.root, workdir), deps.disk_free)

    result = deps.downloader.download(clip.video_id, choose, workdir, _hooks(deps, ctx, report))
    ctx.check_cancelled()
    cover = _cover(deps, clip, ctx)
    ctx.check_cancelled()
    report.stage("writing")
    out = workdir / "out.mp4"
    deps.media.finalize_mp4(
        result.path,
        out,
        clip.meta,
        cover=cover,
        subtitle=subtitle,
        audio_language=result.choice.audio_language,
        cancel=ctx.cancelled,
        on_progress=report.fraction,
        no_audio=bool(params.get("noAudio")),
    )
    suffix = NO_AUDIO_SUFFIX if params.get("noAudio") else ""
    notes = (*result.choice.notes, *sub_notes)
    return _finish(deps, ctx, clip, out, suffix=suffix, ext="mp4", kind="video", notes=notes)


def _audio(deps: HandlerDeps, job: Job, ctx: JobContext) -> JobResult:
    report = _Reporter(ctx)
    clip = _start(deps, job, ctx, report)
    params = job.params
    fmt = str(params.get("format") or "m4a")
    if fmt not in ("m4a", "mp3", "wav"):
        raise YtError("E_UNKNOWN", f"audio format {fmt!r}")
    workdir = Path(ctx.workdir)

    def choose(raw: dict) -> DownloadChoice:
        return _disk_checked(audio_choice(raw, params), (clip.root, workdir), deps.disk_free)

    result = deps.downloader.download(clip.video_id, choose, workdir, _hooks(deps, ctx, report))
    ctx.check_cancelled()
    language = result.choice.audio_language
    out = workdir / f"out.{fmt}"
    common: dict[str, Any] = {"audio_language": language, "cancel": ctx.cancelled, "on_progress": report.fraction}
    if fmt == "wav":
        report.stage("converting")
        deps.media.to_wav(result.path, out, clip.meta, **common)
    else:
        cover = _cover(deps, clip, ctx)
        ctx.check_cancelled()
        if fmt == "mp3":
            report.stage("converting")
            kbps = int(params.get("mp3Kbps") or DEFAULT_MP3_KBPS)
            deps.media.to_mp3(result.path, out, clip.meta, kbps=kbps, cover=cover, **common)
        else:
            report.stage("writing")
            deps.media.finalize_m4a(result.path, out, clip.meta, cover=cover, **common)
    report.stage("writing")
    return _finish(deps, ctx, clip, out, suffix="", ext=fmt, kind="audio", notes=result.choice.notes)


def _subtitle(deps: HandlerDeps, job: Job, ctx: JobContext) -> JobResult:
    report = _Reporter(ctx)
    clip = _start(deps, job, ctx, report)
    params = job.params
    fmt = str(params.get("format") or "srt")
    track_id = params.get("trackId") or deps.subtitles.tracks(clip.video_id).get("defaultTrackId")
    if not track_id:
        # คลิปไม่มีซับ: งานจบแบบไม่มีไฟล์ (ไม่ใช่ error สีแดง PRD 7) ไม่สร้างโฟลเดอร์
        return JobResult(notes=("NO_SUBTITLES",), title=clip.title or None)
    opts = _sub_options(params.get("options"), "options")
    try:
        result = _export_subtitle(deps, ctx, clip.video_id, str(track_id), fmt, opts)
    except YtError as exc:
        if exc.code != "E_NO_SUBTITLES":
            raise
        # แทร็กที่เลือกหายไปจากคลิปแล้ว: เหมือนคลิปไม่มีซับ
        return JobResult(notes=("NO_SUBTITLES",), title=clip.title or None)
    ctx.check_cancelled()
    report.stage("writing")
    out = Path(ctx.workdir) / f"out.{fmt}"
    out.write_bytes(result.data)
    lang = files.safe_component(result.lang, "und")
    return _finish(deps, ctx, clip, out, suffix=f".{lang}", ext=fmt, kind="subtitle")


def _frames(deps: HandlerDeps, clip: _Clip, ctx: JobContext, report: _Reporter) -> list[tuple[int, Path]]:
    """ไฟล์ภาพเฟรมโหมดเร็ว (storyboard ใน cache) เรียงตามเวลา"""
    report.stage("downloading_video")
    index = get_storyboard(clip.video_id, deps.videos, deps.cache_root, deps.downloader.fetch)
    folder = Path(deps.cache_root) / clip.video_id / STORYBOARD_FOLDER
    ctx.check_cancelled()
    return [(frame["tMs"], folder / frame["file"]) for frame in index["frames"]]


def _contact_sheet(deps: HandlerDeps, job: Job, ctx: JobContext) -> JobResult:
    report = _Reporter(ctx)
    clip = _start(deps, job, ctx, report)
    frames = _frames(deps, clip, ctx, report)
    report.stage("converting")
    columns = int(job.params.get("columns") or 5)
    data = contact_sheet(frames, clip.title, int(clip.info.get("durationS") or 0), columns)
    ctx.check_cancelled()
    report.stage("writing")
    out = Path(ctx.workdir) / "out.jpg"
    out.write_bytes(data)
    return _finish(deps, ctx, clip, out, suffix=CONTACT_SHEET_SUFFIX, ext="jpg", kind="image")


def _frames_zip(deps: HandlerDeps, job: Job, ctx: JobContext) -> JobResult:
    report = _Reporter(ctx)
    clip = _start(deps, job, ctx, report)
    frames = _frames(deps, clip, ctx, report)
    report.stage("converting")
    data = frames_zip(frames)
    ctx.check_cancelled()
    report.stage("writing")
    out = Path(ctx.workdir) / "out.zip"
    out.write_bytes(data)
    return _finish(deps, ctx, clip, out, suffix=FRAMES_ZIP_SUFFIX, ext="zip", kind="archive")


def build_handlers(deps: HandlerDeps) -> dict[str, Handler]:
    """ตัวทำงานของทุกชนิดงานใน M4 (frames_sharp เป็นงาน M5 ยังไม่มี)"""

    def bind(fn: Callable[[HandlerDeps, Job, JobContext], JobResult]) -> Handler:
        def handler(job: Job, ctx: JobContext) -> JobResult:
            return fn(deps, job, ctx)

        handler.__name__ = fn.__name__.lstrip("_")
        return handler

    return {
        "video": bind(_video),
        "audio": bind(_audio),
        "subtitle": bind(_subtitle),
        "contact_sheet": bind(_contact_sheet),
        "frames_zip": bind(_frames_zip),
    }
