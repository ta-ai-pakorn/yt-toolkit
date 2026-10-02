"""เครื่องมือจัดการไฟล์สื่อด้วย ffmpeg (M4): ใส่ซับ/ปก/ข้อมูลลงไฟล์ แปลงเป็น mp3/wav

ทุกคำสั่งเป็น list ของอาร์กิวเมนต์ (ไม่ผ่าน shell) ชื่อคลิปที่มีอักขระแปลก ๆ จึงเป็น
อาร์กิวเมนต์ตัวเดียวเสมอ ตัวสร้างอาร์กิวเมนต์ (`*_args`) เป็นฟังก์ชันล้วนเพื่อเทสตรง ๆ
"""

from __future__ import annotations

import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from .cancel import JobCancelled
from .yterrors import YtError

_ISO639_2 = {
    "th": "tha", "en": "eng", "ja": "jpn", "ko": "kor", "zh": "chi", "fr": "fre", "de": "ger",
    "es": "spa", "pt": "por", "ru": "rus", "vi": "vie", "id": "ind", "ms": "may", "hi": "hin",
    "ar": "ara", "it": "ita", "lo": "lao", "my": "bur", "km": "khm",
}  # fmt: skip

_STDERR_TAIL_CHARS = 4000
_POLL_SECONDS = 0.1


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


# ---------- ตัวสร้างอาร์กิวเมนต์ (ฟังก์ชันล้วน) ----------


def _head(ffmpeg: str, src: Path) -> list[str]:
    return [ffmpeg, "-hide_banner", "-nostdin", "-y", "-progress", "pipe:1", "-nostats", "-i", str(src)]


def _meta_args(meta: MediaMeta) -> list[str]:
    args = ["-metadata", f"title={meta.title}", "-metadata", f"artist={meta.artist}", "-metadata", f"comment={meta.comment}"]
    if meta.date:
        args += ["-metadata", f"date={meta.date}"]
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
    return (
        _head(ffmpeg, src)
        + ["-map", "0:a:0", "-c:a", "pcm_s16le"]
        + ["-metadata", f"title={meta.title}", "-metadata", f"artist={meta.artist}"]
        + [str(dst)]
    )


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
            time.sleep(_POLL_SECONDS)
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


class FakeMediaTools:
    """MediaTools ที่ไม่ใช้ ffmpeg: คัดลอกไฟล์ (ใช้ใน e2e และเทสที่ไม่มี ffmpeg)

    mp4 / m4a คัดลอก `src` ไป `dst` ส่วน mp3 / wav เขียนสำเนาของ audio.mp3 / audio.wav ใน `media_root`
    """

    def __init__(self, media_root: Path) -> None:
        self._root = media_root

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
