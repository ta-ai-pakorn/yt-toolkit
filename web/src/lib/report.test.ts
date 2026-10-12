import { describe, expect, it, vi } from "vitest"

import { th } from "@/i18n/th"

import { ApiError } from "./api"
import { cleanRequest, copyReport, fetchReport, MAX_DETAIL, reportRequest, STACK_LINES } from "./report"

const REPORT = "## รายงานปัญหา YT Toolkit\n- เวลา: 2026-10-12 10:00 (+07:00)\n"
const VIDEO = "dQw4w9WgXcQ"

class FakeItem {
  readonly items: Record<string, Promise<Blob> | Blob>
  constructor(items: Record<string, Promise<Blob> | Blob>) {
    this.items = items
  }
}
const Item = FakeItem as unknown as typeof ClipboardItem

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })
}

describe("reportRequest", () => {
  it("ApiError = รหัสและ detail จากเซิร์ฟเวอร์ พร้อมหน้าจอและคลิป", () => {
    const error = new ApiError(502, "E_YT_REFUSED", "ยูทูปไม่ยอมส่งไฟล์", "HTTP Error 403: Forbidden", null)
    expect(reportRequest(error, { context: "video-header", videoId: VIDEO })).toEqual({
      code: "E_YT_REFUSED",
      detail: "HTTP Error 403: Forbidden",
      context: "video-header",
      videoId: VIDEO,
    })
  })

  it("ApiError ที่ไม่มี detail = ไม่มีช่อง detail", () => {
    expect(reportRequest(new ApiError(0, "E_OFFLINE", "x", null, null), { context: "crash" })).toEqual({
      code: "E_OFFLINE",
      context: "crash",
    })
  })

  it("Error อื่น = E_UNKNOWN + ชื่อ: ข้อความ + stack ไม่เกิน 10 บรรทัด", () => {
    const error = new TypeError("x is undefined")
    // แบบ Chrome (V8): บรรทัดแรกของ stack คือ "<name>: <message>" อยู่แล้ว ต้องไม่ซ้ำ และยังได้ครบ 10 เฟรม
    error.stack = ["TypeError: x is undefined", ...Array.from({ length: 30 }, (_, i) => `    at f${i} (app.js:${i})`)].join("\n")
    const req = reportRequest(error, { context: "crash" })
    expect(req.code).toBe("E_UNKNOWN")
    const lines = req.detail!.split("\n")
    expect(lines[0]).toBe("TypeError: x is undefined")
    expect(lines).toHaveLength(1 + STACK_LINES)
    expect(lines[1]).toBe("    at f0 (app.js:0)")
    expect(lines.at(-1)).toBe("    at f9 (app.js:9)")
  })

  it("stack ที่ไม่มีบรรทัดหัว (เบราว์เซอร์อื่น) = หัว + 10 เฟรม", () => {
    const error = new Error("boom")
    error.stack = Array.from({ length: 30 }, (_, i) => `f${i}@app.js:${i}`).join("\n")
    const lines = reportRequest(error, { context: "crash" }).detail!.split("\n")
    expect(lines[0]).toBe("Error: boom")
    expect(lines).toHaveLength(1 + STACK_LINES)
    expect(lines.at(-1)).toBe("f9@app.js:9")
  })

  it("ค่าที่ไม่ใช่ error = E_UNKNOWN ไม่มี detail", () => {
    expect(reportRequest("boom", { context: "chunk" })).toEqual({ code: "E_UNKNOWN", context: "chunk" })
    expect(reportRequest(undefined, { context: "chunk" })).toEqual({ code: "E_UNKNOWN", context: "chunk" })
  })

  it("detail ยาวเกิน = ตัดที่ 4,000 ตัว (เซิร์ฟเวอร์ไม่ตอบ 422 กับ error จริง)", () => {
    const error = new ApiError(500, "E_UNKNOWN", "x", "d".repeat(9000), null)
    expect(reportRequest(error, { context: "crash" }).detail).toHaveLength(MAX_DETAIL)
  })
})

describe("cleanRequest: body ผ่านกฎของเซิร์ฟเวอร์เสมอ", () => {
  it("videoId / jobId / context ที่ผิดรูปถูกทิ้ง รหัสที่ผิดรูปเป็น E_UNKNOWN", () => {
    expect(
      cleanRequest({ code: "boom", videoId: "abc", jobId: "../x", context: "Video Header", detail: "d" }),
    ).toEqual({ code: "E_UNKNOWN", detail: "d" })
  })

  it("ค่าที่ถูกต้องผ่านครบ · detail ว่างไม่ส่ง", () => {
    const ok = { jobId: "01a1-b_2", code: "E_HTTP_502", context: "queue", videoId: VIDEO }
    expect(cleanRequest({ ...ok, detail: "" })).toEqual(ok)
  })
})

describe("fetchReport", () => {
  it("POST /api/diagnostics พร้อม token และ body ที่ทำความสะอาดแล้ว คืนข้อความรายงาน", async () => {
    const fetch = vi.fn().mockResolvedValue(jsonResponse(200, { report: REPORT }))
    await expect(fetchReport({ code: "E_NETWORK", videoId: "bad" }, { fetch, token: "tok" })).resolves.toBe(REPORT)
    const [url, init] = fetch.mock.calls[0]
    expect(url).toBe("/api/diagnostics")
    expect(init.method).toBe("POST")
    expect(new Headers(init.headers).get("X-Toolkit-Token")).toBe("tok")
    expect(JSON.parse(init.body)).toEqual({ code: "E_NETWORK" })
  })
})

