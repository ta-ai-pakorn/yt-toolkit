import { resolution } from "@/lib/download-options"
import type { VideoFormat } from "@/lib/types"

/**
 * ภาพคม (M5 รอบ B spec 3.2): แผนเวลาชุดเดียวกับ core/sharp.py (เคสร่วม tests/fixtures/sharp/plan-cases.json)
 * และตัวคำนวณของ dialog "ขอภาพคม" (จำนวนภาพ ขนาดวิดีโอชั่วคราว ความละเอียด ค่าที่ส่งเข้าคิว)
 */

export const MAX_SHARP_FRAMES = 200
export const MAX_INTERVAL_S = 3600
/** ภาพคมโหลดด้านสั้นไม่เกิน 720 (D4) */
const SHARP_SHORT_SIDE = 720

export type SharpPlan = { timesMs: number[]; intervalS: number | null; raised: boolean }

/** react-query key ของ GET /videos/{id}/sharp (หน้า W2 และตัวรับข่าว SSE ใช้ตัวเดียวกัน) */
export const sharpKey = (videoId: string) => ["sharp", videoId] as const

export const defaultIntervalS = (durationS: number): number => Math.max(1, Math.ceil(durationS / 100))

export const raisedIntervalS = (durationS: number): number => Math.ceil(durationS / MAX_SHARP_FRAMES)

/** จำนวนภาพของช่วงห่าง N = ceil(d / N) (เท่ากับจำนวน t_i = i × N วินาทีที่ยังน้อยกว่าความยาวคลิป) */
const countFor = (intervalS: number, durationS: number): number => Math.ceil(durationS / intervalS)

export function customTimes(intervalS: number, durationS: number): number[] {
  const out: number[] = []
  for (let t = 0; t < durationS * 1000; t += intervalS * 1000) out.push(t)
  return out
}

function raised(durationS: number): SharpPlan {
  const n2 = raisedIntervalS(durationS)
  return { timesMs: customTimes(n2, durationS), intervalS: n2, raised: true }
}

export function planSharp(
  durationS: number,
  opts: { intervalS: number | null; fastTimes: readonly number[] | null }
): SharpPlan {
  const { intervalS, fastTimes } = opts
  if (!Number.isInteger(durationS) || durationS <= 0) throw new RangeError(`durationS must be a positive integer: ${durationS}`)
  if (intervalS !== null && (!Number.isInteger(intervalS) || intervalS < 1 || intervalS > MAX_INTERVAL_S)) {
    throw new RangeError(`intervalS must be 1..${MAX_INTERVAL_S}: ${intervalS}`)
  }
  if (intervalS === null && fastTimes !== null) {
    if (fastTimes.length === 0) throw new RangeError("fastTimes is empty")
    return fastTimes.length <= MAX_SHARP_FRAMES ? { timesMs: [...fastTimes], intervalS: null, raised: false } : raised(durationS)
  }
  if (intervalS === null) {
    const n = defaultIntervalS(durationS)
    return { timesMs: customTimes(n, durationS), intervalS: n, raised: false }
  }
  if (countFor(intervalS, durationS) > MAX_SHARP_FRAMES) return raised(durationS)
  return { timesMs: customTimes(intervalS, durationS), intervalS, raised: false }
}

/** ช่อง "ตั้งเอง ทุก N วินาที": เลขอารบิกล้วน 1-3600 (ช่องว่างหัวท้ายได้) อย่างอื่น = null */
export function parseIntervalText(text: string): number | null {
  const trimmed = text.trim()
  if (!/^\d{1,4}$/.test(trimmed)) return null
  const n = Number(trimmed)
  return n >= 1 && n <= MAX_INTERVAL_S ? n : null
}

export type SharpEstimate = { sizeBytes?: number; shortSide: number | null; portrait: boolean }

const codecRank = (vcodec: string): number =>
  vcodec.startsWith("avc1") ? 0 : vcodec.startsWith("vp09") || vcodec.startsWith("vp9") ? 1 : vcodec.startsWith("av01") ? 2 : 3

/**
 * format ที่งานภาพคมน่าจะโหลด (ลำดับเดียวกับ download.sharp_choice ยกเว้นเรื่อง SDR ที่ VideoInfo ไม่มี):
 * ด้านสั้นมากสุดที่ไม่เกิน 720 · avc1 ก่อน vp9 ก่อน av01 · ไฟล์เล็กสุด (ไม่รู้ขนาดไว้ท้าย)
 * ไม่มีตัวไหนไม่เกิน 720 = ตัวที่ด้านสั้นน้อยสุด
 */
