import type { SubOptions, SubPreset } from "@/lib/types"

/**
 * ค่าสำเร็จรูป 4 แบบ ต้องตรงกับ core/srt_builder.py ทุกตัวเลข (สัญญา C5) ลำดับเดียวกับปุ่มในหน้าเว็บ
 * "ทีละคำ" (word) = ซับละ 1 token แบบซับคลิปสั้น: token เดียวไม่ถูกตัดและยาวเกิน maxChars ได้
 * ค่าตัวอักษรกับเวลาจึงเท่ากับ "สั้น" (คำแสดงค้างได้ถึง 0.8 วิ หรือจนคำถัดไปขึ้น)
 */
export const PRESETS: Record<SubPreset, SubOptions> = {
  short: { maxChars: 15, lines: 1, minMs: 800, maxMs: 3000, mode: "chars" },
  medium: { maxChars: 25, lines: 1, minMs: 1200, maxMs: 5000, mode: "chars" },
  long: { maxChars: 42, lines: 2, minMs: 1500, maxMs: 7000, mode: "chars" },
  word: { maxChars: 15, lines: 1, minMs: 800, maxMs: 3000, mode: "tokens", tokensPerCue: 1 },
}

/** ชื่อสำเร็จรูปตามลำดับปุ่ม: สั้น · กลาง · ยาว · ทีละคำ */
export const PRESET_NAMES = Object.keys(PRESETS) as SubPreset[]

/** ชื่อสำเร็จรูปที่รู้จัก (ใช้ตรวจค่าที่จำไว้ในเบราว์เซอร์) */
export function isPresetName(value: unknown): value is SubPreset {
  return PRESET_NAMES.some((name) => name === value)
}

export const DEFAULT_PRESET: SubPreset = "medium"

/** ช่วงที่อนุญาต [ต่ำสุด, สูงสุด] ของแต่ละค่า (สไลเดอร์: minMs ก้าว 100, maxMs ก้าว 500) */
export const LIMITS = {
  maxChars: [10, 60],
  lines: [1, 2],
  minMs: [300, 3000],
  maxMs: [1000, 10000],
  tokensPerCue: [1, 20],
} as const

/** ค่าเริ่มต้นของ "คำต่อซับ" ตอนเปิดโหมดนับเป็นคำ */
export const DEFAULT_TOKENS_PER_CUE = 3

/** ระยะห่างขั้นต่ำที่บังคับให้ maxMs เหนือ minMs เมื่อผู้ใช้ตั้งสองค่าชนกัน */
const MIN_SPAN_MS = 500

function clamp(value: number, [low, high]: readonly [number, number]): number {
  const n = Number.isFinite(value) ? Math.round(value) : low
  return Math.min(Math.max(n, low), high)
}

/** บีบทุกค่าให้อยู่ในช่วง LIMITS และบังคับ minMs < maxMs (ยก maxMs เป็น minMs + 500) ค่าที่ไม่ใช้ในโหมดนั้นถูกตัดทิ้ง */
export function clampOptions(o: SubOptions): SubOptions {
  const minMs = clamp(o.minMs, LIMITS.minMs)
  let maxMs = clamp(o.maxMs, LIMITS.maxMs)
  if (minMs >= maxMs) maxMs = minMs + MIN_SPAN_MS
  const base = {
    maxChars: clamp(o.maxChars, LIMITS.maxChars),
    lines: clamp(o.lines, LIMITS.lines) === 2 ? (2 as const) : (1 as const),
    minMs,
    maxMs,
  }
  if (o.mode === "tokens") {
    return { ...base, mode: "tokens", tokensPerCue: clamp(o.tokensPerCue ?? DEFAULT_TOKENS_PER_CUE, LIMITS.tokensPerCue) }
  }
  return { ...base, mode: "chars" }
}

function sameOptions(a: SubOptions, b: SubOptions): boolean {
  return (
    a.maxChars === b.maxChars &&
    a.lines === b.lines &&
    a.minMs === b.minMs &&
    a.maxMs === b.maxMs &&
    a.mode === b.mode &&
    (a.mode === "tokens" ? a.tokensPerCue === b.tokensPerCue : true)
  )
}

/** ชื่อสำเร็จรูปที่ตรงกับค่านี้ทุกช่อง ไม่ตรงสักแบบคือ null (= ปรับเอง) */
export function presetOf(o: SubOptions): SubPreset | null {
  for (const name of PRESET_NAMES) {
    if (sameOptions(o, PRESETS[name])) return name
  }
  return null
}

/** คีย์ความยาวซับใน query ลำดับคงที่: maxChars, lines, minMs, maxMs, mode[, tokensPerCue] */
function optionParams(o: SubOptions): string[] {
  const query = [`maxChars=${o.maxChars}`, `lines=${o.lines}`, `minMs=${o.minMs}`, `maxMs=${o.maxMs}`, `mode=${o.mode}`]
  if (o.mode === "tokens" && o.tokensPerCue !== undefined) query.push(`tokensPerCue=${o.tokensPerCue}`)
  return query
}

/**
 * path โหลดโน้ต .md ของคลิป (สัญญา C-A3): แทร็กที่ใช้อยู่ + ความยาวซับชุดเดียวกับไฟล์ซับ
 * ไม่มีแทร็ก (ยังโหลดรายการแทร็กไม่เสร็จ หรือคลิปไม่มีซับ) = ไม่ส่ง trackId ให้ backend ใช้แทร็กเริ่มต้นเอง
 * ลำดับคีย์คงที่: trackId, maxChars, lines, minMs, maxMs, mode[, tokensPerCue]
 */
export function notePath(videoId: string, trackId: string | null, o: SubOptions): string {
  const query = [...(trackId ? [`trackId=${encodeURIComponent(trackId)}`] : []), ...optionParams(o)]
  return `/api/videos/${encodeURIComponent(videoId)}/note?${query.join("&")}`
}
