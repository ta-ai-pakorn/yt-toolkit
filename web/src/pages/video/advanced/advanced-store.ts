import { useSyncExternalStore } from "react"

import { formatDuration } from "@/lib/format"

/**
 * ค่าตัวเลือกขั้นสูงของคลิปที่เปิดอยู่ (M5 รอบ A, D3): ก้อนเดียวในหน่วยความจำ ใช้ร่วมกันทุกแท็บ ตัวเล่น และเมนูภาพเฟรม
 * เปิดคลิปอื่นหรือโหลดหน้าใหม่ = เริ่มใหม่ · ส่งงานเข้าคิวแล้วค่ายังอยู่ (โหลดอีกแบบของช่วงเดิมได้)
 * หมวด SponsorBlock ไม่อยู่ที่นี่ (จำข้ามคลิปในการตั้งค่า sponsorblockDefault)
 */
export type AdvancedValues = {
  /** ข้อความในช่อง "เริ่ม" / "จบ" ตามที่พิมพ์ (ตรวจด้วย validateRange) */
  startText: string
  endText: string
  splitChapters: boolean
  /** สวิตช์ "ตัดโฆษณา (SponsorBlock)" เริ่มปิดทุกคลิป */
  sponsorblock: boolean
  /** ส่วน "ตัวเลือกขั้นสูง" กางอยู่ (กดตั้งจุดจากตัวเล่นแล้วกางให้เอง) */
  open: boolean
  /** แสดง error ของช่องเวลาแล้ว (ออกจากช่อง กดตั้งจุด หรือกดโหลด) */
  checked: boolean
}

export const EMPTY_ADVANCED: AdvancedValues = Object.freeze({
  startText: "",
  endText: "",
  splitChapters: false,
  sponsorblock: false,
  open: false,
  checked: false,
})

let held: { videoId: string | null; values: AdvancedValues } = { videoId: null, values: EMPTY_ADVANCED }
const listeners = new Set<() => void>()

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** ค่าของคลิปนี้ (คลิปอื่น = ค่าว่างก้อนเดิมเสมอ) */
export function getAdvanced(videoId: string): AdvancedValues {
  return held.videoId === videoId ? held.values : EMPTY_ADVANCED
}

/** มีตัวเลือกขั้นสูงที่ใช้อยู่ (ป้าย "ใช้ตัวเลือกขั้นสูงอยู่" ทุกแท็บ) */
export function advancedActive(v: AdvancedValues): boolean {
  return v.startText.trim() !== "" || v.endText.trim() !== "" || v.splitChapters || v.sponsorblock
}

export const advancedActions = {
  /** แก้ค่าของคลิปนี้ (คลิปอื่นที่ค้างอยู่ถูกล้าง) */
  patch(videoId: string, patch: Partial<AdvancedValues>): void {
    held = { videoId, values: { ...getAdvanced(videoId), ...patch } }
    for (const listener of listeners) listener()
  },
  /** "ตั้งจุดเริ่ม/จบ" จากตัวเล่นหรือภาพเฟรม: เวลาปัดลงเป็นวินาที · แยก chapter เปิดอยู่ = "blocked" ไม่เปลี่ยนค่า */
  mark(videoId: string, which: "start" | "end", ms: number): "set" | "blocked" {
    if (getAdvanced(videoId).splitChapters) return "blocked"
    const text = formatDuration(Math.floor(Math.max(0, ms) / 1000))
    advancedActions.patch(videoId, {
      ...(which === "start" ? { startText: text } : { endText: text }),
      open: true,
      checked: true,
    })
    return "set"
  },
}

/** ค่าของคลิปนี้แบบ reactive (เรนเดอร์ใหม่เมื่อค่าของคลิปนี้เปลี่ยน) */
export function useAdvanced(videoId: string): AdvancedValues {
  return useSyncExternalStore(
    subscribe,
    () => getAdvanced(videoId),
    () => getAdvanced(videoId),
  )
}

/** ทดสอบเท่านั้น */
export function __resetAdvancedForTests(): void {
  held = { videoId: null, values: EMPTY_ADVANCED }
  for (const listener of listeners) listener()
}
