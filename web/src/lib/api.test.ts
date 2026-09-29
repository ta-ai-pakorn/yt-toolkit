import { describe, expect, it, vi } from "vitest"

import { fill } from "@/i18n/th"

import { ApiError, api, readToken } from "./api"
import { pasteShortcut } from "./platform"

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })
}

describe("api", () => {
  it("GET ไม่แนบ token", async () => {
    const fetch = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }))
    await api("/ping", {}, { fetch, token: "tok" })
    const [url, init] = fetch.mock.calls[0]
    expect(url).toBe("/api/ping")
    expect(new Headers(init.headers).get("X-Toolkit-Token")).toBeNull()
  })

  it("POST แนบ token และ Content-Type", async () => {
    const fetch = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }))
    await api("/shutdown", { method: "POST", body: JSON.stringify({ force: false }) }, { fetch, token: "tok" })
    const headers = new Headers(fetch.mock.calls[0][1].headers)
    expect(headers.get("X-Toolkit-Token")).toBe("tok")
    expect(headers.get("Content-Type")).toBe("application/json")
  })

  it("HEAD ไม่แนบ token", async () => {
    const fetch = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }))
    await api("/ping", { method: "HEAD" }, { fetch, token: "tok" })
    expect(new Headers(fetch.mock.calls[0][1].headers).get("X-Toolkit-Token")).toBeNull()
  })

  it("body เป็น FormData ไม่บังคับ Content-Type (ให้เบราว์เซอร์ใส่ boundary เอง)", async () => {
    const fetch = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }))
    await api("/upload", { method: "POST", body: new FormData() }, { fetch, token: "tok" })
    const headers = new Headers(fetch.mock.calls[0][1].headers)
    expect(headers.get("X-Toolkit-Token")).toBe("tok")
    expect(headers.get("Content-Type")).toBeNull()
  })

  it("POST ไม่มี body ไม่ใส่ Content-Type", async () => {
    const fetch = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }))
    await api("/tools/ffmpeg/install", { method: "POST" }, { fetch, token: "tok" })
    expect(new Headers(fetch.mock.calls[0][1].headers).get("Content-Type")).toBeNull()
  })

  it("ผู้เรียกกำหนด Content-Type เองแล้ว ใช้ตามนั้น", async () => {
    const fetch = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }))
    await api("/x", { method: "POST", body: "a=1", headers: { "content-type": "text/plain" } }, { fetch, token: "tok" })
    expect(new Headers(fetch.mock.calls[0][1].headers).get("Content-Type")).toBe("text/plain")
  })

  it("แปลง error ของ backend เป็น ApiError", async () => {
    const body = { error: { code: "E_TOOL_INSTALL_FAILED", message: "โหลดไม่สำเร็จ", detail: "x" } }
    const fetch = vi.fn().mockResolvedValue(jsonResponse(502, body))
    const error = (await api("/tools/ffmpeg/install", { method: "POST" }, { fetch, token: "t" }).catch((e) => e)) as ApiError
    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(502)
    expect(error.code).toBe("E_TOOL_INSTALL_FAILED")
    expect(error.message).toBe("โหลดไม่สำเร็จ")
    expect(error.detail).toBe("x")
  })

  it("ตอบ 409 แบบไม่มี error object ยังได้ ApiError พร้อม body", async () => {
    const fetch = vi.fn().mockResolvedValue(jsonResponse(409, { pendingJobs: 2 }))
    const error = (await api("/shutdown", { method: "POST" }, { fetch, token: "t" }).catch((e) => e)) as ApiError
    expect(error.status).toBe(409)
    expect(error.code).toBe("E_UNKNOWN")
    expect(error.body).toEqual({ pendingJobs: 2 })
  })

  it("fetch ล้มเพราะต่อ backend ไม่ได้ → ApiError E_OFFLINE ภาษาไทย", async () => {
    const fetch = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"))
    const error = (await api("/health", {}, { fetch, token: "t" }).catch((e) => e)) as ApiError
    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(0)
    expect(error.code).toBe("E_OFFLINE")
    expect(error.message).toBe("เชื่อมต่อโปรแกรมไม่ได้ ถ้าปิดโปรแกรมไปแล้ว เปิดใหม่ด้วย start.bat")
    expect(error.detail).toBe("TypeError: Failed to fetch")
    expect(error.body).toBeNull()
  })
})

describe("pasteShortcut", () => {
  it("แสดงตามระบบ", () => {
    expect(pasteShortcut("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)")).toBe("⌘V")
    expect(pasteShortcut("Mozilla/5.0 (Windows NT 10.0; Win64; x64)")).toBe("Ctrl+V")
  })
})

describe("readToken", () => {
  function docWith(meta: { content: string } | null) {
    return { querySelector: () => meta } as unknown as Document
  }

  it("อ่านค่าจาก meta yt-token", () => {
    expect(readToken(docWith({ content: "abc123" }))).toBe("abc123")
  })

  it("ไม่มี meta คืนสตริงว่าง", () => {
    expect(readToken(docWith(null))).toBe("")
  })
})

describe("fill", () => {
  it("แทนค่าตามคีย์ที่รู้จัก", () => {
    expect(fill("มีงานค้าง {n} งาน", { n: 3 })).toBe("มีงานค้าง 3 งาน")
  })

  it("คีย์ที่ไม่รู้จักคงเครื่องหมายไว้ ไม่กลายเป็น undefined", () => {
    expect(fill("มีงานค้าง {n} งาน {x}", { n: 3 })).toBe("มีงานค้าง 3 งาน {x}")
  })
})
