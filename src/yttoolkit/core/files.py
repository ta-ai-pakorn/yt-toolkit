"""ไฟล์ปลายทางของงานโหลด (C10): ตั้งชื่อโฟลเดอร์/ไฟล์ ย้ายเข้าที่ และแหล่งที่มา.txt

- โฟลเดอร์ของคลิป = `<outputDir>/<ชื่อคลิป> [<videoId>]/` ชื่อโฟลเดอร์ขึ้นกับ (root, title, video_id) เท่านั้น
  ทุกงานของคลิปเดียวกันจึงลงโฟลเดอร์เดียวกัน
- งานจากหน้าเลือกหลายคลิป (W3) มีโฟลเดอร์กลุ่มคั่นกลาง: `<outputDir>/<ชื่อโฟลเดอร์>/<ชื่อคลิป> [<videoId>]/`
- path เต็มต้องไม่เกิน 240 ตัวอักษร (เผื่อ " (99)" ไว้ต่อท้ายตอนชื่อซ้ำ)
- M6 รอบ A: ชื่อไฟล์ตามรูปแบบ (title / title-channel / title-quality) คิดใน plan_names ที่เดียว
  หน้าเว็บมีตัวเดียวกันที่ web/src/lib/filename.ts (เทียบกันด้วย tests/fixtures/names/*.json)
- แหล่งที่มา.txt: UTF-8 ไม่มี BOM ขึ้นบรรทัดแบบ CRLF มีไฟล์เดียวต่อโฟลเดอร์ เขียนทับเมื่อมีงานใหม่
core/ ไม่ import api/ หรือ platform/
"""

from __future__ import annotations

import errno
import os
import re
import shutil
import threading
import unicodedata
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .yterrors import YtError

PATH_LIMIT = 240
TITLE_MAX = 100
TAIL_RESERVE = 30  # suffix + "." + ext ยาวไม่เกินนี้ (งบที่จองไว้ให้โฟลเดอร์ของคลิป ไม่เปลี่ยนตั้งแต่ M4)
TAIL_MAX = 60  # M5: ส่วนต่อท้าย (ไม่มีเสียง) + ช่วงเวลา + (ตัดโฆษณา) + นามสกุล ยาวได้ถึงนี้ (ส่วนเกิน TAIL_RESERVE ตัดจากชื่อไฟล์)
CHAPTER_DIR = "แยกตาม chapter ({ext})"  # D4: โฟลเดอร์ย่อยของไฟล์แยกตาม chapter ในโฟลเดอร์ของคลิป
# owner ruling 2026-10-02: chapter ของวิดีโอไม่มีเสียงแยกโฟลเดอร์ ไม่ปนกับชุดที่มีเสียง (ชื่อไฟล์ข้างในเหมือนกัน)
CHAPTER_DIR_NO_AUDIO = "แยกตาม chapter ({ext}, ไม่มีเสียง)"
UNIQUE_RESERVE = 5  # " (99)"
SOURCE_NOTE_NAME = "แหล่งที่มา.txt"
GROUP_FALLBACK = "YT-Toolkit batch"  # ชื่อโฟลเดอร์กลุ่มที่ทำความสะอาดแล้วว่าง (เช่น "..")
SHARP_DIR_SUFFIX = " - ภาพคม"  # D2: โฟลเดอร์ภาพคม "<ชื่อคลิป> - ภาพคม" ในโฟลเดอร์ของคลิป
PARTIAL_MARKER = ".yttoolkit-partial"  # อยู่ในโฟลเดอร์ภาพคมเฉพาะระหว่างย้ายไฟล์เข้า (เจอตอนเปิดโปรแกรม = ของค้าง)
_LONGEST_FRAME_NAME = "frame_000-00-00_200.jpg"  # ชื่อภาพคมยาวสุด: ชั่วโมง 3 หลัก ภาพที่ 200 ในวินาทีเดียวกัน

# M6 รอบ A: รูปแบบชื่อไฟล์ (ค่าเดียวกับ settings.FILENAME_STYLES ซึ่งเป็นที่ตรวจค่าตั้ง files ไม่ import settings)
NAME_STYLES = ("title", "title-channel", "title-quality")
CHANNEL_SEP = " - "  # "<ชื่อคลิป> - <ช่อง>"
QUALITY_LABEL = re.compile(r"[a-z0-9 ]{1,16}")  # ส่วนคุณภาพ เช่น "1080p" "mp3 192k" "m4a" "wav"

