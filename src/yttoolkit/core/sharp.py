"""ภาพคม (M5 รอบ B spec 3.2): แผนเวลาของภาพ เป็นฟังก์ชันล้วน

ฝั่งเว็บมีชุดเดียวกันใน web/src/lib/sharp-frames.ts และทั้งสองฝั่งอ่านเคสใน tests/fixtures/sharp/plan-cases.json
ความยาวคลิปใช้ durationS ของ VideoInfo (วินาทีเต็ม) เหมือนหน้าเว็บ จำนวนภาพที่ dialog บอกจึงตรงกับงานจริง
เวลาของ "เวลาเดียวกับภาพเร็ว" คิดจากข้อมูลคลิปที่เก็บไว้ (storyboard.plan_frames) ไม่ต้องโหลดแผ่น storyboard
core/ ไม่ import api/ หรือ platform/
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .storyboard import pick_storyboard, plan_frames

MAX_SHARP_FRAMES = 200  # AC-FRAME-04: ดึงได้ไม่เกิน 200 ภาพต่อครั้ง
MAX_INTERVAL_S = 3600  # ช่อง "ตั้งเอง ทุก N วินาที" รับ 1-3600


@dataclass(frozen=True)
class SharpPlan:
    times_ms: tuple[int, ...]
    interval_s: int | None  # None = เวลาเดียวกับภาพเร็ว
    raised: bool  # ปรับช่วงห่างขึ้นให้ไม่เกิน 200 ภาพ (โน้ต SHARP_INTERVAL_RAISED)


def _ceil_div(a: int, b: int) -> int:
    return -(-a // b)


def default_interval_s(duration_s: int) -> int:
    """ช่วงห่างเริ่มต้นเมื่อคลิปไม่มี storyboard: ราว 100 ภาพต่อคลิป อย่างน้อยทุก 1 วินาที"""
    return max(1, _ceil_div(duration_s, 100))


def raised_interval_s(duration_s: int) -> int:
    """ช่วงห่างที่รับประกันว่าไม่เกิน 200 ภาพ"""
    return _ceil_div(duration_s, MAX_SHARP_FRAMES)


def custom_times(interval_s: int, duration_s: int) -> list[int]:
    """t_i = i × N × 1000 ms ตราบที่ยังน้อยกว่าความยาวคลิป"""
    return list(range(0, duration_s * 1000, interval_s * 1000))


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _raised(duration_s: int) -> SharpPlan:
    n2 = raised_interval_s(duration_s)
    return SharpPlan(tuple(custom_times(n2, duration_s)), n2, True)


def plan_sharp(duration_s: int, *, interval_s: int | None, fast_times: Sequence[int] | None) -> SharpPlan:
    """เวลาของภาพคมตาม spec 3.2 (ValueError = ค่าที่ API ควรกันไว้แล้ว ผู้เรียกแปลงเป็น error ของงาน)"""
    if not _is_int(duration_s) or duration_s <= 0:
        raise ValueError(f"duration_s must be a positive int: {duration_s!r}")
    if interval_s is not None and (not _is_int(interval_s) or not 1 <= interval_s <= MAX_INTERVAL_S):
        raise ValueError(f"interval_s must be 1..{MAX_INTERVAL_S}: {interval_s!r}")
    if interval_s is None and fast_times is not None:
        times = tuple(int(t) for t in fast_times)
        if not times:
            raise ValueError("fast_times is empty")
        return SharpPlan(times, None, False) if len(times) <= MAX_SHARP_FRAMES else _raised(duration_s)
    if interval_s is None:
        n = default_interval_s(duration_s)
        return SharpPlan(tuple(custom_times(n, duration_s)), n, False)
    if _ceil_div(duration_s, interval_s) > MAX_SHARP_FRAMES:
        return _raised(duration_s)
    return SharpPlan(tuple(custom_times(interval_s, duration_s)), interval_s, False)


def fast_times(raw: Mapping[str, Any]) -> list[int] | None:
    """เวลาของภาพเร็ว (เท่ากับ tMs ใน index.json ของ storyboard ทุกตัว) จากข้อมูลคลิปที่ตัดแล้ว ไม่มี storyboard = None"""
    sb = pick_storyboard(dict(raw))
    if sb is None:
        return None
    times = [spec.t_ms for spec in plan_frames(sb, raw.get("duration"))]
    return times or None
