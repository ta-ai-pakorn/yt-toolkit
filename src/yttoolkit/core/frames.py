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

from .yterrors import YtError

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
# ข้อความที่ผู้ใช้เห็น (หัว contact sheet และรายละเอียด error)
LABEL_DURATION = "ความยาว"
LABEL_FRAMES = "เฟรม"
LABEL_SAMPLED = "แสดง {shown} จาก {total} เฟรม"
FRAME_FILE_BAD = "ไฟล์เฟรมหายหรือเสีย"
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


def _attached(char: str) -> bool:
    """อักษรที่ต้องติดกับตัวหน้า: สระบน/ล่าง/วรรณยุกต์ (Mn) และ ำ (Lo แต่เป็นสระตามหลัง)"""
    return unicodedata.category(char) == "Mn" or char == _SARA_AM


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
    while 0 < keep < len(text) and _attached(text[keep]):
        keep -= 1
    while keep > 0 and text[keep - 1] in _LEADING_VOWELS:
        keep -= 1
    return text[:keep].rstrip() + _ELLIPSIS


# ---------- วางสระ/วรรณยุกต์ไทยเองเมื่อไม่มี raqm ----------
# layout แบบ BASIC ของ Pillow วางเครื่องหมายทุกตัวที่ตำแหน่งตั้งต้นของฟอนต์ ไม่รู้ว่าตัวหน้าเป็นสระบนหรือ
# พยัญชนะหัวสูง จึงซ้อนทับกัน (ที่ = วรรณยุกต์จมอยู่ใต้ ี) ฟังก์ชันด้านล่างวาดทีละกลุ่มอักษร (พยัญชนะ + เครื่องหมาย)
# แล้วขยับเครื่องหมายเองโดยวัดจากหมึกของอักษรจริงในฟอนต์ ไม่ใช้เลขพิกเซลตายตัว
_UPPER_VOWELS = "ัิีึื็"  # ั ิ ี ึ ื ็
_NIKHAHIT = "ํ"  # ํ
_SARA_AM = "ำ"  # ำ = ํ + า
_SARA_AA = "า"
_TONES = "่้๊๋์"  # ่ ้ ๊ ๋ และการันต์ ์
_LOWER_VOWELS = "ฺุู"  # ุ ู ฺ
_ASCENDERS = "ปฝฟฬ"
# ฎ ฏ หางยาวลงใต้เส้นบรรทัด สระล่างต้องลงต่ำกว่าหาง ส่วน ญ ฐ ปล่อยตำแหน่งตั้งต้น: ฟอนต์มีรูปหางสั้น
# สำหรับสองตัวนี้แต่ต้องใช้ GSUB ซึ่ง BASIC เรียกไม่ได้
_DESCENDERS = "ฎฏ"
_PLAIN_TOP = "ก"  # พยัญชนะไม่มีหัวสูง ใช้เป็นเส้นแบ่งเขตหัว


def _marks_needed(text: str) -> bool:
    return any(_attached(c) for c in text)


@cache
def _ink(font: ImageFont.FreeTypeFont, char: str) -> tuple[int, int, int, int] | None:
    """กรอบหมึกจริง (ซ้าย, บน, ขวา, ล่าง) ของอักษร เทียบจุดวาง (x) และเส้นบรรทัด (y) ค่า y ติดลบ = เหนือเส้น"""
    pad = font.size * 3
    image = Image.new("L", (pad * 2, pad * 2), 0)
    ImageDraw.Draw(image).text((pad, pad), char, font=font, fill=255, anchor="ls")
    box = image.getbbox()
    if box is None:
        return None
    return (box[0] - pad, box[1] - pad, box[2] - pad, box[3] - pad)


@cache
def _ascender_left(font: ImageFont.FreeTypeFont, char: str) -> int | None:
    """ขอบซ้ายของส่วนหัวสูง (ส่วนที่โผล่เหนือพยัญชนะทั่วไป) ของพยัญชนะ ป ฝ ฟ ฬ"""
    plain, ink = _ink(font, _PLAIN_TOP), _ink(font, char)
    if plain is None or ink is None or ink[1] >= plain[1]:
        return None
    pad = font.size * 3
    image = Image.new("L", (pad * 2, pad * 2), 0)
    ImageDraw.Draw(image).text((pad, pad), char, font=font, fill=255, anchor="ls")
    head = image.crop((0, 0, pad * 2, pad + plain[1])).getbbox()
    return None if head is None else head[0] - pad


def _gap(ink: tuple[int, int, int, int]) -> int:
    return max(1, round((ink[3] - ink[1]) * 0.15))


