import { fill, th } from "@/i18n/th"
import { formatDuration, formatTimecode } from "@/lib/format"

/** ส่วนที่คิดล้วน ๆ ของการถ่ายภาพคมตรงจุด (M5 รอบ B2) เทสได้ใน node */

/** ปุ่มถ่ายภาพปัดเวลาของตัวเล่นทีละ 100 ms (spec 2.1) */
export const CAPTURE_STEP_MS = 100

/**
 * เวลาที่ส่งไปถ่าย: ปัดทีละ 100 ms ไม่ติดลบ · รู้ความยาวคลิป (durationS > 0) = ไม่เกิน 100 ms ก่อนจบ
 * (ดูจนจบคลิปแล้วกดถ่าย เวลาของตัวเล่นเท่ากับความยาวคลิปพอดี ซึ่งไม่มีภาพ)
 */
export function captureTimeMs(ms: number, durationS?: number | null): number {
  const safe = Number.isFinite(ms) ? Math.max(0, ms) : 0
  const rounded = Math.round(safe / CAPTURE_STEP_MS) * CAPTURE_STEP_MS
  if (durationS == null || !Number.isFinite(durationS) || durationS <= 0) return rounded
  return Math.min(rounded, Math.max(0, Math.floor(durationS * 1000) - CAPTURE_STEP_MS))
}

/** เวลาของภาพที่ถ่าย "2:05" หรือ "2:05.4": ละเอียดถึง 0.1 วินาที สองภาพในวินาทีเดียวกันจึงอ่านต่างกัน */
export function captureClock(ms: number): string {
  const safe = Math.max(0, Math.round(Number.isFinite(ms) ? ms : 0))
  const whole = formatDuration(Math.floor(safe / 1000))
  const tenth = Math.floor((safe % 1000) / 100)
  return tenth === 0 ? whole : `${whole}.${tenth}`
}

/** เวลาแบบนาฬิกา HH:MM ของเครื่อง (คิวพักถึงกี่โมง) อ่านไม่ได้ = "" */
export function clockTime(iso: string): string {
  const at = new Date(iso)
  if (Number.isNaN(at.getTime())) return ""
  return `${String(at.getHours()).padStart(2, "0")}:${String(at.getMinutes()).padStart(2, "0")}`
}

/** เหตุที่ถ่ายไม่ได้ตอนนี้: คลิปสด · คิวพักเพราะยูทูปขอตรวจสอบ (pausedUntil ยังไม่ถึง) · null = ถ่ายได้ */
export type CaptureBlock = { kind: "live" } | { kind: "paused"; until: string } | null

export function captureBlock(o: { isLive: boolean; pausedUntil: string | null; now: number }): CaptureBlock {
  if (o.isLive) return { kind: "live" }
  if (o.pausedUntil) {
    const until = Date.parse(o.pausedUntil)
    if (!Number.isNaN(until) && until > o.now) return { kind: "paused", until: o.pausedUntil }
  }
  return null
}

export function blockTooltip(block: CaptureBlock): string | null {
  if (block === null) return null
  if (block.kind === "live") return th.capture.liveDisabled
  return fill(th.capture.pausedDisabled, { time: clockTime(block.until) })
}

/** ปุ่มในแถบภาพที่ถ่ายไว้ (จุดหยุด Tab เดียว เลื่อนด้วยลูกศร): ตำแหน่งใหม่ · null = ไม่ใช่ปุ่มของแถบ */
export function stripKeyTarget(key: string, index: number, count: number): number | null {
  if (count <= 0) return null
  switch (key) {
    case "ArrowRight":
    case "ArrowDown":
      return Math.min(count - 1, index + 1)
    case "ArrowLeft":
    case "ArrowUp":
      return Math.max(0, index - 1)
    case "Home":
      return 0
    case "End":
      return count - 1
    default:
      return null
  }
}

/** ลบภาพแล้วโฟกัสภาพไหนต่อ: ภาพถัดไป ไม่มีก็ภาพก่อนหน้า · ไม่เหลือภาพ = null */
export function focusAfterDelete(ids: readonly string[], removed: string): string | null {
  const at = ids.indexOf(removed)
  if (at < 0) return ids[0] ?? null
  return ids[at + 1] ?? ids[at - 1] ?? null
}

/** url สำหรับโหลดภาพ (?v= มีอยู่แล้ว ต่อ &download=1) */
export function captureDownloadUrl(url: string): string {
  return `${url}${url.includes("?") ? "&" : "?"}download=1`
}

/** ชื่อไฟล์สำรองตอนโหลด frame_HH-MM-SS.jpg (แบบเดียวกับไฟล์ในโฟลเดอร์) */
export function captureFileName(ms: number): string {
  return `frame_${formatTimecode(ms).replaceAll(":", "-")}.jpg`
}

/**
 * เลื่อนแถวภาพ (แนวนอน) ให้เห็นภาพที่เพิ่งถ่าย โดยไม่เลื่อนทั้งหน้า: คืนค่า scrollLeft ใหม่ของแถว
 * item/view = ตำแหน่งซ้ายและความกว้างในพิกัดเนื้อหาของแถว (ภาพ) และพื้นที่ที่มองเห็นอยู่ (scrollLeft + clientWidth)
 */
export function revealScrollLeft(o: { itemLeft: number; itemWidth: number; viewLeft: number; viewWidth: number }): number {
  if (o.itemLeft < o.viewLeft) return Math.max(0, o.itemLeft)
  const overflow = o.itemLeft + o.itemWidth - (o.viewLeft + o.viewWidth)
  return overflow > 0 ? o.viewLeft + overflow : o.viewLeft
}
