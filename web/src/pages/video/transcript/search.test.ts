import { describe, expect, it } from "vitest"

import type { Cue } from "@/lib/types"

import { lineRanges, prepareLine, prepareLines, searchLines, searchNeedle, searchPrepared } from "./search"

const cue = (startMs: number, ...lines: string[]): Cue => ({ startMs, endMs: startMs + 2000, lines })

const CUES = [
  cue(0, "สวัสดีครับ ยินดีต้อนรับสู่", "กรุงเทพมหานคร"),
  cue(2000, "Hello World from Bangkok"),
  cue(4000, "วันนี้อากาศดี"),
  cue(6000, "ไปเที่ยวกรุงเทพกัน"),
  cue(8000, "ยินดีต้อนรับสู่กรุงเทพ", "มหานคร"),
]

/** ข้อความที่ถูกเน้นในบรรทัด (ตามช่วงของ lineRanges) */
function marked(line: Cue, query: string): string[] {
  const prepared = prepareLine(line)
  return lineRanges(prepared, searchNeedle(query)).map(([start, end]) => prepared.text.slice(start, end))
}

describe("searchLines", () => {
  it("หาคำไทยที่อยู่กลางข้อความได้ รวมบรรทัดที่คำอยู่ในบรรทัดย่อยที่สอง", () => {
    expect(searchLines(CUES, "กรุงเทพ")).toEqual([0, 3, 4])
    expect(searchLines(CUES, "อากาศ")).toEqual([2])
  })

  it("ภาษาอังกฤษไม่สนตัวพิมพ์เล็ก/ใหญ่", () => {
    expect(searchLines(CUES, "hello world")).toEqual([1])
    expect(searchLines(CUES, "BANGKOK")).toEqual([1])
  })

  it("ช่องว่างหลายช่องในคำค้นไม่มีผล และตัดช่องว่างหัวท้าย", () => {
    expect(searchLines(CUES, "hello   world")).toEqual([1])
    expect(searchLines(CUES, "  bangkok  ")).toEqual([1])
  })

  it("ไม่สนช่องว่าง: คำที่ถูกแบ่งเป็นสองบรรทัดย่อยก็เจอ และคำค้นมีช่องว่างก็เจอข้อความที่ไม่มีช่องว่าง", () => {
    expect(searchLines(CUES, "กรุงเทพมหานคร")).toEqual([0, 4])
    expect(searchLines(CUES, "helloworld")).toEqual([1])
    expect(searchLines(CUES, "ยินดี ต้อนรับ")).toEqual([0, 4])
  })

  it("เทียบหลัง NFC: ตัวอักษรที่เขียนแบบแยกเครื่องหมาย (e + ◌́) เทียบกับแบบรวม (é) ได้", () => {
    const decomposed = [cue(0, "Café ริมน้ำ")]
    expect(searchLines(decomposed, "CAFÉ")).toEqual([0])
  })

  it("คำค้นว่างหรือมีแต่ช่องว่าง = ทุกบรรทัด", () => {
    expect(searchLines(CUES, "")).toEqual([0, 1, 2, 3, 4])
    expect(searchLines(CUES, "  ")).toEqual([0, 1, 2, 3, 4])
  })

  it("ไม่เจอ = รายการว่าง · ไม่มีบรรทัดเลย = รายการว่าง", () => {
    expect(searchLines(CUES, "เชียงใหม่")).toEqual([])
    expect(searchLines([], "")).toEqual([])
  })
})

describe("lineRanges", () => {
  it("คืนทุกช่วงที่ตรง ไม่ซ้อนกัน ไม่สนตัวพิมพ์", () => {
    expect(marked(cue(0, "Aa aA aa"), "aa")).toEqual(["Aa", "aA", "aa"])
  })

  it("ช่วงตรงกับข้อความที่แสดง (บรรทัดย่อยต่อด้วยช่องว่าง)", () => {
    expect(marked(CUES[0], "กรุงเทพ")).toEqual(["กรุงเทพ"])
  })

  it("คำที่ถูกแบ่งสองบรรทัดย่อยเน้นทั้งช่วง รวมช่องว่างตรงกลาง", () => {
    expect(marked(CUES[4], "กรุงเทพมหานคร")).toEqual(["กรุงเทพ มหานคร"])
    expect(marked(CUES[1], "loworld")).toEqual(["lo World"])
  })

  it("ตัวพิมพ์เล็กยาวไม่เท่าตัวพิมพ์ใหญ่ (İ) ช่วงยังตรงกับข้อความจริง", () => {
    expect(marked(cue(0, "İstanbul City"), "city")).toEqual(["City"])
  })

  it("คำค้นว่าง = ไม่มีช่วง", () => {
    expect(lineRanges(prepareLine(cue(0, "abc")), searchNeedle(" "))).toEqual([])
  })
})

describe("ความเร็วของการค้นหา (คลิปยาว 1 ชั่วโมง)", () => {
  // 3,200 บรรทัดไทย ~ คลิปพูด 1 ชั่วโมงที่แบ่งบรรทัดแบบสั้น
  const WORDS = ["สวัสดี", "ครับ", "วันนี้", "เรา", "จะ", "ไป", "เที่ยว", "ตลาด", "น้ำ", "อาหาร", "อร่อย", "มาก", "ที่สุด", "กรุงเทพ"]
  const many: Cue[] = Array.from({ length: 3200 }, (_, i) => {
    const words = Array.from({ length: 8 }, (_, j) => WORDS[(i * 7 + j * 3) % WORDS.length])
    return cue(i * 1100, words.slice(0, 4).join(""), words.slice(4).join(" "))
  })

  it("ค้นหาต่อหนึ่งครั้งพิมพ์ (บรรทัดเตรียมไว้แล้ว) ค่ากลางน้อยกว่า 20 ms", () => {
    const prepared = prepareLines(many)
    const queries = ["ก", "กร", "กรุง", "กรุงเทพ", "น้ำ", "อร่อยมาก", "ตลาด น้ำ", "ไม่มีคำนี้", "ครับวันนี้", "ที่สุด", "เที่ยว"]
    const times = queries.map((query) => {
      const start = performance.now()
      searchPrepared(prepared, query)
      return performance.now() - start
    })
    times.sort((a, b) => a - b)
    expect(times[Math.floor(times.length / 2)]).toBeLessThan(20)
    expect(searchPrepared(prepared, "กรุงเทพ").length).toBeGreaterThan(0)
  })
})
