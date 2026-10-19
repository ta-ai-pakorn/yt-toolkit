import { queryOptions, type QueryClient } from "@tanstack/react-query"

import { fill, th } from "@/i18n/th"

import { api, ApiError } from "./api"
import type { AccountStatus } from "./types"

/** บัญชียูทูปชั่วคราว (M5 รอบ C): สถานะจาก GET /api/cookies ข่าว SSE "account" แก้แคชนี้ (events.ts) */
export const ACCOUNT_KEY = ["account"] as const

/** รหัสที่ใช้บัญชีชั่วคราวช่วยได้ (backend core/yterrors.ACCOUNT_CODES) ไม่รวม E_BOT_CHECK */
export const ACCOUNT_CODES: ReadonlySet<string> = new Set(["E_AGE_RESTRICTED", "E_VIDEO_PRIVATE"])

/** ไฟล์ cookies.txt ไม่เกิน 1 MB (backend ตอบ 413 เมื่อเกิน) */
export const MAX_COOKIE_FILE_BYTES = 1_048_576

export const INACTIVE: AccountStatus = { active: false, used: false }

/** ข่าว SSE "account": {active, expiresAt?, reason?} · reason = manual | queue_done | expired | shutdown */
export type AccountEvent = { active: boolean; expiresAt?: string; reason?: string }

/** สถานะบัญชี · SSE คอยแก้แคชให้ จึงไม่โหลดซ้ำเอง · backend รุ่นที่ไม่มี API นี้ (404) = ถือว่าไม่ได้ใช้บัญชี */
export function accountQuery() {
  return queryOptions({
    queryKey: ACCOUNT_KEY,
    queryFn: async ({ signal }): Promise<AccountStatus> => {
      try {
        return await api<AccountStatus>("/cookies", { signal })
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return INACTIVE
        throw error
      }
    },
    staleTime: Infinity,
    retry: false,
  })
}

/**
 * ใส่สถานะบัญชีที่เพิ่งรู้ (หลังนำเข้า ลบ หรือข่าว SSE) ลงแคช โดยยกเลิก GET /api/cookies ที่ยังค้างอยู่ก่อน
 * คำตอบของคำขอนั้นคำนวณก่อนการเปลี่ยนแปลง ถ้ามาถึงทีหลังจะทับสถานะใหม่: เช่นกด "ลบออกตอนนี้" ตอน SSE เพิ่งต่อติด
 * (events.ts โหลดสถานะบัญชีใหม่) toast ขึ้นว่าลบแล้ว แต่แถบบนหน้ากลับมาค้าง · ยกเลิก = คืนสถานะก่อนคำขอทันที แล้วจึงใส่ค่าใหม่
 */
export function putAccountStatus(client: QueryClient, status: AccountStatus): void {
  void client.cancelQueries({ queryKey: ACCOUNT_KEY })
  client.setQueryData<AccountStatus>(ACCOUNT_KEY, status)
}

/** นำเข้าข้อความของ cookies.txt (ยอมรับคำเตือนใน dialog แล้ว) · ใช้ไม่ได้ = ApiError 422/413 E_COOKIES_INVALID */
export function importAccount(text: string): Promise<AccountStatus> {
  return api<AccountStatus>("/cookies/import", { method: "POST", body: JSON.stringify({ text, acceptWarning: true }) })
}

/** ลบบัญชีออกจากแอพทันที (ไม่ต้องยืนยัน) */
export function deleteAccount(): Promise<AccountStatus> {
  return api<AccountStatus>("/cookies", { method: "DELETE" })
}

export function isAccountCode(code: string | null | undefined): boolean {
  return code != null && ACCOUNT_CODES.has(code)
}

/** error จาก backend ที่บัญชีชั่วคราวช่วยได้ (จำกัดอายุ / ส่วนตัว / เฉพาะสมาชิก) */
export function needsAccount(error: unknown): boolean {
  return error instanceof ApiError && isAccountCode(error.code)
}

/** ปุ่ม "ใช้บัญชียูทูปชั่วคราว" ขึ้นเมื่อรหัสเป็นของบัญชีและยังไม่ได้ถือบัญชี (ถืออยู่แล้ว = ข้อความ "ลองด้วยบัญชีแล้ว…" แทน) */
export function showAccountButton(code: string | null | undefined, active: boolean): boolean {
  return isAccountCode(code) && !active
}

