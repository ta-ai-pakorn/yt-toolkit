import { needsAccount } from "@/lib/account"
import { ApiError } from "@/lib/api"

// error เหล่านี้ลองใหม่ทันทีก็ไม่ช่วย จึงซ่อนปุ่ม "ลองใหม่" และไม่ยิงซ้ำเมื่อสลับแท็บ: เกิดจากตัวคลิปเอง (ผลเหมือนเดิมทุกครั้ง)
// หรือ E_BOT_CHECK ที่ยูทูปให้รอสักพัก (M2 ยังไม่มีคิวพักให้ กดซ้ำรัว ๆ มีแต่ทำให้ถูกบล็อกนานขึ้น)
// E_TRANSLATION_BLOCKED = ยูทูปไม่ให้โหลดซับแปลอัตโนมัติ ยิงซ้ำก็ได้ 429 เหมือนเดิม (ให้เลือกซับภาษาต้นฉบับแทน)
const FINAL_CODES = new Set([
  "E_BOT_CHECK",
  "E_TRANSLATION_BLOCKED",
  "E_NO_SUBTITLES",
  "E_LIVE_NOT_READY",
  "E_VIDEO_PRIVATE",
  "E_VIDEO_UNAVAILABLE",
  "E_GEO_BLOCKED",
  "E_AGE_RESTRICTED",
  "E_INVALID_INPUT",
])

/** เน็ตหลุด (E_NETWORK, E_OFFLINE) และรหัสที่ไม่รู้จักลองใหม่ได้ · error ที่เป็นเรื่องของคลิปเอง และ E_BOT_CHECK ลองใหม่ไม่ช่วย */
export function canRetry(error: unknown): boolean {
  return !(error instanceof ApiError && FINAL_CODES.has(error.code))
}

/**
 * ปุ่ม "ลองใหม่" ของกล่อง error · M5 รอบ C: error ที่บัญชีช่วยได้ (จำกัดอายุ/ส่วนตัว) ในกล่องที่รับบัญชี (W2) และถือบัญชีอยู่แล้ว
 * (นำเข้าจากหน้าตั้งค่าหรือแท็บอื่นขณะ error ค้าง) = ลองใหม่ได้ เพราะรอบใหม่ไปผ่านบัญชี (ไม่งั้นกล่องนี้ไม่มีปุ่มให้กดเลย)
 */
export function showRetry(error: unknown, accountBox: boolean, active: boolean): boolean {
  return canRetry(error) || (accountBox && active && needsAccount(error))
}

/** error จาก backend ที่มีรหัสนี้หรือไม่ (error อื่นที่ไม่ใช่ ApiError = ไม่ใช่) */
export function hasCode(error: unknown, code: string): boolean {
  return error instanceof ApiError && error.code === code
}

/** ข้อความไทยจาก envelope ของ backend · error ที่ไม่ใช่ ApiError ใช้ข้อความกลางของแอพ */
export function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback
}
