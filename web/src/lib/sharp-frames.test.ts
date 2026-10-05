/**
 * ภาพคม (M5 รอบ B): แผนเวลาต้องตรงกับ core/sharp.py ทุกเคส (อ่าน fixture ชุดเดียวกับ tests/unit/test_sharp_plan.py)
 * และตัวคำนวณของ dialog "ขอภาพคม" · ห้ามแก้ไฟล์ fixture เพื่อให้เทสนี้ผ่าน
 */
import { describe, expect, it } from "vitest"

import casesRaw from "../../../tests/fixtures/sharp/plan-cases.json?raw"

import {
  MAX_SHARP_FRAMES,
  customTimes,
  defaultCustomText,
  defaultIntervalS,
  parseIntervalText,
  planSharp,
  raisedIntervalS,
  sharpDialogModel,
  sharpEstimate,
  sharpKey,
  type SharpFast,
} from "./sharp-frames"
import type { VideoFormat } from "./types"

type PlanCase = {
  name: string
  durationS: number
  intervalS: number | null
  fast: { stepMs: number; count: number } | null
  expect: { count: number; first: number; last: number; intervalS: number | null; raised: boolean; times?: number[] }
}

const cases = (JSON.parse(casesRaw) as { cases: PlanCase[] }).cases
const steps = (stepMs: number, count: number) => Array.from({ length: count }, (_, i) => i * stepMs)

describe("planSharp (parity with core/sharp.py)", () => {
  it.each(cases.map((c) => [c.name, c] as const))("%s", (_, c) => {
    const plan = planSharp(c.durationS, { intervalS: c.intervalS, fastTimes: c.fast ? steps(c.fast.stepMs, c.fast.count) : null })
    expect(plan.timesMs).toHaveLength(c.expect.count)
    expect(plan.timesMs.length).toBeLessThanOrEqual(MAX_SHARP_FRAMES)
    expect(plan.timesMs[0]).toBe(c.expect.first)
    expect(plan.timesMs.at(-1)).toBe(c.expect.last)
    expect(plan.intervalS).toBe(c.expect.intervalS)
    expect(plan.raised).toBe(c.expect.raised)
    if (c.expect.times) expect(plan.timesMs).toEqual(c.expect.times)
  })

  it("helpers", () => {
    expect([defaultIntervalS(19), defaultIntervalS(635), defaultIntervalS(36000)]).toEqual([1, 7, 360])
    expect([raisedIntervalS(635), raisedIntervalS(200)]).toEqual([4, 1])
    expect(customTimes(3, 10)).toEqual([0, 3000, 6000, 9000])
    expect(sharpKey("aqz-KE-bpKQ")).toEqual(["sharp", "aqz-KE-bpKQ"])
  })

  it.each<[number, number | null, number[] | null]>([
    [0, null, null],
    [10, 0, null],
    [10, 3601, null],
    [10, 1.5, null],
    [10, null, []],
  ])("throws on bad input (%s, %s, %j)", (durationS, intervalS, fastTimes) => {
    expect(() => planSharp(durationS, { intervalS, fastTimes })).toThrow(RangeError)
  })
})

describe("parseIntervalText", () => {
  it.each<[string, number | null]>([
    ["7", 7],
    [" 60 ", 60],
    ["3600", 3600],
    ["1", 1],
    ["", null],
    ["0", null],
    ["3601", null],
    ["1.5", null],
    ["1e3", null],
    ["-2", null],
    ["๕", null],
  ])("%j -> %s", (text, want) => {
    expect(parseIntervalText(text)).toBe(want)
  })
})

const fmt = (over: Partial<VideoFormat> & Pick<VideoFormat, "formatId" | "height">): VideoFormat => ({
  fps: 30,
  vcodec: "avc1.4d401f",
  compat: true,
  ...over,
})

