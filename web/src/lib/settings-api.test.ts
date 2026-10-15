import { describe, expect, it, vi } from "vitest"

import {
  clearStorage,
  exportSettings,
  importSettings,
  MAX_SETTINGS_FILE_BYTES,
  openOutputFolder,
  patchSettings,
  SETTINGS_KEY,
  settingsQuery,
  STORAGE_KEY,
  storageQuery,
} from "./settings-api"

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

describe("settings-api", () => {
  it("patchSettings ส่ง PATCH พร้อม JSON body และ token", async () => {
    const settings = { concurrency: 3 }
    const fetch = vi.fn().mockResolvedValue(jsonResponse(200, settings))
    await expect(
      patchSettings({ concurrency: 3 }, { fetch, token: "tok" })
    ).resolves.toEqual(settings)
    const [url, init] = fetch.mock.calls[0]
    expect(url).toBe("/api/settings")
    expect(init.method).toBe("PATCH")
    expect(JSON.parse(init.body)).toEqual({ concurrency: 3 })
    const headers = new Headers(init.headers)
    expect(headers.get("X-Toolkit-Token")).toBe("tok")
    expect(headers.get("Content-Type")).toBe("application/json")
  })

  it("settingsQuery อ่าน GET /settings ด้วยคีย์ ['settings']", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(jsonResponse(200, { theme: "dark" }))
    const query = settingsQuery({ fetch })
    expect(query.queryKey).toEqual(["settings"])
    expect(SETTINGS_KEY).toEqual(["settings"])
    await expect(query.queryFn()).resolves.toEqual({ theme: "dark" })
    expect(fetch.mock.calls[0][0]).toBe("/api/settings")
  })

  it("openOutputFolder POST พร้อม token · เขียนไม่ได้ได้ ApiError", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(200, { ok: true }))
      .mockResolvedValueOnce(
        jsonResponse(422, {
          error: {
            code: "E_OUTPUT_NOT_WRITABLE",
            message: "เขียนไฟล์ในโฟลเดอร์นี้ไม่ได้",
          },
        })
      )
    await openOutputFolder({ fetch, token: "tok" })
    const [url, init] = fetch.mock.calls[0]
    expect(`${init.method} ${url}`).toBe("POST /api/settings/open-output")
    expect(new Headers(init.headers).get("X-Toolkit-Token")).toBe("tok")
    await expect(
      openOutputFolder({ fetch, token: "tok" })
    ).rejects.toMatchObject({ code: "E_OUTPUT_NOT_WRITABLE" })
  })
})

// M6 รอบ A: สำรอง/นำเข้าค่าตั้ง (spec 4.3) และข้อมูลชั่วคราว (spec 3.4)
describe("settings-api M6 รอบ A", () => {
  it("exportSettings โหลด GET /api/settings/export แล้วบันทึกด้วยชื่อจาก Content-Disposition", async () => {
    const fetch = vi.fn().mockResolvedValue(
      new Response("{}\n", {
        status: 200,
        headers: { "Content-Disposition": "attachment; filename=\"yt-toolkit-settings-2026-10-14.json\"" },
      })
    )
    const save = vi.fn()
    await expect(exportSettings({ fetch, save })).resolves.toBe("yt-toolkit-settings-2026-10-14.json")
    expect(fetch).toHaveBeenCalledWith("/api/settings/export")
    expect(save).toHaveBeenCalledWith(expect.any(Blob), "yt-toolkit-settings-2026-10-14.json")
  })

  it("exportSettings ไม่มี Content-Disposition ใช้ชื่อสำรอง", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }))
    const save = vi.fn()
    await expect(exportSettings({ fetch, save })).resolves.toBe("yt-toolkit-settings.json")
  })

  it("importSettings ส่ง POST เนื้อไฟล์ดิบพร้อม token และ Content-Type JSON คืน {settings, warnings}", async () => {
    const body = { settings: { theme: "dark" }, warnings: ["outputDir"] }
    const fetch = vi.fn().mockResolvedValue(jsonResponse(200, body))
    const text = '{"app": "yt-toolkit", "schema": 1, "settings": {"theme": "dark"}}'
    await expect(importSettings(text, { fetch, token: "tok" })).resolves.toEqual(body)
    const [url, init] = fetch.mock.calls[0]
    expect(`${init.method} ${url}`).toBe("POST /api/settings/import")
    expect(init.body).toBe(text) // ไม่ parse ไม่แก้ backend ตรวจเอง
    const headers = new Headers(init.headers)
    expect(headers.get("X-Toolkit-Token")).toBe("tok")
    expect(headers.get("Content-Type")).toBe("application/json")
  })

  it("importSettings ไฟล์ผิดรูปแบบได้ ApiError E_SETTINGS_INVALID พร้อม status", async () => {
    const fetch = vi.fn().mockResolvedValue(
      jsonResponse(413, { error: { code: "E_SETTINGS_INVALID", message: "ไฟล์นี้ใช้ไม่ได้", detail: "file larger than 1048576 bytes" } })
    )
    await expect(importSettings("x", { fetch, token: "tok" })).rejects.toMatchObject({
      status: 413,
      code: "E_SETTINGS_INVALID",
      detail: "file larger than 1048576 bytes",
    })
  })

  it("storageQuery อ่าน GET /storage ด้วยคีย์ ['storage'] · clearStorage POST พร้อม token", async () => {
    const usage = { cacheBytes: 1_200_000_000, workBytes: 5, reclaimableBytes: 1_200_000_005 }
    const fetch = vi.fn().mockResolvedValueOnce(jsonResponse(200, usage)).mockResolvedValueOnce(jsonResponse(200, { freedBytes: 42 }))
    const query = storageQuery({ fetch })
    expect(query.queryKey).toEqual(["storage"])
    expect(STORAGE_KEY).toEqual(["storage"])
    await expect(query.queryFn()).resolves.toEqual(usage)
    expect(fetch.mock.calls[0][0]).toBe("/api/storage")
    await expect(clearStorage({ fetch, token: "tok" })).resolves.toEqual({ freedBytes: 42 })
    const [url, init] = fetch.mock.calls[1]
    expect(`${init.method} ${url}`).toBe("POST /api/storage/clear")
    expect(new Headers(init.headers).get("X-Toolkit-Token")).toBe("tok")
  })

  it("เพดานไฟล์ค่าตั้ง 1 MB ตรงกับ backend", () => {
    expect(MAX_SETTINGS_FILE_BYTES).toBe(1_048_576)
  })
})
