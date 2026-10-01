import { describe, expect, it } from "vitest"

import { cueInReplayed, inReplayed } from "./most-replayed"

const SEGMENTS = [
  { startMs: 80_000, endMs: 95_000 },
  { startMs: 310_000, endMs: 320_000 },
]

describe("inReplayed", () => {
  it("นับต้นช่วง ไม่นับปลายช่วง", () => {
    expect(inReplayed(80_000, SEGMENTS)).toBe(true)
    expect(inReplayed(94_999, SEGMENTS)).toBe(true)
    expect(inReplayed(95_000, SEGMENTS)).toBe(false)
    expect(inReplayed(79_999, SEGMENTS)).toBe(false)
    expect(inReplayed(315_000, SEGMENTS)).toBe(true)
  })

  it("ไม่มีช่วง (คลิปไม่มี heatmap) = ไม่มีภาพไหนอยู่ในช่วง", () => {
    expect(inReplayed(80_000, undefined)).toBe(false)
    expect(inReplayed(80_000, [])).toBe(false)
  })
})

describe("cueInReplayed", () => {
  const cue = (startMs: number, endMs: number) => ({ startMs, endMs, lines: ["x"] })

  it("บรรทัดที่คาบเกี่ยวกับช่วงนับ แม้เริ่มก่อนช่วง", () => {
    expect(cueInReplayed(cue(78_000, 81_000), SEGMENTS)).toBe(true)
    expect(cueInReplayed(cue(90_000, 99_000), SEGMENTS)).toBe(true)
    expect(cueInReplayed(cue(70_000, 100_000), SEGMENTS)).toBe(true)
  })

  it("บรรทัดที่จบตรงต้นช่วงหรือเริ่มตรงปลายช่วงไม่นับ", () => {
    expect(cueInReplayed(cue(77_000, 80_000), SEGMENTS)).toBe(false)
    expect(cueInReplayed(cue(95_000, 97_000), SEGMENTS)).toBe(false)
  })

  it("บรรทัดยาว 0 ms นับเหมือนจุดเวลาเดียว · ไม่มีช่วง = ไม่นับ", () => {
    expect(cueInReplayed(cue(80_000, 80_000), SEGMENTS)).toBe(true)
    expect(cueInReplayed(cue(95_000, 95_000), SEGMENTS)).toBe(false)
    expect(cueInReplayed(cue(80_000, 90_000), undefined)).toBe(false)
  })
})
