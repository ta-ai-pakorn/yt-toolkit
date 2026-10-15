/**
 * ชื่อโฟลเดอร์/ไฟล์ตามรูปแบบชื่อไฟล์ (M6 รอบ A spec 2.2) — ตัวเดียวกับ files.plan_names ของ backend ทุกตัวอักษร
 *
 * หน้าเว็บใช้ทำบรรทัด "ตัวอย่าง: …" ในหน้าตั้งค่าโดยไม่เรียก API (AC-OUT-10) ชื่อไฟล์จริงตั้งที่ backend เสมอ
 * ทั้งสองฝั่งเทียบกันด้วย tests/fixtures/names/{cases,golden}.json (filename-parity.test.ts) ห้ามแก้ golden ให้เทสผ่าน
 *
 * จุดที่ต้องเลียน Python ให้ตรง:
 * - ความยาวนับเป็น UTF-16 code unit (`string.length`) เหมือน files._u16
 * - `\s` ของ Python ไม่เท่ากับของ JS: PY_WS = ช่องว่างตาม str.isspace() (มี \x1c-\x1f \x85 ไม่มี U+FEFF)
 * - ตัวที่ทิ้ง: \ / : * ? " < > | และหมวด Cc Cf Cs ตรวจทีละ code point
 * - ตัดชื่อทีละ code point ไม่ทิ้งสระ/วรรณยุกต์ (หมวด M) ไว้ตัวแรกหลังรอยตัด แล้วตัด "." และช่องว่างท้ายชื่อ
 */
import type { Settings } from "./types"

export type FilenameStyle = Settings["filenameStyle"]

/** ลำดับเดียวกับ files.NAME_STYLES / settings.FILENAME_STYLES ของ backend (ลำดับที่แสดงในหน้าตั้งค่า) */
export const FILENAME_STYLES = ["title", "title-channel", "title-quality"] as const satisfies readonly FilenameStyle[]

export type NameInput = {
  baseLen: number
  title: string
  clipId: string
  suffix: string
  ext: string
  style?: FilenameStyle
  uploader?: string
  quality?: string | null
}

export const PATH_LIMIT = 240
export const TITLE_MAX = 100
export const TAIL_RESERVE = 30
export const TAIL_MAX = 60
export const UNIQUE_RESERVE = 5
export const CHANNEL_SEP = " - "
const MIN_TITLE = 8
const QUALITY_LABEL = /^[a-z0-9 ]{1,16}$/

// ช่องว่างตาม str.isspace() ของ Python (ตรงกับ \s ของ re ใน Python) ไม่ใช่ \s ของ JS: ครบ 29 ตัว
const PY_WS_CODES = [
  0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x85, 0xa0, 0x1680,
  0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007, 0x2008, 0x2009, 0x200a,
  0x2028, 0x2029, 0x202f, 0x205f, 0x3000,
]
// ตัวอักษรจริงในวงเล็บ [] (ไม่ใช้ escape แบบ backslash-u ในซอร์ส) · ไม่มีตัวไหนมีความหมายพิเศษในวงเล็บ
const PY_WS_CLASS = String.fromCodePoint(...PY_WS_CODES)
const PY_WS = new RegExp(`[${PY_WS_CLASS}]+`, "gu")
const PY_WS_EDGES = new RegExp(`^[${PY_WS_CLASS}]+|[${PY_WS_CLASS}]+$`, "gu")
const FORBIDDEN = new Set(["\\", "/", ":", "*", "?", '"', "<", ">", "|"])
const DROPPED_CATEGORY = /^[\p{Cc}\p{Cf}\p{Cs}]$/u
const MARK = /^\p{M}$/u
const TRAILING_DOTS = /[. ]+$/

const RESERVED = new Set<string>([
  "CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
  ...Array.from({ length: 9 }, (_, i) => `COM${i + 1}`),
  ...Array.from({ length: 9 }, (_, i) => `LPT${i + 1}`),
  // Windows ถือเลขยกกำลัง ¹ ² ³ เป็นเลขพอร์ตด้วย
  ...["COM", "LPT"].flatMap((dev) => ["¹", "²", "³"].map((sup) => `${dev}${sup}`)),
])

export class PathTooLongError extends Error {
  constructor() {
    super("path too long")
    this.name = "PathTooLongError"
  }
}

