/** เรขาคณิตของแถบไทม์ไลน์ใต้ตัวเล่น (คำนวณล้วน ไม่แตะ DOM ทดสอบได้ง่าย) */

/** ปุ่มลูกศรซ้าย/ขวาเลื่อนทีละ 5 วินาที */
export const KEY_STEP_MS = 5000

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value))

/** ตำแหน่ง ms เป็นสัดส่วน 0-1 ของความยาวคลิป (คลิปไม่มีความยาว = 0) */
export function fractionOf(ms: number, durationMs: number): number {
  if (!(durationMs > 0) || !Number.isFinite(ms)) return 0
  return clamp(ms / durationMs, 0, 1)
}

/** เปอร์เซ็นต์สำหรับ CSS (left / width) */
export function percentOf(ms: number, durationMs: number): string {
  return `${(fractionOf(ms, durationMs) * 100).toFixed(3)}%`
}

/** จุดที่คลิก/แตะ (clientX) บนแถบที่เริ่มที่ left กว้าง width → เวลา ms (ปัดเป็นวินาทีเต็ม ตรงกับ timecode) */
export function msAtPoint(clientX: number, left: number, width: number, durationMs: number): number {
  if (!(width > 0) || !(durationMs > 0)) return 0
  const fraction = clamp((clientX - left) / width, 0, 1)
  return clamp(Math.round((fraction * durationMs) / 1000) * 1000, 0, durationMs)
}

/** ช่วงเวลา → ตำแหน่งและความกว้างบนแถบ (ช่วงที่อยู่นอกคลิปทั้งหมด = null) · กว้างอย่างน้อย minPercent ให้ตาเห็น */
export function rangeBox(
  range: { startMs: number; endMs: number },
  durationMs: number,
  minPercent = 0.5,
): { left: string; width: string } | null {
  if (!(durationMs > 0) || range.endMs <= range.startMs || range.startMs >= durationMs) return null
  const start = fractionOf(range.startMs, durationMs) * 100
  const end = fractionOf(range.endMs, durationMs) * 100
  const width = Math.max(end - start, minPercent)
  return { left: `${start.toFixed(3)}%`, width: `${Math.min(width, 100 - start).toFixed(3)}%` }
}

/** ปุ่มคีย์บอร์ดของแถบ (slider) → เวลาใหม่ · ปุ่มอื่น = null */
export function keyTarget(key: string, currentMs: number, durationMs: number): number | null {
  switch (key) {
    case "ArrowLeft":
    case "ArrowDown":
      return clamp(currentMs - KEY_STEP_MS, 0, durationMs)
    case "ArrowRight":
    case "ArrowUp":
      return clamp(currentMs + KEY_STEP_MS, 0, durationMs)
    case "Home":
      return 0
    case "End":
      return durationMs
    default:
      return null
  }
}
