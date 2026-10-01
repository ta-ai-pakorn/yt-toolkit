import { describe, expect, it } from "vitest"

import { isUserScroll, nearestScrollTop } from "./follow"

describe("isUserScroll: อะไรทำให้หยุดเลื่อนตามบรรทัดที่กำลังเล่น", () => {
  it("ล้อเมาส์ ลากนิ้ว และกดแถบเลื่อน = ผู้ใช้เลื่อนเอง", () => {
    expect(isUserScroll({ type: "wheel" })).toBe(true)
    expect(isUserScroll({ type: "touchmove" })).toBe(true)
    expect(isUserScroll({ type: "scrollbar" })).toBe(true)
  })

  it("Ctrl + ล้อ (ซูมหน้า) ไม่ใช่การเลื่อนรายการ", () => {
    expect(isUserScroll({ type: "wheel", ctrlKey: true })).toBe(false)
  })

  it("ปุ่มเลื่อนบนคีย์บอร์ด = ผู้ใช้เลื่อนเอง", () => {
    for (const key of ["ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End"]) {
      expect(isUserScroll({ type: "keydown", key, target: "BUTTON" })).toBe(true)
    }
  })

  it("Space บนปุ่ม = กดปุ่ม ไม่ใช่เลื่อน · Space บนกรอบรายการ = เลื่อน", () => {
    expect(isUserScroll({ type: "keydown", key: " ", target: "BUTTON" })).toBe(false)
    expect(isUserScroll({ type: "keydown", key: " ", target: "DIV" })).toBe(true)
  })

  it("Tab Enter ตัวอักษร และปุ่มที่กดพร้อม Ctrl/Alt/Meta ไม่ใช่การเลื่อน", () => {
    expect(isUserScroll({ type: "keydown", key: "Tab", target: "BUTTON" })).toBe(false)
    expect(isUserScroll({ type: "keydown", key: "Enter", target: "BUTTON" })).toBe(false)
    expect(isUserScroll({ type: "keydown", key: "a", target: "DIV" })).toBe(false)
    expect(isUserScroll({ type: "keydown", key: "ArrowDown", target: "DIV", ctrlKey: true })).toBe(false)
    expect(isUserScroll({ type: "keydown", key: "Home", target: "DIV", altKey: true })).toBe(false)
    expect(isUserScroll({ type: "keydown", key: "End", target: "DIV", metaKey: true })).toBe(false)
  })

  it("เหตุการณ์ scroll (รวมที่แอปเลื่อนตามบรรทัดเอง และบรรทัดไกลจอที่ขนาดเปลี่ยนตอนวาด) ไม่หยุดเลื่อนตาม", () => {
    expect(isUserScroll({ type: "scroll" })).toBe(false)
  })
})

describe("nearestScrollTop: เลื่อนกรอบให้เห็นบรรทัดแบบ block nearest", () => {
  // กรอบรายการอยู่ที่ y 100-460 (สูง 360) เลื่อนไปแล้ว 1000
  const FRAME = { top: 100, bottom: 460 }

  it("บรรทัดอยู่ในกรอบแล้ว = ไม่เลื่อน", () => {
    expect(nearestScrollTop(1000, FRAME, { top: 100, bottom: 136 })).toBe(1000)
    expect(nearestScrollTop(1000, FRAME, { top: 300, bottom: 336 })).toBe(1000)
    expect(nearestScrollTop(1000, FRAME, { top: 424, bottom: 460 })).toBe(1000)
  })

  it("ล้นขอบล่าง = เลื่อนลงพอให้ชิดขอบล่าง", () => {
    expect(nearestScrollTop(1000, FRAME, { top: 440, bottom: 476 })).toBe(1016)
    expect(nearestScrollTop(1000, FRAME, { top: 2000, bottom: 2036 })).toBe(1000 + 2036 - 460)
  })

  it("ล้นขอบบน = เลื่อนขึ้นพอให้ชิดขอบบน", () => {
    expect(nearestScrollTop(1000, FRAME, { top: 90, bottom: 126 })).toBe(990)
    expect(nearestScrollTop(1000, FRAME, { top: -500, bottom: -464 })).toBe(400)
  })

  it("บรรทัดสูงกว่ากรอบ = ชิดขอบบน (เห็นต้นบรรทัด)", () => {
    expect(nearestScrollTop(1000, FRAME, { top: 200, bottom: 700 })).toBe(1100)
  })
})
