import { describe, expect, it } from "vitest"

import type { Cue } from "@/lib/types"

import { cueDisplayText, matchRanges, searchLines } from "./search"

const cue = (startMs: number, ...lines: string[]): Cue => ({ startMs, endMs: startMs + 2000, lines })

const CUES = [
  cue(0, "สวัสดีครับ ยินดีต้อนรับสู่", "กรุงเทพมหานคร"),
  cue(2000, "Hello World from Bangkok"),
  cue(4000, "วันนี้อากาศดี"),
  cue(6000, "ไปเที่ยวกรุงเทพกัน"),
]

describe("searchLines", () => {
  it("หาคำไทยที่อยู่กลางข้อความได้ รวมบรรทัดที่คำอยู่ในบรรทัดย่อยที่สอง", () => {
    expect(searchLines(CUES, "กรุงเทพ")).toEqual([0, 3])
    expect(searchLines(CUES, "อากาศ")).toEqual([2])
  })

  it("ภาษาอังกฤษไม่สนตัวพิมพ์เล็ก/ใหญ่", () => {
    expect(searchLines(CUES, "hello world")).toEqual([1])
    expect(searchLines(CUES, "BANGKOK")).toEqual([1])
  })

  it("ช่องว่างหลายช่องในคำค้นยุบเหลือช่องเดียว และตัดช่องว่างหัวท้าย", () => {
    expect(searchLines(CUES, "hello   world")).toEqual([1])
    expect(searchLines(CUES, "  bangkok  ")).toEqual([1])
  })

  it("คำค้นข้ามบรรทัดย่อย (ต่อด้วยช่องว่าง) ก็เจอ", () => {
    expect(searchLines(CUES, "สู่ กรุงเทพ")).toEqual([0])
  })

  it("เทียบหลัง NFC: ตัวอักษรที่เขียนแบบแยกเครื่องหมาย (e + ◌́) เทียบกับแบบรวม (é) ได้", () => {
    const decomposed = [cue(0, "Café ริมน้ำ")]
    expect(searchLines(decomposed, "CAFÉ")).toEqual([0])
  })

  it("คำค้นว่างหรือมีแต่ช่องว่าง = ทุกบรรทัด", () => {
    expect(searchLines(CUES, "")).toEqual([0, 1, 2, 3])
    expect(searchLines(CUES, "  ")).toEqual([0, 1, 2, 3])
  })

  it("ไม่เจอ = รายการว่าง · ไม่มีบรรทัดเลย = รายการว่าง", () => {
    expect(searchLines(CUES, "เชียงใหม่")).toEqual([])
    expect(searchLines([], "")).toEqual([])
  })
})

describe("matchRanges", () => {
  it("คืนทุกช่วงที่ตรง ไม่ซ้อนกัน ไม่สนตัวพิมพ์", () => {
    const text = cueDisplayText(cue(0, "Aa aA aa"))
    expect(matchRanges(text, "aa")).toEqual([
      [0, 2],
      [3, 5],
      [6, 8],
    ])
  })

  it("ตำแหน่งตรงกับข้อความที่แสดง (บรรทัดย่อยต่อด้วยช่องว่าง)", () => {
    const text = cueDisplayText(CUES[0])
    const [[start, end]] = matchRanges(text, "กรุงเทพ")
    expect(text.slice(start, end)).toBe("กรุงเทพ")
  })

  it("คำค้นว่าง = ไม่มีช่วง", () => {
    expect(matchRanges("abc", " ")).toEqual([])
  })
})
