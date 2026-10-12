import type { ReactNode } from "react"

import { cleanRequest, reportRequest, type ReportRequest, type ReportWhere } from "@/lib/report"

/**
 * ตรรกะของส่วน "ดูรายละเอียด" และ toast ของ error (M6 รอบ B spec 1.1) แยกจาก JSX เพื่อเทสใน node ได้
 * (vitest ไม่มี DOM แบบเดียวกับ components/account/dialog-model.ts)
 */

/** id ของ toast "คัดลอกแล้ว" / คัดลอกไม่สำเร็จ: กดซ้ำหลายครั้งได้ toast เดียว */
export const REPORT_TOAST_ID = "report-copy"

export type ToastButton = { label: string; onClick: () => void }

/** ตัวเลือกของ showErrorToast: request = body ของรายงาน · id คงที่ต่อแหล่ง error (error ครั้งใหม่แทนที่ toast เดิม) */
export type ErrorToastOptions = {
  request: ReportRequest
  id?: string | number
  description?: ReactNode
  action?: ToastButton
  cancel?: ToastButton
}

/** ที่มาของส่วนพับ: error ที่จับได้ + ที่ที่เกิด หรือ body ที่ประกอบไว้แล้ว (แถวงานที่พลาดในคิว) */
export type DetailsSource = ({ error: unknown } & ReportWhere) | { request: ReportRequest }

/** body ของรายงานของส่วนพับ · รหัสและ detail ที่แสดงมาจาก body นี้ จึงตรงกับที่ส่งไปเสมอ */
export function detailsRequest(source: DetailsSource): ReportRequest {
  if ("request" in source) return cleanRequest(source.request)
  return reportRequest(source.error, { context: source.context, videoId: source.videoId, jobId: source.jobId })
}

/**
 * กางไว้ตั้งแต่แรกเมื่อรหัสเป็น E_UNKNOWN (planner ruling R1): ข้อความของรหัสนี้บอกให้กดปุ่ม
 * ปุ่มจึงต้องเห็นโดยไม่ต้องกดอะไรก่อน · ผู้เรียกกำหนดเองได้ด้วย defaultOpen
 */
export function detailsOpenByDefault(code: string | undefined, defaultOpen?: boolean): boolean {
  return defaultOpen ?? code === "E_UNKNOWN"
}

/** ตัวเลือก sonner ของ toast error (ยกเว้น description ที่ error-toast.tsx ใส่ปุ่มคัดลอก): ค้างจนกดปิด (D1) */
export function errorToastSettings(opts: Pick<ErrorToastOptions, "id" | "action" | "cancel">) {
  return { id: opts.id, duration: Infinity, action: opts.action, cancel: opts.cancel }
}

/**
 * กระจายใส่ toast ที่ใช้ id เดียวกับ toast error (เช่น "โหลดเสร็จแล้ว" ของงานที่เคยพลาด "บันทึกแล้ว" กำลังโหลด ffmpeg)
 * sonner รวมค่าใหม่ทับ toast เดิมที่มี id เดียวกัน ช่องที่ไม่ส่งจะค้างจาก toast error (ปุ่มคัดลอก + ไม่หายเอง)
 */
export const PLAIN_TOAST = { description: undefined, duration: undefined, action: undefined, cancel: undefined }
