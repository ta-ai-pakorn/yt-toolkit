import type { Cue, ReplaySegment } from "@/lib/types"

/** เวลา ms อยู่ในช่วงที่คนดูซ้ำมากที่สุดช่วงใดช่วงหนึ่งหรือไม่ (นับต้นช่วง ไม่นับปลายช่วง) */
export function inReplayed(ms: number, segments: readonly ReplaySegment[] | undefined): boolean {
  return segments?.some((segment) => ms >= segment.startMs && ms < segment.endMs) ?? false
}

/**
 * บรรทัดซับคาบเกี่ยวกับช่วงที่คนดูซ้ำมากที่สุดหรือไม่
 * บรรทัดที่เริ่มก่อนช่วงแต่พูดต่อเข้าไปในช่วงก็นับ · บรรทัดที่จบตรงต้นช่วงพอดีไม่นับ
 * บรรทัดที่ยาว 0 ms (เริ่ม = จบ) นับเหมือนจุดเวลาเดียว
 */
export function cueInReplayed(cue: Cue, segments: readonly ReplaySegment[] | undefined): boolean {
  if (cue.endMs <= cue.startMs) return inReplayed(cue.startMs, segments)
  return segments?.some((segment) => cue.startMs < segment.endMs && cue.endMs > segment.startMs) ?? false
}
