"""เครื่องมือจัดการไฟล์สื่อด้วย ffmpeg (M4): ใส่ซับ/ปก/ข้อมูลลงไฟล์ แปลงเป็น mp3/wav

ทุกคำสั่งเป็น list ของอาร์กิวเมนต์ (ไม่ผ่าน shell) ชื่อคลิปที่มีอักขระแปลก ๆ จึงเป็น
อาร์กิวเมนต์ตัวเดียวเสมอ ตัวสร้างอาร์กิวเมนต์ (`*_args`) เป็นฟังก์ชันล้วนเพื่อเทสตรง ๆ
"""

from __future__ import annotations

import shutil
import subprocess
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, Protocol

from .cancel import JobCancelled
from .yterrors import YtError

_ISO639_2 = {
    "th": "tha", "en": "eng", "ja": "jpn", "ko": "kor", "zh": "chi", "fr": "fre", "de": "ger",
    "es": "spa", "pt": "por", "ru": "rus", "vi": "vie", "id": "ind", "ms": "may", "hi": "hin",
    "ar": "ara", "it": "ita", "lo": "lao", "my": "bur", "km": "khm",
}  # fmt: skip

_STDERR_TAIL_CHARS = 4000
_POLL_SECONDS = 0.1

CutMode = Literal["exact", "fast"]
CutTarget = Literal["mp4", "m4a", "wav"]
# ตัดแบบแม่นยำ (D1) เข้ารหัสภาพใหม่ด้วย H.264 ที่เปิดได้ทุกที่ ความเร็วพอดีกับโน้ตบุ๊กทั่วไป
X264_PRESET = "veryfast"
X264_CRF = 20
CUT_AAC_KBPS = 192
# ภาพคม (M5 รอบ B D4): ด้านยาว 1280 ไม่ขยายภาพเล็ก · -q:v 2 ของ mjpeg (คมพอสำหรับงานสไลด์ ไฟล์ราว 150-300 KB)
SHARP_LONG_SIDE = 1280
SHARP_JPEG_Q = 2
_HLG = "HLG"


def iso639_2(lang: str | None) -> str:
    """รหัสภาษา 2 ตัวของยูทูป (th, en-US) -> รหัส 3 ตัวที่ไฟล์สื่อใช้ ไม่รู้จัก = "und" """
    if not lang:
        return "und"
    base = lang.strip().lower().split("-")[0].split("_")[0]
    if base in _ISO639_2:
        return _ISO639_2[base]
    if len(base) == 3 and base.isalpha():
        return base
    return "und"


@dataclass(frozen=True)
class MediaMeta:
    title: str
    artist: str  # ชื่อช่อง
    comment: str  # https://www.youtube.com/watch?v=<id>
    date: str | None  # YYYY-MM-DD
    duration_s: float | None  # ใช้คิดความคืบหน้าเท่านั้น
    track: str | None = None  # "3/12" ของไฟล์แยกตาม chapter


@dataclass(frozen=True)
class SubtitleInput:
    path: Path  # .srt แบบ UTF-8 ในโฟลเดอร์ทำงาน
    language: str  # ISO 639-2 เช่น "tha"


class MediaTools(Protocol):
    def available(self) -> bool: ...

    def ffmpeg_path(self) -> Path | None: ...

    def finalize_mp4(
        self,
        src: Path,
        dst: Path,
        meta: MediaMeta,
        *,
        cover: Path | None,
        subtitle: SubtitleInput | None,
        audio_language: str | None,
        cancel: Callable[[], bool],
        on_progress: Callable[[float | None], None],
        no_audio: bool = False,
    ) -> None: ...

    def finalize_m4a(
        self,
        src: Path,
        dst: Path,
        meta: MediaMeta,
        *,
        cover: Path | None,
        audio_language: str | None,
        cancel: Callable[[], bool],
        on_progress: Callable[[float | None], None],
    ) -> None: ...

    def to_mp3(
        self,
        src: Path,
        dst: Path,
        meta: MediaMeta,
        *,
        kbps: int,
        cover: Path | None,
        audio_language: str | None,
        cancel: Callable[[], bool],
        on_progress: Callable[[float | None], None],
    ) -> None: ...

    def to_wav(
        self,
        src: Path,
        dst: Path,
        meta: MediaMeta,
        *,
        audio_language: str | None,
        cancel: Callable[[], bool],
        on_progress: Callable[[float | None], None],
    ) -> None: ...

    def cut(
        self,
        src: Path,
        dst: Path,
        intervals: Sequence[tuple[int, int]],
        *,
        mode: CutMode,
        target: CutTarget,
        has_audio: bool,
        cancel: Callable[[], bool],
        on_progress: Callable[[float | None], None],
    ) -> None: ...

    def extract_frame(
        self,
        src: Path,
        dst: Path,
        t_ms: int,
        *,
        long_side: int | None,
        dynamic_range: str | None,
        cancel: Callable[[], bool],
    ) -> bool: ...


