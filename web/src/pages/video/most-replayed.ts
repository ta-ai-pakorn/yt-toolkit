import type { Cue, ReplaySegment, StoryboardFrame } from "@/lib/types"

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

/**
 * ภาพเฟรมของช่วงหนึ่ง (review M-2): ภาพแรกที่อยู่ในช่วง · ไม่มีภาพไหนอยู่ในช่วงเลย (ช่วงสั้นกว่าระยะห่างของภาพ)
 * = ภาพที่ใกล้กลางช่วงที่สุด (ห่างเท่ากันเลือกภาพที่มาก่อน) · ไม่มีภาพเลย = -1
 */
export function segmentFrameIndex(frames: readonly StoryboardFrame[], segment: ReplaySegment): number {
  const inside = frames.findIndex((frame) => frame.tMs >= segment.startMs && frame.tMs < segment.endMs)
  if (inside >= 0) return inside
  const middle = (segment.startMs + segment.endMs) / 2
  let best = -1
  let bestDistance = Infinity
  frames.forEach((frame, index) => {
    const distance = Math.abs(frame.tMs - middle)
    if (distance < bestDistance) {
      best = index
      bestDistance = distance
    }
  })
  return best
}

/**
 * ภาพเฟรมที่มีป้าย "ดูซ้ำบ่อย": ทุกภาพที่อยู่ในช่วง + ภาพแทนของช่วงที่ไม่มีภาพอยู่ข้างในเลย
 * (ปุ่มเวลาของช่วงนั้นพาไปภาพที่มีป้ายเสมอ)
 */
export function replayedFrames(frames: readonly StoryboardFrame[], segments: readonly ReplaySegment[] | undefined): Set<number> {
  const marked = new Set<number>()
  frames.forEach((frame, index) => {
    if (inReplayed(frame.tMs, segments)) marked.add(index)
  })
  for (const segment of segments ?? []) {
    const index = segmentFrameIndex(frames, segment)
    if (index >= 0) marked.add(index)
  }
  return marked
}

/**
 * ตัวกรอง "ดูซ้ำบ่อย" ของแท็บภาพเฟรม: ตำแหน่ง (ใน frames) ของภาพที่มีป้าย เรียงตามลำดับเดิม
 * ใช้ชุดเดียวกับป้าย ภาพที่เห็นตอนเปิดตัวกรองจึงเป็นภาพที่มีป้ายทุกภาพ · ความยาวของผล = ตัวเลขบนปุ่ม
 */
export function replayedFrameIndexes(
  frames: readonly StoryboardFrame[],
  segments: readonly ReplaySegment[] | undefined,
): number[] {
  return [...replayedFrames(frames, segments)].sort((a, b) => a - b)
}