export function sharpEstimate(video: readonly VideoFormat[]): SharpEstimate {
  const sized = video.filter((f) => resolution(f) > 0)
  if (sized.length === 0) return { shortSide: null, portrait: false }
  const under = sized.filter((f) => resolution(f) <= SHARP_SHORT_SIDE)
  const target = under.length > 0 ? Math.max(...under.map(resolution)) : Math.min(...sized.map(resolution))
  const [best] = sized
    .filter((f) => resolution(f) === target)
    .sort(
      (a, b) =>
        codecRank(a.vcodec) - codecRank(b.vcodec) ||
        (a.sizeBytes ?? Number.MAX_SAFE_INTEGER) - (b.sizeBytes ?? Number.MAX_SAFE_INTEGER) ||
        a.formatId.localeCompare(b.formatId)
    )
  const portrait = best.width !== undefined && best.width < best.height
  return best.sizeBytes === undefined ? { shortSide: target, portrait } : { sizeBytes: best.sizeBytes, shortSide: target, portrait }
}

export type SharpMode = "same" | "custom"
export type SharpFast = { intervalMs: number; timesMs: readonly number[] }
export type SharpResolution = { kind: "wide" } | { kind: "tall" } | { kind: "low"; h: number }

export type SharpDialogModel = {
  sameAvailable: boolean
  mode: SharpMode
  sameInterval: string | null
  sameCount: number | null
  customCount: number | null
  customError: boolean
  overflow: { n: string; count: number; n2: number } | null
  params: { intervalS?: number } | null
  sizeBytes: number | null
  resolution: SharpResolution
  replace: boolean
}

/** ค่าตั้งต้นของช่อง "ตั้งเอง" (spec 1.3: คลิปไม่มี storyboard ใช้ max(1, ceil(d/100)) · มี storyboard ใช้ค่าเดียวกัน) */
export const defaultCustomText = (durationS: number): string => String(defaultIntervalS(Math.max(1, durationS)))

export function sharpDialogModel(input: {
  durationS: number
  fast: SharpFast | null
  mode: SharpMode
  customText: string
  video: readonly VideoFormat[]
  hasSharp: boolean
}): SharpDialogModel {
  const { durationS, fast, customText, video, hasSharp } = input
  const sameAvailable = fast !== null && fast.timesMs.length > 0
  const mode: SharpMode = sameAvailable ? input.mode : "custom"
  const sameCount = sameAvailable ? fast.timesMs.length : null
  const sameInterval = sameAvailable ? (Math.round(fast.intervalMs / 100) / 10).toFixed(1) : null
  const typed = parseIntervalText(customText)
  const usable = Number.isInteger(durationS) && durationS > 0
  const customCount = typed !== null && usable ? countFor(typed, durationS) : null
  let overflow: SharpDialogModel["overflow"] = null
  let params: SharpDialogModel["params"] = null
  if (usable && mode === "same" && sameCount !== null && sameInterval !== null) {
    if (sameCount > MAX_SHARP_FRAMES) {
      const n2 = raisedIntervalS(durationS)
      overflow = { n: sameInterval, count: sameCount, n2 }
      params = { intervalS: n2 }
    } else params = {}
  } else if (usable && mode === "custom" && typed !== null && customCount !== null) {
    if (customCount > MAX_SHARP_FRAMES) {
      const n2 = raisedIntervalS(durationS)
      overflow = { n: String(typed), count: customCount, n2 }
      params = { intervalS: n2 }
    } else params = { intervalS: typed }
  }
  const estimate = sharpEstimate(video)
  const resolutionLine: SharpResolution =
    estimate.shortSide !== null && estimate.shortSide < SHARP_SHORT_SIDE
      ? { kind: "low", h: estimate.shortSide }
      : estimate.portrait
        ? { kind: "tall" }
        : { kind: "wide" }
  return {
    sameAvailable,
    mode,
    sameInterval,
    sameCount,
    customCount,
    customError: mode === "custom" && typed === null,
    overflow,
    params,
    sizeBytes: estimate.sizeBytes ?? null,
    resolution: resolutionLine,
    replace: hasSharp,
  }
}
