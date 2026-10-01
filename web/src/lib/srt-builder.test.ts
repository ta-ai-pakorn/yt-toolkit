import { describe, expect, it } from "vitest"

import casesRaw from "../../../tests/fixtures/subs/builder-cases.json?raw"
import { cuesFor } from "@/pages/video/use-cues"
import { PRESETS } from "./sub-options"
import {
  buildCues,
  cueStats,
  cueText,
  displayLen,
  isPunctOnly,
  MERGE_LIMIT_FACTOR,
  toMd,
  toSrt,
  toTxt,
} from "./srt-builder"
import type { Cue, SubOptions, SubToken } from "./types"

type MdCase = { title: string; videoId: string; chapters: { startMs: number; title: string }[]; out: string }

type BuilderCase = {
  name: string
  options: SubOptions
  tokens: SubToken[]
  cues: Cue[]
  srt: string
  txt: string
  md?: MdCase
}

// ชุดทดสอบเดียวกับฝั่ง Python (core/srt_builder.py) ผลต้องตรงกันทุกไบต์
const { cases } = JSON.parse(casesRaw) as { cases: BuilderCase[] }

describe("shared builder cases", () => {
  it("มีครบ 32 เคส", () => {
    expect(cases).toHaveLength(32)
  })
})

describe.each(cases)("builder case $name", (c) => {
  it("cues", () => expect(buildCues(c.tokens, c.options)).toEqual(c.cues))
  it("srt", () => expect(toSrt(buildCues(c.tokens, c.options))).toBe(c.srt))
  it("txt", () => expect(toTxt(c.tokens)).toBe(c.txt))
  if (c.md) {
    const md = c.md
    it("md", () => expect(toMd(c.tokens, md)).toBe(md.out))
  }
})

describe("displayLen", () => {
  it("ไม่นับสระบน สระล่าง และวรรณยุกต์ไทย", () => {
    expect(displayLen("ที่")).toBe(1)
    expect(displayLen("น้ำ")).toBe(2)
    expect(displayLen("ดี")).toBe(1)
    expect(displayLen("กัน")).toBe(2)
  })

  it("นับ emoji เป็น 1 ตัว (code point ไม่ใช่ UTF-16)", () => {
    expect(displayLen("😀")).toBe(1)
    expect(displayLen("a😀b")).toBe(3)
  })

  it("ข้อความว่าง = 0", () => {
    expect(displayLen("")).toBe(0)
  })
})

describe("cueText", () => {
  it("ยุบช่องว่าง U+0020 ที่ติดกัน และตัดเฉพาะ U+0020 ที่หัวท้าย", () => {
    const tok = (t: string): SubToken => ({ t, s: 0, e: 0 })
    expect(cueText([tok("  Hello"), tok("   world "), tok(" ")])).toBe("Hello world")
    expect(cueText([tok(" a"), tok(" b ")])).toBe(" a b ")
  })
})

describe("buildCues", () => {
  it("โหมดนับคำที่ไม่มี tokensPerCue โยน error", () => {
    expect(() => buildCues([{ t: "a", s: 0, e: 100 }], { ...PRESETS.medium, mode: "tokens" })).toThrow()
  })

  it("ไม่ตรวจช่วงค่า (ค่านอก LIMITS ใช้ได้)", () => {
    expect(() => buildCues([{ t: "a", s: 0, e: 100 }], { ...PRESETS.medium, maxChars: 1, minMs: 1 })).not.toThrow()
  })

  it("MERGE_LIMIT_FACTOR = 1.0 (Q3 = ก)", () => {
    expect(MERGE_LIMIT_FACTOR).toBe(1)
  })

  it("SRT ชั่วโมงเกิน 2 หลักได้", () => {
    const cues = buildCues([{ t: "x", s: 360_000_005, e: 360_002_000 }], PRESETS.medium)
    expect(toSrt(cues)).toBe("1\r\n100:00:00,005 --> 100:00:02,000\r\nx\r\n")
  })
})

