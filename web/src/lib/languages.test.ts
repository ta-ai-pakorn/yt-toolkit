import { describe, expect, it } from "vitest"

import { audioLanguageName, languageName } from "./languages"

describe("audioLanguageName", () => {
  it("รหัสมีภูมิภาคได้ชื่อแบบวงเล็บ", () => {
    expect(audioLanguageName("en-US")).toBe("อังกฤษ (สหรัฐอเมริกา)")
    expect(audioLanguageName("th")).toBe("ไทย")
  })

  it("รหัสที่ไม่รู้จักหรือรูปแบบผิดคืนรหัสเดิม", () => {
    expect(audioLanguageName("x")).toBe("x")
    expect(audioLanguageName("xx-bogus")).toBe("xx-bogus")
  })

  it("languageName ยังเป็นแบบเดิม (ป้ายของ M3)", () => {
    expect(languageName("en-US")).toBe("อังกฤษ - สหรัฐอเมริกา")
  })
})

describe("languageName", () => {
  it("รหัสภาษาเดี่ยวได้ชื่อไทย", () => {
    expect(languageName("th")).toBe("ไทย")
  })

  it("รหัสมีภูมิภาคได้ชื่อภาษาอังกฤษเป็นภาษาไทย", () => {
    expect(languageName("en-US")).toContain("อังกฤษ")
  })

  it("รหัสที่ไม่รู้จักหรือรูปแบบผิดคืนรหัสเดิม", () => {
    expect(languageName("xx-bogus")).toBe("xx-bogus")
    expect(languageName("x")).toBe("x")
  })
})
