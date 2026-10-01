"""ไฟล์ปลายทางของงานโหลด (C10): ตั้งชื่อโฟลเดอร์/ไฟล์ ย้ายเข้าที่ และแหล่งที่มา.txt

- โฟลเดอร์ของคลิป = `<outputDir>/<ชื่อคลิป> [<videoId>]/` ชื่อโฟลเดอร์ขึ้นกับ (root, title, video_id) เท่านั้น
  ทุกงานของคลิปเดียวกันจึงลงโฟลเดอร์เดียวกัน
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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .yterrors import YtError

PATH_LIMIT = 240
TITLE_MAX = 100
TAIL_RESERVE = 30  # suffix + "." + ext ยาวไม่เกินนี้
UNIQUE_RESERVE = 5  # " (99)"
SOURCE_NOTE_NAME = "แหล่งที่มา.txt"

_MIN_TITLE = 8
_FORBIDDEN = frozenset('\\/:*?"<>|')
_RESERVED = frozenset({"CON", "PRN", "AUX", "NUL", *(f"COM{n}" for n in range(1, 10)), *(f"LPT{n}" for n in range(1, 10))})
_WHITESPACE = re.compile(r"\s+")
_BANGKOK = timezone(timedelta(hours=7))
_CRLF = "\r\n"

# ชื่อไฟล์ที่กำลังย้ายเข้าที่พร้อมกันหลายงานต้องไม่ได้ชื่อเดียวกัน จึงเลือกชื่อและย้ายภายใต้ล็อกเดียว
_move_lock = threading.Lock()
_note_locks: dict[str, threading.Lock] = {}
_note_locks_guard = threading.Lock()


def safe_component(text: str, fallback: str) -> str:
    """ชื่อที่ใช้เป็นส่วนหนึ่งของ path บน Windows ได้: ตัดอักขระต้องห้ามและตัวควบคุม ช่องว่างติดกันเหลือช่องเดียว"""
    spaced = _WHITESPACE.sub(" ", text)
    kept = "".join(ch for ch in spaced if ch not in _FORBIDDEN and unicodedata.category(ch) not in ("Cc", "Cf"))
    name = kept.strip().rstrip(". ")
    if not name:
        return fallback
    if name.split(".", 1)[0].strip().upper() in _RESERVED:
        name = "_" + name
    return name


def truncate_title(text: str, limit: int) -> str:
    """ตัดให้ไม่เกิน limit ตัวอักษร โดยไม่ทิ้งสระ/วรรณยุกต์ (หมวด M) ไว้ตัวแรกหลังรอยตัด"""
    if len(text) <= limit:
        return text.rstrip(". ")
    cut = max(limit, 0)
    while cut > 0 and unicodedata.category(text[cut]).startswith("M"):
        cut -= 1
    return text[:cut].rstrip(". ")


def plan_output(root: Path, title: str, video_id: str, suffix: str, ext: str) -> Path:
    """path ปลายทางที่วางแผนไว้ (ยังไม่สร้างอะไร) ชื่อยาวเกินให้ตัดชื่อคลิป ถ้าไม่พอแม้แต่ 8 ตัวใช้ videoId แทน"""
    tail = f"{suffix}.{ext}"
    assert len(tail) <= TAIL_RESERVE, "suffix + extension longer than TAIL_RESERVE"
    t = safe_component(title, video_id)
    budget = PATH_LIMIT - (len(str(root)) + 1) - len(f" [{video_id}]") - 1 - TAIL_RESERVE - UNIQUE_RESERVE
    cap = budget // 2
    short = ""
    if cap >= _MIN_TITLE:
        short = truncate_title(t, min(TITLE_MAX, len(t), cap))
    if short:
        planned = root / f"{short} [{video_id}]" / f"{short}{tail}"
    else:
        planned = root / video_id / f"{video_id}{tail}"
    if len(str(planned)) > PATH_LIMIT - UNIQUE_RESERVE:
        raise YtError("E_OUTPUT_NOT_WRITABLE", "path too long")
    return planned


def unique_path(path: Path) -> Path:
    """path เดิมถ้ายังว่าง ไม่งั้น "<ชื่อ> (2)<นามสกุล>" ... "(99)" เต็มหมดให้ error"""
    if not path.exists():
        return path
    for n in range(2, 100):
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate
    raise YtError("E_OUTPUT_NOT_WRITABLE", f"no free name for {path.name}")


def move_into_place(src: Path, planned: Path) -> Path:
    """ย้ายไฟล์จากโฟลเดอร์ทำงานเข้าที่หมาย (สร้างโฟลเดอร์ให้ ชื่อซ้ำต่อ (2)) คืน path สุดท้าย"""
    try:
        planned.parent.mkdir(parents=True, exist_ok=True)
        with _move_lock:
            final = unique_path(planned)
            try:
                os.replace(src, final)
            except OSError:
                shutil.move(str(src), str(final))  # ข้ามไดรฟ์
    except OSError as err:
        if err.errno == errno.ENOSPC:
            raise YtError("E_DISK_FULL", str(err)) from err
        raise YtError("E_OUTPUT_NOT_WRITABLE", str(err)) from err
    return final


def ensure_output_root(root: Path) -> None:
    """สร้างโฟลเดอร์ปลายทางและลองเขียนไฟล์เล็กๆ ถ้าไม่ได้ให้ E_OUTPUT_NOT_WRITABLE"""
    probe = root / f".yttoolkit-write-test-{os.getpid()}"
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
