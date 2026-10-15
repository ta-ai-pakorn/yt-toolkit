import { describe, expect, it } from "vitest"

import { FILENAME_STYLES, PATH_LIMIT, PathTooLongError, planNames, safeComponent, truncateTitle } from "./filename"

/** ตัวอักษรจาก code point (เทสไม่ใช้ escape แบบ backslash-u ในซอร์ส) */
const cp = (...codes: number[]) => String.fromCodePoint(...codes)

describe("safeComponent (กฎเดียวกับ files.safe_component)", () => {
  it("ช่องว่างแบบ Python: U+001C-U+001F และ U+0085 เป็นช่องว่าง U+FEFF กับ U+200B ถูกทิ้ง (Cf)", () => {
    expect(safeComponent(`a${cp(0x1c)}b${cp(0x1f)}c${cp(0x85)}d`, "x")).toBe("a b c d")
    expect(safeComponent(`a${cp(0xfeff)}b${cp(0x200b)}c`, "x")).toBe("abc")
    expect(safeComponent(`${cp(0x3000)}ก${cp(0xa0)}ข${cp(0x09, 0x0a)}`, "x")).toBe("ก ข")
  })

  it("ตัดอักขระต้องห้ามแล้วรวมช่องว่างซ้ำ ตัดจุด/ช่องว่างท้ายชื่อ", () => {
    expect(safeComponent('ทดสอบ: "A/B" <ภาค 1>?', "x")).toBe("ทดสอบ AB ภาค 1")
    expect(safeComponent("Why | How", "x")).toBe("Why How")
    expect(safeComponent("Hello... . ", "x")).toBe("Hello")
  })

  it("ว่าง = ค่าสำรอง · ชื่อสงวนของ Windows ได้ _ นำหน้า", () => {
    expect(safeComponent('?:*"<>|', "dQw4w9WgXcQ")).toBe("dQw4w9WgXcQ")
    expect(safeComponent("CON", "x")).toBe("_CON")
    expect(safeComponent("com1.txt", "x")).toBe("_com1.txt")
    expect(safeComponent("LPT¹", "x")).toBe("_LPT¹")
    expect(safeComponent("CONSOLE", "x")).toBe("CONSOLE")
  })
})

describe("truncateTitle (กฎเดียวกับ files.truncate_title)", () => {
  it("ไม่ตัดกลางคู่ surrogate (อีโมจินับ 2)", () => {
    expect(truncateTitle("😀😀😀", 5)).toBe("😀😀")
    expect(truncateTitle("😀😀😀", 1)).toBe("")
  })

  it("ไม่ทิ้งสระ/วรรณยุกต์ไว้หลังรอยตัด (ถอยไปก่อนพยัญชนะ)", () => {
    expect(truncateTitle("กี่", 1)).toBe("")
    expect(truncateTitle("กี่กี่", 4)).toBe("กี่")
    expect(truncateTitle("ที่นี่", 2)).toBe("")
    expect(truncateTitle("ที่นี่", 4)).toBe("ที่")
  })

  it("พอดีแล้วไม่ตัด แต่ยังตัดจุด/ช่องว่างท้าย", () => {
    expect(truncateTitle("abc. ", 10)).toBe("abc")
    expect(truncateTitle("abcdef", 3)).toBe("abc")
  })
})

describe("planNames", () => {
  const base = { baseLen: 40, title: "สอนทำกับข้าวง่าย ๆ ใน 10 นาที", clipId: "abcdefghijk", suffix: "", ext: "mp4" }

  it("สามรูปแบบ: โฟลเดอร์เดิม ชื่อไฟล์ต่างกันตามรูปแบบ", () => {
    const names = FILENAME_STYLES.map((style) => planNames({ ...base, style, uploader: "ครัวบ้านเรา", quality: "1080p" }))
    expect(new Set(names.map((n) => n.folder))).toEqual(new Set(["สอนทำกับข้าวง่าย ๆ ใน 10 นาที [abcdefghijk]"]))
    expect(names.map((n) => n.file)).toEqual([
      "สอนทำกับข้าวง่าย ๆ ใน 10 นาที.mp4",
      "สอนทำกับข้าวง่าย ๆ ใน 10 นาที - ครัวบ้านเรา.mp4",
      "สอนทำกับข้าวง่าย ๆ ใน 10 นาที (1080p).mp4",
    ])
  })

  it("path ยาวเกินแม้ใช้รหัสคลิป = PathTooLongError", () => {
    expect(() => planNames({ ...base, baseLen: PATH_LIMIT })).toThrow(PathTooLongError)
  })

  it("รูปแบบที่ไม่รู้จักหรือส่วนคุณภาพผิดรูป = Error (ข้อผิดพลาดของโปรแกรม)", () => {
    expect(() => planNames({ ...base, style: "channel" as never })).toThrow("unknown filename style")
    expect(() => planNames({ ...base, style: "title-quality", quality: "1080P" })).toThrow("bad quality label")
  })
})
