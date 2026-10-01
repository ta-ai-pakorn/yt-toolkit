import { api } from "./api"
import type { Settings } from "./types"

/** ทางลัดสำหรับเทส: ส่ง fetch/token ปลอมต่อให้ api() */
type ApiDeps = Parameters<typeof api>[2]

export const SETTINGS_KEY = ["settings"] as const

/** การตั้งค่าทั้งหมด (ค่าเริ่มต้นรวมกับค่าที่ผู้ใช้เคยเปลี่ยน) */
export function settingsQuery(deps?: ApiDeps): {
  queryKey: typeof SETTINGS_KEY
  queryFn: () => Promise<Settings>
} {
  return {
    queryKey: SETTINGS_KEY,
    queryFn: () => api<Settings>("/settings", {}, deps),
  }
}

/** เปลี่ยนเฉพาะค่าที่ส่งไป (ทั้งหมดหรือไม่เปลี่ยนเลย) คืนการตั้งค่าทั้งหมดหลังเปลี่ยน · ค่าผิด = ApiError 422 */
export function patchSettings(
  partial: Partial<Settings>,
  deps?: ApiDeps
): Promise<Settings> {
  return api<Settings>(
    "/settings",
    { method: "PATCH", body: JSON.stringify(partial) },
    deps
  )
}

/** เปิดโฟลเดอร์ผลงานบนเครื่อง (สร้างให้ถ้ายังไม่มี) · เขียนไม่ได้ = ApiError 422 E_OUTPUT_NOT_WRITABLE */
export async function openOutputFolder(deps?: ApiDeps): Promise<void> {
  await api("/settings/open-output", { method: "POST" }, deps)
}
