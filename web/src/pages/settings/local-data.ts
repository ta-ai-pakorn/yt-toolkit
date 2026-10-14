import type { QueryClient } from "@tanstack/react-query"

import { fill, th } from "@/i18n/th"
import { formatBytes } from "@/lib/format"
import type { ReportRequest } from "@/lib/report"
import { MAX_SETTINGS_FILE_BYTES, STORAGE_KEY, type ImportResult, type StorageUsage } from "@/lib/settings-api"

/**
 * ตรรกะของส่วน "ข้อมูลในเครื่อง" (M6 รอบ A spec 3.3, 4.3, 5) แยกจาก JSX เพื่อเทสใน node ได้
 */

/** id คงที่ของ toast แต่ละแหล่ง (error ครั้งใหม่แทนที่ toast เดิม) */
export const CLEAR_TOAST_ID = "storage-clear"
export const IMPORT_TOAST_ID = "settings-import"
export const EXPORT_TOAST_ID = "settings-export"

/**
 * ข้อมูลของคลิปที่หายไปพร้อม data/cache หลังล้าง: ลบออกจากแคชของหน้าเว็บ เปิดคลิปเก่าแล้วโหลดใหม่ (spec 3.3)
 * ["video"], ["history"], ["subtitles"] (รายชื่อแทร็กจาก probe) และ ["settings"] ยังใช้ได้ จึงไม่แตะ
 */
export const CLIP_CACHE_KEYS = [["storyboard"], ["sharp"], ["captures"], ["subtokens"], ["pinned-comment"]] as const

export function forgetClipCaches(client: Pick<QueryClient, "removeQueries" | "invalidateQueries">): void {
  for (const queryKey of CLIP_CACHE_KEYS) client.removeQueries({ queryKey })
  void client.invalidateQueries({ queryKey: STORAGE_KEY })
}

export type ClearButton = { label: string; size: string | null; disabled: boolean }

/** ปุ่ม "ล้างข้อมูลชั่วคราว (<ขนาด>)" · ยังโหลดไม่เสร็จหรือโหลดไม่ได้ = ไม่มีขนาดและกดไม่ได้ (ข้อมูลรอง ไม่แจ้ง error) */
export function clearButton(usage: StorageUsage | undefined): ClearButton {
  if (!usage) return { label: th.general.clearTempPlain, size: null, disabled: true }
  const size = formatBytes(usage.reclaimableBytes)
  return { label: fill(th.general.clearTemp, { size }), size, disabled: usage.reclaimableBytes <= 0 }
}

/** ไฟล์ที่ใหญ่เกิน 1 MB ไม่ส่งไป backend เลย (backend ตอบ 413 แบบเดียวกัน) */
export function importTooLarge(file: Pick<Blob, "size">): boolean {
  return file.size > MAX_SETTINGS_FILE_BYTES
}

/** body ของรายงานแจ้งปัญหาเมื่อไฟล์ใหญ่เกิน (detail เดียวกับ 413 ของ backend) */
export const TOO_LARGE_REQUEST: ReportRequest = {
  code: "E_SETTINGS_INVALID",
  detail: `file larger than ${MAX_SETTINGS_FILE_BYTES} bytes`,
  context: IMPORT_TOAST_ID,
}

export type ImportNotice = { kind: "success" | "warning"; message: string }

/** นำเข้าสำเร็จ: ไม่มีคำเตือน = "นำเข้าค่าตั้งแล้ว" · ใช้โฟลเดอร์ในไฟล์ไม่ได้ = คำเตือนที่ค้างจนกดปิด (Pete Q2 = B, Q3) */
export function importNotice(result: Pick<ImportResult, "warnings">): ImportNotice {
  return result.warnings.includes("outputDir")
    ? { kind: "warning", message: th.general.importedKeptFolder }
    : { kind: "success", message: th.general.imported }
}
