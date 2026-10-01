import type { Cue } from "@/lib/types"

/**
 * รูปแบบกลางก่อนแสดงและค้นหา: NFC (ตัวอักษรเดียวกันที่เขียนได้หลายแบบ เช่น é แบบรวม กับ e + ◌́ กลายเป็นแบบเดียวกัน)
 * และช่องว่าง/ขึ้นบรรทัดติดกันเหลือช่องเดียว · NFC ไม่แก้สระ/วรรณยุกต์ไทยที่พิมพ์ผิดลำดับ และไม่รวม ํ + า เป็น ำ
 */
function normalize(text: string): string {
  return text.normalize("NFC").replace(/\s+/g, " ")
}

const lower = (text: string) => text.toLocaleLowerCase("th")
const SPACE = /\s/

/** ข้อความของบรรทัดทรานสคริปต์ที่แสดง: ต่อบรรทัดย่อยด้วยช่องว่าง */
export function cueDisplayText(cue: Cue): string {
  return normalize(cue.lines.join(" "))
}

/**
 * บรรทัดที่เตรียมไว้ค้นหา (ทำครั้งเดียวต่อชุดบรรทัด ไม่ใช่ทุกครั้งที่พิมพ์)
 * key = ตัวพิมพ์เล็กและตัดช่องว่างทิ้งทั้งหมด · at[i] = ตำแหน่งใน text ของตัวที่ i ใน key (ไว้วาด <mark> บนข้อความจริง)
 */
export type PreparedLine = { text: string; key: string; at: number[] }

export function prepareLine(cue: Cue): PreparedLine {
  const text = cueDisplayText(cue)
  const lowered = lower(text)
  // ตัวพิมพ์เล็กยาวเท่าเดิม (แทบทุกภาษา) = เทียบตำแหน่งตรงตัว · ไม่เท่า (เช่น İ) = แปลงทีละตัว
  const sameLength = lowered.length === text.length
  let key = ""
  const at: number[] = []
  for (let i = 0; i < text.length; i++) {
    if (SPACE.test(text[i])) continue
    const piece = sameLength ? lowered[i] : lower(text[i])
    key += piece
    for (let j = 0; j < piece.length; j++) at.push(i)
  }
  return { text, key, at }
}

export function prepareLines(cues: readonly Cue[]): PreparedLine[] {
  return cues.map(prepareLine)
}

/**
 * คำค้นที่ใช้เทียบกับ key: NFC ตัวพิมพ์เล็ก และไม่มีช่องว่าง
 * ช่องว่างไม่มีผลทั้งสองฝั่ง: "กรุงเทพมหานคร" เจอข้อความที่ถูกแบ่งเป็นสองบรรทัด และ "hello world" เจอ "helloworld"
 */
export function searchNeedle(query: string): string {
  return lower(normalize(query)).replace(/\s/g, "")
}

/** ช่วงที่ตรงคำค้นในข้อความที่แสดง (ไม่ซ้อนกัน เรียงซ้ายไปขวา) · needle ว่าง = ไม่มีช่วง */
export type Range = readonly [start: number, end: number]

export function lineRanges(line: PreparedLine, needle: string): Range[] {
  if (needle === "") return []
  const ranges: Range[] = []
  let from = line.key.indexOf(needle)
  while (from !== -1) {
    const last = from + needle.length - 1
    ranges.push([line.at[from], line.at[last] + 1])
    from = line.key.indexOf(needle, from + needle.length)
  }
  return ranges
}

/** ตำแหน่งของบรรทัดที่มีคำค้น · คำค้นว่าง (หรือมีแต่ช่องว่าง) = ทุกบรรทัด */
export function searchPrepared(lines: readonly PreparedLine[], query: string): number[] {
  const needle = searchNeedle(query)
  const found: number[] = []
  lines.forEach((line, index) => {
    if (needle === "" || line.key.includes(needle)) found.push(index)
  })
  return found
}

/**
 * ตำแหน่งของบรรทัดที่มีคำค้น (ค้นใน lines.join(" ")) ไม่สนตัวพิมพ์เล็ก/ใหญ่ เทียบหลัง NFC และไม่สนช่องว่าง
 * คำค้นว่าง (หรือมีแต่ช่องว่าง) = ทุกบรรทัด · หน้าเว็บเตรียมบรรทัดไว้ครั้งเดียวแล้วใช้ searchPrepared แทน
 */
export function searchLines(cues: readonly Cue[], query: string): number[] {
  return searchPrepared(prepareLines(cues), query)
}
