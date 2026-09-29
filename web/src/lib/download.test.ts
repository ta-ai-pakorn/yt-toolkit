import { describe, expect, it, vi } from "vitest"

import { ApiError } from "./api"
import { downloadFile, parseContentDisposition } from "./download"

describe("parseContentDisposition", () => {
  it("อ่าน filename ในเครื่องหมายคำพูด", () => {
    expect(parseContentDisposition('attachment; filename="frame_00-00-04.jpg"')).toBe("frame_00-00-04.jpg")
  })

  it("อ่าน filename ที่ไม่มีเครื่องหมายคำพูด", () => {
    expect(parseContentDisposition("attachment; filename=frames.zip")).toBe("frames.zip")
  })

  it("filename* (UTF-8) มาก่อน filename สำรอง", () => {
    const header = `attachment; filename="contact-sheet.jpg"; filename*=UTF-8''${encodeURIComponent("คลิปทดสอบ - contact sheet.jpg")}`
    expect(parseContentDisposition(header)).toBe("คลิปทดสอบ - contact sheet.jpg")
  })

  it("filename* อยู่ก่อน filename ก็ยังใช้ filename*", () => {
    expect(parseContentDisposition(`attachment; filename*=utf-8''a%20b.jpg; filename="fallback.jpg"`)).toBe("a b.jpg")
  })

  it("filename* ที่ถอดรหัสไม่ได้ให้ใช้ filename สำรอง", () => {
    expect(parseContentDisposition(`attachment; filename="fallback.jpg"; filename*=UTF-8''%E0%A4%A`)).toBe("fallback.jpg")
  })

  it("filename* ที่ครอบด้วยเครื่องหมายคำพูดก็อ่านได้", () => {
    expect(parseContentDisposition(`attachment; filename*="UTF-8''a%20b.jpg"`)).toBe("a b.jpg")
  })

  it("filename* ใช้ charset ตามที่ระบุ (ISO-8859-1)", () => {
    expect(parseContentDisposition("attachment; filename*=ISO-8859-1''caf%E9.jpg")).toBe("café.jpg")
    expect(parseContentDisposition("attachment; filename*=iso-8859-1''%E9.jpg")).toBe("é.jpg")
  })

  it("charset ที่ไม่รู้จักหรือไบต์ไม่ตรงกับ charset → ใช้ filename สำรอง", () => {
    expect(parseContentDisposition(`attachment; filename="fallback.jpg"; filename*=x-nonsense''a.jpg`)).toBe("fallback.jpg")
    expect(parseContentDisposition(`attachment; filename="fallback.jpg"; filename*=UTF-8''%E9.jpg`)).toBe("fallback.jpg")
  })

  it("filename* ไม่มี charset (ไม่มี ' คั่น) ถือเป็น UTF-8", () => {
    expect(parseContentDisposition("attachment; filename*=a%20b.jpg")).toBe("a b.jpg")
  })

  it("อ่านเครื่องหมายคำพูดที่ escape ไว้ในชื่อ", () => {
    expect(parseContentDisposition('attachment; filename="a\\"b.jpg"')).toBe('a"b.jpg')
  })

  it("ไม่มีชื่อไฟล์ = null", () => {
    expect(parseContentDisposition(null)).toBeNull()
    expect(parseContentDisposition("")).toBeNull()
    expect(parseContentDisposition("inline")).toBeNull()
    expect(parseContentDisposition('attachment; filename=""')).toBeNull()
  })
})

describe("downloadFile", () => {
  it("โหลดสำเร็จ: บันทึกไฟล์ด้วยชื่อจาก Content-Disposition", async () => {
    const save = vi.fn()
    const fetcher = vi.fn().mockResolvedValue(
      new Response("jpegbytes", { status: 200, headers: { "Content-Disposition": 'attachment; filename="frame_00-00-04.jpg"' } }),
    )
    const name = await downloadFile("/api/cache/x/storyboard/f_0001.jpg?v=1&download=1", "fallback.jpg", { fetch: fetcher, save })
    expect(name).toBe("frame_00-00-04.jpg")
    expect(save).toHaveBeenCalledOnce()
    expect(save.mock.calls[0]?.[1]).toBe("frame_00-00-04.jpg")
    expect(await (save.mock.calls[0]?.[0] as Blob).text()).toBe("jpegbytes")
  })

  it("ไม่มีหัว Content-Disposition ใช้ชื่อสำรอง", async () => {
    const save = vi.fn()
    const fetcher = vi.fn().mockResolvedValue(new Response("x", { status: 200 }))
    expect(await downloadFile("/api/x", "fallback.zip", { fetch: fetcher, save })).toBe("fallback.zip")
  })

  it("backend ตอบ error: โยน ApiError พร้อมข้อความจาก envelope และไม่บันทึกไฟล์", async () => {
    const save = vi.fn()
    const body = { error: { code: "E_NO_STORYBOARD", message: "คลิปนี้ไม่มีภาพตัวอย่างแบบเร็ว", detail: null } }
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 404 }))
    const error = await downloadFile("/api/x", "a.zip", { fetch: fetcher, save }).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).code).toBe("E_NO_STORYBOARD")
    expect((error as ApiError).message).toBe("คลิปนี้ไม่มีภาพตัวอย่างแบบเร็ว")
    expect(save).not.toHaveBeenCalled()
  })

  it("error ที่ไม่ใช่ JSON ได้ข้อความกลางของแอพ", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response("<html>", { status: 502 }))
    const error = await downloadFile("/api/x", "a.zip", { fetch: fetcher, save: vi.fn() }).catch((e: unknown) => e)
    expect((error as ApiError).code).toBe("E_UNKNOWN")
    expect((error as ApiError).message).toMatch(/โหลดไฟล์ไม่สำเร็จ/)
  })

  it("ต่อ backend ไม่ได้: E_OFFLINE", async () => {
    const fetcher = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"))
    const error = await downloadFile("/api/x", "a.zip", { fetch: fetcher, save: vi.fn() }).catch((e: unknown) => e)
    expect((error as ApiError).code).toBe("E_OFFLINE")
  })
})
