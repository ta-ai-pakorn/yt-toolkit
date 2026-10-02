"""ตัวทำงานของแต่ละชนิดงานในคิว (M4): video, audio, subtitle, note, contact_sheet, frames_zip

ตัวทำงานแค่เรียงขั้นตอน ไม่ตัดสินใจเรื่องคิว (ลองใหม่ พักคิว ยกเลิก เป็นของ core/queue.py):
ดึงข้อมูลคลิป (cache) -> โหลด (extractor) -> จัดไฟล์สื่อ (ffmpeg) -> ย้ายเข้าโฟลเดอร์ผลลัพธ์ -> แหล่งที่มา.txt

- ไฟล์ระหว่างทำทุกไฟล์อยู่ใน ctx.workdir (ตัวรันคิวลบทิ้งหลังงานจบ) ชื่อจริงในโฟลเดอร์ผลลัพธ์
  จองด้วย files.move_into_place เท่านั้น จึงไม่มีไฟล์ครึ่ง ๆ กลาง ๆ ค้างที่ชื่อจริง
- log บอกแค่รหัสงานและ path สัมพัทธ์กับโฟลเดอร์ผลลัพธ์ (path เต็มมีชื่อผู้ใช้ Windows)
- params.folder (งานจาก W3) = โฟลเดอร์กลุ่มคั่นระหว่างโฟลเดอร์ผลลัพธ์กับโฟลเดอร์ของคลิป (files.plan_output)
- M5 รอบ A: โหลดทั้งคลิปแล้วตัดช่วงเวลา/โฆษณาด้วย ffmpeg (core/media.cut) ก่อนขั้นจัดไฟล์เดิม
core/ ไม่ import api/ หรือ platform/
"""

from __future__ import annotations

import io
import logging
import math
import shutil
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image

from . import files
from .advanced import ADS_SUFFIX, Interval, keep_intervals, kept_ms, range_suffix
from .download import (
    DownloadChoice,
    Downloader,
    DownloadHooks,
    DownloadResult,
    SponsorBlockError,
    SponsorSource,
    audio_choice,
    video_choice,
)
from .frames import contact_sheet, frames_zip
from .jobs import MIN_RANGE_MS, Handler, Job, JobContext, JobResult, OutputFile
from .media import CutTarget, MediaMeta, MediaTools, SubtitleInput, iso639_2
from .srt_builder import SubOptions, options_from_dict
from .storyboard import FOLDER as STORYBOARD_FOLDER
from .storyboard import get_storyboard
from .yterrors import YtError

if TYPE_CHECKING:
    from .subtitles import NoteExport, SubtitleExport, SubtitleService
    from .videos import VideoService

log = logging.getLogger("yttoolkit")

DISK_FACTOR = 2  # ต้องมีที่ว่างอย่างน้อย 2 เท่าของขนาดคาดการณ์ (ไฟล์โหลด + ไฟล์ที่จัดเสร็จ)
CUT_DISK_FACTOR = 3  # งานที่ตัด: ไฟล์ที่โหลด + ไฟล์ที่ตัด + ไฟล์ที่จัดเสร็จ อยู่พร้อมกันได้
WARMING_WAIT_S = 5  # E_SESSION_WARMING ที่ไม่บอกเวลารอ
DEFAULT_MP3_KBPS = 192
NO_AUDIO_SUFFIX = " (ไม่มีเสียง)"
CONTACT_SHEET_SUFFIX = " - contact sheet"
FRAMES_ZIP_SUFFIX = " - frames"
NOTE_SUFFIX = ".note"  # โน้ต = "<ชื่อ>.note.md" (ชื่อเดียวกับที่ GET /videos/{id}/note ตั้ง)
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
    # ตัวดึงคอมเมนต์ปักหมุดของงานโน้ต (PinnedCommentService.get ตัวเดียวกับ API) None = โน้ตไม่มีหัวข้อนี้
    pinned: Callable[[str], dict | None] | None = None
    # เบรกฉุกเฉินของคิว (QueueRunner.brake) สำหรับ E_BOT_CHECK ที่ตัวทำงานกลืนไว้เองไม่โยนต่อ
    # (คอมเมนต์ปักหมุดของงานโน้ต) open_services ต่อให้หลังสร้างคิว None = ไม่เบรก
    on_bot_check: Callable[[], None] | None = None
    # ที่มาของช่วงโฆษณา (C4 ตัว extractor) lifecycle ต่อให้ None = ติดต่อ SponsorBlock ไม่ได้ (ได้คลิปเต็มพร้อมโน้ต)
    sponsors: SponsorSource | None = None


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
    group: str | None = None  # params.folder ดิบ (files.plan_output ทำความสะอาดเอง) None = ไม่มีโฟลเดอร์กลุ่ม

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
    return _Clip(job.video_id, info, title, root, job_group(job.params))