# ---------- ตัวสร้างอาร์กิวเมนต์ (ฟังก์ชันล้วน) ----------


def _head(ffmpeg: str, src: Path) -> list[str]:
    return [ffmpeg, "-hide_banner", "-nostdin", "-y", "-progress", "pipe:1", "-nostats", "-i", str(src)]


def _meta_args(meta: MediaMeta) -> list[str]:
    args = ["-metadata", f"title={meta.title}", "-metadata", f"artist={meta.artist}", "-metadata", f"comment={meta.comment}"]
    if meta.date:
        args += ["-metadata", f"date={meta.date}"]
    if meta.track:
        args += ["-metadata", f"track={meta.track}"]
    return args


def _audio_lang(audio_language: str | None) -> list[str]:
    return ["-metadata:s:a:0", f"language={iso639_2(audio_language)}"] if audio_language else []


def mp4_args(
    ffmpeg: str,
    src: Path,
    dst: Path,
    meta: MediaMeta,
    *,
    cover: Path | None,
    subtitle: SubtitleInput | None,
    audio_language: str | None,
    no_audio: bool = False,
) -> list[str]:
    """no_audio = ทิ้งเสียงทุกแทร็ก: format วิดีโอที่เลือก (bv*) อาจเป็นไฟล์ที่มีเสียงติดมา
    แต่ไฟล์ "(ไม่มีเสียง)" ต้องไม่มีเสียงจริงๆ"""
    args = _head(ffmpeg, src)
    next_index = 1
    cover_idx = sub_idx = None
    if cover is not None:
        args += ["-i", str(cover)]
        cover_idx = next_index
        next_index += 1
    if subtitle is not None:
        args += ["-i", str(subtitle.path)]
        sub_idx = next_index
    args += ["-map", "0:v:0"] if no_audio else ["-map", "0:v:0", "-map", "0:a?"]
    if sub_idx is not None:
        args += ["-map", f"{sub_idx}:0"]
    if cover_idx is not None:
        args += ["-map", f"{cover_idx}:0"]
    args += ["-c", "copy"]
    if no_audio:
        args += ["-an"]
    if subtitle is not None:
        args += ["-c:s", "mov_text", "-metadata:s:s:0", f"language={subtitle.language}", "-disposition:s:0", "default"]
    if cover is not None:
        args += ["-disposition:v:1", "attached_pic"]
    args += _meta_args(meta) + ([] if no_audio else _audio_lang(audio_language))
    args += ["-movflags", "+faststart", str(dst)]
    return args


def m4a_args(
    ffmpeg: str,
    src: Path,
    dst: Path,
    meta: MediaMeta,
    *,
    cover: Path | None,
    audio_language: str | None,
) -> list[str]:
    args = _head(ffmpeg, src)
    if cover is not None:
        args += ["-i", str(cover)]
    args += ["-map", "0:a:0"]
    if cover is not None:
        args += ["-map", "1:0", "-disposition:v:0", "attached_pic"]
    args += ["-c", "copy"] + _meta_args(meta) + _audio_lang(audio_language)
    args += ["-f", "mp4", "-movflags", "+faststart", str(dst)]
    return args


def mp3_args(
    ffmpeg: str,
    src: Path,
    dst: Path,
    meta: MediaMeta,
    *,
    kbps: int,
    cover: Path | None,
    audio_language: str | None,
) -> list[str]:
    args = _head(ffmpeg, src)
    if cover is not None:
        args += ["-i", str(cover)]
    args += ["-map", "0:a:0"]
    if cover is not None:
        args += ["-map", "1:0"]
    args += ["-c:a", "libmp3lame", "-b:a", f"{kbps}k"]
    if cover is not None:
        args += ["-c:v", "copy", "-disposition:v:0", "attached_pic"]
    args += ["-id3v2_version", "3"] + _meta_args(meta) + _audio_lang(audio_language)
    args += [str(dst)]
    return args


