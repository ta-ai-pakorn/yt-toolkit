"""ประกอบภาพเฟรมเป็นของที่ผู้ใช้โหลดได้: contact sheet (JPEG) และ zip (PRD FR-FRAME, AC-FRAME-05/06)

รับ `list[tuple[int, Path]]` = (เวลาเป็น ms, ไฟล์ภาพเฟรม) ตามลำดับที่จะแสดง
ตัวอักษรใช้ IBM Plex Sans Thai ที่แถมมากับแพ็กเกจ (assets/fonts) อ่านจากตำแหน่งแพ็กเกจเสมอ
ไม่ขึ้นกับโฟลเดอร์ที่รันโปรแกรม

ไม่ import api/platform (PRD 6.6)
"""

from __future__ import annotations

import io
import logging
import re
import unicodedata
import zipfile
from functools import cache
from importlib import resources
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps, features

log = logging.getLogger("yttoolkit")

Frames = list[tuple[int, Path]]

CELL_W, CELL_H = 320, 180
GUTTER = 8
HEADER_H = 88
TEXT_MARGIN = 16
JPEG_QUALITY = 88
# ยาวเกินนี้จะสุ่มเลือกแบบห่างเท่า ๆ กัน: 400 เฟรม = 80 แถว สูงราว 15k px ยังเปิดในเบราว์เซอร์ได้
MAX_SHEET_FRAMES = 400

BACKGROUND = (0x0E, 0x0F, 0x11)
TEXT = (0xEC, 0xEC, 0xEE)
BADGE_FILL = (0, 0, 0, 166)  # rgba(0,0,0,.65)
BADGE_TEXT = (255, 255, 255)
_BADGE_SIZE = 14
_BADGE_PAD_X, _BADGE_H, _BADGE_INSET = 6, 22, 4

_FONT_FILES = {
    "regular": "IBMPlexSansThai-Regular.ttf",
    "semibold": "IBMPlexSansThai-SemiBold.ttf",
}
_ELLIPSIS = "…"
_ZIP_DATE = (1980, 1, 1, 0, 0, 0)
_SPACES = re.compile(r"\s+")
# สระนำ: ห้ามทิ้งท้ายชื่อที่ตัดไว้ตามลำพัง เช่น "เ…"
_LEADING_VOWELS = "เแโใไ"


def timecode(ms: int) -> str:
    """HH:MM:SS ปัดเศษลง ชั่วโมงแสดงเสมอ (0 ms = 00:00:00)"""
    total = max(0, int(ms)) // 1000
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def file_timecode(ms: int) -> str:
    """เหมือน timecode แต่ใช้ขีดแทนโคลอน เพื่อเป็นชื่อไฟล์บน Windows ได้"""
    return timecode(ms).replace(":", "-")


@cache
def _layout_engine() -> ImageFont.Layout:
    # raqm จัดวางสระ/วรรณยุกต์ไทยได้ถูกต้องกว่า ถ้าเครื่องไม่มี (Pillow บน Windows มักไม่แถมมา)
    # ก็ใช้ BASIC แทน บันทึกผลไว้ครั้งเดียวเพื่อให้ตรวจย้อนหลังได้
    if features.check("raqm"):
        log.info("contact sheet: ใช้ layout engine raqm")
        return ImageFont.Layout.RAQM
    log.info("contact sheet: ไม่มี raqm ใช้ layout engine BASIC แทน")
    return ImageFont.Layout.BASIC


@cache
def load_font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    """โหลดฟอนต์ที่แถมมากับแพ็กเกจ (weight = "regular" | "semibold") ครั้งเดียวต่อขนาด"""
    name = _FONT_FILES[weight]
    path = Path(str(resources.files("yttoolkit") / "assets" / "fonts" / name))
    return ImageFont.truetype(str(path), size, layout_engine=_layout_engine())


def fit_text(font: ImageFont.FreeTypeFont, text: str, max_width: float) -> str:
    """ตัดข้อความให้ไม่กว้างเกิน max_width แล้วต่อ "…" ไม่ตัดกลางกลุ่มพยัญชนะ+สระ/วรรณยุกต์"""
    text = _SPACES.sub(" ", text).strip()
    if font.getlength(text) <= max_width:
        return text
    low, high = 0, len(text)  # หาจำนวนตัวอักษรมากสุดที่ยังพอดีเมื่อต่อ "…"
    while low < high:
        mid = (low + high + 1) // 2
        if font.getlength(text[:mid].rstrip() + _ELLIPSIS) <= max_width:
            low = mid
        else:
            high = mid - 1
    keep = low
    # ตัวถัดไปเป็นสระบน/ล่าง/วรรณยุกต์ = ติดกับตัวที่เก็บไว้ ต้องถอยทั้งกลุ่ม
    while 0 < keep < len(text) and unicodedata.category(text[keep]) == "Mn":
        keep -= 1
    while keep > 0 and text[keep - 1] in _LEADING_VOWELS:
        keep -= 1
    return text[:keep].rstrip() + _ELLIPSIS