function pyStrip(text: string): string {
  return text.replace(PY_WS_EDGES, "")
}

/** files.safe_component: ชื่อที่เป็นส่วนหนึ่งของ path บน Windows ได้ · เหลือว่าง = fallback */
export function safeComponent(text: string, fallback: string): string {
  const spaced = text.replace(PY_WS, " ")
  let kept = ""
  for (const ch of spaced) {
    if (!FORBIDDEN.has(ch) && !DROPPED_CATEGORY.test(ch)) kept += ch
  }
  const name = pyStrip(kept.replace(PY_WS, " ")).replace(TRAILING_DOTS, "")
  if (!name) return fallback
  const head = pyStrip(name.split(".")[0] ?? "").toUpperCase()
  return RESERVED.has(head) ? `_${name}` : name
}

/** files.truncate_title: ยาวไม่เกิน limit (UTF-16) ไม่ตัดกลางคู่ surrogate และไม่ทิ้งสระ/วรรณยุกต์ไว้หลังรอยตัด */
export function truncateTitle(text: string, limit: number): string {
  if (text.length <= limit) return text.replace(TRAILING_DOTS, "")
  const points = Array.from(text)
  let cut = 0
  let used = 0
  for (const ch of points) {
    used += ch.length
    if (used > limit) break
    cut += 1
  }
  while (cut > 0 && MARK.test(points[cut] ?? "")) cut -= 1
  return points.slice(0, cut).join("").replace(TRAILING_DOTS, "")
}

function stem(short: string, channel: string, avail: number): string {
  if (!channel) return short.length <= avail ? short : truncateTitle(short, avail)
  const joined = `${short}${CHANNEL_SEP}${channel}`
  if (joined.length <= avail) return joined
  const sep = CHANNEL_SEP.length
  const cut = truncateTitle(short, Math.max(avail - sep - channel.length, MIN_TITLE))
  if (cut && `${cut}${CHANNEL_SEP}${channel}`.length <= avail) return `${cut}${CHANNEL_SEP}${channel}`
  const room = avail - cut.length - sep
  const shortChannel = cut && room >= 1 ? truncateTitle(channel, room) : ""
  if (shortChannel) return `${cut}${CHANNEL_SEP}${shortChannel}`
  return truncateTitle(short, avail)
}

/** files.plan_names: (ชื่อโฟลเดอร์ของคลิป, ชื่อไฟล์) · path ยาวเกินแม้ใช้รหัสคลิป = PathTooLongError */
export function planNames(input: NameInput): { folder: string; file: string } {
  const { baseLen, title, clipId, suffix, ext, style = "title", uploader = "", quality = null } = input
  if (!(FILENAME_STYLES as readonly string[]).includes(style)) throw new Error(`unknown filename style: ${style}`)
  if (quality !== null && !QUALITY_LABEL.test(quality)) throw new Error(`bad quality label: ${quality}`)
  const qualityPart = style === "title-quality" && quality ? ` (${quality})` : ""
  const tail = `${qualityPart}${suffix}.${ext}`
  if (tail.length > TAIL_MAX) throw new Error("suffix + extension longer than TAIL_MAX")
  const t = safeComponent(title, clipId)
  const budget = PATH_LIMIT - (baseLen + 1) - ` [${clipId}]`.length - 1 - TAIL_RESERVE - UNIQUE_RESERVE
  const cap = Math.floor(budget / 2)
  const short = cap >= MIN_TITLE ? truncateTitle(t, Math.min(TITLE_MAX, cap)) : ""
  let folder: string
  let file: string
  if (short) {
    folder = `${short} [${clipId}]`
    const avail = budget - short.length + TAIL_RESERVE - tail.length
    const channel = style === "title-channel" ? safeComponent(uploader, "") : ""
    file = `${stem(short, channel, avail) || clipId}${tail}`
  } else {
    // โฟลเดอร์ลึกจนต้องใช้รหัสคลิป: ทิ้งส่วนคุณภาพ ได้ชื่อเดียวกับแบบ title (เลือกรูปแบบชื่อแล้วโหลดไม่ล้ม)
    folder = clipId
    file = `${clipId}${suffix}.${ext}`
  }
  if (baseLen + 1 + folder.length + 1 + file.length > PATH_LIMIT - UNIQUE_RESERVE) throw new PathTooLongError()
  return { folder, file }
}
