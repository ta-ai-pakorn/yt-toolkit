import { describe, expect, it } from "vitest"

import {
  blockTooltip,
  captureBlock,
  captureClock,
  captureDownloadUrl,
  captureFileName,
  captureTimeMs,
  clockTime,
  focusAfterDelete,
  stripKeyTarget,
} from "./capture-model"

describe("captureTimeMs", () => {
  it("ปัดทีละ 100 ms ไม่ติดลบ", () => {
    expect(captureTimeMs(125_449)).toBe(125_400)
    expect(captureTimeMs(125_450)).toBe(125_500)
    expect(captureTimeMs(-30)).toBe(0)
    expect(captureTimeMs(Number.NaN)).toBe(0)
  })
})

describe("captureClock", () => {
  it("วินาทีเต็มไม่มีทศนิยม · มีเศษแสดงหนึ่งตำแหน่ง · ครบชั่วโมงแสดงชั่วโมง", () => {
    expect(captureClock(125_000)).toBe("2:05")
    expect(captureClock(125_400)).toBe("2:05.4")
    expect(captureClock(3_725_900)).toBe("1:02:05.9")
    expect(captureClock(0)).toBe("0:00")
  })
})

describe("clockTime", () => {
  it("HH:MM ตามนาฬิกาเครื่อง · อ่านไม่ได้ = ว่าง", () => {
    const at = new Date(2026, 9, 5, 7, 4)
    expect(clockTime(at.toISOString())).toBe("07:04")
    expect(clockTime("ไม่ใช่เวลา")).toBe("")
  })
})

describe("captureBlock / blockTooltip", () => {
  const now = Date.parse("2026-10-05T10:00:00Z")
  it("คลิปสดมาก่อน", () => {
    const block = captureBlock({ isLive: true, pausedUntil: "2026-10-05T10:10:00Z", now })
    expect(block).toEqual({ kind: "live" })
    expect(blockTooltip(block)).toBe("คลิปสดถ่ายภาพคมไม่ได้")
  })

  it("คิวพักอยู่ = บอกเวลาที่ลองใหม่ได้ · ครบเวลาแล้วหรืออ่านไม่ได้ = ถ่ายได้", () => {
    const until = "2026-10-05T10:10:00Z"
    const block = captureBlock({ isLive: false, pausedUntil: until, now })
    expect(block).toEqual({ kind: "paused", until })
    expect(blockTooltip(block)).toBe(`พักการโหลดอยู่เพราะยูทูปขอตรวจสอบ ลองใหม่หลัง ${clockTime(until)}`)
    expect(captureBlock({ isLive: false, pausedUntil: "2026-10-05T09:59:00Z", now })).toBeNull()
    expect(captureBlock({ isLive: false, pausedUntil: "x", now })).toBeNull()
    expect(captureBlock({ isLive: false, pausedUntil: null, now })).toBeNull()
    expect(blockTooltip(null)).toBeNull()
  })
})

describe("stripKeyTarget", () => {
  it("ลูกศรเลื่อนทีละภาพไม่เลยขอบ · Home/End · ปุ่มอื่น = null", () => {
    expect(stripKeyTarget("ArrowRight", 0, 3)).toBe(1)
    expect(stripKeyTarget("ArrowDown", 2, 3)).toBe(2)
    expect(stripKeyTarget("ArrowLeft", 0, 3)).toBe(0)
    expect(stripKeyTarget("ArrowUp", 2, 3)).toBe(1)
    expect(stripKeyTarget("Home", 2, 3)).toBe(0)
    expect(stripKeyTarget("End", 0, 3)).toBe(2)
    expect(stripKeyTarget("Enter", 1, 3)).toBeNull()
    expect(stripKeyTarget("ArrowRight", 0, 0)).toBeNull()
  })
})

describe("focusAfterDelete", () => {
  it("ภาพถัดไป · ภาพสุดท้ายถูกลบ = ภาพก่อนหน้า · ไม่เหลือ = null", () => {
    expect(focusAfterDelete(["a", "b", "c"], "b")).toBe("c")
    expect(focusAfterDelete(["a", "b", "c"], "c")).toBe("b")
    expect(focusAfterDelete(["a"], "a")).toBeNull()
    expect(focusAfterDelete(["a", "b"], "x")).toBe("a")
  })
})

describe("ชื่อและลิงก์โหลดภาพ", () => {
  it("ต่อ download=1 ถูกตัว · ชื่อ frame_HH-MM-SS.jpg", () => {
    expect(captureDownloadUrl("/api/cache/x/captures/c_1.jpg?v=9")).toBe("/api/cache/x/captures/c_1.jpg?v=9&download=1")
    expect(captureDownloadUrl("/a.jpg")).toBe("/a.jpg?download=1")
    expect(captureFileName(125_400)).toBe("frame_00-02-05.jpg")
  })
})
