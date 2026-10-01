"""เลือก format ของงานโหลด (C8): เสียงภาษาไหน วิดีโอแบบไหน และขนาดไฟล์คาดการณ์สำหรับตรวจพื้นที่ว่าง

เป็นฟังก์ชันล้วน รับ info dict ของ yt-dlp (หรือแบบที่ trim_probe ตัดแล้ว) แล้วคืน DownloadChoice
ตัวโหลดจริง (core/extractor.py) และตัวปลอมใช้ชนิดข้อมูลในไฟล์นี้ร่วมกัน ไม่ import yt_dlp
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

# งานที่ต้องดึงจากยูทูป (คิวเว้นช่วง 2-5 วินาทีระหว่างงานเหล่านี้) และงานที่ต้องมี ffmpeg
YOUTUBE_KINDS = frozenset({"video", "audio", "subtitle", "frames_sharp"})
FFMPEG_KINDS = frozenset({"video", "audio"})

DEFAULT_MAX_HEIGHT = 1080
# wav = PCM 16 บิต: ขนาดคาดการณ์ใช้ 44,100 Hz 2 ช่อง (C8)
WAV_RATE = 44100
WAV_CHANNELS = 2
WAV_BYTES_PER_SAMPLE = 2

@dataclass(frozen=True)
class DownloadChoice:
    format_spec: str  # สตริง format ของ yt-dlp
    merge_mp4: bool  # True = ให้ yt-dlp รวมวิดีโอกับเสียงเป็น mp4 (merge_output_format "mp4")
    audio_language: str | None  # ภาษาของแทร็กเสียงที่เลือก (ใส่ใน metadata) None = ไม่รู้ / ไม่มีเสียง
    notes: tuple[str, ...]  # รหัสใน core.jobs.NOTES
    expected_bytes: int | None  # ใช้ตรวจพื้นที่ว่าง None = ไม่รู้


@dataclass
class DownloadHooks:
    on_stage: Callable[[str], None]
    on_progress: Callable[[float | None, int | None, int | None], None]  # สัดส่วน, ความเร็ว B/s, เหลืออีกกี่วินาที
    is_cancelled: Callable[[], bool]
    ffmpeg_location: Path | None


@dataclass(frozen=True)
class DownloadResult:
    path: Path  # ไฟล์สื่อใน workdir
    info: dict  # info ของ yt-dlp (sanitize แล้ว) จากการดึงข้อมูลรอบนี้
    choice: DownloadChoice


@runtime_checkable
class Downloader(Protocol):
    def download(
        self,
        video_id: str,
        choose: Callable[[dict], DownloadChoice],
        workdir: Path,
        hooks: DownloadHooks,
    ) -> DownloadResult:
        """ดึงข้อมูลคลิปครั้งเดียว ให้ choose เลือก format แล้วโหลดลง workdir/media.<ext>"""
        ...

    def fetch(self, url: str) -> bytes:
        """โหลดไฟล์ (เช่น ภาพปก) ด้วย HTTP GET"""
        ...


# ---------- ตัวช่วย ----------


def _number(value: Any) -> float | None:
    """ตัวเลขจริงที่เป็นบวก อย่างอื่น = ไม่รู้"""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) and value > 0 else None


def _filesize(fmt: Mapping[str, Any]) -> int | None:
    for key in ("filesize", "filesize_approx"):
        if (size := _number(fmt.get(key))) is not None:
            return round(size)
    return None


def _audio_bytes(aud: Mapping[str, Any], duration: Any) -> int | None:
    """ขนาดแทร็กเสียง: filesize, filesize_approx หรือ abr (kbps) x ความยาวคลิป"""
    size = _filesize(aud)
    if size is not None:
        return size
    abr, seconds = _number(aud.get("abr")), _number(duration)
    if abr is None or seconds is None:
        return None
    return round(abr * 1000 / 8 * seconds)


def _formats(info: Mapping[str, Any]) -> list[dict]:
    return [f for f in (info.get("formats") or []) if isinstance(f, dict)]


def _is_video(fmt: dict) -> bool:
    """format ที่มีภาพจริง (วิดีโอล้วนหรือวิดีโอ+เสียง) ไม่ใช่เสียงล้วนหรือ storyboard"""
    from .videos import _is_storyboard  # import ในฟังก์ชัน เหตุผลเดียวกับ pick_audio

    vcodec = fmt.get("vcodec")
    return not _is_storyboard(fmt) and bool(vcodec) and vcodec != "none"


def _resolution(fmt: Mapping[str, Any]) -> float:
    """ความละเอียดของ format = ด้านสั้นของภาพ min(width, height) แบบเดียวกับ "res" ของ yt-dlp

    คลิปแนวตั้ง (Shorts) 1080x1920 จึงเป็น 1080p ไม่ใช่ 1920p · ไม่รู้ width = ใช้ height · ไม่รู้ height = 0
    """
    height = _number(fmt.get("height"))
    if height is None:
        return 0.0
    width = _number(fmt.get("width"))
    return height if width is None else min(width, height)


def _is_portrait(videos: list[dict]) -> bool:
    """คลิปแนวตั้ง: format ภาพใหญ่สุด (พื้นที่ภาพ) กว้างน้อยกว่าสูง · ไม่รู้ขนาดเลย = แนวนอน (ใช้ height เหมือนเดิม)"""
    sizes = [
        (width, height)
        for f in videos
        if (width := _number(f.get("width"))) is not None
        and (height := _number(f.get("height"))) is not None
    ]
    if not sizes:
        return False
    width, height = max(sizes, key=lambda size: size[0] * size[1])
    return width < height


def _video_bytes(pool: list[dict]) -> int | None:
    """ขนาดของ format ที่ดีที่สุดในกลุ่ม (ละเอียดสุดก่อน แล้วไฟล์ใหญ่สุด) None = ไม่มีหรือไม่รู้ขนาด"""
    if not pool:
        return None
    best = max(pool, key=lambda f: (_resolution(f), _filesize(f) or -1))
    return _filesize(best)


def _sum(*sizes: int | None) -> int | None:
    return None if any(s is None for s in sizes) else sum(s for s in sizes if s is not None)


def _max_audio(pool: list[dict]) -> dict:
    return max(pool, key=lambda f: (_number(f.get("abr")) or 0.0, str(f.get("format_id"))))


# ---------- ตัวเลือก ----------


def pick_audio(
    formats: list[dict], want: str, *, codec_prefix: str | None
) -> tuple[dict | None, tuple[str, ...]]:
    """เลือกแทร็กเสียง (format dict ดิบ) ตามภาษาที่ต้องการ

    1. ผู้สมัคร = แทร็กเดียวกับรายการเสียงใน VideoInfo (ไม่มี DRC/storyboard) codec_prefix ตัดเหลือ codec นั้น
       (ไม่เหลือเลย = ใช้ทั้งหมด)
    2. want ว่างหรือ "original" = แทร็กต้นฉบับ (ไม่มีแทร็กไหนถูกตีว่าเป็นต้นฉบับ = ทุกแทร็ก) abr สูงสุด
    3. ภาษาอื่น = แทร็กที่ภาษาตรงกัน (ไม่สนตัวพิมพ์ "en" ตรงกับ "en-US") ไม่มี = ต้นฉบับ + AUDIO_LANG_FALLBACK
    4. ไม่มีแทร็กเสียงเลย = (None, ())
    """
    # import ในฟังก์ชัน: videos import extractor และ extractor (T9) import โมดูลนี้ (กัน import วน)
    from .videos import _audio_formats

    entries = _audio_formats(formats)
    by_id: dict[str, dict] = {}
    for fmt in formats:
        if isinstance(fmt, dict) and fmt.get("format_id") is not None:
            by_id.setdefault(str(fmt["format_id"]), fmt)
    candidates = [(by_id[e["formatId"]], e["isOriginal"]) for e in entries if e["formatId"] in by_id]
    if not candidates:
        return None, ()
    if codec_prefix:
        same_codec = [c for c in candidates if str(c[0].get("acodec") or "").startswith(codec_prefix)]
        candidates = same_codec or candidates

    originals = [fmt for fmt, original in candidates if original]
    original = _max_audio(originals or [fmt for fmt, _ in candidates])
    wanted = (want or "").strip().lower()
    if not wanted or wanted == "original":
        return original, ()
    matches = [
        fmt
        for fmt, _ in candidates
        if (lang := str(fmt.get("language") or "").lower()) == wanted or lang.startswith(wanted + "-")
    ]
    if matches:
        return _max_audio(matches), ()
    return original, ("AUDIO_LANG_FALLBACK",)


def video_choice(info: dict, params: Mapping[str, Any]) -> DownloadChoice:
    """งาน video: format ของวิดีโอ (+ เสียง) ตาม params ของงาน (C3)

    - formatId ของ format ที่มีภาพและยังมีอยู่ = ใช้ตัวนั้น ไม่มีแล้ว/เสียงล้วน/storyboard = เลือกอัตโนมัติ + QUALITY_FALLBACK
    - maxQuality = วิดีโอดีที่สุดทุก codec (bv*) ไม่งั้น = H.264 ไม่เกิน maxHeight (เปิดได้ทุกที่)
      เพดานนับที่ด้านสั้นของภาพ: คลิปแนวนอนกรอง [height<=H] (เหมือนเดิม) คลิปแนวตั้ง (Shorts) กรอง [width<=H]
    - noAudio = วิดีโออย่างเดียว ไม่มี "+" ไม่มีตัวสำรอง (AC-VID-08)
    """
    formats = _formats(info)
    notes: list[str] = []
    height_cap = params.get("maxHeight") or DEFAULT_MAX_HEIGHT
    max_quality = bool(params.get("maxQuality"))
    format_id = params.get("formatId")
    videos = [f for f in formats if _is_video(f)]
    # formatId ต้องเป็น format ที่มีภาพ (ไม่มีแล้ว หรือเป็นเสียงล้วน/storyboard = เลือกอัตโนมัติ + QUALITY_FALLBACK)
    if format_id and not any(str(f.get("format_id")) == str(format_id) for f in videos):
        format_id = None
        notes.append("QUALITY_FALLBACK")

    if format_id:
        video = str(format_id)
        pool = [f for f in videos if str(f.get("format_id")) == video]
        tail = ""
    elif max_quality:
        video = "bv*"
        pool = videos
        tail = "/b"
    else:
        # เพดานนับที่ด้านสั้น: Shorts 1080x1920 ได้ 1080p ไม่ถูกตัดลงเหลือ 480x854 (format แนวตั้งตัวใหญ่สุดที่สูงไม่เกิน 1080)
        short_side = "width" if _is_portrait(videos) else "height"
        video = f"bv*[vcodec^=avc1][{short_side}<={height_cap}]"
        pool = [
            f
            for f in videos
            if str(f.get("vcodec")).startswith("avc1") and 0 < _resolution(f) <= height_cap
        ]
        tail = "/b[ext=mp4]"
    video_bytes = _video_bytes(pool)

    if params.get("noAudio"):
        return DownloadChoice(
            format_spec=video,
            merge_mp4=True,
            audio_language=None,
            notes=tuple(notes),
            expected_bytes=video_bytes,
        )

    aud, audio_notes = pick_audio(
        formats,
        str(params.get("audioLanguage") or "original"),
        codec_prefix=None if max_quality else "mp4a",
    )
    notes.extend(audio_notes)
    if aud is not None:
        audio_id = str(aud["format_id"])
        audio_bytes = _audio_bytes(aud, info.get("duration"))
    else:
        audio_id = "ba" if max_quality else "ba[acodec^=mp4a]"
        audio_bytes = None
    return DownloadChoice(
        format_spec=f"{video}+{audio_id}{tail}",
        merge_mp4=True,
        audio_language=aud.get("language") if aud is not None else None,
        notes=tuple(notes),
        expected_bytes=_sum(video_bytes, audio_bytes),
    )


def audio_choice(info: dict, params: Mapping[str, Any]) -> DownloadChoice:
    """งาน audio: แทร็ก AAC (m4a) ของภาษาที่เลือก mp3/wav แปลงต่อจากแทร็กนี้ด้วย ffmpeg"""
    aud, notes = pick_audio(
        _formats(info), str(params.get("audioLanguage") or "original"), codec_prefix="mp4a"
    )
    if aud is None:
        return DownloadChoice(
            format_spec="ba[acodec^=mp4a]/ba",
            merge_mp4=False,
            audio_language=None,
            notes=notes,
            expected_bytes=None,
        )
    expected = _audio_bytes(aud, info.get("duration"))
    if params.get("format") == "wav" and expected is not None:
        seconds = _number(info.get("duration"))
        pcm = (
            round(seconds * WAV_RATE * WAV_CHANNELS * WAV_BYTES_PER_SAMPLE)
            if seconds is not None
            else None
        )
        expected = _sum(expected, pcm)
    return DownloadChoice(
        format_spec=str(aud["format_id"]),
        merge_mp4=False,
        audio_language=aud.get("language"),
        notes=notes,
        expected_bytes=expected,
    )
