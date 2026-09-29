import { fill, th } from "@/i18n/th"

const pad = (n: number) => String(n).padStart(2, "0")

/** ความยาวคลิป: M:SS หรือ H:MM:SS เมื่อครบชั่วโมง */
export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.floor(Number.isFinite(seconds) ? seconds : 0))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`
}

/** timecode ทุกที่ในแอพเป็น HH:MM:SS (ตัดมิลลิวินาทีทิ้ง ไม่ปัดขึ้น) */
export function formatTimecode(ms: number): string {
  const total = Math.max(0, Math.floor((Number.isFinite(ms) ? ms : 0) / 1000))
  return `${pad(Math.floor(total / 3600))}:${pad(Math.floor((total % 3600) / 60))}:${pad(total % 60)}`
}

const MINUTE = 60
const HOUR = 3600
const DAY = 86400

/** เวลาแบบ "5 นาทีก่อน" (นับจากเวลาที่ผ่านไปจริง ไม่ใช่ปฏิทิน) · ISO ที่อ่านไม่ได้หรืออยู่ในอนาคต = เมื่อสักครู่ */
export function relativeTime(iso: string, now: Date = new Date()): string {
  const then = Date.parse(iso)
  const diff = Number.isNaN(then) ? 0 : Math.floor((now.getTime() - then) / 1000)
  if (diff < MINUTE) return th.time.justNow
  if (diff < HOUR) return fill(th.time.minutesAgo, { n: Math.floor(diff / MINUTE) })
  if (diff < DAY) return fill(th.time.hoursAgo, { n: Math.floor(diff / HOUR) })
  const days = Math.floor(diff / DAY)
  if (days === 1) return th.time.yesterday
  if (days < 7) return fill(th.time.daysAgo, { n: days })
  if (days < 30) return fill(th.time.weeksAgo, { n: Math.floor(days / 7) })
  if (days < 365) return fill(th.time.monthsAgo, { n: Math.floor(days / 30) })
  return fill(th.time.yearsAgo, { n: Math.floor(days / 365) })
}
