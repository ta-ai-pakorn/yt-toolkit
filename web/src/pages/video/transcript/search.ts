import type { Cue } from "@/lib/types"

/** ข้อความของบรรทัดทรานสคริปต์ที่แสดงและใช้ค้นหา: ต่อบรรทัดย่อยด้วยช่องว่าง */
export function cueDisplayText(cue: Cue): string {
  return normalize(cue.lines.join(" "))
}

/** รูปแบบกลางก่อนเทียบ: NFC (สระ/วรรณยุกต์ไทยที่พิมพ์ต่างลำดับกันเทียบกันได้) และช่องว่างติดกันเหลือช่องเดียว */
function normalize(text: string): string {
  return text.normalize("NFC").replace(/\s+/g, " ")
}

const lower = (text: string) => text.toLocaleLowerCase("th")

/** คำค้นหลังจัดรูปแล้ว (ตัดช่องว่างหัวท้าย ตัวพิมพ์เล็ก) · ค้นแต่ช่องว่าง = "" (ไม่กรอง) */
function needle(query: string): string {
  return lower(normalize(query).trim())
}

export type Range = readonly [start: number, end: number]

/**
 * ช่วงที่ตรงคำค้นใน text (ตำแหน่งใน text ที่ผ่าน cueDisplayText แล้ว) ไม่ซ้อนกัน เรียงจากซ้ายไปขวา
 * ไม่สนตัวพิมพ์เล็ก/ใหญ่ · คำค้นว่าง = ไม่มีช่วง
 */
export function matchRanges(text: string, query: string): Range[] {
  const q = needle(query)
  if (q === "") return []
  const ranges: Range[] = []
  let index = 0
  while (index + q.length <= text.length) {
    if (lower(text.slice(index, index + q.length)) === q) {
      ranges.push([index, index + q.length])
      index += q.length
    } else index += 1
  }
  return ranges
}

/**
 * ตำแหน่งของบรรทัดที่มีคำค้น (ค้นใน lines.join(" ")) ไม่สนตัวพิมพ์เล็ก/ใหญ่ เทียบหลัง NFC และยุบช่องว่าง
 * คำค้นว่าง (หรือมีแต่ช่องว่าง) = ทุกบรรทัด
 */
export function searchLines(cues: readonly Cue[], query: string): number[] {
  const all = cues.map((_, index) => index)
  if (needle(query) === "") return all
  return all.filter((index) => matchRanges(cueDisplayText(cues[index]), query).length > 0)
}