_MIN_TITLE = 8
_FORBIDDEN = frozenset('\\/:*?"<>|')
_RESERVED = frozenset({
    "CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
    *(f"COM{n}" for n in range(1, 10)), *(f"LPT{n}" for n in range(1, 10)),
    # Windows ถือเลขยกกำลัง ¹ ² ³ เป็นเลขพอร์ตด้วย (mkdir "COM¹" ไม่ได้)
    *(f"{dev}{sup}" for dev in ("COM", "LPT") for sup in "¹²³"),
})  # fmt: skip
_WHITESPACE = re.compile(r"\s+")
_BANGKOK = timezone(timedelta(hours=7))
_CRLF = "\r\n"

_note_locks: dict[str, threading.Lock] = {}
_note_locks_guard = threading.Lock()
# ".<lang>.<fmt>" ของไฟล์ซับถือเป็นนามสกุลก้อนเดียว เลขกันซ้ำจะได้อยู่หน้ารหัสภาษา ("t (2).th.srt") player ยังเห็นภาษา
_SUB_EXT = re.compile(r"^(?P<stem>.+?)(?P<ext>\.[A-Za-z0-9-]+\.(?:srt|txt|md|vtt))$", re.IGNORECASE)
_WINERROR_NOT_SAME_DEVICE = 17


def _u16(text: str) -> int:
    """ความยาวเป็น UTF-16 code unit (Windows นับ path แบบนี้ อีโมจิหนึ่งตัวนับ 2)"""
    return len(text.encode("utf-16-le", errors="surrogatepass")) // 2


def safe_component(text: str, fallback: str) -> str:
    """ชื่อที่ใช้เป็นส่วนหนึ่งของ path บน Windows ได้: ตัดอักขระต้องห้ามและตัวควบคุม ช่องว่างติดกันเหลือช่องเดียว"""
    spaced = _WHITESPACE.sub(" ", text)
    kept = "".join(ch for ch in spaced if ch not in _FORBIDDEN and unicodedata.category(ch) not in ("Cc", "Cf", "Cs"))
    # ตัดตัวอักษรที่อยู่ระหว่างช่องว่างสองตัว ("Why | How") ทำให้เหลือช่องว่างติดกัน ต้องรวมอีกรอบ
    name = _WHITESPACE.sub(" ", kept).strip().rstrip(". ")
    if not name:
        return fallback
    if name.split(".", 1)[0].strip().upper() in _RESERVED:
        name = "_" + name
    return name


def truncate_title(text: str, limit: int) -> str:
    """ตัดให้ยาวไม่เกิน limit (UTF-16 code unit) โดยไม่ทิ้งสระ/วรรณยุกต์ (หมวด M) ไว้ตัวแรกหลังรอยตัด"""
    if _u16(text) <= limit:
        return text.rstrip(". ")
    cut = 0
    used = 0
    for ch in text:
        used += _u16(ch)
        if used > limit:
            break
        cut += 1
    while cut > 0 and unicodedata.category(text[cut]).startswith("M"):
        cut -= 1
    return text[:cut].rstrip(". ")


def group_folder_name(folder: str) -> str:
    """ชื่อโฟลเดอร์กลุ่ม (W3 "ชื่อโฟลเดอร์") ที่ใช้เป็น path หนึ่งชั้นบน Windows ได้แน่นอน

    ไม่เชื่อข้อความจากหน้าเว็บเป็น path: ตัวคั่น/อักขระต้องห้ามถูกตัด ".." และชื่อที่เหลือแต่จุด/ช่องว่าง
    = GROUP_FALLBACK ชื่อสงวนของ Windows (CON, NUL ...) ได้ "_" นำหน้า ไม่มีจุด/ช่องว่างท้ายชื่อ
    """
    return safe_component(folder, GROUP_FALLBACK)


def _stem(short: str, channel: str, avail: int) -> str:
    """ชื่อไฟล์ก่อนส่วนท้าย (ยาวไม่เกิน avail) ไม่มีช่อง = กฎเดิมของ M4 ทุกตัวอักษร · มีช่อง = ตัดชื่อคลิปก่อน
    (เหลืออย่างน้อย 8 ตัว) แล้วค่อยตัดชื่อช่อง ยังไม่พอ = ทิ้งชื่อช่อง · คืน "" = ให้ผู้เรียกใช้รหัสคลิปแทน"""
    if not channel:
        return short if _u16(short) <= avail else truncate_title(short, avail)
    joined = f"{short}{CHANNEL_SEP}{channel}"
    if _u16(joined) <= avail:
        return joined
    sep = _u16(CHANNEL_SEP)
    cut = truncate_title(short, max(avail - sep - _u16(channel), _MIN_TITLE))
    if cut and _u16(f"{cut}{CHANNEL_SEP}{channel}") <= avail:
        return f"{cut}{CHANNEL_SEP}{channel}"
    room = avail - _u16(cut) - sep
    short_channel = truncate_title(channel, room) if cut and room >= 1 else ""
    if short_channel:
        return f"{cut}{CHANNEL_SEP}{short_channel}"
    return truncate_title(short, avail)


