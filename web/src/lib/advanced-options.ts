import { formatDuration } from "./format"
import type { VideoInfo } from "./types"

/** ช่วงเวลาที่ผู้ใช้ตั้ง (มิลลิวินาที เต็มวินาที) รูปร่างเดียวกับ TimeRange ของงาน */
export type ClipRange = { startMs: number; endMs: number }

/** เหตุผลที่ช่องเวลาใช้ไม่ได้ (ข้อความอยู่ที่ th.advanced.errors) */
export type RangeError = "format" | "order" | "beyond"

export type RangeCheck = { range: ClipRange | null; startError: RangeError | null; endError: RangeError | null }

const NONE: RangeCheck = { range: null, startError: null, endError: null }

// ss | m:ss | mm:ss | h:mm:ss (วินาทีเต็ม ไม่มีทศนิยม ตัวเลขอารบิกเท่านั้น)
const CLOCK = /^(?:(\d{1,5})|(\d{1,3}):([0-5]\d)|(\d{1,2}):([0-5]\d):([0-5]\d))$/

/** เวลาที่พิมพ์ในช่อง "เริ่ม"/"จบ" เป็นวินาที · รูปแบบผิด = null */
export function parseClock(text: string): number | null {
  const match = CLOCK.exec(text.trim())
  if (!match) return null
  if (match[1] !== undefined) return Number(match[1])
  if (match[2] !== undefined) return Number(match[2]) * 60 + Number(match[3])
  return Number(match[4]) * 3600 + Number(match[5]) * 60 + Number(match[6])
}

/**
 * ตรวจช่องเวลา (spec 1.1): ว่างทั้งคู่ = ไม่มีช่วง · ว่างช่องเดียว = ปลายอีกด้านของคลิป
 * ลำดับ: รูปแบบผิด / เกินความยาวคลิป (ต่อช่อง) แล้วจึงเริ่มต้องก่อนจบ (แสดงที่ช่องเริ่ม)
 */
export function validateRange(startText: string, endText: string, durationS: number): RangeCheck {
  const startBlank = startText.trim() === ""
  const endBlank = endText.trim() === ""
  if (startBlank && endBlank) return NONE
  const start = startBlank ? 0 : parseClock(startText)
  const end = endBlank ? durationS : parseClock(endText)
  const startError: RangeError | null = start === null ? "format" : start > durationS ? "beyond" : null
  const endError: RangeError | null = end === null ? "format" : end > durationS ? "beyond" : null
  if (start === null || end === null || startError !== null || endError !== null) return { range: null, startError, endError }
  if (start >= end) return { range: null, startError: "order", endError: null }
  return { range: { startMs: start * 1000, endMs: end * 1000 }, startError: null, endError: null }
}

/** ตั้งช่วงเวลาได้: ไม่ใช่คลิปสด และรู้ความยาวคลิป */
export function rangeAvailable(video: Pick<VideoInfo, "isLive" | "durationS">): boolean {
  return !video.isLive && video.durationS > 0
}

/** แยกไฟล์ตาม chapter ได้: คลิปมีอย่างน้อย 2 chapter */
export function chaptersAvailable(video: Pick<VideoInfo, "chapters">): boolean {
  return video.chapters.length >= 2
}

/** "1:30-5:00" (เวลาแบบเดียวกับความยาวคลิปในแอพ) ใช้ทั้งป้ายปุ่ม หัวตัวอย่างซับ และแถวคิว */
export function rangeText(range: ClipRange): string {
  return `${formatDuration(range.startMs / 1000)}-${formatDuration(range.endMs / 1000)}`
}

export function keptSeconds(range: ClipRange): number {
  return (range.endMs - range.startMs) / 1000
}

/** ขนาดประมาณตามความยาวที่เหลือหลังตัดช่วง (ไม่รู้ขนาด หรือไม่มีช่วง = ค่าเดิม) */
export function scaleBytes(bytes: number | undefined, durationS: number, keptS: number | undefined): number | undefined {
  if (bytes === undefined || keptS === undefined || durationS <= 0) return bytes
  return Math.round((bytes * Math.min(keptS, durationS)) / durationS)
}

export type ChoicePart = { kind: "range"; range: ClipRange } | { kind: "chapters" } | { kind: "ads" }

/** ส่วนที่ต่อท้ายป้ายปุ่มโหลด เช่น "โหลด mp4 (1:30-5:00, ตัดโฆษณา)" เรียง ช่วง → chapter → โฆษณา */
export function choiceParts(o: { range: ClipRange | null; splitChapters: boolean; ads: boolean }): ChoicePart[] {
  const parts: ChoicePart[] = []
  if (o.range) parts.push({ kind: "range", range: o.range })
  if (o.splitChapters) parts.push({ kind: "chapters" })
  if (o.ads) parts.push({ kind: "ads" })
  return parts
}

export type ChapterBlock = "range" | "sponsorblock" | "embedSubs"

/** เหตุผลที่สวิตช์ "แยกไฟล์ตาม chapter" กดไม่ได้ (ตัวที่เปิดก่อนชนะ spec 1.2) · null = กดได้ */
export function chapterBlock(
  v: { startText: string; endText: string; sponsorblock: boolean },
  embedSubsOn: boolean,
): ChapterBlock | null {
  if (v.startText.trim() !== "" || v.endText.trim() !== "") return "range"
  if (v.sponsorblock) return "sponsorblock"
  if (embedSubsOn) return "embedSubs"
  return null
}
