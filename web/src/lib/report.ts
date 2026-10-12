import { th } from "@/i18n/th"

import { api, ApiError } from "./api"

/**
 * รายงานแจ้งปัญหา (M6 รอบ B · PRD 7.1): หน้าเว็บส่งแค่ข้อมูลของ error ไป POST /api/diagnostics
 * เซิร์ฟเวอร์สร้างรายงานทั้งหมดและซ่อนข้อมูลส่วนตัวที่จุดเดียว · โมดูลนี้ไม่มี React (เทสใน node ได้)
 */

/** ความยาวสูงสุดของ detail ที่ส่ง (เท่ากับ MAX_DETAIL ของ api/diagnostics.py): error จริงต้องไม่โดน 422 */
export const MAX_DETAIL = 4000
/** จำนวนบรรทัดของ stack ที่ใส่ต่อท้าย "<name>: <message>" ของ error ที่ไม่ใช่ ApiError */
export const STACK_LINES = 10

/** body ของ POST /api/diagnostics (ทุกช่องไม่บังคับ) */
export type ReportRequest = { jobId?: string; code?: string; detail?: string; context?: string; videoId?: string }

/** ที่ที่ error เกิด: context = แท็ก ASCII ของหน้าจอ (spec 1.3) เช่น "video-header" */
export type ReportWhere = { context: string; videoId?: string; jobId?: string }

export type CopyOutcome = { ok: true } | { ok: false; message: string }

// กฎเดียวกับ api/diagnostics.py PATTERNS: ค่าที่ไม่ผ่านกฎไม่ส่ง (ไม่ให้ปุ่มได้ 422 แทนรายงาน)
const PATTERNS = {
  jobId: /^[A-Za-z0-9_-]{1,64}$/,
  code: /^E_[A-Z0-9_]{1,40}$/,
  context: /^[a-z][a-z0-9-]{0,31}$/,
  videoId: /^[A-Za-z0-9_-]{11}$/,
} as const

/**
 * ทำ body ให้ผ่านกฎของเซิร์ฟเวอร์เสมอ: ช่องที่ผิดรูปถูกทิ้ง (code ที่ผิดรูปกลายเป็น E_UNKNOWN) · detail ตัดที่ MAX_DETAIL
 * เช่น /v/abc (videoId พิมพ์เองผิด) ยังได้รายงาน ไม่ใช่ 422
 */
export function cleanRequest(req: ReportRequest): ReportRequest {
  const out: ReportRequest = {}
  for (const key of ["jobId", "context", "videoId"] as const) {
    const value = req[key]
    if (value !== undefined && PATTERNS[key].test(value)) out[key] = value
  }
  if (req.code !== undefined) out.code = PATTERNS.code.test(req.code) ? req.code : "E_UNKNOWN"
  if (req.detail) out.detail = req.detail.slice(0, MAX_DETAIL)
  return out
}

/**
 * body ของรายงานจาก error ที่จับได้: ApiError = รหัสและ detail จากเซิร์ฟเวอร์ · Error อื่น = E_UNKNOWN + "<name>: <message>"
 * ตามด้วย stack ไม่เกิน 10 บรรทัด · ค่าอื่น = E_UNKNOWN ไม่มี detail
 */
export function reportRequest(error: unknown, where: ReportWhere): ReportRequest {
  const req: ReportRequest = { context: where.context, videoId: where.videoId, jobId: where.jobId }
  if (error instanceof ApiError) {
    req.code = error.code
    req.detail = error.detail ?? undefined
  } else if (error instanceof Error) {
    req.code = "E_UNKNOWN"
    const head = `${error.name}: ${error.message}`
    // Chrome (V8) ขึ้นต้น stack ด้วย "<name>: <message>" อยู่แล้ว: ตัดบรรทัดนั้นทิ้งไม่ให้หัวซ้ำ และยังได้เฟรมจริงครบ STACK_LINES
    const frames = error.stack ? error.stack.split("\n") : []
    if (frames[0] === head) frames.shift()
    const stack = frames.slice(0, STACK_LINES).join("\n")
    req.detail = stack ? `${head}\n${stack}` : head
  } else {
    req.code = "E_UNKNOWN"
  }
  return cleanRequest(req)
}

/** ขอรายงาน (Markdown) จากเซิร์ฟเวอร์ · api() ใส่ token ให้เอง · ต่อไม่ได้ = ApiError E_OFFLINE */
export async function fetchReport(req: ReportRequest, deps?: Parameters<typeof api>[2]): Promise<string> {
  const { report } = await api<{ report: string }>(
    "/diagnostics",
    { method: "POST", body: JSON.stringify(cleanRequest(req)) },
    deps,
  )
  return report
}

type CopyDeps = {
  clipboard?: Partial<Pick<Clipboard, "write" | "writeText">>
  ClipboardItem?: typeof ClipboardItem
  fetchReport?: (req: ReportRequest) => Promise<string>
}

/**
 * ขอรายงานแล้วคัดลอกลงคลิปบอร์ด · ไม่โยน error เลย
 * เริ่มขอรายงานทันทีในจังหวะที่กด แล้วส่ง Promise<Blob> ให้ ClipboardItem (แบบเดียวกับ copyImage ใน clipboard.ts)
 * การเขียนจึงยังอยู่ในจังหวะที่ผู้ใช้กด แม้รายงานมาถึงทีหลัง · ไม่มี ClipboardItem = รอรายงานแล้ว writeText
 * พลาด: ขอรายงานไม่ได้ = ข้อความของเซิร์ฟเวอร์ (ปิดโปรแกรมไปแล้ว = th.errors.offline) · คลิปบอร์ดไม่ยอม = th.errors.copyFailed
 */
export async function copyReport(req: ReportRequest, deps: CopyDeps = {}): Promise<CopyOutcome> {
  const clipboard = "clipboard" in deps ? deps.clipboard : globalThis.navigator?.clipboard
  const Item = "ClipboardItem" in deps ? deps.ClipboardItem : globalThis.ClipboardItem
  const text = (deps.fetchReport ?? fetchReport)(req)
  // ถ้าขอรายงานไม่สำเร็จ write จะล้มเองอยู่แล้ว: กันไม่ให้ Promise ตัวนี้กลายเป็น unhandled rejection อีกทาง
  text.catch(() => {})
  try {
    if (clipboard?.write && Item) {
      const blob = text.then((t) => new Blob([t], { type: "text/plain" }))
      // เบราว์เซอร์อาจปฏิเสธ write ก่อนอ่าน item (เช่น "Document is not focused"): ถ้าขอรายงานพลาดด้วย
      // Promise<Blob> นี้จะไม่มีใครรับ จึงกันไว้เหมือน text (ผลลัพธ์ยังมาจาก catch ข้างล่าง)
      blob.catch(() => {})
      await clipboard.write([new Item({ "text/plain": blob })])
    } else if (clipboard?.writeText) {
      await clipboard.writeText(await text)
    } else {
      throw new Error("clipboard unsupported")
    }
    return { ok: true }
  } catch {
    const failed = await text.then(
      () => null,
      (error: unknown) => error ?? new Error("report failed"),
    )
    if (failed !== null) return { ok: false, message: failed instanceof ApiError ? failed.message : th.errors.unknown }
    return { ok: false, message: th.errors.copyFailed }
  }
}