def plan_names(
    base_len: int,
    title: str,
    clip_id: str,
    *,
    suffix: str,
    ext: str,
    style: str = "title",
    uploader: str = "",
    quality: str | None = None,
) -> tuple[str, str]:
    """(ชื่อโฟลเดอร์ของคลิป, ชื่อไฟล์) ตามรูปแบบชื่อไฟล์ (M6 รอบ A spec 2.2) กฎเดียวกับ web/src/lib/filename.ts

    base_len = ความยาว UTF-16 ของโฟลเดอร์ที่โฟลเดอร์ของคลิปจะอยู่ (โฟลเดอร์ผลลัพธ์ + "\\<กลุ่ม>" ถ้ามี)
    clip_id = รหัสคลิปแบบข้อความทึบ (ใช้เป็นชื่อสำรองและใน " [<id>]" เท่านั้น ไม่ตรวจรูปแบบ C12)
    uploader = ชื่อช่อง (ใช้เฉพาะแบบ title-channel) · quality = ส่วนคุณภาพ เช่น "1080p" / "mp3 192k" (เฉพาะ title-quality)
    ชื่อโฟลเดอร์ไม่ขึ้นกับรูปแบบ (ทุกงานของคลิปลงโฟลเดอร์เดียวกัน) · ยาวเกิน = ตัดชื่อคลิปก่อน แล้วชื่อช่อง
    ไม่ตัดส่วนคุณภาพและนามสกุล · path ยาวเกินแม้ใช้รหัสคลิป = E_OUTPUT_NOT_WRITABLE
    """
    if style not in NAME_STYLES:
        raise ValueError(f"unknown filename style: {style!r}")
    if quality is not None and not QUALITY_LABEL.fullmatch(quality):
        raise ValueError(f"bad quality label: {quality!r}")
    quality_part = f" ({quality})" if style == "title-quality" and quality else ""
    tail = f"{quality_part}{suffix}.{ext}"
    assert _u16(tail) <= TAIL_MAX, "suffix + extension longer than TAIL_MAX"
    t = safe_component(title, clip_id)
    budget = PATH_LIMIT - (base_len + 1) - _u16(f" [{clip_id}]") - 1 - TAIL_RESERVE - UNIQUE_RESERVE
    cap = budget // 2
    short = truncate_title(t, min(TITLE_MAX, cap)) if cap >= _MIN_TITLE else ""
    if short:
        # ชื่อโฟลเดอร์คิดจากงบเดิมเสมอ (ทุกงานของคลิปลงโฟลเดอร์เดียวกัน) ส่วนท้ายที่ยาวกว่า TAIL_RESERVE
        # ตัดเฉพาะชื่อไฟล์ลงเท่าส่วนที่เกิน: ชื่อแบบ M4 (ส่วนท้าย <= 30) จึงเหมือนเดิมทุกตัวอักษร
        folder = f"{short} [{clip_id}]"
        avail = budget - _u16(short) + TAIL_RESERVE - _u16(tail)
        channel = safe_component(uploader, "") if style == "title-channel" else ""
        file = f"{_stem(short, channel, avail) or clip_id}{tail}"
    else:
        folder, file = clip_id, f"{clip_id}{tail}"
    if base_len + 1 + _u16(folder) + 1 + _u16(file) > PATH_LIMIT - UNIQUE_RESERVE:
        raise YtError("E_OUTPUT_NOT_WRITABLE", "path too long")
    return folder, file


