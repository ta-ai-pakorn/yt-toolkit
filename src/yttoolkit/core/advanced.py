"""ตัวเลือกขั้นสูงของงานโหลด (M5 รอบ A): ช่วงที่เก็บไว้หลังตัดช่วงเวลา/โฆษณา ช่วงของ chapter และส่วนต่อท้ายชื่อไฟล์

ฟังก์ชันล้วน เวลาเป็นมิลลิวินาทีบนเส้นเวลาของคลิปต้นฉบับ core/handlers.py เรียกใช้ ไม่แตะไฟล์ ไม่เรียก ffmpeg
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

Interval = tuple[int, int]
MIN_PIECE_MS = 1000  # ชิ้นที่เหลือหลังตัดโฆษณาสั้นกว่านี้ทิ้งไป (spec 3.2)
ADS_SUFFIX = " (ตัดโฆษณา)"
_HOUR_MS = 3_600_000


def _clock(ms: int, hours: bool) -> str:
    total = ms // 1000
    h, rest = divmod(total, 3600)
    m, s = divmod(rest, 60)
    return f"{h}.{m:02d}.{s:02d}" if hours else f"{m:02d}.{s:02d}"


def range_suffix(start_ms: int, end_ms: int) -> str:
    """ส่วนต่อท้ายชื่อไฟล์ของช่วงเวลา " (01.30-05.00)" ปลายช่วงถึงชั่วโมงแรก = มีชั่วโมงทั้งสองข้าง " (1.02.30-1.05.00)"
    ใช้ "." แทน ":" เพราะ Windows ห้ามใช้ ":" ในชื่อไฟล์"""
    hours = end_ms >= _HOUR_MS
    return f" ({_clock(start_ms, hours)}-{_clock(end_ms, hours)})"


def merge_intervals(items: Iterable[Interval]) -> list[Interval]:
    """เรียงและรวมช่วงที่ทับหรือชนกัน ช่วงว่าง (end <= start) ถูกทิ้ง"""
    merged: list[list[int]] = []
    for start, end in sorted((s, e) for s, e in items if e > s):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(s, e) for s, e in merged]


def keep_intervals(span: Interval, ads: Iterable[Interval]) -> list[Interval]:
    """span ลบช่วงโฆษณา (ตัดให้อยู่ใน span แล้วรวมกันก่อน) ชิ้นที่เหลือสั้นกว่า 1 วินาทีถูกทิ้ง เรียงตามเวลา"""
    start, end = span
    clipped = [(max(s, start), min(e, end)) for s, e in ads]
    pieces: list[Interval] = []
    cursor = start
    for s, e in merge_intervals(clipped):
        if s > cursor:
            pieces.append((cursor, s))
        cursor = max(cursor, e)
    if end > cursor:
        pieces.append((cursor, end))
    return [(s, e) for s, e in pieces if e - s >= MIN_PIECE_MS]


def kept_ms(intervals: Iterable[Interval]) -> int:
    return sum(e - s for s, e in intervals)


@dataclass(frozen=True)
class ChapterPart:
    index: int  # เริ่มที่ 1
    total: int
    start_ms: int
    end_ms: int
    title: str  # ตัดช่องว่างหัวท้ายแล้ว อาจว่าง (ชื่อไฟล์ใช้ "chapter <n>" แทน)


def _ms(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value) or value < 0:
        return None
    return round(value * 1000)


def chapter_parts(chapters: Sequence[Mapping[str, Any]], duration_ms: int) -> list[ChapterPart]:
    """chapter ของ VideoInfo ({startS, endS, title}) -> ช่วงของแต่ละไฟล์ ปลายไม่เกินความยาวจริงของไฟล์ที่โหลดมา
    chapter ที่อ่านเวลาไม่ได้หรือเหลือยาว 0 ถูกข้าม เหลือไม่ถึง 2 chapter = [] (ตัวทำงานใส่โน้ต NO_CHAPTERS)"""
    spans: list[tuple[int, int, str]] = []
    for chapter in chapters:
        start, end = _ms(chapter.get("startS")), _ms(chapter.get("endS"))
        if start is None or end is None:
            continue
        end = min(end, duration_ms)
        if end > start:
            spans.append((start, end, str(chapter.get("title") or "").strip()))
    if len(spans) < 2:
        return []
    total = len(spans)
    return [ChapterPart(i, total, s, e, t) for i, (s, e, t) in enumerate(spans, start=1)]