def job_group(params: Mapping[str, Any]) -> str | None:
    """โฟลเดอร์กลุ่มของงาน (params.folder ดิบ) ไม่มี = None (lifecycle ใช้หาไฟล์ค้างด้วยกฎเดียวกัน)

    API strip และตัดค่าว่างมาแล้ว ที่นี่กันข้อมูลงานแปลก ๆ อีกชั้น
    """
    folder = params.get("folder") if isinstance(params, Mapping) else None
    if not isinstance(folder, str):
        return None
    return folder.strip() or None


def _human_size(n: int) -> str:
    """ขนาดแบบทศนิยม (1 GB = 10^9 ไบต์) ปัดขึ้น ข้อความจึงไม่บอกน้อยกว่าที่ต้องใช้จริง"""
    if n >= 1_000_000_000:
        return f"{math.ceil(n / 100_000_000) / 10:.1f} GB"
    return f"{max(1, math.ceil(n / 1_000_000))} MB"


def _disk_checked(
    choice: DownloadChoice,
    paths: Iterable[Path],
    disk_free: Callable[[Path], int],
    *,
    factor: int = DISK_FACTOR,
) -> DownloadChoice:
    """ไม่เริ่มโหลดถ้าที่ว่างน้อยกว่า factor เท่าของขนาดคาดการณ์ (ไม่รู้ขนาด หรืออ่านที่ว่างไม่ได้ = ไม่ตรวจ)
    งานที่ตัดช่วงเวลา/โฆษณาใช้ CUT_DISK_FACTOR (มีไฟล์ที่ตัดอีกไฟล์)

    ตรวจทั้งโฟลเดอร์ผลลัพธ์และโฟลเดอร์ทำงาน (อาจอยู่คนละไดรฟ์ ไฟล์โหลดลงโฟลเดอร์ทำงานก่อน)
    ตั้งใจใช้ 2 เท่ากับทั้งสองที่ (รวมโฟลเดอร์ผลลัพธ์ที่อยู่คนละไดรฟ์ซึ่งต้องการจริงแค่ 1 เท่า):
    เผื่อไว้ก่อนดีกว่าให้งานล้มกลางทางหลังโหลดไปนานแล้ว (review T10 minor 1)
    """
    if not choice.expected_bytes:
        return choice
    need = factor * choice.expected_bytes
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


def _requested_range(params: Mapping[str, Any]) -> Interval | None:
    """ช่วงเวลาของงาน (API ตรวจมาแล้ว) ไม่มี = None · ข้อมูลงานเสีย = E_UNKNOWN"""
    raw = params.get("range")
    if raw is None:
        return None
    start = raw.get("startMs") if isinstance(raw, Mapping) else None
    end = raw.get("endMs") if isinstance(raw, Mapping) else None
    if type(start) is not int or type(end) is not int or start < 0 or end - start < MIN_RANGE_MS:
        raise YtError("E_UNKNOWN", f"range: {raw!r}")
    return start, end


