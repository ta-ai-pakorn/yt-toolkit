import { QueryClient } from "@tanstack/react-query"
import { describe, expect, it } from "vitest"

import { th } from "@/i18n/th"

import { clearButton, CLIP_CACHE_KEYS, forgetClipCaches, importNotice, importTooLarge, TOO_LARGE_REQUEST } from "./local-data"

describe("clearButton", () => {
  it("มีขนาด: ป้ายตาม BRD (1.2 GB) และกดได้", () => {
    expect(clearButton({ cacheBytes: 1_200_000_000, workBytes: 0, reclaimableBytes: 1_200_000_000 })).toEqual({
      label: "ล้างข้อมูลชั่วคราว (1.2 GB)",
      size: "1.2 GB",
      disabled: false,
    })
  })

  it("ไม่มีอะไรให้ล้าง = กดไม่ได้ · ยังไม่รู้ขนาด = ป้ายไม่มีขนาดและกดไม่ได้", () => {
    expect(clearButton({ cacheBytes: 5, workBytes: 0, reclaimableBytes: 0 })).toMatchObject({ disabled: true })
    expect(clearButton(undefined)).toEqual({ label: th.general.clearTempPlain, size: null, disabled: true })
  })
})

describe("forgetClipCaches", () => {
  it("ลบข้อมูลของคลิปที่หายไปกับ cache ส่วนข้อมูลคลิป ประวัติ รายชื่อซับ และค่าตั้งคงไว้", () => {
    const client = new QueryClient()
    for (const key of [...CLIP_CACHE_KEYS.map((k) => [...k, "aqz-KE-bpKQ"]), ["video", "aqz-KE-bpKQ"], ["history", {}],
      ["subtitles", "aqz-KE-bpKQ"], ["settings"], ["storage"]]) {
      client.setQueryData(key, { cached: true })
    }
    forgetClipCaches(client)
    const left = client.getQueryCache().getAll().map((q) => q.queryKey[0])
    expect(left.sort()).toEqual(["history", "settings", "storage", "subtitles", "video"])
    expect(client.getQueryState(["storage"])?.isInvalidated).toBe(true)
  })
})

describe("import helpers", () => {
  it("ไฟล์เกิน 1 MB ไม่ส่ง · รายงานใช้ detail เดียวกับ 413 ของ backend", () => {
    expect(importTooLarge({ size: 1_048_576 })).toBe(false)
    expect(importTooLarge({ size: 1_048_577 })).toBe(true)
    expect(TOO_LARGE_REQUEST).toEqual({
      code: "E_SETTINGS_INVALID",
      detail: "file larger than 1048576 bytes",
      context: "settings-import",
    })
  })

  it("ข้อความหลังนำเข้า: สำเร็จ / ใช้โฟลเดอร์ในไฟล์ไม่ได้", () => {
    expect(importNotice({ warnings: [] })).toEqual({ kind: "success", message: "นำเข้าค่าตั้งแล้ว" })
    expect(importNotice({ warnings: ["outputDir"] })).toEqual({ kind: "warning", message: th.general.importedKeptFolder })
  })
})
