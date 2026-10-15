import { describe, expect, it } from "vitest"

import type { Stats } from "@/lib/types"

import { count, isEmpty, kindLabel, monthLabel, sinceLabel, topKind } from "./stats"

const base: Stats = { since: null, clips: 0, files: 0, totalBytes: 0, byKind: [], byMonth: [] }

describe("stats model (M6 รอบ C spec §3.3)", () => {
  it("ชื่อชนิดภาษาไทยตาม BRD", () => {
    expect(["video", "audio", "subtitle", "image"].map((k) => kindLabel(k as never))).toEqual([
      "วิดีโอ",
      "เสียง",
      "ซับ",
      "ภาพ",
    ])
  })

  it("ชนิดที่ใช้บ่อยที่สุด = ตัวแรกของ byKind (server เรียงแล้ว) · ว่าง = null", () => {
    expect(topKind(base)).toBeNull()
    const top = { kind: "audio" as const, files: 4, bytes: 9 }
    expect(topKind({ ...base, byKind: [top, { kind: "video", files: 1, bytes: 1 }] })).toEqual(top)
  })

  it("ชื่อเดือนเป็นภาษาไทย พ.ศ. ไม่เลื่อนตามเขตเวลา", () => {
    expect(monthLabel("2026-10")).toBe("ตุลาคม 2569")
    expect(monthLabel("2026-01")).toBe("มกราคม 2569")
    expect(monthLabel("2025-12")).toBe("ธันวาคม 2568")
  })

  it("นับตั้งแต่ = วันที่ตามเวลาไทย", () => {
    // 17:30 UTC = 00:30 ของวันถัดไปในเวลาไทย
    expect(sinceLabel("2026-10-14T17:30:00+00:00")).toBe("15 ตุลาคม 2569")
    expect(sinceLabel("2026-10-15T16:59:59+00:00")).toBe("15 ตุลาคม 2569")
  })

  it("ตัวเลขมีคั่นหลักพัน", () => {
    expect(count(0)).toBe("0")
    expect(count(1234567)).toBe("1,234,567")
  })

  it("ว่าง = ไม่มีคลิปที่นับได้", () => {
    expect(isEmpty(base)).toBe(true)
    expect(isEmpty({ ...base, since: "2026-10-15T00:00:00+00:00" })).toBe(true)
    expect(isEmpty({ ...base, clips: 1 })).toBe(false)
  })
})