def plan_output(
    root: Path,
    title: str,
    video_id: str,
    suffix: str,
    ext: str,
    group: str | None = None,
    *,
    style: str = "title",
    uploader: str = "",
    quality: str | None = None,
) -> Path:
    """path ปลายทางที่วางแผนไว้ (ยังไม่สร้างอะไร) ชื่อยาวเกินให้ตัดชื่อคลิป ถ้าไม่พอแม้แต่ 8 ตัวใช้ videoId แทน

    group = ชื่อโฟลเดอร์กลุ่มดิบจากงาน (params.folder) มี = `<root>/<กลุ่มที่ปลอดภัย>/<ชื่อคลิป> [<id>]/<ไฟล์>`
    ชื่อกลุ่มไม่ถูกตัด: path ยาวเกินให้ตัดชื่อคลิปก่อน แล้วค่อยใช้ทางสำรองเดิม (videoId / E_OUTPUT_NOT_WRITABLE)
    style / uploader / quality = รูปแบบชื่อไฟล์ (M6 รอบ A ดู plan_names) ผู้เรียกที่ใช้แค่ .parent ไม่ต้องส่ง
    """
    base = root / group_folder_name(group) if group else root
    folder, file = plan_names(
        _u16(str(base)), title, video_id, suffix=suffix, ext=ext, style=style, uploader=uploader, quality=quality
    )
    return base / folder / file


def chapter_dir_name(ext: str, *, no_audio: bool = False) -> str:
    """ชื่อโฟลเดอร์ย่อยของไฟล์แยกตาม chapter เช่น แยกตาม chapter (mp4) หรือ แยกตาม chapter (mp4, ไม่มีเสียง)"""
    return (CHAPTER_DIR_NO_AUDIO if no_audio else CHAPTER_DIR).format(ext=ext)


def plan_chapter_output(
    root: Path,
    title: str,
    video_id: str,
    ext: str,
    group: str | None,
    *,
    index: int,
    total: int,
    chapter_title: str,
    no_audio: bool = False,
) -> Path:
    """ไฟล์ของ chapter ที่ index: <โฟลเดอร์ของคลิป>/แยกตาม chapter (<ext>)/<NN> - <ชื่อ chapter>.<ext>
    no_audio (วิดีโอไม่มีเสียง) = โฟลเดอร์ย่อย "แยกตาม chapter (<ext>, ไม่มีเสียง)" ชื่อไฟล์ข้างในแบบเดียวกัน

    NN 2 หลัก (3 หลักเมื่อมี 100 chapter ขึ้นไป) ชื่อ chapter ทำความสะอาดแบบชื่อคลิป ว่าง = "chapter <n>"
    ตัดชื่อ chapter ให้ path ไม่เกิน 240 ไม่เหลือที่เลย = "<NN>.<ext>" ยังยาวเกิน = E_OUTPUT_NOT_WRITABLE
    """
    clip_folder = plan_output(root, title, video_id, "", ext, group).parent
    folder = clip_folder / chapter_dir_name(ext, no_audio=no_audio)
    number = f"{index:0{3 if total >= 100 else 2}d}"
    name = safe_component(chapter_title, f"chapter {index}")
    budget = PATH_LIMIT - UNIQUE_RESERVE - (_u16(str(folder)) + 1) - _u16(f"{number} - ") - _u16(f".{ext}")
    short = truncate_title(name, budget) if budget > 0 else ""
    planned = folder / (f"{number} - {short}.{ext}" if short else f"{number}.{ext}")
    if _u16(str(planned)) > PATH_LIMIT - UNIQUE_RESERVE:
        raise YtError("E_OUTPUT_NOT_WRITABLE", "path too long")
    return planned


def plan_sharp_dir(root: Path, title: str, video_id: str, group: str | None = None) -> Path:
    """โฟลเดอร์ภาพคม (ยังไม่สร้าง): <โฟลเดอร์ของคลิป>/<ชื่อ> - ภาพคม ชื่อตัดตามกฎของ plan_output แล้วตัดเพิ่มให้
    "<โฟลเดอร์> (99)/<ชื่อภาพยาวสุด>" ไม่เกิน 240 ไม่เหลือที่ = ใช้ videoId ยังยาวเกิน = E_OUTPUT_NOT_WRITABLE"""
    planned = plan_output(root, title, video_id, SHARP_DIR_SUFFIX, "jpg", group)
    folder = planned.with_name(planned.name[: -len(".jpg")])
    limit = PATH_LIMIT - UNIQUE_RESERVE - 1 - _u16(_LONGEST_FRAME_NAME)
    excess = _u16(str(folder)) - limit
    if excess > 0:
        stem = folder.name[: -len(SHARP_DIR_SUFFIX)]
        short = truncate_title(stem, _u16(stem) - excess)
        folder = folder.with_name(f"{short or video_id}{SHARP_DIR_SUFFIX}")
        if _u16(str(folder)) > limit:
            raise YtError("E_OUTPUT_NOT_WRITABLE", "path too long")
    return folder