def wav_args(
    ffmpeg: str,
    src: Path,
    dst: Path,
    meta: MediaMeta,
    *,
    audio_language: str | None,
) -> list[str]:
    # ไม่ใส่ -ar: อัตราสุ่มตัวอย่างคงเดิม  audio_language รับไว้ให้ลายเซ็นเหมือนตัวอื่น (wav ไม่มีแท็กภาษา)
    tags = ["-metadata", f"title={meta.title}", "-metadata", f"artist={meta.artist}"]
    if meta.track:
        tags += ["-metadata", f"track={meta.track}"]
    return _head(ffmpeg, src) + ["-map", "0:a:0", "-c:a", "pcm_s16le"] + tags + [str(dst)]


def _seconds(ms: int) -> str:
    return f"{ms / 1000:.3f}"


def _check_intervals(intervals: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    clean = [(int(s), int(e)) for s, e in intervals]
    if not clean or any(s < 0 or e <= s for s, e in clean):
        raise ValueError(f"bad cut intervals: {intervals!r}")
    return clean


def _check_cut(intervals: Sequence[tuple[int, int]], mode: CutMode, target: CutTarget) -> list[tuple[int, int]]:
    """กฎเดียวกันทั้งตัวจริง (cut_args) และตัวปลอม: ใช้ผิดในโหมดปลอมก็พังเหมือนของจริง"""
    clean = _check_intervals(intervals)
    if mode == "fast" and (target != "mp4" or len(clean) != 1):
        raise ValueError("fast cut takes exactly one interval of an mp4")
    return clean


def cut_args(
    ffmpeg: str,
    src: Path,
    dst: Path,
    intervals: Sequence[tuple[int, int]],
    *,
    mode: CutMode,
    target: CutTarget,
    has_audio: bool,
) -> list[str]:
    """ตัดช่วง (มิลลิวินาทีบนเส้นเวลาต้นฉบับ) ลงไฟล์ระหว่างทาง (C3)

    - fast: mp4 ช่วงเดียว คัดลอกสตรีม เริ่มที่ keyframe ก่อนจุดตัด (แยก chapter ของวิดีโอ D6)
    - exact + m4a ช่วงเดียว: คัดลอกสตรีม (คลาดไม่เกินหนึ่งเฟรม AAC ~23 ms)
    - exact อื่น ๆ: แต่ละช่วงเป็น input ของตัวเอง (-ss ก่อน -i = seek แม่นยำเมื่อเข้ารหัสใหม่) แล้วต่อด้วย concat
      mp4 = H.264 + AAC (หรือไม่มีเสียง) · m4a = AAC · wav = PCM (ให้ to_mp3/to_wav แปลงต่อ)
    """
    clean = _check_cut(intervals, mode, target)
    head = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-progress", "pipe:1", "-nostats"]
    if mode == "fast":
        ((s, e),) = clean
        maps = ["-map", "0:v:0"] + (["-map", "0:a?"] if has_audio else [])
        return head + ["-ss", _seconds(s), "-t", _seconds(e - s), "-i", str(src)] + maps + [
            "-c", "copy", "-avoid_negative_ts", "make_zero", "-f", "mp4", str(dst)]  # fmt: skip
    if target == "m4a" and len(clean) == 1:
        ((s, e),) = clean
        return head + ["-ss", _seconds(s), "-t", _seconds(e - s), "-i", str(src),
                       "-map", "0:a:0", "-c", "copy", "-f", "mp4", str(dst)]  # fmt: skip
    video = target == "mp4"
    audio = has_audio or target != "mp4"
    args = list(head)
    chains: list[str] = []
    pads: list[str] = []
    for i, (s, e) in enumerate(clean):
        args += ["-ss", _seconds(s), "-t", _seconds(e - s), "-i", str(src)]
        if video:
            chains.append(f"[{i}:v:0]setpts=PTS-STARTPTS[v{i}]")
            pads.append(f"[v{i}]")
        if audio:
            chains.append(f"[{i}:a:0]asetpts=PTS-STARTPTS[a{i}]")
            pads.append(f"[a{i}]")
    outs = ("[v]" if video else "") + ("[a]" if audio else "")
    chains.append("".join(pads) + f"concat=n={len(clean)}:v={int(video)}:a={int(audio)}{outs}")
    args += ["-filter_complex", ";".join(chains)]
    if video:
        args += ["-map", "[v]"]
    if audio:
        args += ["-map", "[a]"]
    if video:
        args += ["-c:v", "libx264", "-preset", X264_PRESET, "-crf", str(X264_CRF), "-pix_fmt", "yuv420p"]
    if audio:
        args += ["-c:a", "pcm_s16le"] if target == "wav" else ["-c:a", "aac", "-b:a", f"{CUT_AAC_KBPS}k"]
    else:
        args += ["-an"]
    return args + ["-f", "wav" if target == "wav" else "mp4", str(dst)]


def scale_filter(long_side: int) -> str:
    """ย่อให้ด้านยาวไม่เกิน long_side คงสัดส่วน ไม่ขยาย (แนวนอน 1280x720 · แนวตั้ง 720x1280 · ภาพเล็กคงเดิม)"""
    return f"scale=w='min({long_side},iw)':h='min({long_side},ih)':force_original_aspect_ratio=decrease"


def tonemap_filter(dynamic_range: str) -> str:
    """HDR -> SDR (D8 ใช้เฉพาะคลิปที่ไม่มี format SDR เลย) setparams บอกช่วงสีให้ zscale เองเพราะบางไฟล์ไม่ติดป้าย
    (วัดแล้ว: ไม่มี setparams = "no path between colorspaces") HLG ใช้ arib-std-b67 นอกนั้น smpte2084 (HDR10)"""
    trc = "arib-std-b67" if dynamic_range.strip().upper() == _HLG else "smpte2084"
    return (
        f"setparams=range=tv:color_primaries=bt2020:color_trc={trc}:colorspace=bt2020nc,"
        "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0,"
        "zscale=t=bt709:m=bt709:r=tv,format=yuv420p"
    )


def _check_frame(t_ms: int, long_side: int | None, dynamic_range: str | None) -> None:
    """กฎเดียวกันทั้งตัวจริงและตัวปลอม · long_side None = ไม่ย่อ (ภาพคมตรงจุด M5 รอบ B2)"""
    if isinstance(t_ms, bool) or not isinstance(t_ms, int) or t_ms < 0:
        raise ValueError(f"bad frame time: {t_ms!r}")
    if long_side is not None and (isinstance(long_side, bool) or not isinstance(long_side, int) or long_side < 1):
        raise ValueError(f"bad long side: {long_side!r}")
    if dynamic_range is not None and dynamic_range.strip().upper() in ("", "SDR"):
        raise ValueError("pass dynamic_range=None for SDR")


def frame_args(
    ffmpeg: str,
    src: Path,
    dst: Path,
    t_ms: int,
    *,
    long_side: int | None = SHARP_LONG_SIDE,
    dynamic_range: str | None = None,
) -> list[str]:
    """ภาพคมหนึ่งภาพ (spec 3.4): -ss ก่อน -i บนไฟล์ในเครื่อง = ตรงเวลา · dynamic_range = HDR ที่ต้อง tone-map
    long_side None = เก็บความละเอียดเท่าต้นฉบับ (M5 รอบ B2) · ไม่มีตัวกรองเลย = ไม่ใส่ -vf"""
    _check_frame(t_ms, long_side, dynamic_range)
    filters: list[str] = []
    if dynamic_range is not None:
        filters.append(tonemap_filter(dynamic_range))
    if long_side is not None:
        filters.append(scale_filter(long_side))
    vf = ["-vf", ",".join(filters)] if filters else []
    return [ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-ss", _seconds(t_ms), "-i", str(src),
            "-frames:v", "1", *vf, "-q:v", str(SHARP_JPEG_Q), str(dst)]  # fmt: skip


def _no_progress(_fraction: float | None) -> None:
    """ภาพเดียวจบเร็ว ความคืบหน้านับต่อภาพที่ตัวทำงาน"""


# ---------- ตัวรัน ffmpeg ----------


def run_ffmpeg(
    args: list[str],
    *,
    duration_s: float | None,
    cancel: Callable[[], bool],
    on_progress: Callable[[float | None], None],
    popen_flags: int = 0,
) -> None:
    """รัน ffmpeg แล้วรายงานความคืบหน้า (0..1) จาก `-progress pipe:1` ยกเลิกได้ภายใน ~0.1 วินาที"""
    try:
        proc = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=popen_flags,
        )
    except (FileNotFoundError, PermissionError) as exc:
        # ffmpeg ถูกลบ ย้าย หรือโดนโปรแกรมแอนตี้ไวรัสกักกันหลังจากหาเจอแล้ว
        raise YtError("E_FFMPEG_MISSING", type(exc).__name__) from exc
    stderr_tail: list[str] = []

    def read_stdout() -> None:
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.decode("utf-8", errors="replace").strip()
            # out_time_ms ของ ffmpeg เป็นไมโครวินาทีเหมือน out_time_us (ชื่อผิดมาตั้งแต่ต้น) รับไว้เป็นตัวสำรอง
            if not line.startswith(("out_time_us=", "out_time_ms=")):
                continue
            try:
                micros = int(line.split("=", 1)[1])
            except ValueError:
                continue
            if duration_s and duration_s > 0:
                value: float | None = min(1.0, max(0.0, micros / (duration_s * 1_000_000)))
            else:
                value = None
            try:
                on_progress(value)
            except Exception:
                continue  # callback พัง ต้องไม่ทำให้ตัวอ่านหยุด ไม่งั้น ffmpeg จะค้างเพราะ pipe เต็ม

    def read_stderr() -> None:
        assert proc.stderr is not None
        data = proc.stderr.read().decode("utf-8", errors="replace")
        stderr_tail.append(data[-_STDERR_TAIL_CHARS:])

    threads = [threading.Thread(target=read_stdout, daemon=True), threading.Thread(target=read_stderr, daemon=True)]
    for t in threads:
        t.start()
    try:
        while proc.poll() is None:
            if cancel():
                proc.kill()
                proc.wait()
                raise JobCancelled()
            try:
                proc.wait(timeout=_POLL_SECONDS)  # ffmpeg จบเมื่อไหร่ก็กลับทันที (ไม่รอเต็มรอบ)
            except subprocess.TimeoutExpired:
                continue
    except BaseException:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        raise
    finally:
        for t in threads:
            t.join(timeout=2)
        for stream in (proc.stdout, proc.stderr):
            if stream is not None:
                stream.close()
    if proc.returncode != 0:
        tail = "".join(stderr_tail)[-_STDERR_TAIL_CHARS:]
        if "No space left on device" in tail:
            raise YtError("E_DISK_FULL", tail)
        raise YtError("E_UNKNOWN", f"ffmpeg exit {proc.returncode}: {tail}")


