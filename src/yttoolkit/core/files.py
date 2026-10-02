"""ไฟล์ปลายทางของงานโหลด (C10): ตั้งชื่อโฟลเดอร์/ไฟล์ ย้ายเข้าที่ และแหล่งที่มา.txt

- โฟลเดอร์ของคลิป = `<outputDir>/<ชื่อคลิป> [<videoId>]/` ชื่อโฟลเดอร์ขึ้นกับ (root, title, video_id) เท่านั้น
  ทุกงานของคลิปเดียวกันจึงลงโฟลเดอร์เดียวกัน
- งานจากหน้าเลือกหลายคลิป (W3) มีโฟลเดอร์กลุ่มคั่นกลาง: `<outputDir>/<ชื่อโฟลเดอร์>/<ชื่อคลิป> [<videoId>]/`
- path เต็มต้องไม่เกิน 240 ตัวอักษร (เผื่อ " (99)" ไว้ต่อท้ายตอนชื่อซ้ำ)
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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .yterrors import YtError

PATH_LIMIT = 240
TITLE_MAX = 100
TAIL_RESERVE = 30  # suffix + "." + ext ยาวไม่เกินนี้
UNIQUE_RESERVE = 5  # " (99)"
SOURCE_NOTE_NAME = "แหล่งที่มา.txt"
GROUP_FALLBACK = "YT-Toolkit batch"  # ชื่อโฟลเดอร์กลุ่มที่ทำความสะอาดแล้วว่าง (เช่น "..")

_MIN_TITLE = 8
_FORBIDDEN = frozenset('\\/:*?"<>|')
_RESERVED = frozenset({
    "CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
    *(f"COM{n}" for n in range(1, 10)), *(f"LPT{n}" for n in range(1, 10)),
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


def plan_output(root: Path, title: str, video_id: str, suffix: str, ext: str, group: str | None = None) -> Path:
    """path ปลายทางที่วางแผนไว้ (ยังไม่สร้างอะไร) ชื่อยาวเกินให้ตัดชื่อคลิป ถ้าไม่พอแม้แต่ 8 ตัวใช้ videoId แทน

    group = ชื่อโฟลเดอร์กลุ่มดิบจากงาน (params.folder) มี = `<root>/<กลุ่มที่ปลอดภัย>/<ชื่อคลิป> [<id>]/<ไฟล์>`
    ชื่อกลุ่มไม่ถูกตัด: path ยาวเกินให้ตัดชื่อคลิปก่อน แล้วค่อยใช้ทางสำรองเดิม (videoId / E_OUTPUT_NOT_WRITABLE)
    """
    tail = f"{suffix}.{ext}"
    assert _u16(tail) <= TAIL_RESERVE, "suffix + extension longer than TAIL_RESERVE"
    base = root / group_folder_name(group) if group else root
    t = safe_component(title, video_id)
    budget = PATH_LIMIT - (_u16(str(base)) + 1) - _u16(f" [{video_id}]") - 1 - TAIL_RESERVE - UNIQUE_RESERVE
    cap = budget // 2
    short = ""
    if cap >= _MIN_TITLE:
        short = truncate_title(t, min(TITLE_MAX, cap))
    if short:
        planned = base / f"{short} [{video_id}]" / f"{short}{tail}"
    else:
        planned = base / video_id / f"{video_id}{tail}"
    if _u16(str(planned)) > PATH_LIMIT - UNIQUE_RESERVE:
        raise YtError("E_OUTPUT_NOT_WRITABLE", "path too long")
    return planned


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
