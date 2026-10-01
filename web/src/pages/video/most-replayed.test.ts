import { describe, expect, it } from "vitest"

import { cueInReplayed, inReplayed, replayedFrameIndexes, replayedFrames, segmentFrameIndex } from "./most-replayed"

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

describe("ภาพเฟรมของช่วงดูซ้ำบ่อย (review M-2)", () => {
  // ภาพทุก 10 วินาที: 0, 10, 20, ... 100 วินาที
  const frames = Array.from({ length: 11 }, (_, index) => ({ index, tMs: index * 10_000, url: `f${index}` }))

  it("ปุ่มเวลาไปภาพแรกที่อยู่ในช่วง ไม่ใช่ภาพที่ใกล้เวลาเริ่ม (ซึ่งอาจอยู่นอกช่วง)", () => {
    // เริ่ม 41 วินาที: ภาพที่ใกล้ที่สุดคือ 40 (นอกช่วง) ภาพแรกในช่วงคือ 50
    expect(segmentFrameIndex(frames, { startMs: 41_000, endMs: 58_000 })).toBe(5)
    expect(segmentFrameIndex(frames, { startMs: 40_000, endMs: 45_000 })).toBe(4)
  })

  it("ช่วงสั้นที่ไม่มีภาพอยู่ข้างใน: ภาพที่ใกล้กลางช่วงที่สุด (เท่ากันเลือกภาพก่อน)", () => {
    expect(segmentFrameIndex(frames, { startMs: 190, endMs: 570 })).toBe(0)
    expect(segmentFrameIndex(frames, { startMs: 12_000, endMs: 19_000 })).toBe(2)
    expect(segmentFrameIndex(frames, { startMs: 11_000, endMs: 19_000 })).toBe(1)
    expect(segmentFrameIndex([], { startMs: 0, endMs: 1 })).toBe(-1)
  })

  it("ภาพที่มีป้าย = ภาพในช่วงทั้งหมด + ภาพแทนของช่วงที่ไม่มีภาพข้างใน (ปุ่มเวลาพาไปภาพที่มีป้ายเสมอ)", () => {
    const segments = [
      { startMs: 41_000, endMs: 62_000 },
      { startMs: 12_000, endMs: 19_000 },
    ]
    expect([...replayedFrames(frames, segments)].sort((a, b) => a - b)).toEqual([2, 5, 6])
    for (const segment of segments) {
      expect(replayedFrames(frames, segments).has(segmentFrameIndex(frames, segment))).toBe(true)
    }
    expect(replayedFrames(frames, undefined).size).toBe(0)
  })
})

describe("ตัวกรองดูซ้ำบ่อยของแท็บภาพเฟรม", () => {
  // ภาพทุก 10 วินาที: 0, 10, 20, ... 100 วินาที
  const frames = Array.from({ length: 11 }, (_, index) => ({ index, tMs: index * 10_000, url: `f${index}` }))

  it("ได้ตำแหน่งภาพที่อยู่ในช่วง เรียงตามเวลา · นับต้นช่วง ไม่นับปลายช่วง · ช่วงซ้อนกันไม่นับซ้ำ", () => {
    const segments = [
      { startMs: 60_000, endMs: 80_000 },
      { startMs: 20_000, endMs: 40_000 },
      { startMs: 30_000, endMs: 41_000 },
    ]
    const indexes = replayedFrameIndexes(frames, segments)
    expect(indexes).toEqual([2, 3, 4, 6, 7])
    // จำนวนบนปุ่ม "ดูซ้ำบ่อย (n ภาพ)"
    expect(indexes).toHaveLength(5)
    // เวลาของภาพที่กรองแล้วยังเป็นเวลาเดิมของภาพนั้น
    expect(indexes.map((index) => frames[index].tMs)).toEqual([20_000, 30_000, 40_000, 60_000, 70_000])
  })

  it("ช่วงสั้นที่ไม่มีภาพข้างในได้ภาพแทน 1 ภาพ (ภาพเดียวกับที่มีป้าย)", () => {
    const segments = [{ startMs: 12_000, endMs: 19_000 }]
    expect(replayedFrameIndexes(frames, segments)).toEqual([2])
    expect(replayedFrameIndexes(frames, segments)).toEqual([...replayedFrames(frames, segments)])
  })

  it("ไม่มีข้อมูลช่วง ช่วงว่าง หรือไม่มีภาพ = 0 ภาพ (ไม่มีปุ่มกรอง)", () => {
    expect(replayedFrameIndexes(frames, undefined)).toEqual([])
    expect(replayedFrameIndexes(frames, [])).toEqual([])
    expect(replayedFrameIndexes([], [{ startMs: 0, endMs: 10_000 }])).toEqual([])
  })
})