/**
 * เวลาที่เหลือก่อนลบเองเป็นคำ (พี่พิธเลือก Q1 = A) ปัดนาทีขึ้น ไม่ติดลบ เช่น "2 ชม." · "1 ชม. 59 นาที" · 9 นาที 1 วินาที = "10 นาที"
 * importedAt = ไม่นับเวลาก่อนนำเข้า (นาฬิกาของหน้าเว็บเดินทุก 15 วินาที อาจช้ากว่าเวลานำเข้า ห้ามโชว์เกิน 2 ชม.)
 */
export function remainingClock(expiresAt: string, now: number, importedAt?: string): string {
  const end = Date.parse(expiresAt)
  const start = importedAt === undefined ? Number.NaN : Date.parse(importedAt)
  const from = Number.isNaN(start) ? now : Math.max(now, start)
  const minutes = Number.isNaN(end) ? 0 : Math.max(0, Math.ceil((end - from) / 60_000))
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  const hours = fill(th.account.remainHours, { h })
  const mins = fill(th.account.remainMinutes, { m })
  if (h === 0) return mins
  return m === 0 ? hours : `${hours} ${mins}`
}

/** นาฬิกาตามเครื่อง "HH:MM" ของเวลา ISO (เวลานำเข้าในหน้าตรวจสุขภาพ) อ่านไม่ได้ = "" */
export function localClock(iso: string): string {
  const at = new Date(iso)
  if (Number.isNaN(at.getTime())) return ""
  return `${String(at.getHours()).padStart(2, "0")}:${String(at.getMinutes()).padStart(2, "0")}`
}

/**
 * Q1 ของพี่พิธ (ตอบแล้ว 2026-10-06 = A): "ลบอัตโนมัติภายใน {time}" ของแถบบนหน้าและแท็บขั้นสูง
 * "remaining" = เวลาที่เหลือเป็นคำ ("1 ชม. 59 นาที") · "clock" = เวลาบนนาฬิกาที่จะลบ (เช่น "17:05")
 * เปลี่ยนแบบที่แสดงได้ด้วยบรรทัดนี้บรรทัดเดียว
 */
export const DELETE_TIME_STYLE = "remaining" as "remaining" | "clock"

/** เวลาใน "ลบอัตโนมัติภายใน {time}" ตาม DELETE_TIME_STYLE (หรือ style ที่ส่งมา สำหรับเทส) */
export function deleteTime(
  status: { expiresAt: string; importedAt?: string },
  now: number,
  style: "remaining" | "clock" = DELETE_TIME_STYLE,
): string {
  return style === "clock" ? localClock(status.expiresAt) : remainingClock(status.expiresAt, now, status.importedAt)
}

export function fileTooBig(size: number): boolean {
  return size > MAX_COOKIE_FILE_BYTES
}

/**
 * ใส่ข่าว SSE ลงสถานะในแคช: ไม่ถือบัญชี = INACTIVE · ยังถืออยู่ = เวลาลบใหม่ (grace เริ่ม/ยกเลิก)
 * · เพิ่งนำเข้าแต่แคชไม่รู้เวลานำเข้า = undefined (ผู้เรียกโหลดสถานะเต็มใหม่)
 */
export function applyAccountEvent(prev: AccountStatus | undefined, event: AccountEvent): AccountStatus | undefined {
  if (!event.active) return INACTIVE
  if (prev?.active && event.expiresAt !== undefined) return { ...prev, expiresAt: event.expiresAt }
  return undefined
}

/**
 * ใส่ข่าว SSE "account" ลงแคช (events.ts) · ยังถือบัญชี (active:true) = โหลดสถานะเต็มใหม่ทุกครั้งด้วย
 * (นำเข้าซ้ำจากแท็บอื่น = เวลานำเข้าเปลี่ยน ข่าวไม่มีเวลานำเข้า) · ทุกข่าว = โหลดหน้าตรวจสุขภาพใหม่ (แถวบัญชี)
 */
export function syncAccountCache(client: QueryClient, event: AccountEvent): void {
  const next = applyAccountEvent(client.getQueryData<AccountStatus>(ACCOUNT_KEY), event)
  if (next !== undefined) putAccountStatus(client, next)
  if (event.active) void client.invalidateQueries({ queryKey: ACCOUNT_KEY })
  void client.invalidateQueries({ queryKey: ["health"] })
}
