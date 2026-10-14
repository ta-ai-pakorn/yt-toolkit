import { api } from "./api"
import { downloadFile } from "./download"
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
  partial: Partial<Omit<Settings, "statsResetAt">>,
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

// ---------- M6 รอบ A: สำรอง/นำเข้าค่าตั้ง และข้อมูลชั่วคราว ----------

/** ไฟล์ค่าตั้งใหญ่สุดที่นำเข้าได้ (ตรงกับ MAX_SETTINGS_IMPORT_BYTES ของ backend · เกิน = ไม่ส่ง) */
export const MAX_SETTINGS_FILE_BYTES = 1_048_576

/** ชื่อสำรองเมื่อ backend ไม่ส่ง Content-Disposition (ปกติได้ yt-toolkit-settings-YYYY-MM-DD.json) */
export const SETTINGS_FILE_FALLBACK = "yt-toolkit-settings.json"

type DownloadDeps = Parameters<typeof downloadFile>[2]

/** สำรองค่าตั้ง: โหลด GET /api/settings/export ลงเครื่อง คืนชื่อไฟล์ที่บันทึก · ล้มเหลว = ApiError */
export function exportSettings(deps?: DownloadDeps): Promise<string> {
  return downloadFile("/api/settings/export", SETTINGS_FILE_FALLBACK, deps)
}

export type ImportResult = { settings: Settings; warnings: string[] }

/** นำเข้าค่าตั้งจากเนื้อไฟล์ (ส่งข้อความดิบ backend ตรวจเอง) · ไฟล์ผิดรูปแบบ = ApiError 422/413 E_SETTINGS_INVALID */
export function importSettings(text: string, deps?: ApiDeps): Promise<ImportResult> {
  return api<ImportResult>("/settings/import", { method: "POST", body: text }, deps)
}

export const STORAGE_KEY = ["storage"] as const

/** ขนาดของ data/cache และ work/ (ไบต์) · reclaimableBytes = ส่วนที่ปุ่ม "ล้างข้อมูลชั่วคราว" ลบได้ตอนนี้ */
export type StorageUsage = { cacheBytes: number; workBytes: number; reclaimableBytes: number }

export function storageQuery(deps?: ApiDeps): {
  queryKey: typeof STORAGE_KEY
  queryFn: () => Promise<StorageUsage>
} {
  return {
    queryKey: STORAGE_KEY,
    queryFn: () => api<StorageUsage>("/storage", {}, deps),
  }
}

/** ล้างข้อมูลชั่วคราวที่ไม่มีงานใช้ คืนจำนวนไบต์ที่ได้คืนจริง */
export function clearStorage(deps?: ApiDeps): Promise<{ freedBytes: number }> {
  return api<{ freedBytes: number }>("/storage/clear", { method: "POST" }, deps)
}
