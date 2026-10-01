import { describe, expect, it } from "vitest"

import { fractionOf, keyTarget, msAtPoint, percentOf, rangeBox } from "./timeline-geometry"

describe("fractionOf / percentOf", () => {
  it("สัดส่วนของความยาวคลิป ไม่เกินขอบ 0-1", () => {
    expect(fractionOf(30_000, 60_000)).toBe(0.5)
    expect(fractionOf(-5, 60_000)).toBe(0)
    expect(fractionOf(90_000, 60_000)).toBe(1)
    expect(percentOf(15_000, 60_000)).toBe("25.000%")
  })

  it("คลิปไม่มีความยาว หรือค่าไม่ใช่ตัวเลข = 0", () => {
    expect(fractionOf(10, 0)).toBe(0)
    expect(fractionOf(Number.NaN, 1000)).toBe(0)
  })
})

describe("msAtPoint", () => {
  it("จุดที่คลิกบนแถบ → เวลา (ปัดเป็นวินาทีเต็ม)", () => {
    expect(msAtPoint(150, 100, 200, 600_000)).toBe(150_000)
    expect(msAtPoint(100, 100, 200, 600_000)).toBe(0)
    expect(msAtPoint(301, 100, 200, 600_000)).toBe(600_000)
    expect(msAtPoint(101, 100, 200, 61_000)).toBe(0)
  })

  it("คลิกนอกแถบ = ติดขอบ · แถบกว้าง 0 หรือคลิปไม่มีความยาว = 0", () => {
    expect(msAtPoint(0, 100, 200, 600_000)).toBe(0)
    expect(msAtPoint(999, 100, 200, 600_000)).toBe(600_000)
    expect(msAtPoint(150, 100, 0, 600_000)).toBe(0)
    expect(msAtPoint(150, 100, 200, 0)).toBe(0)
  })
})

describe("rangeBox", () => {
  it("ช่วงเวลา → left/width เป็นเปอร์เซ็นต์", () => {
    expect(rangeBox({ startMs: 20_000, endMs: 30_000 }, 100_000)).toEqual({ left: "20.000%", width: "10.000%" })
  })

  it("ช่วงสั้นมากยังกว้างอย่างน้อย 0.5% · ไม่ล้นขวา", () => {
    expect(rangeBox({ startMs: 10_000, endMs: 10_001 }, 100_000)).toEqual({ left: "10.000%", width: "0.500%" })
    expect(rangeBox({ startMs: 99_900, endMs: 99_950 }, 100_000)).toEqual({ left: "99.900%", width: "0.100%" })
    expect(rangeBox({ startMs: 90_000, endMs: 200_000 }, 100_000)).toEqual({ left: "90.000%", width: "10.000%" })
  })

  it("ช่วงผิดรูปหรืออยู่นอกคลิป = null", () => {
    expect(rangeBox({ startMs: 30, endMs: 30 }, 100_000)).toBeNull()
    expect(rangeBox({ startMs: 100_000, endMs: 120_000 }, 100_000)).toBeNull()
    expect(rangeBox({ startMs: 0, endMs: 10 }, 0)).toBeNull()
  })
})

describe("keyTarget", () => {
  it("ซ้าย/ขวา ทีละ 5 วินาที ไม่เกินขอบ · Home/End ไปต้น/ท้าย", () => {
    expect(keyTarget("ArrowRight", 10_000, 60_000)).toBe(15_000)
    expect(keyTarget("ArrowLeft", 10_000, 60_000)).toBe(5000)
    expect(keyTarget("ArrowLeft", 2000, 60_000)).toBe(0)
    expect(keyTarget("ArrowRight", 58_000, 60_000)).toBe(60_000)
    expect(keyTarget("ArrowUp", 0, 60_000)).toBe(5000)
    expect(keyTarget("ArrowDown", 6000, 60_000)).toBe(1000)
    expect(keyTarget("Home", 30_000, 60_000)).toBe(0)
    expect(keyTarget("End", 30_000, 60_000)).toBe(60_000)
  })

  it("ปุ่มอื่น = null", () => {
    expect(keyTarget("Enter", 0, 60_000)).toBeNull()
    expect(keyTarget("a", 0, 60_000)).toBeNull()
  })
})