def summary_line(duration_s: int, shown: int, total: int) -> str:
    count = f"{shown} เฟรม" if shown == total else f"แสดง {shown} จาก {total} เฟรม"
    return f"ความยาว {timecode(int(duration_s) * 1000)} · {count}"


def sample_frames(frames: Frames, limit: int = MAX_SHEET_FRAMES) -> Frames:
    """เกิน limit เลือกให้ห่างเท่า ๆ กัน เก็บเฟรมแรกและเฟรมสุดท้ายไว้เสมอ"""
    total = len(frames)
    if total <= limit:
        return list(frames)
    step = (total - 1) / (limit - 1)
    return [frames[round(i * step)] for i in range(limit)]


def _load_cell(path: Path) -> Image.Image:
    with Image.open(path) as source:
        image = source.convert("RGB")
    if image.size != (CELL_W, CELL_H):
        image = ImageOps.pad(image, (CELL_W, CELL_H), color=(0, 0, 0))
    return image


def _draw_badge(draw: ImageDraw.ImageDraw, left: int, top: int, label: str) -> None:
    font = load_font("regular", _BADGE_SIZE)
    width = round(font.getlength(label)) + 2 * _BADGE_PAD_X
    right = left + CELL_W - _BADGE_INSET
    bottom = top + CELL_H - _BADGE_INSET
    box = (right - width, bottom - _BADGE_H, right, bottom)
    draw.rounded_rectangle(box, radius=4, fill=BADGE_FILL)
    draw.text(
        ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2),
        label,
        font=font,
        fill=BADGE_TEXT,
        anchor="mm",
    )


def contact_sheet(
    frames: Frames, title: str, duration_s: int, columns: int = 5
) -> bytes:
    """ภาพรวมทุกเฟรมในไฟล์ JPEG เดียว: หัวภาพ (ชื่อคลิป + ความยาว + จำนวนเฟรม) แล้วตามด้วยกริด

    เกิน MAX_SHEET_FRAMES เฟรมจะสุ่มเลือกห่างเท่า ๆ กันและบอกไว้ที่หัวภาพ
    """
    if not frames:
        raise ValueError("ไม่มีเฟรมให้ทำ contact sheet")
    if columns < 1:
        raise ValueError("columns ต้องมากกว่า 0")
    total = len(frames)
    shown = sample_frames(frames)
    rows = -(-len(shown) // columns)
    width = columns * CELL_W + (columns + 1) * GUTTER
    height = HEADER_H + rows * (CELL_H + GUTTER) + GUTTER
    sheet = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(sheet, "RGBA")  # โหมด RGBA = สีโปร่งของป้ายผสมกับภาพเฟรมจริง

    title_font = load_font("semibold", 28)
    draw.text(
        (TEXT_MARGIN, 44),
        fit_text(title_font, title, width - 2 * TEXT_MARGIN),
        font=title_font,
        fill=TEXT,
        anchor="ls",
    )
    draw.text(
        (TEXT_MARGIN, 74),
        summary_line(duration_s, len(shown), total),
        font=load_font("regular", 18),
        fill=TEXT,
        anchor="ls",
    )

    for position, (t_ms, path) in enumerate(shown):
        row, col = divmod(position, columns)
        left = GUTTER + col * (CELL_W + GUTTER)
        top = HEADER_H + GUTTER + row * (CELL_H + GUTTER)
        sheet.paste(_load_cell(path), (left, top))
        _draw_badge(draw, left, top, timecode(t_ms))

    out = io.BytesIO()
    sheet.save(out, "JPEG", quality=JPEG_QUALITY)
    return out.getvalue()


def frames_zip(frames: Frames) -> bytes:
    """zip แบบไม่บีบอัด (JPEG บีบซ้ำไม่ได้ประโยชน์) ชื่อ frame_HH-MM-SS.jpg ตามลำดับเฟรม

    ชื่อซ้ำ (หลายเฟรมอยู่ในวินาทีเดียวกัน) ต่อท้าย _2, _3 วันที่ในไฟล์ตายตัว
    จึงได้ไบต์เหมือนเดิมทุกครั้งที่ทำจากเฟรมชุดเดิม
    """
    if not frames:
        raise ValueError("ไม่มีเฟรมให้ใส่ zip")
    seen: dict[str, int] = {}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as archive:
        for t_ms, path in frames:
            stem = f"frame_{file_timecode(t_ms)}"
            seen[stem] = seen.get(stem, 0) + 1
            name = f"{stem}.jpg" if seen[stem] == 1 else f"{stem}_{seen[stem]}.jpg"
            info = zipfile.ZipInfo(name, date_time=_ZIP_DATE)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            archive.writestr(info, Path(path).read_bytes())
    return out.getvalue()