def _candidates(path: Path):
    """path เดิม แล้ว "<ชื่อ> (2)<นามสกุล>" ... "(99)" (ไฟล์ซับ: "<ชื่อ> (2).<lang>.<fmt>")"""
    yield path
    match = _SUB_EXT.match(path.name)
    stem, ext = (match["stem"], match["ext"]) if match else (path.stem, path.suffix)
    for n in range(2, 100):
        yield path.with_name(f"{stem} ({n}){ext}")


def unique_path(path: Path) -> Path:
    """path เดิมถ้ายังว่าง ไม่งั้นต่อ (2) ... (99) เต็มหมดให้ error"""
    for candidate in _candidates(path):
        if not candidate.exists():
            return candidate
    raise YtError("E_OUTPUT_NOT_WRITABLE", f"no free name for {path.name}")


def _reserve(planned: Path) -> Path:
    """จองชื่อที่ว่างโดยสร้างไฟล์ว่างแบบ exclusive (atomic) หลายงานพร้อมกันจึงไม่ได้ชื่อซ้ำกัน"""
    for candidate in _candidates(planned):
        try:
            with candidate.open("xb"):
                pass
        except FileExistsError:
            continue
        return candidate
    raise YtError("E_OUTPUT_NOT_WRITABLE", f"no free name for {planned.name}")


def _is_cross_device(err: OSError) -> bool:
    return err.errno == errno.EXDEV or getattr(err, "winerror", None) == _WINERROR_NOT_SAME_DEVICE


def _copy_across_devices(src: Path, final: Path) -> None:
    """ข้ามไดรฟ์: คัดลอกเป็น <ชื่อ>.part แล้ว os.replace เป็นชื่อจริง ล้มเหลวตรงไหนก็ลบ .part ทิ้ง"""
    part = final.with_name(final.name + ".part")
    try:
        shutil.copy2(src, part)
        os.replace(part, final)
    finally:
        part.unlink(missing_ok=True)
    src.unlink(missing_ok=True)


def move_into_place(src: Path, planned: Path) -> Path:
    """ย้ายไฟล์จากโฟลเดอร์ทำงานเข้าที่หมาย (สร้างโฟลเดอร์ให้ ชื่อซ้ำต่อ (2)) คืน path สุดท้าย"""
    final: Path | None = None
    try:
        planned.parent.mkdir(parents=True, exist_ok=True)
        final = _reserve(planned)
        try:
            os.replace(src, final)
        except OSError as err:
            if not _is_cross_device(err):
                raise
            _copy_across_devices(src, final)
    except OSError as err:
        if final is not None:
            final.unlink(missing_ok=True)  # คืนชื่อที่จองไว้
        if err.errno == errno.ENOSPC:
            raise YtError("E_DISK_FULL", str(err)) from err
        raise YtError("E_OUTPUT_NOT_WRITABLE", str(err)) from err
    return final


def _dir_candidates(path: Path):
    """โฟลเดอร์เดิม แล้ว "<ชื่อ> (2)" ... "(99)" (ต่อท้ายทั้งชื่อ: โฟลเดอร์ไม่มีนามสกุล "Ep.1 - ภาพคม" จึงไม่ถูกตัดที่จุด)"""
    yield path
    for n in range(2, 100):
        yield path.with_name(f"{path.name} ({n})")


def _reserve_dir(planned: Path) -> Path:
    """จองชื่อโฟลเดอร์ด้วย mkdir แบบไม่ยอมให้มีอยู่ก่อน (atomic) หลายงานพร้อมกันจึงไม่ได้ชื่อซ้ำกัน"""
    for candidate in _dir_candidates(planned):
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        return candidate
    raise YtError("E_OUTPUT_NOT_WRITABLE", f"no free name for {planned.name}")