def _sponsor_segments(
    deps: HandlerDeps, ctx: JobContext, clip: _Clip, params: Mapping[str, Any]
) -> tuple[list[Interval] | None, tuple[str, ...]]:
    """ช่วงโฆษณาตามหมวดที่ขอ: None = ไม่ได้ขอตัดโฆษณา หรือติดต่อ SponsorBlock ไม่ได้ (คู่กับโน้ต)

    error ของ SponsorBlock ไม่ทำให้งานล้ม ไม่ลองใหม่ ไม่พักคิว (ไม่ใช่ยูทูป) log บอกแค่ชนิด error
    """
    categories = params.get("sponsorblock")
    if not categories:
        return None, ()
    source = deps.sponsors
    if source is None:
        log.info("งาน %s ไม่มีตัวดึงข้อมูล SponsorBlock ได้คลิปเต็ม", ctx.job_id)
        return None, ("SPONSORBLOCK_UNREACHABLE",)
    try:
        found = source.sponsor_segments(clip.video_id, [str(c) for c in categories], clip.meta.duration_s)
    except SponsorBlockError as exc:
        log.info("งาน %s ติดต่อ SponsorBlock ไม่ได้ (%s) ได้คลิปเต็ม", ctx.job_id, exc)
        return None, ("SPONSORBLOCK_UNREACHABLE",)
    return [(start, end) for start, end, _ in found], ()


def _duration_ms(raw: Mapping[str, Any], clip: _Clip) -> int | None:
    """ความยาวจริงของไฟล์ที่โหลด (duration ของ yt-dlp รอบนี้ ไม่มีใช้ของ probe) ไม่รู้ = None"""
    for value in (raw.get("duration"), clip.info.get("durationS")):
        if isinstance(value, int | float) and not isinstance(value, bool) and value > 0:
            return round(value * 1000)
    return None


def _clipped_range(span: Interval | None, total_ms: int | None) -> Interval | None:
    """ช่วงที่ขอ ตัดปลายให้ไม่เกินความยาวคลิป (API ตรวจไม่ได้ถ้าคลิปยังไม่เคยดึงข้อมูลก่อนเข้าคิว)

    ไม่รู้ความยาว = ตามที่ขอ · เหลือไม่ถึง 1 วินาที = E_UNKNOWN
    งานวิดีโอ เสียง ซับ และการฝังซับใช้กฎเดียวกัน ช่วงของสื่อกับของซับจึงตรงกันเสมอ
    """
    if span is None:
        return None
    start, end = span
    if total_ms is not None:
        end = min(end, total_ms)
    if end - start < MIN_RANGE_MS:
        raise YtError("E_UNKNOWN", f"range {span} is outside the clip ({total_ms} ms)")
    return start, end


def _job_range(params: Mapping[str, Any], clip: _Clip) -> Interval | None:
    """ช่วงเวลาของงานที่ตัดปลายตามความยาวจาก probe แล้ว (ตรวจก่อนโหลด ช่วงนอกคลิปไม่ต้องรอโหลดทั้งคลิปก่อนล้ม)"""
    return _clipped_range(_requested_range(params), _duration_ms({}, clip))


def _has_audio_stream(raw: Mapping[str, Any]) -> bool:
    """คลิปมีเสียงไหม ดูจากรายการ format ของการดึงข้อมูลรอบที่โหลด (ชุดเดียวกับที่ choose ใช้เลือก format)

    มี format ที่ acodec ไม่ใช่ "none" = มีเสียง (acodec ไม่รู้ เช่น HLS ถือว่าอาจมีเสียง)
    ไม่มีรายการ format = ไม่รู้ ถือว่ามีเสียงแบบ M4
    คลิปไม่มีเสียงเลยต้องตัดแบบไม่มีเสียง ไม่งั้นการตัดแบบแม่นยำต้องการแทร็กเสียงแล้ว ffmpeg ล้ม
    """
    formats = [f for f in (raw.get("formats") or []) if isinstance(f, Mapping)]
    if not formats:
        return True
    return any(f.get("acodec") != "none" for f in formats)


@dataclass(frozen=True)
class _Cut:
    path: Path  # ไฟล์ที่จะเข้าขั้นจัดไฟล์ (ไม่ได้ตัด = ไฟล์ที่โหลดมาเอง)
    suffix: str  # ส่วนต่อท้ายชื่อไฟล์ ช่วงเวลา + (ตัดโฆษณา)
    duration_s: float | None  # ความยาวหลังตัด (ความคืบหน้าของขั้นถัดไป)
    notes: tuple[str, ...]


