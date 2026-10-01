/**
 * ฝั่งเว็บต้องสร้างซับได้ตรงกับ backend ทุกไบต์ (PRD AC-SUB-06)
 *
 * อ่าน token และ golden ชุดเดียวกับที่ tests/unit/test_srt_golden.py สร้างจากข้อมูลจริง
 * แล้วเทียบผลของ srt-builder.ts กับไฟล์ golden ตรง ๆ ถ้าไม่ตรงคือฝั่งใดฝั่งหนึ่งผิดจากสัญญา C6
 * ห้ามแก้ golden เพื่อให้เทสนี้ผ่าน
 */
import { describe, expect, it } from "vitest"

import { buildCues, toMd, toSrt, toTxt, type MdMeta } from "./srt-builder"
import { PRESETS } from "./sub-options"
import type { SubOptions, SubToken } from "./types"

const tokenFiles = import.meta.glob("../../../tests/fixtures/subs/tokens/*.json", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>
const goldenFiles = import.meta.glob("../../../tests/fixtures/subs/golden/*", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>

type TokenDoc = { tokens: SubToken[]; hasWordTiming: boolean; md: MdMeta }

const baseName = (path: string) => path.slice(path.lastIndexOf("/") + 1)

const tokenDocs = new Map<string, TokenDoc>(
  Object.entries(tokenFiles).map(([path, raw]) => [baseName(path).replace(/\.json$/, ""), JSON.parse(raw) as TokenDoc]),
)
const golden = new Map<string, string>(Object.entries(goldenFiles).map(([path, raw]) => [baseName(path), raw]))

const CUSTOM: SubOptions = { maxChars: 30, lines: 2, minMs: 1000, maxMs: 6000, mode: "tokens", tokensPerCue: 4 }
const NAMES = ["th-asr", "th-vtt", "en-asr", "en-owner", "th-owner"] as const
const PRESET_NAMES = ["short", "medium", "long"] as const
// preset "ทีละคำ" มี golden เฉพาะซับอัตโนมัติที่มีเวลาระดับคำ ไทยและอังกฤษ (ตรงกับ WORD_NAMES ใน test_srt_golden.py)
const WORD_NAMES = ["th-asr", "en-asr"] as const

function expected(file: string): string {
  const text = golden.get(file)
  if (text === undefined) throw new Error(`golden ${file} is missing: run YT_UPDATE_GOLDEN=1 uv run pytest tests/unit/test_srt_golden.py`)
  return text
}

describe("golden files found", () => {
  it("finds exactly the expected golden and token files", () => {
    // 5 ชื่อ x (3 srt + txt + md) + ทีละคำ 2 ไฟล์ + custom-tokens = 28 ไฟล์ ขาดหรือเกินแม้ไฟล์เดียวต้องแดง
    const names: string[] = [`th-asr.custom-tokens.srt`]
    for (const name of NAMES) {
      for (const preset of PRESET_NAMES) names.push(`${name}.${preset}.srt`)
      names.push(`${name}.txt`, `${name}.md`)
    }
    for (const name of WORD_NAMES) names.push(`${name}.word.srt`)
    expect([...golden.keys()].sort()).toEqual(names.sort())
    expect(golden.size).toBe(28)
    expect([...tokenDocs.keys()].sort()).toEqual([...NAMES].sort())
  })

  it("keeps CRLF and no BOM in the raw golden text", () => {
    for (const [file, text] of golden) {
      expect(text.charCodeAt(0), file).not.toBe(0xfeff)
      expect(text.includes("\r\n"), file).toBe(true)
      expect(text.replace(/\r\n/g, "").includes("\n"), file).toBe(false)
    }
  })
})

describe.each(NAMES)("%s parity with the Python builder", (name) => {
  const doc = tokenDocs.get(name)
  if (!doc) throw new Error(`tokens/${name}.json is missing`)

  it.each(PRESET_NAMES)("%s .srt", (preset) => {
    expect(toSrt(buildCues(doc.tokens, PRESETS[preset]))).toBe(expected(`${name}.${preset}.srt`))
  })

  it(".txt", () => {
    expect(toTxt(doc.tokens)).toBe(expected(`${name}.txt`))
  })

  it(".md", () => {
    expect(toMd(doc.tokens, doc.md)).toBe(expected(`${name}.md`))
  })
})

describe.each(WORD_NAMES)("%s word preset parity", (name) => {
  it("word .srt", () => {
    const doc = tokenDocs.get(name)
    if (!doc) throw new Error(`tokens/${name}.json is missing`)
    const cues = buildCues(doc.tokens, PRESETS.word)
    expect(cues).toHaveLength(doc.tokens.length)
    expect(toSrt(cues)).toBe(expected(`${name}.word.srt`))
  })
})

describe("custom options", () => {
  it("th-asr tokens mode, 30 chars, 2 lines", () => {
    const doc = tokenDocs.get("th-asr")
    if (!doc) throw new Error("tokens/th-asr.json is missing")
    expect(toSrt(buildCues(doc.tokens, CUSTOM))).toBe(expected("th-asr.custom-tokens.srt"))
  })
})
