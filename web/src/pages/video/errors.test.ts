import { describe, expect, it } from "vitest"

import { ApiError } from "@/lib/api"

import { canRetry, errorMessage, hasCode } from "./errors"

const err = (code: string) => new ApiError(400, code, "ข้อความ", null, null)

describe("canRetry", () => {
  it.each([
    "E_LIVE_NOT_READY",
    "E_VIDEO_PRIVATE",
    "E_VIDEO_UNAVAILABLE",
    "E_GEO_BLOCKED",
    "E_AGE_RESTRICTED",
    "E_BOT_CHECK",
    "E_TRANSLATION_BLOCKED",
    "E_NO_SUBTITLES",
  ])(
    "%s ลองใหม่ไม่ช่วย ซ่อนปุ่ม",
    (code) => {
      expect(canRetry(err(code))).toBe(false)
    },
  )

  it.each(["E_NETWORK", "E_OFFLINE", "E_UNKNOWN", "E_ไม่รู้จัก"])("%s ยังให้ลองใหม่", (code) => {
    expect(canRetry(err(code))).toBe(true)
  })

  it("error ที่ไม่ใช่ ApiError ให้ลองใหม่ได้", () => {
    expect(canRetry(new Error("boom"))).toBe(true)
  })
})

describe("hasCode", () => {
  it("ตรงรหัสของ ApiError เท่านั้น", () => {
    expect(hasCode(err("E_TRANSLATION_BLOCKED"), "E_TRANSLATION_BLOCKED")).toBe(true)
    expect(hasCode(err("E_BOT_CHECK"), "E_TRANSLATION_BLOCKED")).toBe(false)
    expect(hasCode(new Error("E_TRANSLATION_BLOCKED"), "E_TRANSLATION_BLOCKED")).toBe(false)
    expect(hasCode(null, "E_TRANSLATION_BLOCKED")).toBe(false)
  })
})

describe("errorMessage", () => {
  it("ใช้ข้อความจาก envelope", () => {
    expect(errorMessage(err("E_VIDEO_PRIVATE"), "สำรอง")).toBe("ข้อความ")
  })

  it("error อื่นใช้ข้อความสำรอง", () => {
    expect(errorMessage(new Error("boom"), "สำรอง")).toBe("สำรอง")
  })
})