# ---------- ตัวจริงและตัวปลอม ----------


class FfmpegTools:
    """MediaTools ที่เรียก ffmpeg จริง `find_ffmpeg` ถูกเรียกทุกครั้งที่ใช้ (ผู้ใช้อาจเพิ่งติดตั้ง ffmpeg)"""

    def __init__(self, find_ffmpeg: Callable[[], Path | None], *, popen_flags: int = 0) -> None:
        self._find = find_ffmpeg
        self._popen_flags = popen_flags

    def available(self) -> bool:
        return self._find() is not None

    def ffmpeg_path(self) -> Path | None:
        return self._find()

    def _require(self) -> str:
        path = self._find()
        if path is None:
            raise YtError("E_FFMPEG_MISSING")
        return str(path)

    @staticmethod
    def _abs(path: Path | None) -> Path | None:
        # path แบบสัมพัทธ์ที่ขึ้นต้นด้วย "-" จะถูก ffmpeg อ่านเป็นตัวเลือก
        return path.resolve() if path is not None else None

    def _run(
        self,
        args: list[str],
        meta: MediaMeta,
        cancel: Callable[[], bool],
        on_progress: Callable[[float | None], None],
    ) -> None:
        run_ffmpeg(
            args,
            duration_s=meta.duration_s,
            cancel=cancel,
            on_progress=on_progress,
            popen_flags=self._popen_flags,
        )

    def finalize_mp4(
        self,
        src: Path,
        dst: Path,
        meta: MediaMeta,
        *,
        cover: Path | None,
        subtitle: SubtitleInput | None,
        audio_language: str | None,
        cancel: Callable[[], bool],
        on_progress: Callable[[float | None], None],
        no_audio: bool = False,
    ) -> None:
        if subtitle is not None:
            subtitle = replace(subtitle, path=subtitle.path.resolve())
        args = mp4_args(
            self._require(), src.resolve(), dst.resolve(), meta,
            cover=self._abs(cover), subtitle=subtitle, audio_language=audio_language, no_audio=no_audio,
        )  # fmt: skip
        self._run(args, meta, cancel, on_progress)

    def finalize_m4a(
        self,
        src: Path,
        dst: Path,
        meta: MediaMeta,
        *,
        cover: Path | None,
        audio_language: str | None,
        cancel: Callable[[], bool],
        on_progress: Callable[[float | None], None],
    ) -> None:
        args = m4a_args(
            self._require(), src.resolve(), dst.resolve(), meta, cover=self._abs(cover), audio_language=audio_language
        )
        self._run(args, meta, cancel, on_progress)

    def to_mp3(
        self,
        src: Path,
        dst: Path,
        meta: MediaMeta,
        *,
        kbps: int,
        cover: Path | None,
        audio_language: str | None,
        cancel: Callable[[], bool],
        on_progress: Callable[[float | None], None],
    ) -> None:
        args = mp3_args(
            self._require(), src.resolve(), dst.resolve(), meta,
            kbps=kbps, cover=self._abs(cover), audio_language=audio_language,
        )  # fmt: skip
        self._run(args, meta, cancel, on_progress)

    def to_wav(
        self,
        src: Path,
        dst: Path,
        meta: MediaMeta,
        *,
        audio_language: str | None,
        cancel: Callable[[], bool],
        on_progress: Callable[[float | None], None],
    ) -> None:
        args = wav_args(self._require(), src.resolve(), dst.resolve(), meta, audio_language=audio_language)
        self._run(args, meta, cancel, on_progress)

    def cut(
        self,
        src: Path,
        dst: Path,
        intervals: Sequence[tuple[int, int]],
        *,
        mode: CutMode,
        target: CutTarget,
        has_audio: bool,
        cancel: Callable[[], bool],
        on_progress: Callable[[float | None], None],
    ) -> None:
        args = cut_args(self._require(), src.resolve(), dst.resolve(), intervals,
                        mode=mode, target=target, has_audio=has_audio)  # fmt: skip
        kept_s = sum(e - s for s, e in intervals) / 1000
        run_ffmpeg(args, duration_s=kept_s, cancel=cancel, on_progress=on_progress, popen_flags=self._popen_flags)

    def extract_frame(
        self,
        src: Path,
        dst: Path,
        t_ms: int,
        *,
        long_side: int | None,
        dynamic_range: str | None,
        cancel: Callable[[], bool],
    ) -> bool:
        """True = ได้ภาพ JPEG ที่ dst · False = ffmpeg ไม่ได้ภาพ (เวลาเลยภาพสุดท้าย ช่วงวินาทีท้ายคลิป) ภาพจึงถูกข้าม
        ffmpeg หาไม่เจอ / ดิสก์เต็ม / ยกเลิก = โยนต่อ"""
        args = frame_args(self._require(), src.resolve(), dst.resolve(), t_ms,
                          long_side=long_side, dynamic_range=dynamic_range)  # fmt: skip
        if cancel():
            # เหมือนตัวปลอม: ยกเลิกแล้วไม่เปิด ffmpeg (ภาพเดียวจบเร็วกว่ารอบเช็กยกเลิกของ run_ffmpeg)
            raise JobCancelled()
        dst.unlink(missing_ok=True)
        try:
            run_ffmpeg(args, duration_s=None, cancel=cancel, on_progress=_no_progress, popen_flags=self._popen_flags)
        except YtError as exc:
            if exc.code != "E_UNKNOWN":
                raise
            dst.unlink(missing_ok=True)
            return False
        return dst.is_file() and dst.stat().st_size > 0


