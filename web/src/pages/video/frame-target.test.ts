import { describe, expect, it } from "vitest"

import type { Cue, StoryboardFrame } from "@/lib/types"

import { cueIndexAt, nearestFrameIndex } from "./frame-target"

const frame = (index: number, tMs: number): StoryboardFrame => ({ index, tMs, url: `/f/${index}.jpg` })
// ภาพห่างกัน 5 วินาที: 0, 5000, 10000, 15000
const FRAMES = [0, 5000, 10000, 15000].map((tMs, index) => frame(index, tMs))

const cue = (startMs: number, endMs: number): Cue => ({ startMs, endMs, lines: [`${startMs}`] })
// บรรทัด 1-3 วินาที, 4-6 วินาที (ช่องว่าง 3-4), 10-12 วินาที (ช่องว่าง 6-10)
const CUES = [cue(1000, 3000), cue(4000, 6000), cue(10000, 12000)]

describe("nearestFrameIndex", () => {
  it("เวลาตรงกับภาพพอดีได้ภาพนั้น", () => {
    expect(nearestFrameIndex(FRAMES, 10000)).toBe(2)
    expect(nearestFrameIndex(FRAMES, 0)).toBe(0)
  })

  it("ใกล้ภาพไหนมากกว่าได้ภาพนั้น", () => {
    expect(nearestFrameIndex(FRAMES, 7600)).toBe(2)
    expect(nearestFrameIndex(FRAMES, 7400)).toBe(1)
  })

  it("อยู่กึ่งกลางพอดีเลือกภาพที่มาก่อน", () => {
    expect(nearestFrameIndex(FRAMES, 7500)).toBe(1)
    expect(nearestFrameIndex(FRAMES, 2500)).toBe(0)
  })

  it("ก่อนภาพแรกได้ภาพแรก", () => {
    const later = [frame(0, 3000), frame(1, 8000)]
    expect(nearestFrameIndex(later, 0)).toBe(0)
  })

  it("หลังภาพสุดท้ายได้ภาพสุดท้าย", () => {
    expect(nearestFrameIndex(FRAMES, 999_999)).toBe(3)
  })

  it("ไม่มีภาพเลย = -1", () => {
    expect(nearestFrameIndex([], 5000)).toBe(-1)
  })
})

describe("cueIndexAt", () => {
  it("ก่อนบรรทัดแรกได้บรรทัดแรก", () => {
    expect(cueIndexAt(CUES, 0)).toBe(0)
    expect(cueIndexAt(CUES, 999)).toBe(0)
  })

  it("อยู่ในบรรทัดได้บรรทัดนั้น (รวมเวลาเริ่มพอดี)", () => {
    expect(cueIndexAt(CUES, 1000)).toBe(0)
    expect(cueIndexAt(CUES, 5000)).toBe(1)
    expect(cueIndexAt(CUES, 10000)).toBe(2)
  })

  it("อยู่ในช่องว่างระหว่างบรรทัดได้บรรทัดก่อนหน้า", () => {
    expect(cueIndexAt(CUES, 3500)).toBe(0)
    expect(cueIndexAt(CUES, 8000)).toBe(1)
  })

  it("หลังบรรทัดสุดท้ายได้บรรทัดสุดท้าย", () => {
    expect(cueIndexAt(CUES, 60_000)).toBe(2)
  })

  it("ไม่มีบรรทัดเลย = -1", () => {
    expect(cueIndexAt([], 5000)).toBe(-1)
  })
})
