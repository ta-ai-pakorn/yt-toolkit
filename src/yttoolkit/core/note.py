"""โน้ตของคลิปแบบ Markdown สำหรับ Obsidian หรือแอพโน้ตอื่น (C-A3, owner round 2)

ฟังก์ชันล้วน: รับ VideoInfo (คีย์ camelCase) + บรรทัดทรานสคริปต์ที่ทำไว้แล้ว คืนข้อความโน้ต
- front matter แบบ YAML (ข้อความทุกช่องเป็น double-quoted ที่ escape แล้ว)
- หัวข้อ คำอธิบาย / Chapter / ทรานสคริปต์ หัวข้อที่ไม่มีข้อมูลไม่ใส่
- ขึ้นบรรทัดแบบ LF (Obsidian ชอบ LF) ต่างจากไฟล์ซับที่ใช้ CRLF
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from .srt_builder import md_time, md_title

SOURCE = "YT Toolkit"
LF = "\n"
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

# escape ของ YAML double-quoted scalar (YAML 1.2 ข้อ 5.7) ตัวขึ้นบรรทัดของ YAML 1.1 (NEL, LS, PS) ก็ escape
# เพราะตัวอ่าน YAML 1.1 (เช่น PyYAML) ถือว่าเป็นการขึ้นบรรทัด
_YAML_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\0": "\\0",
    "\a": "\\a",
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\v": "\\v",
    "\f": "\\f",
    "\r": "\\r",
    "\x1b": "\\e",
    "\x85": "\\N",
    " ": "\\L",
    " ": "\\P",
}


def _printable(cp: int) -> bool:
    """อักขระที่ YAML ยอมให้อยู่ในไฟล์ตรง ๆ (c-printable) ไม่รวม BOM กลางข้อความ"""
    return (
        0x20 <= cp <= 0x7E
        or 0xA0 <= cp <= 0xD7FF
        or (0xE000 <= cp <= 0xFFFD and cp != 0xFEFF)
        or 0x10000 <= cp <= 0x10FFFF
    )


def yaml_str(text: str) -> str:
    """ข้อความ -> YAML double-quoted scalar บรรทัดเดียว (อ่านกลับได้ตรงตัวทุกอักขระ)"""
    out = []
    for ch in text:
        cp = ord(ch)
        if ch in _YAML_ESCAPES:
            out.append(_YAML_ESCAPES[ch])
        elif _printable(cp):
            out.append(ch)
        elif cp <= 0xFF:
            out.append(f"\\x{cp:02X}")
        elif cp <= 0xFFFF:
            out.append(f"\\u{cp:04X}")
        else:
            out.append(f"\\U{cp:08X}")
    return '"' + "".join(out) + '"'


def hms(seconds: int) -> str:
    """ความยาวคลิปแบบ H:MM:SS (ชั่วโมงไม่เติมศูนย์) เช่น 372 -> 0:06:12"""
    h, rem = divmod(max(int(seconds), 0), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}"


def _lines(text: str) -> list[str]:
    """ข้อความหลายบรรทัด -> รายการบรรทัด (CRLF/CR เป็น LF) ตัดบรรทัดว่างท้ายข้อความ"""
    return text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n").split("\n")


def _front_matter(info: dict[str, Any], video_id: str) -> list[str]:
    title = str(info.get("title") or "")
    out = ["---", f"title: {yaml_str(title)}", f"url: https://www.youtube.com/watch?v={video_id}"]
    channel = info.get("channel")
    if isinstance(channel, str) and channel:
        out.append(f"channel: {yaml_str(channel)}")
    published = info.get("publishedAt")
    if isinstance(published, str) and _DATE.fullmatch(published):
        out.append(f"published: {published}")
    duration = info.get("durationS")
    if isinstance(duration, int) and not isinstance(duration, bool) and duration > 0:
        out.append(f'duration: "{hms(duration)}"')
    tags = [t for t in info.get("tags") or [] if isinstance(t, str) and t]
    if tags:
        out.append("tags: [" + ", ".join(yaml_str(t) for t in tags) + "]")
    views = (info.get("stats") or {}).get("views")
    if isinstance(views, int) and not isinstance(views, bool):
        out.append(f"views: {views}")
    out += [f"source: {SOURCE}", "---"]
    return out


def build_note(info: dict[str, Any], video_id: str, transcript: Sequence[str] | None) -> str:
    """ข้อความโน้ตทั้งไฟล์ (LF ปิดท้ายด้วย LF)

    transcript = บรรทัดจาก srt_builder.md_sections(level=3) หรือ None/ว่าง = ไม่มีหัวข้อทรานสคริปต์
    """
    out = _front_matter(info, video_id)
    out += ["", "# " + (md_title(str(info.get("title") or "")) or video_id)]
    description = info.get("description")
    if isinstance(description, str) and description.strip():
        out += ["", "## คำอธิบาย", *_lines(description)]
    chapters = [c for c in info.get("chapters") or [] if isinstance(c, dict)]
    if chapters:
        out += ["", "## Chapter"]
        for chapter in sorted(chapters, key=lambda c: c.get("startS") or 0):
            start_ms = round((chapter.get("startS") or 0) * 1000)
            out.append(f"- [{md_time(start_ms)}] {md_title(str(chapter.get('title') or ''))}".rstrip(" "))
    if transcript:
        out += ["", "## ทรานสคริปต์", *transcript]
    return LF.join(out) + LF