def _cut(
    deps: HandlerDeps,
    ctx: JobContext,
    clip: _Clip,
    result: DownloadResult,
    report: _Reporter,
    *,
    span: Interval | None,
    ads: list[Interval] | None,
    target: CutTarget,
    has_audio: bool,
) -> _Cut:
    """ตัดช่วงเวลาและ/หรือโฆษณาแบบแม่นยำ (D1) ไม่มีอะไรต้องตัด = ใช้ไฟล์ที่โหลดมา ไม่แปลงซ้ำ ไม่ต่อชื่อ

    ปลายช่วงเกินความยาวจริง (API ตรวจไม่ได้เพราะยังไม่มีข้อมูลคลิป) = ตัดปลายให้เท่าความยาวจริง เหลือไม่ถึง 1 วิ = E_UNKNOWN
    ขอตัดโฆษณาแต่ไม่มีอะไรถูกตัดเลย = โน้ต SPONSORBLOCK_EMPTY (ชื่อไฟล์ไม่มี (ตัดโฆษณา))
    """
    full = _Cut(result.path, "", clip.meta.duration_s, ())
    if span is None and ads is None:
        return full
    total = _duration_ms(result.info, clip)
    span = _clipped_range(span, total)
    whole = span if span is not None else ((0, total) if total is not None else None)
    if whole is None:
        raise YtError("E_UNKNOWN", "clip duration unknown, cannot cut")
    keep = keep_intervals(whole, ads or ())
    ads_cut = bool(keep) and keep != [whole]
    notes = ("SPONSORBLOCK_EMPTY",) if ads is not None and not ads_cut else ()
    if span is None and not ads_cut:
        return replace(full, notes=notes)
    if not ads_cut:
        keep = [whole]
    report.stage("cutting_ads" if ads_cut else "cutting")
    out = Path(ctx.workdir) / f"cut.{target}"
    deps.media.cut(result.path, out, keep, mode="exact", target=target, has_audio=has_audio,
                   cancel=ctx.cancelled, on_progress=report.fraction)  # fmt: skip
    ctx.check_cancelled()
    result.path.unlink(missing_ok=True)  # ไฟล์ที่โหลดมาไม่ใช้แล้ว คืนที่ว่างก่อนขั้นจัดไฟล์
    suffix = (range_suffix(*span) if span is not None else "") + (ADS_SUFFIX if ads_cut else "")
    return _Cut(out, suffix, kept_ms(keep) / 1000, notes)


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
    deps: HandlerDeps,
    ctx: JobContext,
    video_id: str,
    track_id: str,
    fmt: str,
    opts: SubOptions,
    span: Interval | None = None,
) -> SubtitleExport:
    """SubtitleService.export ถ้าเซสชันผู้ชมยังไม่พร้อม (E_SESSION_WARMING) รอตามที่บอกแล้วลองอีกครั้งเดียว"""
    try:
        return deps.subtitles.export(video_id, track_id, fmt, opts, span)
    except YtError as exc:
        if exc.code != "E_SESSION_WARMING":
            raise
        ctx.wait(exc.retry_after or WARMING_WAIT_S)
    return deps.subtitles.export(video_id, track_id, fmt, opts, span)