describe("sharpEstimate", () => {
  it("largest short side <= 720, avc1 before vp9 before av01, then the smallest size", () => {
    const video = [
      fmt({ formatId: "299", width: 1920, height: 1080, sizeBytes: 257_000_000 }),
      fmt({ formatId: "398", width: 1280, height: 720, vcodec: "av01.0.08M.08", sizeBytes: 71_000_000 }),
      fmt({ formatId: "302", width: 1280, height: 720, vcodec: "vp9", sizeBytes: 112_000_000 }),
      fmt({ formatId: "298", width: 1280, height: 720, sizeBytes: 150_524_867 }),
      fmt({ formatId: "135", width: 854, height: 480, sizeBytes: 28_000_000 }),
    ]
    expect(sharpEstimate(video)).toEqual({ sizeBytes: 150_524_867, shortSide: 720, portrait: false })
  })

  it("portrait clips are measured on the short side", () => {
    const video = [
      fmt({ formatId: "137", width: 1080, height: 1920 }),
      fmt({ formatId: "136", width: 720, height: 1280, sizeBytes: 9_000_000 }),
    ]
    expect(sharpEstimate(video)).toEqual({ sizeBytes: 9_000_000, shortSide: 720, portrait: true })
  })

  it("low resolution, unknown size, nothing at all", () => {
    expect(sharpEstimate([fmt({ formatId: "134", width: 320, height: 240 })])).toEqual({ shortSide: 240, portrait: false })
    expect(sharpEstimate([])).toEqual({ shortSide: null, portrait: false })
  })

  it("only formats above 720: the smallest of them", () => {
    const video = [fmt({ formatId: "308", width: 2560, height: 1440 }), fmt({ formatId: "299", width: 1920, height: 1080, sizeBytes: 5 })]
    expect(sharpEstimate(video)).toEqual({ sizeBytes: 5, shortSide: 1080, portrait: false })
  })
})

const BBB_FAST: SharpFast = { intervalMs: 4961, timesMs: steps(4961, 128) }
const BBB_VIDEO = [fmt({ formatId: "298", width: 1280, height: 720, sizeBytes: 150_524_867 })]

describe("sharpDialogModel", () => {
  const base = { durationS: 635, fast: BBB_FAST, mode: "same" as const, customText: "7", video: BBB_VIDEO, hasSharp: false }

  it("same times by default: interval with one decimal, count, sends {}", () => {
    expect(sharpDialogModel(base)).toEqual({
      sameAvailable: true,
      mode: "same",
      sameInterval: "5.0",
      sameCount: 128,
      customCount: 91,
      customError: false,
      overflow: null,
      params: {},
      sizeBytes: 150_524_867,
      resolution: { kind: "wide" },
      replace: false,
    })
  })

  it.each([
    [4926, "4.9"],
    [1450, "1.5"],
  ])("the same-times interval %d ms rounds half up to %s", (intervalMs, text) => {
    const fast: SharpFast = { intervalMs, timesMs: steps(intervalMs, 20) }
    expect(sharpDialogModel({ ...base, fast }).sameInterval).toBe(text)
  })

  it("custom 7 sends intervalS 7", () => {
    const model = sharpDialogModel({ ...base, mode: "custom" })
    expect(model.params).toEqual({ intervalS: 7 })
    expect(model.customCount).toBe(91)
  })

  it("custom 2 on 635 s is over 200: sentence values and intervalS 4 (AC-FRAME-04)", () => {
    const model = sharpDialogModel({ ...base, mode: "custom", customText: "2" })
    expect(model.overflow).toEqual({ n: "2", count: 318, n2: 4 })
    expect(model.params).toEqual({ intervalS: 4 })
  })

  it("same times over 200 (long clip): the one-decimal interval and intervalS N2", () => {
    const fast: SharpFast = { intervalMs: 10_000, timesMs: steps(10_000, 360) }
    const model = sharpDialogModel({ ...base, durationS: 3600, fast })
    expect(model.overflow).toEqual({ n: "10.0", count: 360, n2: 18 })
    expect(model.params).toEqual({ intervalS: 18 })
  })

  it.each(["", "0", "1.5", "abc", "3601"])("custom %j is invalid: error and no params", (customText) => {
    const model = sharpDialogModel({ ...base, mode: "custom", customText })
    expect(model.customError).toBe(true)
    expect(model.customCount).toBeNull()
    expect(model.params).toBeNull()
  })

  it("an invalid custom text does not block the same-times choice", () => {
    expect(sharpDialogModel({ ...base, customText: "abc" }).params).toEqual({})
  })

  it("no storyboard: custom only, default text max(1, ceil(d/100))", () => {
    expect(defaultCustomText(19)).toBe("1")
    expect(defaultCustomText(635)).toBe("7")
    const model = sharpDialogModel({ ...base, durationS: 19, fast: null, customText: defaultCustomText(19), video: [fmt({ formatId: "134", width: 320, height: 240 })] })
    expect(model.sameAvailable).toBe(false)
    expect(model.mode).toBe("custom")
    expect(model.params).toEqual({ intervalS: 1 })
    expect(model.customCount).toBe(19)
    expect(model.resolution).toEqual({ kind: "low", h: 240 })
    expect(model.sizeBytes).toBeNull()
  })

  it("portrait clip and an existing sharp set", () => {
    const model = sharpDialogModel({ ...base, video: [fmt({ formatId: "136", width: 720, height: 1280 })], hasSharp: true })
    expect(model.resolution).toEqual({ kind: "tall" })
    expect(model.replace).toBe(true)
  })
})