describe("cueStats", () => {
  it("เคสแรก: 2 ซับ เฉลี่ย 16.5 ตัว ไม่มีซับสั้นกว่า 1 วินาที", () => {
    const first = cases[0]
    expect(cueStats(buildCues(first.tokens, first.options))).toEqual({ count: 2, avgChars: 16.5, underOneSecond: 0 })
  })

  it("ไม่มีซับ = ศูนย์ทั้งหมด", () => {
    expect(cueStats([])).toEqual({ count: 0, avgChars: 0, underOneSecond: 0 })
  })

  it("นับซับที่สั้นกว่า 1 วินาที และปัดค่าเฉลี่ยเป็นทศนิยม 1 ตำแหน่ง", () => {
    const cues: Cue[] = [
      { startMs: 0, endMs: 999, lines: ["ab"] },
      { startMs: 999, endMs: 1999, lines: ["ab", "c"] },
      { startMs: 1999, endMs: 2500, lines: ["ที่"] },
    ]
    // (2 + 4 + 1) / 3 = 2.333…
    expect(cueStats(cues)).toEqual({ count: 3, avgChars: 2.3, underOneSecond: 2 })
  })
})

describe("cuesFor (ตัวในของ useCues)", () => {
  it("ยังไม่มี token = ไม่มีซับ", () => {
    expect(cuesFor(undefined, PRESETS.medium)).toEqual([])
  })

  it("มี token = buildCues", () => {
    const first = cases[0]
    expect(cuesFor(first.tokens, first.options)).toEqual(first.cues)
  })
})

// AC-SUB-07: ตัวอย่างซับต้องขึ้นภายใน 200 ms (รวมวาดหน้าจอ) จึงให้ buildCues เองใช้ไม่เกิน 100 ms
// preset ยาว (2 บรรทัด) หนักสุด เพราะต้องหาจุดแบ่งบรรทัดทุกครั้งที่เพิ่มคำ
describe.each(["medium", "long"] as const)("performance (%s)", (preset) => {
  it("20,000 คำไทย ผ่าน buildCues ค่ามัธยฐาน 5 รอบ < 100 ms", () => {
    const tokens: SubToken[] = Array.from({ length: 20_000 }, (_, i) => ({ t: "น้ำ", s: i * 300, e: i * 300 + 300 }))
    const runs: number[] = []
    for (let n = 0; n < 5; n++) {
      const t0 = performance.now()
      buildCues(tokens, PRESETS[preset])
      runs.push(performance.now() - t0)
    }
    runs.sort((a, b) => a - b)
    expect(runs[2]).toBeLessThan(100)
  })
})

describe("isPunctOnly (owner round 3, เหมือน is_punct_only ฝั่ง Python)", () => {
  const tok = (t: string): SubToken => ({ t, s: 0, e: 1 })

  it.each([".", ",", " ?", "!?", "...", "\u2026", "--", '"', "(", ")", "\u266a", "$", "+", "\u{1F600}", "\u0E5A", " . "])(
    "%j เป็นเครื่องหมายล้วน",
    (text) => {
      expect(isPunctOnly(tok(text))).toBe(true)
    }
  )

  it.each(["a.", "1", ". .", "ok", "\u0E19\u0E30", "\u0E2F", "\u00a0.", "x\u266a"])("%j ไม่ใช่", (text) => {
    expect(isPunctOnly(tok(text))).toBe(false)
  })
})

describe("word preset + punctuation (owner round 3)", () => {
  it("ไม่มีซับที่มีแค่ . หรือ , และ 1 คำต่อซับ", () => {
    const tokens: SubToken[] = [
      { t: "Yes", s: 0, e: 300 },
      { t: ",", s: 300, e: 320 },
      { t: " sir", s: 320, e: 700 },
      { t: ".", s: 700, e: 900 },
    ]
    const cues = buildCues(tokens, PRESETS.word)
    expect(cues.map((cue) => cue.lines)).toEqual([["Yes,"], ["sir."]])
  })
})
