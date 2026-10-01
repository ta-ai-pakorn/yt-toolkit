import { describe, expect, it, vi } from "vitest"

import {
  openOutputFolder,
  patchSettings,
  SETTINGS_KEY,
  settingsQuery,
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
