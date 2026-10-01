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

/** วันที่เผยแพร่แบบไทย เช่น "30 พฤษภาคม 2551" (พ.ศ.) · วันที่ที่อ่านไม่ได้ = ข้อความว่าง */
export function formatPublished(iso: string): string {
  // วันที่จาก backend เป็น YYYY-MM-DD (ไม่มีเวลา) อ่านเป็น UTC แล้วแสดงเป็น UTC จะได้วันเดิมไม่ว่าเครื่องอยู่เขตเวลาไหน
  const time = Date.parse(iso)
  if (Number.isNaN(time)) return ""
  return new Intl.DateTimeFormat("th-TH", { dateStyle: "long", timeZone: "UTC" }).format(time)
}

/** ลิงก์ youtu.be ที่เปิดคลิปตรงวินาทีนั้น (ตัดเศษวินาทีทิ้ง ไม่ปัดขึ้น เหมือน timecode) */
export function youtubeLinkAt(videoId: string, ms: number): string {
  const seconds = Math.max(0, Math.floor((Number.isFinite(ms) ? ms : 0) / 1000))
  return `https://youtu.be/${videoId}?t=${seconds}`
}

/**
 * ลิงก์หน้าคลิปบนยูทูป (https://www.youtube.com/watch?v=…) · ใส่ ms = เปิดตรงวินาทีนั้น (&t=…s ตัดเศษทิ้ง เหมือน timecode)
 * ใช้กับปุ่ม "เปิดในยูทูป" ที่หัวคลิป และรายการ "เปิดในยูทูปตรงเวลานี้" ในเมนูภาพเฟรม
 */
export function youtubeWatchUrl(videoId: string, ms?: number): string {
  const base = `https://www.youtube.com/watch?v=${encodeURIComponent(videoId)}`
  if (ms === undefined) return base
  const seconds = Math.max(0, Math.floor((Number.isFinite(ms) ? ms : 0) / 1000))
  return `${base}&t=${seconds}s`
}

// ตัวเลขแบบย่อของไทย ("1.2 แสน", "3.4 ล้าน"): compactDisplay long ได้หน่วยเป็นคำไทย (short ได้ "123K" แบบอังกฤษ)
const compact = new Intl.NumberFormat("th", { notation: "compact", compactDisplay: "long" })
const full = new Intl.NumberFormat("th")

const count = (n: number) => (Number.isFinite(n) && n > 0 ? Math.floor(n) : 0)

/** ตัวเลขย่อสำหรับแถวข้อมูลคลิป เช่น 123456 → "1.2 แสน" · ค่าที่ไม่ใช่ตัวเลขจริงหรือติดลบ = "0" */
export function formatCompact(n: number): string {
  return compact.format(count(n))
}

/** ตัวเลขเต็มมีจุลภาค เช่น 123456 → "123,456" (ใช้ในชื่อสำหรับโปรแกรมอ่านหน้าจอ) */
export function formatCount(n: number): string {
  return full.format(count(n))
}

/** แท็กของคลิปสำหรับคัดลอก: คั่นด้วย ", " ตามลำดับเดิม (ตัดช่องว่างหัวท้าย ข้ามแท็กว่าง) */
export function formatTags(tags: readonly string[]): string {
  return tags
    .map((tag) => tag.trim())
    .filter((tag) => tag !== "")
    .join(", ")
}

/**
 * ขนาดไฟล์แบบฐานสิบ (1 MB = 1,000,000 ไบต์ ตามกติกาของ PRD): ตั้งแต่ 1 GB เป็น GB ทศนิยม 1 ตำแหน่ง
 * · ต่ำกว่า 10 MB มีทศนิยม 1 ตำแหน่ง (อย่างน้อย 0.1 MB) · นอกนั้น MB จำนวนเต็ม · ค่าที่ไม่ใช่ตัวเลขจริงหรือไม่เกิน 0 = "0 MB"
 */
export function formatBytes(bytes: number): string {
  const safe = Number.isFinite(bytes) && bytes > 0 ? bytes : 0
  if (safe === 0) return "0 MB"
  if (safe >= 1e9) return `${(safe / 1e9).toFixed(1)} GB`
  const mb = safe / 1e6
  return mb < 10 ? `${Math.max(0.1, Math.round(mb * 10) / 10).toFixed(1)} MB` : `${Math.round(mb)} MB`
}