// unhandled rejection ใด ๆ ทำให้ vitest ล้มทั้งชุดเอง จึงไม่ต้องดักเพิ่ม (ทุกกรณีข้างล่างต้องไม่มี)
describe("copyReport", () => {
  it("มี ClipboardItem = เขียนทันทีด้วย text/plain ที่เป็น Promise (ยังอยู่ในจังหวะที่ผู้ใช้กด)", async () => {
    let resolve: (text: string) => void = () => {}
    const fetchReport = vi.fn(() => new Promise<string>((r) => (resolve = r)))
    const write = vi.fn(async (items: ClipboardItems) => {
      const blob = await (items[0] as unknown as FakeItem).items["text/plain"]
      expect(await blob.text()).toBe(REPORT)
    })
    const done = copyReport({ code: "E_X" }, { clipboard: { write }, ClipboardItem: Item, fetchReport })
    expect(write).toHaveBeenCalledTimes(1) // ก่อนรายงานมาถึง
    expect(fetchReport).toHaveBeenCalledWith({ code: "E_X" })
    resolve(REPORT)
    await expect(done).resolves.toEqual({ ok: true })
  })

  it("ไม่มี ClipboardItem = รอรายงานแล้ว writeText", async () => {
    const writeText = vi.fn(async () => {})
    const outcome = await copyReport({}, { clipboard: { writeText }, ClipboardItem: undefined, fetchReport: async () => REPORT })
    expect(outcome).toEqual({ ok: true })
    expect(writeText).toHaveBeenCalledWith(REPORT)
  })

  it("เซิร์ฟเวอร์ตอบ error = ข้อความของเซิร์ฟเวอร์", async () => {
    const write = vi.fn(async (items: ClipboardItems) => {
      await (items[0] as unknown as FakeItem).items["text/plain"]
    })
    const fetchReport = () => Promise.reject(new ApiError(422, "E_BAD_REQUEST", "ข้อมูลที่ส่งมาไม่ถูกต้อง ลองรีเฟรชหน้าเว็บ", null, null))
    await expect(copyReport({}, { clipboard: { write }, ClipboardItem: Item, fetchReport })).resolves.toEqual({
      ok: false,
      message: "ข้อมูลที่ส่งมาไม่ถูกต้อง ลองรีเฟรชหน้าเว็บ",
    })
  })

  it("ปิดโปรแกรมไปแล้ว (E_OFFLINE) = th.errors.offline", async () => {
    const fetch = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"))
    const writeText = vi.fn(async () => {})
    const outcome = await copyReport(
      {},
      { clipboard: { writeText }, ClipboardItem: undefined, fetchReport: (req) => fetchReport(req, { fetch, token: "t" }) },
    )
    expect(outcome).toEqual({ ok: false, message: th.errors.offline })
    expect(writeText).not.toHaveBeenCalled()
  })

  it("error ที่ไม่ใช่ ApiError ตอนขอรายงาน = th.errors.unknown", async () => {
    const outcome = await copyReport({}, { clipboard: { writeText: vi.fn() }, ClipboardItem: undefined, fetchReport: () => Promise.reject(new Error("x")) })
    expect(outcome).toEqual({ ok: false, message: th.errors.unknown })
  })

  it("คลิปบอร์ดไม่ยอม = th.errors.copyFailed (คัดลอกไม่สำเร็จ ลองอีกครั้ง)", async () => {
    const write = vi.fn(() => Promise.reject(new DOMException("Document is not focused", "NotAllowedError")))
    const outcome = await copyReport({}, { clipboard: { write }, ClipboardItem: Item, fetchReport: async () => REPORT })
    expect(outcome).toEqual({ ok: false, message: "คัดลอกไม่สำเร็จ ลองอีกครั้ง" })
  })

  it("ขอรายงานพลาด + เบราว์เซอร์ปฏิเสธ write โดยไม่อ่าน item = ข้อความของเซิร์ฟเวอร์ ไม่มี unhandled rejection", async () => {
    const write = vi.fn(() => Promise.reject(new DOMException("Document is not focused", "NotAllowedError")))
    const fetchReport = () => Promise.reject(new ApiError(0, "E_OFFLINE", th.errors.offline, null, null))
    await expect(copyReport({}, { clipboard: { write }, ClipboardItem: Item, fetchReport })).resolves.toEqual({
      ok: false,
      message: th.errors.offline,
    })
    // ให้ Promise<Blob> ที่ไม่มีใครอ่านทำงานจนจบ ก่อน vitest ตัดสิน unhandled rejection
    await new Promise((r) => setTimeout(r, 0))
  })

  it("ไม่มีคลิปบอร์ดเลย = copyFailed", async () => {
    await expect(copyReport({}, { clipboard: undefined, ClipboardItem: undefined, fetchReport: async () => REPORT })).resolves.toEqual({
      ok: false,
      message: th.errors.copyFailed,
    })
  })
})
