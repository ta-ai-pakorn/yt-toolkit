import { fill, th } from "@/i18n/th"
import { formatDuration } from "@/lib/format"
import type { Job } from "@/lib/types"

/** ชื่อที่แสดงของงาน: ชื่อคลิป (ยังไม่รู้ชื่อ = รหัสคลิป) */
export const jobTitle = (job: Pick<Job, "title" | "videoId">): string => job.title || job.videoId

/** เปอร์เซ็นต์จากความคืบหน้า 0..1 (ปัดลง ไม่ขึ้น 100% ก่อนเสร็จจริง) เช่น "42%" */
export function formatPercent(progress: number): string {
  const n = Math.min(100, Math.max(0, Math.floor((Number.isFinite(progress) ? progress : 0) * 100)))
  return fill(th.queue.percent, { n })
}

/** ความเร็วแบบหน่วยฐานสิบ (1 MB = 1,000,000 ไบต์) เช่น "2.4 MB/วินาที" · ต่ำกว่า 1 MB แสดงเป็น KB */
export function formatSpeed(bytesPerSecond: number): string {
  const bps = Math.max(0, Number.isFinite(bytesPerSecond) ? bytesPerSecond : 0)
  const size = bps >= 1e6 ? `${(bps / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(bps / 1e3))} KB`
  return fill(th.queue.speed, { size })
}

/** เวลาที่เหลือ เช่น "เหลือ 1:05" (M:SS หรือ H:MM:SS เหมือนความยาวคลิป) */
export function formatEta(seconds: number): string {
  return fill(th.queue.eta, { time: formatDuration(seconds) })
}

/** "เน็ตหลุด กำลังลองใหม่ (ครั้งที่ n/3)" */
export function retryText(attempt: number): string {
  return fill(th.queue.retrying, { n: attempt })
}

/** มิลลิวินาทีที่เหลือก่อนคิวเริ่มต่อเอง (ไม่ติดลบ · เวลาอ่านไม่ได้ = 0) */
export function pausedRemainingMs(pausedUntil: string, now: number): number {
  const until = Date.parse(pausedUntil)
  return Number.isNaN(until) ? 0 : Math.max(0, until - now)
}

/** นับถอยหลังแบบ m:ss เช่น "9:59" (ปัดวินาทีขึ้น จะได้ไม่ขึ้น 0:00 ก่อนครบเวลาจริง) */
export function pausedCountdown(pausedUntil: string, now: number): string {
  const total = Math.ceil(pausedRemainingMs(pausedUntil, now) / 1000)
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`
}

/**
 * บรรทัดความคืบหน้าของงาน (ใช้ทั้งแถบคิวและแถวในชีต)
 * - กำลังลองใหม่เพราะเน็ตหลุด = ข้อความลองใหม่ · กำลังยกเลิก = "กำลังยกเลิก"
 * - กำลังทำ = ขั้นตอน · % · ความเร็ว · เวลาที่เหลือ (มีเท่าที่รู้) · ยังไม่รู้ขั้นตอน = "กำลังเริ่ม"
 * - รอคิว = "รอคิว" · สถานะอื่น = ข้อความว่าง
 */
export function progressLine(job: Job): string {
  if (job.status === "queued") return th.queue.waiting
  if (job.status !== "running") return ""
  if (job.cancelling) return th.queue.cancelling
  if (job.attempt !== undefined && job.attempt > 0) return retryText(job.attempt)
  if (job.stage === undefined) return th.queue.starting
  const parts: string[] = [th.queue.stages[job.stage]]
  if (job.progress !== undefined) parts.push(formatPercent(job.progress))
  if (job.speedBps !== undefined && job.speedBps > 0) parts.push(formatSpeed(job.speedBps))
  if (job.etaS !== undefined && job.etaS >= 0) parts.push(formatEta(job.etaS))
  return parts.join(" · ")
}
