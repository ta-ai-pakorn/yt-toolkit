import { describe, expect, it } from "vitest"

import { languageName } from "./languages"

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
