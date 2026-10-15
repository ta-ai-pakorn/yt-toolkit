import { th } from "@/i18n/th"
import type { Stats, StatsKind } from "@/lib/types"

/** M6 รอบ C (spec §3.3): ตัวช่วยของแท็บสถิติ ไม่มี React ทดสอบใน node ได้ */

export const RESET_TOAST_ID = "stats-reset"

const MONTH = new Intl.DateTimeFormat("th-TH", { month: "long", year: "numeric", timeZone: "UTC" })
const SINCE = new Intl.DateTimeFormat("th-TH", { dateStyle: "long", timeZone: "Asia/Bangkok" })
const NUMBER = new Intl.NumberFormat("th-TH")

export function kindLabel(kind: StatsKind): string {
  return th.stats.kinds[kind]
}

/** server เรียง byKind มาแล้ว (ไฟล์มากก่อน เท่ากันดูขนาด) */
export function topKind(stats: Stats): Stats["byKind"][number] | null {
  return stats.byKind[0] ?? null
}

/** "2026-10" → "ตุลาคม 2569" · อ่านเป็นวันที่ 1 UTC แสดงเป็น UTC จึงไม่เลื่อนเดือน */
export function monthLabel(month: string): string {
  return MONTH.format(Date.parse(`${month}-01T00:00:00Z`))
}

/** เวลาเริ่มนับ → วันที่แบบไทยตามเวลาไทย (ตรงกับการจัดเดือนของ server) */
export function sinceLabel(iso: string): string {
  return SINCE.format(Date.parse(iso))
}

export function count(n: number): string {
  return NUMBER.format(n)
}

export function isEmpty(stats: Stats): boolean {
  return stats.clips === 0
}
