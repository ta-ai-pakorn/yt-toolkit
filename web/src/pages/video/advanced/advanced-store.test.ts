import { beforeEach, describe, expect, it } from "vitest"

import { __resetAdvancedForTests, advancedActions, advancedActive, EMPTY_ADVANCED, getAdvanced } from "./advanced-store"

beforeEach(() => __resetAdvancedForTests())

describe("ค่าตัวเลือกขั้นสูงต่อคลิป (D3)", () => {
  it("เริ่มว่าง และคืนก้อนเดิมทุกครั้ง (useSyncExternalStore ต้องได้อ้างอิงเดิม)", () => {
    expect(getAdvanced("aqz-KE-bpKQ")).toBe(EMPTY_ADVANCED)
    expect(EMPTY_ADVANCED).toEqual({ startText: "", endText: "", splitChapters: false, sponsorblock: false, open: false, checked: false })
  })

  it("ทุกแท็บของคลิปเดียวกันเห็นค่าเดียวกัน · เปิดคลิปอื่น = เริ่มใหม่", () => {
    advancedActions.patch("aqz-KE-bpKQ", { startText: "1:30" })
    expect(getAdvanced("aqz-KE-bpKQ").startText).toBe("1:30")
    expect(getAdvanced("88o5Sk8_m1Y")).toBe(EMPTY_ADVANCED)
    advancedActions.patch("88o5Sk8_m1Y", { endText: "2:00" })
    expect(getAdvanced("aqz-KE-bpKQ")).toBe(EMPTY_ADVANCED)
    expect(getAdvanced("88o5Sk8_m1Y")).toMatchObject({ startText: "", endText: "2:00" })
  })

  it("ตั้งจุดจากตัวเล่น/ภาพเฟรม: ปัดลงเป็นวินาที เปิดส่วนตัวเลือก และแสดง error ทันที", () => {
    expect(advancedActions.mark("aqz-KE-bpKQ", "start", 90_999)).toBe("set")
    expect(advancedActions.mark("aqz-KE-bpKQ", "end", 3_750_400)).toBe("set")
    expect(getAdvanced("aqz-KE-bpKQ")).toMatchObject({ startText: "1:30", endText: "1:02:30", open: true, checked: true })
  })

  it("แยก chapter เปิดอยู่ = ตั้งจุดไม่ได้ ค่าไม่เปลี่ยน", () => {
    advancedActions.patch("jNQXAC9IVRw", { splitChapters: true })
    expect(advancedActions.mark("jNQXAC9IVRw", "start", 5_000)).toBe("blocked")
    expect(getAdvanced("jNQXAC9IVRw").startText).toBe("")
  })

  it("ใช้ตัวเลือกขั้นสูงอยู่ = มีข้อความในช่องเวลา หรือเปิดแยก chapter / ตัดโฆษณา", () => {
    expect(advancedActive(EMPTY_ADVANCED)).toBe(false)
    expect(advancedActive({ ...EMPTY_ADVANCED, open: true, checked: true })).toBe(false)
    expect(advancedActive({ ...EMPTY_ADVANCED, endText: "5:00" })).toBe(true)
    expect(advancedActive({ ...EMPTY_ADVANCED, splitChapters: true })).toBe(true)
    expect(advancedActive({ ...EMPTY_ADVANCED, sponsorblock: true })).toBe(true)
  })
})
