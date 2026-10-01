import type { Cue, StoryboardFrame } from "@/lib/types"

import { nearestFrameIndex } from "./frame-target"
import type { PlayerState } from "./player/player-store"

/**
 * ตัวช่วยของ M3.5 ส่วน "ภาพเฟรม/ทรานสคริปต์ตามการเล่น" (ไม่รู้จัก React ทดสอบได้ด้วย vitest)
 * ใช้กับ usePlayerValue(selector): selector ต้องถูกและคืนค่า primitive ภาพ/บรรทัดเรนเดอร์ใหม่เฉพาะตอนค่าที่เลือกเปลี่ยน
 */

/** ตัวเล่นมีตำแหน่งที่ควรแสดงไหม: กำลังเล่นหรือหยุดชั่วคราว (ยังไม่เริ่ม กำลังโหลด จบแล้ว หรือผิดพลาด = ไม่มีภาพ/บรรทัดที่กำลังเล่น) */
export function hasPlayhead(state: Pick<PlayerState, "status">): boolean {
  return state.status === "playing" || state.status === "paused"
}

// ภาพเฟรมเป็นร้อยภาพ ต่างคนต่างถามว่า "ฉันใช่ภาพที่กำลังเล่นไหม" ทุกครั้งที่เวลาเดิน: คิดภาพที่ใกล้ที่สุดครั้งเดียวต่อ (ชุดภาพ, เวลา)
let cachedFrames: readonly StoryboardFrame[] | null = null
let cachedMs = Number.NaN
let cachedIndex = -1

/** ตำแหน่ง (ใน frames) ของภาพที่ใกล้ currentMs ที่สุด · ไม่มีตำแหน่งที่ควรแสดง = -1 */
export function nowPlayingFrame(frames: readonly StoryboardFrame[], state: Pick<PlayerState, "status" | "currentMs">): number {
  if (!hasPlayhead(state)) return -1
  if (frames !== cachedFrames || state.currentMs !== cachedMs) {
    cachedFrames = frames
    cachedMs = state.currentMs
    cachedIndex = nearestFrameIndex(frames, state.currentMs)
  }
  return cachedIndex
}

/**
 * บรรทัดที่ช่วงเวลา [startMs, endMs) ครอบ ms (ค้นแบบแบ่งครึ่ง บรรทัดเรียงตามเวลาเริ่ม)
 * อยู่ในช่องว่างระหว่างบรรทัด ก่อนบรรทัดแรก หรือหลังบรรทัดสุดท้าย = -1 · บรรทัดซ้อนกัน = บรรทัดที่เริ่มทีหลัง
 */
export function lineAt(cues: readonly Pick<Cue, "startMs" | "endMs">[], ms: number): number {
  let low = 0
  let high = cues.length - 1
  let found = -1
  // บรรทัดสุดท้ายที่เริ่มก่อนหรือตรง ms
  while (low <= high) {
    const mid = (low + high) >> 1
    if (cues[mid].startMs <= ms) {
      found = mid
      low = mid + 1
    } else high = mid - 1
  }
  return found >= 0 && ms < cues[found].endMs ? found : -1
}

/** บรรทัดที่กำลังเล่น · ไม่มีตำแหน่งที่ควรแสดง = -1 */
export function nowPlayingLine(cues: readonly Cue[], state: Pick<PlayerState, "status" | "currentMs">): number {
  return hasPlayhead(state) ? lineAt(cues, state.currentMs) : -1
}
