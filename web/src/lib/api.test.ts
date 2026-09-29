import { describe, expect, it, vi } from "vitest"

import { ApiError, api } from "./api"
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
})

describe("pasteShortcut", () => {
  it("แสดงตามระบบ", () => {
    expect(pasteShortcut("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)")).toBe("⌘V")
    expect(pasteShortcut("Mozilla/5.0 (Windows NT 10.0; Win64; x64)")).toBe("Ctrl+V")
  })
})