def _placements(
    font: ImageFont.FreeTypeFont, base: str, marks: str
) -> list[tuple[str, float, int]]:
    """[(อักษร, x เทียบต้นกลุ่ม, ขยับ y)] ของเครื่องหมายแต่ละตัว: ำ แตกเป็น ํ ตามด้วย า ที่ท้ายกลุ่ม"""
    base_adv = font.getlength(base)
    base_ink = _ink(font, base)
    asc_left = _ascender_left(font, base) if base in _ASCENDERS else None
    placed: list[tuple[str, float, int]] = []
    stack_top: int | None = None  # ขอบบนสุดของสระบน/นิคหิตที่วางไปแล้ว
    stack_dx = 0.0
    # วรรณยุกต์ต้องคิดหลังสระบน/นิคหิต แม้ในตัวหนังสือจะเขียนก่อน ำ (น้ำ = น ้ ำ)
    ordered = sorted(marks.replace(_SARA_AM, _NIKHAHIT), key=lambda m: m in _TONES)
    for mark in ordered:
        ink = _ink(font, mark)
        dx, dy = 0.0, 0
        if ink is not None:
            # หัวสูง: ดันเครื่องหมายซ้ายให้ขอบขวาห่างขอบซ้ายของหัว
            left_shift = (
                max(0, base_adv + ink[2] - asc_left + _gap(ink))
                if asc_left is not None and mark not in _LOWER_VOWELS
                else 0
            )
            if mark in _UPPER_VOWELS or mark == _NIKHAHIT:
                dx = -left_shift
                stack_top, stack_dx = ink[1], dx
            elif mark in _TONES:
                if stack_top is not None:
                    dx = stack_dx
                    dy = min(0, stack_top - _gap(ink) - ink[3])
                    stack_top = ink[1] + dy
                else:
                    dx = -left_shift
            elif mark in _LOWER_VOWELS and base in _DESCENDERS and base_ink:
                dy = max(0, base_ink[3] - ink[1] + _gap(ink))
        placed.append((mark, base_adv + dx, dy))
    return placed


def draw_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, ...],
) -> None:
    """เหมือน draw.text(..., anchor="ls") แต่วางสระ/วรรณยุกต์ไทยให้ถูกเมื่อ Pillow ไม่มี raqm

    มี raqm = ปล่อยให้ Pillow จัดวางเอง ข้อความที่ไม่มีเครื่องหมายไทยก็วาดตามปกติทั้งบรรทัด
    """
    x, y = xy
    if _layout_engine() == ImageFont.Layout.RAQM or not _marks_needed(text):
        draw.text((x, y), text, font=font, fill=fill, anchor="ls")
        return
    run = ""  # ตัวอักษรธรรมดาที่รอวาดรวดเดียว
    i = 0
    while i < len(text):
        j = i + 1
        while j < len(text) and (_attached(text[j])):
            j += 1
        base, marks = text[i], text[i + 1 : j]
        i = j
        if not marks or unicodedata.category(base) == "Mn":
            run += base + marks
            continue
        if run:
            draw.text((x, y), run, font=font, fill=fill, anchor="ls")
            x += font.getlength(run)
            run = ""
        for mark, dx, dy in _placements(font, base, marks):
            draw.text((x + dx, y + dy), mark, font=font, fill=fill, anchor="ls")
        draw.text((x, y), base, font=font, fill=fill, anchor="ls")
        x += font.getlength(base)
        if _SARA_AM in marks:
            draw.text((x, y), _SARA_AA, font=font, fill=fill, anchor="ls")
            x += font.getlength(_SARA_AA)
    if run:
        draw.text((x, y), run, font=font, fill=fill, anchor="ls")


def summary_line(duration_s: int, shown: int, total: int) -> str:
    count = (
        f"{shown} {LABEL_FRAMES}"
        if shown == total
        else LABEL_SAMPLED.format(shown=shown, total=total)
    )
    return f"{LABEL_DURATION} {timecode(int(duration_s) * 1000)} · {count}"


def sample_frames(frames: Frames, limit: int = MAX_SHEET_FRAMES) -> Frames:
    """เกิน limit เลือกให้ห่างเท่า ๆ กัน เก็บเฟรมแรกและเฟรมสุดท้ายไว้เสมอ"""
    total = len(frames)
    if total <= limit:
        return list(frames)
    step = (total - 1) / (limit - 1)
    return [frames[round(i * step)] for i in range(limit)]


def _missing(path: Path, exc: Exception) -> YtError:
    # ไฟล์เฟรมหาย/เสียหมายถึง cache ของ storyboard ไม่ครบ ให้ผู้เรียกสร้างใหม่ได้
    return YtError(
        "E_NO_STORYBOARD",
        f"{FRAME_FILE_BAD} ({type(exc).__name__}): {path}",
    )


def _load_cell(path: Path) -> Image.Image:
    try:
        with Image.open(path) as source:
            image = source.convert("RGB")
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        raise _missing(Path(path), exc) from exc
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
    draw_text(
        draw,
        (TEXT_MARGIN, 44),
        fit_text(title_font, title, width - 2 * TEXT_MARGIN),
        title_font,
        TEXT,
    )
    draw_text(
        draw,
        (TEXT_MARGIN, 74),
        summary_line(duration_s, len(shown), total),
        load_font("regular", 18),
        TEXT,
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
            try:
                data = Path(path).read_bytes()
            except OSError as exc:
                raise _missing(Path(path), exc) from exc
            archive.writestr(info, data)
    return out.getvalue()
