import { describe, expect, it } from "vitest"

import { th } from "@/i18n/th"
import { ApiError } from "@/lib/api"
import { PRESETS } from "@/lib/sub-options"
import type { Settings } from "@/lib/types"

import { CAPTURE_QUALITIES, choicePatch, displayed, languageOptions, outputDirPatch, serverMessage } from "./general-form"

const SAVED: Settings = {
  outputDir: "C:\\Users\\u\\Videos\\YT-Toolkit",
  videoDefault: "compat-1080",
  audioDefault: "m4a",
  audioLanguage: "original",
  mp3Kbps: 192,
  subPreset: "medium",
  subCustom: PRESETS.medium,
  concurrency: 2,
  sponsorblockDefault: [],
  autoSharpFrames: true,
  captureQuality: "max",
  theme: "system",
  filenameStyle: "title",
  statsResetAt: null,
  lastUsed: {},
}

describe("outputDirPatch", () => {
  it("เปลี่ยนจริงส่งเฉพาะช่องโฟลเดอร์ และตัดช่องว่างหัวท้าย", () => {
    expect(outputDirPatch("  D:\\คลิป  ", SAVED.outputDir)).toEqual({ outputDir: "D:\\คลิป" })
  })
  it("เท่าค่าที่บันทึกอยู่ (แม้มีช่องว่างเกิน) ไม่ต้องบันทึก", () => {
    expect(outputDirPatch(SAVED.outputDir, SAVED.outputDir)).toBeNull()
    expect(outputDirPatch(`${SAVED.outputDir} `, SAVED.outputDir)).toBeNull()
  })
  it("ช่องว่างล้วนหรือว่างเปล่าไม่ส่ง", () => {
    expect(outputDirPatch("", SAVED.outputDir)).toBeNull()
    expect(outputDirPatch("   ", SAVED.outputDir)).toBeNull()
  })
  it("ที่อยู่แบบสัมพัทธ์ยังส่งไปให้เซิร์ฟเวอร์ตัดสิน", () => {
    expect(outputDirPatch("abc", SAVED.outputDir)).toEqual({ outputDir: "abc" })
  })
})

describe("choicePatch", () => {
  it("ค่าใหม่ส่งเฉพาะช่องนั้น", () => {
    expect(choicePatch("concurrency", 1, SAVED)).toEqual({ concurrency: 1 })
    expect(choicePatch("audioDefault", "wav", SAVED)).toEqual({ audioDefault: "wav" })
    expect(choicePatch("videoDefault", "max", SAVED)).toEqual({ videoDefault: "max" })
    expect(choicePatch("audioLanguage", "th", SAVED)).toEqual({ audioLanguage: "th" })
  })
  it("ค่าเดิมไม่ส่ง", () => {
    expect(choicePatch("concurrency", 2, SAVED)).toBeNull()
    expect(choicePatch("audioLanguage", "original", SAVED)).toBeNull()
  })
})

describe("displayed", () => {
  it("ไม่มีที่รออยู่ = ค่าที่บันทึก", () => {
    expect(displayed(SAVED, null)).toBe(SAVED)
  })
  it("มีที่รออยู่ = ทับด้วยค่าที่เพิ่งเลือก", () => {
    expect(displayed(SAVED, { concurrency: 3 }).concurrency).toBe(3)
    expect(displayed(SAVED, { concurrency: 3 }).audioDefault).toBe("m4a")
  })
})

describe("languageOptions", () => {
  it("ต้นฉบับมาก่อน แล้วภาษาในรายการ", () => {
    const options = languageOptions("original")
    expect(options[0]).toEqual({ value: "original", label: "ต้นฉบับ" })
    expect(options).toHaveLength(Object.keys(th.general.languages).length)
  })
  it("ค่าที่บันทึกไว้นอกรายการถูกเพิ่มท้ายรายการพร้อมชื่อไทย", () => {
    const options = languageOptions("en-US")
    expect(options.at(-1)?.value).toBe("en-US")
    expect(options.at(-1)?.label).toContain("อังกฤษ")
  })
  it("ค่าในรายการไม่ซ้ำ", () => {
    expect(languageOptions("th").filter((o) => o.value === "th")).toHaveLength(1)
  })
})

describe("serverMessage", () => {
  it("ใช้ข้อความจากเซิร์ฟเวอร์ตามที่ได้", () => {
    const message = "ใส่ที่อยู่โฟลเดอร์แบบเต็ม เช่น C:\\Users\\ชื่อ\\Videos"
    expect(serverMessage(new ApiError(422, "E_BAD_REQUEST", message, null, null))).toBe(message)
  })
  it("ไม่ใช่ ApiError ใช้ข้อความกลาง", () => {
    expect(serverMessage(new Error("boom"))).toBe(th.general.saveFailed)
  })
})

describe("autoSharpFrames (M5 รอบ B)", () => {
  it("switching sends only that key, the same value sends nothing", () => {
    expect(choicePatch("autoSharpFrames", false, SAVED)).toEqual({ autoSharpFrames: false })
    expect(choicePatch("autoSharpFrames", true, SAVED)).toBeNull()
  })
})

describe("captureQuality (M5 รอบ B2)", () => {
  it("เลือกค่าอื่นส่งเฉพาะ key นั้น ค่าเดิมไม่ส่ง · ตัวเลือกสามค่าตามลำดับพร้อมชื่อไทย", () => {
    expect(CAPTURE_QUALITIES).toEqual(["max", "1080", "720"])
    expect(choicePatch("captureQuality", "720", SAVED)).toEqual({ captureQuality: "720" })
    expect(choicePatch("captureQuality", "max", SAVED)).toBeNull()
    expect(CAPTURE_QUALITIES.map((q) => th.general.captureQualities[q])).toEqual(["สูงสุดที่มี", "1080p", "720p"])
  })
})
