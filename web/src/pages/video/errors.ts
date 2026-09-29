import { ApiError } from "@/lib/api"

// error เหล่านี้เกิดจากตัวคลิปเอง ลองใหม่กี่ครั้งผลก็เหมือนเดิม จึงซ่อนปุ่ม "ลองใหม่"
const FINAL_CODES = new Set([
  "E_LIVE_NOT_READY",
  "E_VIDEO_PRIVATE",
  "E_VIDEO_UNAVAILABLE",
  "E_GEO_BLOCKED",
  "E_AGE_RESTRICTED",
  "E_INVALID_INPUT",
])

/** เน็ตหลุด (E_NETWORK, E_OFFLINE) และรหัสที่ไม่รู้จักลองใหม่ได้ · error ที่เป็นเรื่องของคลิปเองลองใหม่ไม่ช่วย */
export function canRetry(error: unknown): boolean {
  return !(error instanceof ApiError && FINAL_CODES.has(error.code))
}

/** ข้อความไทยจาก envelope ของ backend · error ที่ไม่ใช่ ApiError ใช้ข้อความกลางของแอพ */
export function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback
}
