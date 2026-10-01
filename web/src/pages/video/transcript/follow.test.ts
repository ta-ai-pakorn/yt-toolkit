import { describe, expect, it } from "vitest"

import { centeredScrollTop, isUserScroll } from "./follow"

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

describe("centeredScrollTop: เลื่อนกรอบให้บรรทัดที่กำลังเล่นอยู่กลางกรอบ", () => {
  // กรอบรายการอยู่ที่ y 100-460 (สูง 360 กลาง = 280) เลื่อนไปแล้ว 1000 · เลื่อนได้สูงสุด 5000
  const FRAME = { top: 100, bottom: 460 }
  const MAX = 5000

  it("บรรทัดอยู่กลางกรอบแล้ว = ไม่เลื่อน", () => {
    expect(centeredScrollTop(1000, FRAME, { top: 262, bottom: 298 }, MAX)).toBe(1000)
  })

  it("บรรทัดต่ำกว่ากลาง = เลื่อนลงจนอยู่กลาง (ไม่ไปกองที่ขอบล่าง)", () => {
    expect(centeredScrollTop(1000, FRAME, { top: 424, bottom: 460 }, MAX)).toBe(1000 + 162)
    expect(centeredScrollTop(1000, FRAME, { top: 2000, bottom: 2036 }, MAX)).toBe(1000 + 2018 - 280)
  })

  it("บรรทัดสูงกว่ากลาง = เลื่อนขึ้นจนอยู่กลาง", () => {
    expect(centeredScrollTop(1000, FRAME, { top: 100, bottom: 136 }, MAX)).toBe(1000 - 162)
  })

  it("ต้นรายการและท้ายรายการ: เลื่อนได้แค่ถึงขอบ (บรรทัดแรก ๆ อยู่บน บรรทัดท้าย ๆ อยู่ล่าง)", () => {
    expect(centeredScrollTop(50, FRAME, { top: 110, bottom: 146 }, MAX)).toBe(0)
    expect(centeredScrollTop(4900, FRAME, { top: 430, bottom: 466 }, MAX)).toBe(MAX)
    // รายการสั้นกว่ากรอบ (เลื่อนไม่ได้) = 0 เสมอ
    expect(centeredScrollTop(0, FRAME, { top: 400, bottom: 436 }, 0)).toBe(0)
  })
})