def move_files_into_dir(items: Sequence[tuple[Path, str]], planned: Path) -> Path:
    """ย้ายไฟล์จากโฟลเดอร์ทำงานเข้าโฟลเดอร์ใหม่ (ชื่อซ้ำต่อ (2)) คืนโฟลเดอร์จริง

    ระหว่างย้ายมี PARTIAL_MARKER อยู่ในโฟลเดอร์ ลบเมื่อครบทุกไฟล์ · พลาดหรือถูกยกเลิกกลางทาง = ลบโฟลเดอร์ที่เพิ่งสร้างทิ้ง
    ดับกลางทาง = เหลือโฟลเดอร์ที่มี marker ให้ lifecycle ล้างตอนเปิดโปรแกรม
    """
    for _src, name in items:
        if not name or Path(name).name != name or name in (".", "..", PARTIAL_MARKER):
            raise ValueError(f"bad file name: {name!r}")
    final: Path | None = None
    try:
        planned.parent.mkdir(parents=True, exist_ok=True)
        final = _reserve_dir(planned)
        marker = final / PARTIAL_MARKER
        marker.write_bytes(b"")
        for src, name in items:
            target = final / name
            try:
                os.replace(src, target)
            except OSError as err:
                if not _is_cross_device(err):
                    raise
                _copy_across_devices(src, target)
        marker.unlink()
    except BaseException as err:
        if final is not None:
            shutil.rmtree(final, ignore_errors=True)
        if isinstance(err, OSError):
            code = "E_DISK_FULL" if err.errno == errno.ENOSPC else "E_OUTPUT_NOT_WRITABLE"
            raise YtError(code, str(err)) from err
        raise
    return final


def ensure_output_root(root: Path) -> None:
    """สร้างโฟลเดอร์ปลายทางและลองเขียนไฟล์เล็กๆ ถ้าไม่ได้ให้ E_OUTPUT_NOT_WRITABLE"""
    # ชื่อไม่ซ้ำกันทุกครั้ง: งานหลายงานเริ่มพร้อมกันได้ ถ้าชื่อซ้ำ งานหนึ่งจะลบไฟล์ทดสอบของอีกงานทิ้ง
    probe = root / f".yttoolkit-write-test-{uuid.uuid4().hex}"
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe.write_bytes(b"")
        probe.unlink()
    except OSError as err:
        raise YtError("E_OUTPUT_NOT_WRITABLE", str(err)) from err


@dataclass(frozen=True)
class SourceInfo:
    title: str
    channel: str
    video_id: str
    published: str | None
    license: str | None


def _one_line(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def credit_line(title: str, channel: str, video_id: str) -> str:
    return f"ที่มา: {_one_line(title)} — {_one_line(channel)} (YouTube) https://youtu.be/{video_id}"


def source_note_text(info: SourceInfo, downloaded_at: datetime) -> str:
    """เนื้อหา แหล่งที่มา.txt ขึ้นบรรทัดด้วย CRLF ลงท้ายด้วยบรรทัดว่างหนึ่งบรรทัด (CRLF) เวลาเป็น +07:00"""
    when = downloaded_at.astimezone(_BANGKOK).strftime("%Y-%m-%d %H:%M")
    lines = [
        "แหล่งที่มา",
        f"ชื่อคลิป: {_one_line(info.title)}",
        f"ช่อง: {_one_line(info.channel)}",
        f"ลิงก์: https://www.youtube.com/watch?v={info.video_id}",
        f"วันที่เผยแพร่: {info.published or 'ไม่ระบุ'}",
        f"วันที่โหลด: {when} (+07:00)",
        f"สัญญาอนุญาต: {_one_line(info.license) if info.license else 'ไม่ระบุ'}",
        "",
        "เครดิตพร้อมใช้:",
        credit_line(info.title, info.channel, info.video_id),
        "",
        "ข้อความนี้เป็นข้อมูลอ้างอิงแหล่งที่มาเท่านั้น ไม่ได้แปลว่าได้รับอนุญาตให้ใช้เนื้อหา",
    ]
    return _CRLF.join(lines) + _CRLF


def _folder_lock(folder: Path) -> threading.Lock:
    with _note_locks_guard:
        return _note_locks.setdefault(str(folder), threading.Lock())


def write_source_note(folder: Path, info: SourceInfo, downloaded_at: datetime) -> Path:
    """เขียน แหล่งที่มา.txt ลงโฟลเดอร์ของคลิป (ไฟล์ชั่วคราว + os.replace ใต้ล็อกต่อโฟลเดอร์) เขียนทับของเดิม"""
    target = folder / SOURCE_NOTE_NAME
    data = source_note_text(info, downloaded_at).encode("utf-8")
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with _folder_lock(folder):
            tmp = folder / f".{SOURCE_NOTE_NAME}.{os.getpid()}.{threading.get_ident()}.tmp"
            try:
                tmp.write_bytes(data)
                os.replace(tmp, target)
            finally:
                tmp.unlink(missing_ok=True)
    except OSError as err:
        if err.errno == errno.ENOSPC:
            raise YtError("E_DISK_FULL", str(err)) from err
        raise YtError("E_OUTPUT_NOT_WRITABLE", str(err)) from err
    return target