@dataclass(frozen=True)
class FrameCall:
    """ภาพคมหนึ่งภาพของ FakeMediaTools (ภาพที่เขียนเป็นสำเนาของ cover.jpg เสมอ)"""

    src_name: str
    dst_name: str
    t_ms: int
    long_side: int | None
    dynamic_range: str | None


@dataclass(frozen=True)
class CutCall:
    """การตัดหนึ่งครั้งของ FakeMediaTools (เทสตรวจช่วงที่ตัด ความยาวของไฟล์ปลอมไม่ตรงกับช่วงที่ตัด)"""

    src_name: str
    dst_name: str
    intervals: tuple[tuple[int, int], ...]
    mode: str
    target: str
    has_audio: bool


class FakeMediaTools:
    """MediaTools ที่ไม่ใช้ ffmpeg: คัดลอกไฟล์ (ใช้ใน e2e และเทสที่ไม่มี ffmpeg)

    mp4 / m4a คัดลอก `src` ไป `dst` ส่วน mp3 / wav เขียนสำเนาของ audio.mp3 / audio.wav ใน `media_root`
    ตัดช่วง = คัดลอกไฟล์ (เป้าหมาย wav = audio.wav) และจดการเรียกไว้ใน cuts
    ภาพคม = คัดลอก cover.jpg และจดการเรียกไว้ใน frames
    """

    def __init__(self, media_root: Path) -> None:
        self._root = media_root
        self.cuts: list[CutCall] = []
        self.frames: list[FrameCall] = []
        self.frame_limit_ms: int | None = None  # เวลาตั้งแต่นี้ไม่ได้ภาพ (เลียนแบบภาพท้ายคลิป)

    def available(self) -> bool:
        return True

    def ffmpeg_path(self) -> Path | None:
        return None

    def _copy(
        self,
        source: Path,
        dst: Path,
        cancel: Callable[[], bool],
        on_progress: Callable[[float | None], None],
    ) -> None:
        if cancel():
            raise JobCancelled()
        shutil.copyfile(source, dst)
        on_progress(1.0)

    def finalize_mp4(
        self,
        src: Path,
        dst: Path,
        meta: MediaMeta,
        *,
        cover: Path | None,
        subtitle: SubtitleInput | None,
        audio_language: str | None,
        cancel: Callable[[], bool],
        on_progress: Callable[[float | None], None],
        no_audio: bool = False,
    ) -> None:
        self._copy(src, dst, cancel, on_progress)

    def finalize_m4a(
        self,
        src: Path,
        dst: Path,
        meta: MediaMeta,
        *,
        cover: Path | None,
        audio_language: str | None,
        cancel: Callable[[], bool],
        on_progress: Callable[[float | None], None],
    ) -> None:
        self._copy(src, dst, cancel, on_progress)

    def to_mp3(
        self,
        src: Path,
        dst: Path,
        meta: MediaMeta,
        *,
        kbps: int,
        cover: Path | None,
        audio_language: str | None,
        cancel: Callable[[], bool],
        on_progress: Callable[[float | None], None],
    ) -> None:
        self._copy(self._root / "audio.mp3", dst, cancel, on_progress)

    def to_wav(
        self,
        src: Path,
        dst: Path,
        meta: MediaMeta,
        *,
        audio_language: str | None,
        cancel: Callable[[], bool],
        on_progress: Callable[[float | None], None],
    ) -> None:
        self._copy(self._root / "audio.wav", dst, cancel, on_progress)

    def cut(
        self,
        src: Path,
        dst: Path,
        intervals: Sequence[tuple[int, int]],
        *,
        mode: CutMode,
        target: CutTarget,
        has_audio: bool,
        cancel: Callable[[], bool],
        on_progress: Callable[[float | None], None],
    ) -> None:
        clean = _check_cut(intervals, mode, target)
        if cancel():
            raise JobCancelled()
        self.cuts.append(CutCall(src.name, dst.name, tuple(clean), mode, target, has_audio))
        self._copy(self._root / "audio.wav" if target == "wav" else src, dst, cancel, on_progress)

    def extract_frame(
        self,
        src: Path,
        dst: Path,
        t_ms: int,
        *,
        long_side: int | None,
        dynamic_range: str | None,
        cancel: Callable[[], bool],
    ) -> bool:
        _check_frame(t_ms, long_side, dynamic_range)
        if cancel():
            raise JobCancelled()
        self.frames.append(FrameCall(src.name, dst.name, t_ms, long_side, dynamic_range))
        if not Path(src).is_file() or (self.frame_limit_ms is not None and t_ms >= self.frame_limit_ms):
            return False
        shutil.copyfile(self._root / "cover.jpg", dst)
        return True
