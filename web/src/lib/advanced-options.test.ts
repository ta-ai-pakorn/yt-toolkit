import { describe, expect, it } from "vitest"

import {
  chapterBlock,
  chaptersAvailable,
  choiceParts,
  keptSeconds,
  parseClock,
  rangeAvailable,
  rangeText,
  scaleBytes,
  validateRange,
} from "./advanced-options"

describe("parseClock", () => {
  it.each([
    ["90", 90],
    ["0", 0],
    ["1:30", 90],
    ["01:30", 90],
    ["100:00", 6000],
    ["1:02:30", 3750],
    [" 5:00 ", 300],
  ])("%s = %d วินาที", (text, seconds) => {
    expect(parseClock(text)).toBe(seconds)
  })

  it.each(["", "1:3", "1:60", "1.30", "-5", "1:02:3", "123456", "1:30:00:00", "๑:๓๐", "1:30.5", "abc"])("%s อ่านไม่ได้", (text) => {
    expect(parseClock(text)).toBeNull()
  })
})

describe("validateRange (คลิป 6:12 = 372 วินาที)", () => {
  const D = 372
  it("ว่างทั้งสองช่อง = ไม่มีช่วง ไม่มี error", () => {
    expect(validateRange("", " ", D)).toEqual({ range: null, startError: null, endError: null })
  })
  it("ช่องว่างหนึ่งช่อง = ปลายอีกด้านของคลิป", () => {
    expect(validateRange("1:30", "5:00", D).range).toEqual({ startMs: 90_000, endMs: 300_000 })
    expect(validateRange("", "5:00", D).range).toEqual({ startMs: 0, endMs: 300_000 })
    expect(validateRange("1:30", "", D).range).toEqual({ startMs: 90_000, endMs: 372_000 })
    expect(validateRange("0:00", "6:12", D).range).toEqual({ startMs: 0, endMs: 372_000 })
  })
  it("พิมพ์ผิดรูปแบบ = error ใต้ช่องนั้น", () => {
    expect(validateRange("1:3x", "", D)).toEqual({ range: null, startError: "format", endError: null })
    expect(validateRange("", "abc", D)).toEqual({ range: null, startError: null, endError: "format" })
  })
  it("เริ่มไม่ก่อนจบ = error ที่ช่องเริ่ม", () => {
    expect(validateRange("5:00", "1:30", D)).toEqual({ range: null, startError: "order", endError: null })
    expect(validateRange("6:12", "", D)).toEqual({ range: null, startError: "order", endError: null })
  })
  it("เกินความยาวคลิป", () => {
    expect(validateRange("", "9:00", D)).toEqual({ range: null, startError: null, endError: "beyond" })
    expect(validateRange("7:00", "", D)).toEqual({ range: null, startError: "beyond", endError: null })
  })
})

describe("ความพร้อมของคลิป", () => {
  it("ช่วงเวลา: ต้องไม่ใช่คลิปสดและรู้ความยาว · chapter: อย่างน้อย 2", () => {
    expect(rangeAvailable({ isLive: false, durationS: 372 })).toBe(true)
    expect(rangeAvailable({ isLive: true, durationS: 372 })).toBe(false)
    expect(rangeAvailable({ isLive: false, durationS: 0 })).toBe(false)
    expect(chaptersAvailable({ chapters: [] })).toBe(false)
    expect(chaptersAvailable({ chapters: [{ startS: 0, endS: 5, title: "a" }] })).toBe(false)
    expect(chaptersAvailable({ chapters: [{ startS: 0, endS: 5, title: "a" }, { startS: 5, endS: 9, title: "b" }] })).toBe(true)
  })
})

describe("ป้ายและขนาด", () => {
  it("ข้อความช่วงแบบเวลาในแอพ", () => {
    expect(rangeText({ startMs: 90_000, endMs: 300_000 })).toBe("1:30-5:00")
    expect(rangeText({ startMs: 3_750_000, endMs: 3_900_000 })).toBe("1:02:30-1:05:00")
  })
  it("ส่วนของป้ายปุ่มตามลำดับ ช่วง → chapter → โฆษณา", () => {
    const range = { startMs: 0, endMs: 60_000 }
    expect(choiceParts({ range, splitChapters: false, ads: true })).toEqual([{ kind: "range", range }, { kind: "ads" }])
    expect(choiceParts({ range: null, splitChapters: true, ads: false })).toEqual([{ kind: "chapters" }])
    expect(choiceParts({ range: null, splitChapters: false, ads: false })).toEqual([])
  })
  it("ขนาดประมาณตามความยาวที่เหลือ", () => {
    expect(keptSeconds({ startMs: 90_000, endMs: 300_000 })).toBe(210)
    expect(scaleBytes(372_000_000, 372, 210)).toBe(210_000_000)
    expect(scaleBytes(372_000_000, 372, undefined)).toBe(372_000_000)
    expect(scaleBytes(undefined, 372, 210)).toBeUndefined()
    expect(scaleBytes(1000, 0, 10)).toBe(1000)
  })
})

describe("chapterBlock: ใครเปิดก่อนชนะ", () => {
  const empty = { startText: "", endText: "", sponsorblock: false }
  it("ช่วงเวลา → ตัดโฆษณา → ฝังซับ", () => {
    expect(chapterBlock(empty, false)).toBeNull()
    expect(chapterBlock({ ...empty, endText: "5:00" }, true)).toBe("range")
    expect(chapterBlock({ ...empty, sponsorblock: true }, true)).toBe("sponsorblock")
    expect(chapterBlock(empty, true)).toBe("embedSubs")
  })
})