def _embedded_subtitle(
    deps: HandlerDeps, ctx: JobContext, clip: _Clip, params: Mapping[str, Any], span: Interval | None
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
        result = _export_subtitle(deps, ctx, clip.video_id, str(track_id), "srt", opts, span)
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
    planned = files.plan_output(clip.root, clip.title, clip.video_id, suffix, ext, clip.group)
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
    span = _job_range(params, clip)
    subtitle, sub_notes = _embedded_subtitle(deps, ctx, clip, params, span)
    ads, ad_notes = _sponsor_segments(deps, ctx, clip, params)
    ctx.check_cancelled()
    factor = CUT_DISK_FACTOR if span is not None or ads is not None else DISK_FACTOR

    def choose(raw: dict) -> DownloadChoice:
        return _disk_checked(video_choice(raw, params), (clip.root, workdir), deps.disk_free, factor=factor)

    result = deps.downloader.download(clip.video_id, choose, workdir, _hooks(deps, ctx, report))
    ctx.check_cancelled()
    no_audio = bool(params.get("noAudio"))
    has_audio = not no_audio and _has_audio_stream(result.info)
    cut = _cut(deps, ctx, clip, result, report, span=span, ads=ads, target="mp4", has_audio=has_audio)
    cover = _cover(deps, clip, ctx)
    ctx.check_cancelled()
    report.stage("writing")
    out = workdir / "out.mp4"
    deps.media.finalize_mp4(
        cut.path,
        out,
        replace(clip.meta, duration_s=cut.duration_s),
        cover=cover,
        subtitle=subtitle,
        audio_language=result.choice.audio_language,
        cancel=ctx.cancelled,
        on_progress=report.fraction,
        no_audio=no_audio,
    )
    suffix = (NO_AUDIO_SUFFIX if no_audio else "") + cut.suffix
    notes = (*result.choice.notes, *sub_notes, *ad_notes, *cut.notes)
    return _finish(deps, ctx, clip, out, suffix=suffix, ext="mp4", kind="video", notes=notes)


def _audio(deps: HandlerDeps, job: Job, ctx: JobContext) -> JobResult:
    report = _Reporter(ctx)
    clip = _start(deps, job, ctx, report)
    params = job.params
    fmt = str(params.get("format") or "m4a")
    if fmt not in ("m4a", "mp3", "wav"):
        raise YtError("E_UNKNOWN", f"audio format {fmt!r}")
    workdir = Path(ctx.workdir)
    span = _job_range(params, clip)
    ads, ad_notes = _sponsor_segments(deps, ctx, clip, params)
    ctx.check_cancelled()
    factor = CUT_DISK_FACTOR if span is not None or ads is not None else DISK_FACTOR

    def choose(raw: dict) -> DownloadChoice:
        return _disk_checked(audio_choice(raw, params), (clip.root, workdir), deps.disk_free, factor=factor)

    result = deps.downloader.download(clip.video_id, choose, workdir, _hooks(deps, ctx, report))
    ctx.check_cancelled()
    # m4a ตัดเป็น m4a · mp3/wav ตัดเป็น wav (PCM ตัดได้ตรงตัวอย่างเสียง) แล้วแปลงต่อครั้งเดียว
    target: CutTarget = "m4a" if fmt == "m4a" else "wav"
    cut = _cut(deps, ctx, clip, result, report, span=span, ads=ads, target=target, has_audio=True)
    language = result.choice.audio_language
    meta = replace(clip.meta, duration_s=cut.duration_s)
    out = workdir / f"out.{fmt}"
    common: dict[str, Any] = {"audio_language": language, "cancel": ctx.cancelled, "on_progress": report.fraction}
    if fmt == "wav":
        report.stage("converting")
        deps.media.to_wav(cut.path, out, meta, **common)
    else:
        cover = _cover(deps, clip, ctx)
        ctx.check_cancelled()
        if fmt == "mp3":
            report.stage("converting")
            kbps = int(params.get("mp3Kbps") or DEFAULT_MP3_KBPS)
            deps.media.to_mp3(cut.path, out, meta, kbps=kbps, cover=cover, **common)
        else:
            report.stage("writing")
            deps.media.finalize_m4a(cut.path, out, meta, cover=cover, **common)
    report.stage("writing")
    notes = (*result.choice.notes, *ad_notes, *cut.notes)
    return _finish(deps, ctx, clip, out, suffix=cut.suffix, ext=fmt, kind="audio", notes=notes)


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
    span = _job_range(params, clip)
    try:
        result = _export_subtitle(deps, ctx, clip.video_id, str(track_id), fmt, opts, span)
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
    suffix = (range_suffix(*span) if span is not None else "") + f".{lang}"
    return _finish(deps, ctx, clip, out, suffix=suffix, ext=fmt, kind="subtitle")


def _pinned_getter(deps: HandlerDeps, ctx: JobContext) -> Callable[[str], dict | None] | None:
    """ตัวดึงคอมเมนต์ปักหมุดที่ไม่ทำให้งานโน้ตล้ม: YtError ให้ SubtitleService.note จัดการ (ไม่ใส่หัวข้อ)
    พังแบบอื่น (ไม่คาดคิด) = ไม่มีคอมเมนต์ปักหมุด บันทึกแค่ชื่อชนิด error

    E_BOT_CHECK: โน้ตยังเขียนต่อ แต่ต้องพักคิว (deps.on_bot_check) หนึ่งครั้งต่องาน เหมือนเจอ E_BOT_CHECK
    จากงานอื่น ไม่งั้นงานโน้ตชุดใหญ่จะยิงยูทูปต่อทั้งที่ถูกขอยืนยันว่าไม่ใช่บอทอยู่
    """
    pinned = deps.pinned
    if pinned is None:
        return None
    braked = False

    def get(video_id: str) -> dict | None:
        nonlocal braked
        try:
            return pinned(video_id)
        except YtError as exc:
            if exc.code == "E_BOT_CHECK" and not braked:
                braked = True
                _brake(deps, ctx)
            raise
        except Exception as exc:
            log.warning("งาน %s ดึงคอมเมนต์ปักหมุดไม่ได้ (%s) โน้ตไม่มีหัวข้อนี้", ctx.job_id, type(exc).__name__)
            return None

    return get


def _brake(deps: HandlerDeps, ctx: JobContext) -> None:
    """แจ้งคิวให้เบรกฉุกเฉิน พลาดแค่บันทึก log (งานต้องเสร็จตามปกติ)"""
    if deps.on_bot_check is None:
        return
    log.warning("งาน %s: ยูทูปขอยืนยันว่าไม่ใช่บอทตอนดึงคอมเมนต์ปักหมุด พักคิว", ctx.job_id)
    try:
        deps.on_bot_check()
    except Exception as exc:
        log.warning("งาน %s พักคิวไม่สำเร็จ (%s)", ctx.job_id, type(exc).__name__)


def _build_note(
    deps: HandlerDeps,
    ctx: JobContext,
    video_id: str,
    track_id: str | None,
    pinned: Callable[[str], dict | None] | None,
) -> NoteExport:
    """SubtitleService.note แบบเดียวกับ GET /videos/{id}/note (คอมเมนต์ปักหมุดพลาด = ไม่มีหัวข้อ งานไม่ล้ม)

    เซสชันผู้ชมยังไม่พร้อม (ซับแปล) = รอแล้วลองอีกครั้งเดียว (เหมือนงานซับ)
    แทร็กที่เลือกหายไปจากคลิปแล้ว (E_NO_SUBTITLES) = ใช้แทร็กที่เลือกให้เอง โน้ตยังมีข้อมูลคลิปครบ
    pinned = ตัวดึงจาก _pinned_getter (ตัวเดียวทั้งงาน จึงเบรกคิวไม่เกินหนึ่งครั้งต่องาน)
    """
    try:
        try:
            return deps.subtitles.note(video_id, track_id, pinned=pinned)
        except YtError as exc:
            if exc.code != "E_SESSION_WARMING":
                raise
            ctx.wait(exc.retry_after or WARMING_WAIT_S)
        return deps.subtitles.note(video_id, track_id, pinned=pinned)
    except YtError as exc:
        if exc.code != "E_NO_SUBTITLES" or track_id is None:
            raise
        log.info("งาน %s ไม่มีแทร็กซับที่เลือกแล้ว ใช้แทร็กที่เลือกให้เองแทน", ctx.job_id)
    return _build_note(deps, ctx, video_id, None, pinned)


def _note(deps: HandlerDeps, job: Job, ctx: JobContext) -> JobResult:
    """โน้ต .md ของคลิป (owner preview round 2): front matter + คำอธิบาย + chapter + คอมเมนต์ปักหมุด + ทรานสคริปต์
    ลงโฟลเดอร์ของคลิปเป็น "<ชื่อ>.note.md" พร้อมแหล่งที่มา.txt เหมือนงานอื่น"""
    report = _Reporter(ctx)
    clip = _start(deps, job, ctx, report)
    raw_track = job.params.get("trackId")
    track_id = str(raw_track) if raw_track else None
    result = _build_note(deps, ctx, clip.video_id, track_id, _pinned_getter(deps, ctx))
    ctx.check_cancelled()
    report.stage("writing")
    out = Path(ctx.workdir) / "out.md"
    out.write_bytes(result.data)
    return _finish(deps, ctx, clip, out, suffix=NOTE_SUFFIX, ext="md", kind="note")


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
        "note": bind(_note),
        "contact_sheet": bind(_contact_sheet),
        "frames_zip": bind(_frames_zip),
    }
