/**
 * ซับตามช่วงเวลา (M5 รอบ A, AC-SUB-10): ฝั่งเว็บต้องได้ผลตรงกับ core/srt_builder.range_tokens/clamp_cues ทุกไบต์
 * อ่านชุดเดียวกับ tests/unit/test_srt_range.py ห้ามแก้ไฟล์ fixture เพื่อให้เทสนี้ผ่าน
 */
import { describe, expect, it } from "vitest"

import casesRaw from "../../../tests/fixtures/subs/range-cases.json?raw"
import goldenRaw from "../../../tests/fixtures/subs/range-golden.json?raw"
import enAsrRaw from "../../../tests/fixtures/subs/tokens/en-asr.json?raw"
import thAsrRaw from "../../../tests/fixtures/subs/tokens/th-asr.json?raw"

import { buildCues, clampCues, rangeTokens, toSrt } from "./srt-builder"
import { PRESETS } from "./sub-options"
import type { SubOptions, SubToken } from "./types"

type RangeCase = {
  name: string
  options: SubOptions
  startMs: number
  endMs: number
  tokens: SubToken[]
  ranged: SubToken[]
  srt: string
}

const cases = (JSON.parse(casesRaw) as { cases: RangeCase[] }).cases
const golden = JSON.parse(goldenRaw) as Record<string, string>
const tokenDocs: Record<string, SubToken[]> = {
  "th-asr": (JSON.parse(thAsrRaw) as { tokens: SubToken[] }).tokens,
  "en-asr": (JSON.parse(enAsrRaw) as { tokens: SubToken[] }).tokens,
}

const srtOf = (tokens: readonly SubToken[], startMs: number, endMs: number, options: SubOptions) =>
  toSrt(clampCues(buildCues(rangeTokens(tokens, startMs, endMs), options), endMs - startMs))

describe("range parity with the Python builder", () => {
  it.each(cases.map((c) => [c.name, c] as const))("%s", (_name, c) => {
    expect(rangeTokens(c.tokens, c.startMs, c.endMs)).toEqual(c.ranged)
    expect(srtOf(c.tokens, c.startMs, c.endMs, c.options)).toBe(c.srt)
  })

  it.each(["th-asr", "en-asr"])("%s medium 90000-210000 matches range-golden.json", (name) => {
    const expected = golden[`${name}.medium.90000-210000`]
    expect(expected.length).toBeGreaterThan(0)
    expect(srtOf(tokenDocs[name], 90_000, 210_000, PRESETS.medium)).toBe(expected)
  })

  it("clampCues shortens only the ends", () => {
    const cues = [
      { startMs: 0, endMs: 1000, lines: ["a"] },
      { startMs: 1000, endMs: 5000, lines: ["b"] },
    ]
    expect(clampCues(cues, 3000)).toEqual([cues[0], { startMs: 1000, endMs: 3000, lines: ["b"] }])
  })
})
