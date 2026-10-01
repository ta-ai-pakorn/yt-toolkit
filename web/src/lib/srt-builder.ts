/**
 * แปลง token (คำพร้อมเวลา) เป็นซับ แล้วเขียนออกเป็น .srt / .txt / .md (PRD FR-SUB, AC-SUB-04/05/08)
 *
 * พอร์ตจาก `src/yttoolkit/core/srt_builder.py` ตามสัญญา C6 ในแผน M3 ผลต้องตรงกับฝั่ง Python ทุกไบต์
 * ทั้งสองฝั่งทดสอบด้วยชุดเดียวกันคือ `tests/fixtures/subs/builder-cases.json` แก้ตรงนี้ต้องแก้ฝั่ง Python
 * และชุดทดสอบไปพร้อมกัน
 *
 * ฝั่งเว็บใช้สร้างตัวอย่างซับ (preview) ทันทีที่ผู้ใช้ปรับตัวเลือก ไฟล์ที่โหลดจริงสร้างที่ backend
 */
import type { Cue, SubOptions, SubToken } from "./types"

/** Q3 = ก: รวมซับที่สั้นเกินกับตัวถัดไปได้เฉพาะเมื่อไม่เกินขีดจำกัดเลย */
export const MERGE_LIMIT_FACTOR = 1.0

const GAP_SPLIT_MS = 1000 // เงียบนานเท่านี้ขึ้นไป = ขึ้นซับใหม่
const PARAGRAPH_GAP_MS = 2000 // เงียบนานเท่านี้ขึ้นไป = ขึ้นย่อหน้าใหม่ใน .txt / .md
const MD_SECTION_MS = 120_000 // ไม่มี chapter: แบ่งหัวข้อ .md ทุก 2 นาที
const CRLF = "\r\n"

/** สระบน สระล่าง วรรณยุกต์ไทยที่ไม่กินที่ (Q7 = ก): U+0E31, U+0E34-0E3A, U+0E47-0E4E */
function isThaiMark(cp: number): boolean {
  return cp === 0x0e31 || (cp >= 0x0e34 && cp <= 0x0e3a) || (cp >= 0x0e47 && cp <= 0x0e4e)
}

/** ความยาวตามที่ตาเห็น: นับ code point ยกเว้นสระบน/ล่างและวรรณยุกต์ไทย ("ที่" = 1, "น้ำ" = 2, "😀" = 1) */
export function displayLen(text: string): number {
  let n = 0
  // for…of เดินทีละ code point (ห้ามใช้ .length ซึ่งนับ UTF-16 ทำให้ emoji นับเป็น 2)
  for (const ch of text) {
    if (!isThaiMark(ch.codePointAt(0) ?? 0)) n++
  }
  return n
}

/** ยุบช่องว่าง U+0020 ที่ติดกันเหลือช่องเดียว แล้วตัดเฉพาะ U+0020 ที่หัวท้าย */
function tidy(raw: string): string {
  return raw.replace(/ {2,}/g, " ").replace(/^ +| +$/g, "")
}

/** ต่อข้อความ token ยุบช่องว่าง U+0020 ที่ติดกันเหลือช่องเดียว แล้วตัดเฉพาะ U+0020 ที่หัวท้าย (ไม่ใช้ .trim()) */
export function cueText(tokens: readonly SubToken[]): string {
  let text = ""
  for (const tok of tokens) text += tok.t
  return tidy(text)
}

const PUNCT_ONLY = /^[\p{P}\p{S}]+$/u

/**
 * ข้อความที่เห็นของ token (ตัด U+0020 หัวท้าย) เป็นเครื่องหมายล้วน: หมวด Unicode P* หรือ S* ทุกตัว
 * เช่น "." "," " ?" "♪" "--" นับ ส่วน "a." "1" ". ." (มีช่องว่างกลาง) ไม่นับ (เหมือน `is_punct_only` ฝั่ง Python)
 */
export function isPunctOnly(tok: SubToken): boolean {
  return PUNCT_ONLY.test(tidy(tok.t))
}

/** เครื่องหมายเปิดที่เกาะหน้าคำถัดไปเสมอ (fix round 1): ( [ { « “ ‘ ¿ ¡ และ ( [ { แบบเต็มความกว้าง */
const OPENERS = new Set("([{\u00ab\u201c\u2018\u00bf\u00a1\uff08\uff3b\uff5b")
/** อัญประกาศตรงที่เป็นได้ทั้งเปิดและปิด (" ' และแบบเต็มความกว้าง) ตัดสินจากช่องว่างรอบตัว (tokenKinds) */
const STRAIGHT_QUOTES = new Set("\"'\uff02\uff07")
const WORD = 0
const BACK = 1
const FORWARD = 2

function only(tok: SubToken, chars: Set<string>): boolean {
  const text = tidy(tok.t)
  if (text === "") return false
  for (const ch of text) if (!chars.has(ch)) return false
  return true
}

/**
 * โหมดนับคำ: คำ (WORD) / เครื่องหมายที่เกาะคำก่อนหน้า (BACK) / เครื่องหมายเปิดที่เกาะคำถัดไป (FORWARD)
 * กฎเดียวกับ `_kinds` ฝั่ง Python ทุกข้อ (ดู docstring ที่นั่น)
 */
function tokenKinds(tokens: readonly SubToken[]): number[] {
  const n = tokens.length
  const kinds = new Array<number>(n).fill(WORD)
  for (let i = n - 1; i >= 0; i--) {
    const tok = tokens[i]
    if (!isPunctOnly(tok)) continue
    kinds[i] = BACK
    if (i + 1 >= n || kinds[i + 1] === BACK || tokens[i + 1].s - tok.e >= GAP_SPLIT_MS) continue
    if (only(tok, OPENERS)) {
      kinds[i] = FORWARD
    } else if (only(tok, STRAIGHT_QUOTES)) {
      const prev = i > 0 ? tokens[i - 1] : null
      const spacedBefore =
        prev === null ||
        tok.s - prev.e >= GAP_SPLIT_MS ||
        tok.t.startsWith(" ") ||
        prev.t.endsWith(" ") ||
        only(prev, OPENERS)
      const gluedAfter = !tok.t.endsWith(" ") && !tokens[i + 1].t.startsWith(" ")
      if (spacedBefore && gluedAfter) kinds[i] = FORWARD
    }
  }
  return kinds
}

/** ใช้กับชื่อคลิปและชื่อ chapter เท่านั้น: ช่องว่างทุกแบบของ JS (\s) ยุบเหลือช่องเดียว แล้วตัดหัวท้าย */
function collapse(text: string): string {
  return text.replace(/\s+/g, " ").trim()
}

// ---------- tokens -> cues ----------

/**
 * ซับระหว่างสร้างเก็บเป็นช่วง token [from, to) ของรายการ (ซับเป็นช่วงต่อเนื่องเสมอ รวมสองซับก็ยังต่อเนื่อง)
 * ใช้ช่วงแทนการตัด array ใหม่ทุกครั้ง เพราะ preview ต้องเร็ว: คลิป 1 ชม. เรียก lineLen หลายแสนครั้ง
 */
type Draft = { from: number; to: number; startMs: number; endMs: number }

type Measure = {
  /** cueText ของ token ช่วง [from, to) */
  text: (from: number, to: number) => string
  /** lineLen = displayLen(cueText) ของ token ช่วง [from, to) */
  len: (from: number, to: number) => number
}

/**
 * เตรียมข้อความต่อกันทั้งหมดกับผลรวมสะสมของ displayLen ต่อ token ครั้งเดียว แล้ววัดช่วงไหนก็ได้เร็ว ๆ
 * lineLen = displayLen ของข้อความดิบในช่วง ลบด้วยจำนวนช่องว่างที่ tidy ตัดทิ้ง ตัวที่ถูกตัดเป็น U+0020 ล้วน
 * (1 หน่วย UTF-16 = 1 code point = นับ 1) ผลต่างของ .length จึงเท่ากับจำนวนที่ displayLen ลดลงพอดี
 */
function measure(tokens: readonly SubToken[]): Measure {
  const offsets = [0]
  const lens = [0]
  let full = ""
  for (const tok of tokens) {
    full += tok.t
    offsets.push(full.length)
    lens.push(lens[lens.length - 1] + displayLen(tok.t))
  }
  const raw = (from: number, to: number) => full.slice(offsets[from], offsets[to])
  return {
    text: (from, to) => tidy(raw(from, to)),
    len: (from, to) => {
      const r = raw(from, to)
      return lens[to] - lens[from] - (r.length - tidy(r).length)
    },
  }
}

/**
 * มีจุดแบ่ง 2 บรรทัดในช่วง [from, to) ที่ทั้งสองบรรทัด <= cap ไหม
 * ยาวบรรทัดบนไม่ลดลงเมื่อจุดแบ่งเลื่อนไปทางขวา และบรรทัดล่างไม่เพิ่มขึ้น จึงหาจุดแบ่งซ้ายสุดที่บรรทัดล่าง <= cap
 * ด้วย binary search แล้วดูว่าบรรทัดบนที่จุดนั้นยัง <= cap ไหม (เหมือน `_has_split` ฝั่ง Python)
 */
function hasSplit(m: Measure, from: number, to: number, cap: number): boolean {
  let lo = from + 1
  let hi = to - 1
  if (m.len(hi, to) > cap) return false
  while (lo < hi) {
    const mid = Math.floor((lo + hi) / 2)
    if (m.len(mid, to) <= cap) hi = mid
    else lo = mid + 1
  }
  return m.len(from, lo) <= cap
}

/**
 * ซับที่มี token >= 2 ตัว "พอดี" เมื่อทุกบรรทัดยาวไม่เกิน cap (เจ้าของสั่ง: ห้ามบรรทัดไหนเกิน maxChars)
 * token เดียวไม่ต้องตรวจ: หั่นกลางคำไม่ได้ (FR-SUB-9) และไม่มีคำอื่นมาต่อได้
 */
function fits(m: Measure, from: number, to: number, o: SubOptions, cap: number): boolean {
  if (to - from < 2) return true
  if (m.len(from, to) <= cap) return true
  return o.lines === 2 && hasSplit(m, from, to, cap)
}

function splitLines(m: Measure, from: number, to: number, o: SubOptions): string[] {
  if (o.lines === 2 && to - from >= 2 && m.len(from, to) > o.maxChars) {
    // ซับที่ผ่าน fits มีจุดแบ่งอย่างน้อย 1 จุดเสมอ ยกเว้นคำยาวเกินที่มีเครื่องหมายเกาะท้าย (โหมดนับคำ) = บรรทัดเดียว
    const cap = o.maxChars * MERGE_LIMIT_FACTOR
    let bestK = -1
    let bestDiff = Infinity
    for (let k = from + 1; k < to; k++) {
      const left = m.len(from, k)
      if (left > cap) break // บรรทัดบนยาวขึ้นเรื่อย ๆ เมื่อ k โต ที่เหลือใช้ไม่ได้แน่นอน
      const right = m.len(k, to)
      if (right > cap) continue
      const diff = Math.abs(left - right)
      if (diff < bestDiff) {
        // เท่ากันให้ k ที่น้อยกว่า (ใช้ < ไม่ใช่ <=)
        bestK = k
        bestDiff = diff
      }
    }
    if (bestK > 0) return [m.text(from, bestK), m.text(bestK, to)]
  }
  // token เดียวที่ยาวเกินขีดจำกัดก็อยู่ทั้งก้อน ไม่หั่นกลางคำ (FR-SUB-9)
  return [m.text(from, to)]
}

/**
 * C6 ขั้น 1-4: จับกลุ่ม, เวลาขั้นต่ำ (ยืด/รวม), กันเวลาทับ, แบ่งบรรทัด
 * ไม่ตรวจช่วงค่าของตัวเลือก (ผู้เรียกบีบค่าเอง) ยกเว้นโหมดนับคำที่ไม่มี tokensPerCue = throw
 */
export function buildCues(tokens: readonly SubToken[], o: SubOptions): Cue[] {
  const tokensMode = o.mode === "tokens"
  if (tokensMode && !o.tokensPerCue) throw new Error("tokens mode needs tokensPerCue")
  const perCue = o.tokensPerCue ?? 0
  const m = measure(tokens)
  const draft = (from: number, to: number): Draft => ({ from, to, startMs: tokens[from].s, endMs: tokens[to - 1].e })

  // โหมดนับคำ (owner round 3 + fix round 1): token ที่เป็นเครื่องหมายล้วนไม่นับเป็นคำ
  // เครื่องหมายทั่วไปเกาะซับของคำก่อนหน้า ตัวแรกสุดเกาะซับถัดไป · เครื่องหมายเปิดเกาะหน้าคำถัดไป (tokenKinds)
  // ยกเว้นเงียบ >= 1 วินาที ซึ่งยังขึ้นซับใหม่เหมือนเดิม · wordsBefore[k] = จำนวนคำ (ไม่นับเครื่องหมาย) ใน token [0, k)
  const kinds = tokensMode ? tokenKinds(tokens) : new Array<number>(tokens.length).fill(WORD)
  const punct = kinds.map((kind) => kind !== WORD)
  // คำที่เครื่องหมายเปิดซึ่งต่อกันตั้งแต่ start เกาะอยู่ (token แรกที่ไม่ใช่เครื่องหมายเปิด)
  const chainEnd = (start: number) => {
    let k = start
    while (kinds[k] === FORWARD) k++
    return k
  }
  const wordsBefore = [0]
  for (const p of punct) wordsBefore.push(wordsBefore[wordsBefore.length - 1] + (p ? 0 : 1))
  const words = (from: number, to: number) => wordsBefore[to] - wordsBefore[from]

  // 1. จับกลุ่มแบบ greedy (โหมดนับคำก็ใช้กฎปิดซับครบทุกข้อ) ซับที่กำลังสร้าง = [curFrom, i)
  const drafts: Draft[] = []
  let curFrom = 0
  for (let i = 1; i < tokens.length; i++) {
    const tok = tokens[i]
    const gap = tok.s - tokens[i - 1].e >= GAP_SPLIT_MS
    // เครื่องหมายเปิดตัดสินพร้อมคำที่มันเกาะ (ช่วง i..j): ถ้าคำนั้นต้องขึ้นซับใหม่ เครื่องหมายก็ขึ้นไปด้วย
    const j = kinds[i] === FORWARD ? chainEnd(i) : i
    // ทุก token (รวมเครื่องหมาย) ต้องไม่ทำให้เกินขีดจำกัดตัวอักษร/เวลานานสุด (fix round 2, review #1)
    const capped = !fits(m, curFrom, j + 1, o, o.maxChars) || tokens[j].e - tokens[curFrom].s > o.maxMs
    // กฎจำนวนคำใช้กับคำและเครื่องหมายเปิดเท่านั้น (เหมือนฝั่ง Python)
    const counted = kinds[i] !== BACK && kinds[i - 1] !== FORWARD
    const close = gap || capped || (tokensMode && counted && words(curFrom, i) >= perCue)
    if (close) {
      drafts.push(draft(curFrom, i))
      curFrom = i
    }
  }
  if (tokens.length > 0) drafts.push(draft(curFrom, tokens.length))

  // 2. เวลาขั้นต่ำ: ยืดไปได้ถึงต้นซับถัดไป ถ้ายังสั้นอยู่ลองรวมกับตัวถัดไป แล้วตรวจตัวเดิมซ้ำ
  let i = 0
  while (i < drafts.length) {
    const c = drafts[i]
    const nxt = i + 1 < drafts.length ? drafts[i + 1] : null
    if (c.endMs - c.startMs < o.minMs) {
      const want = c.startMs + o.minMs
      c.endMs = nxt ? Math.min(want, nxt.startMs) : want
      if (c.endMs - c.startMs < o.minMs && nxt) {
        if (
          fits(m, c.from, nxt.to, o, o.maxChars * MERGE_LIMIT_FACTOR) &&
          nxt.endMs - c.startMs <= o.maxMs &&
          (!tokensMode || words(c.from, nxt.to) <= perCue)
        ) {
          drafts.splice(i, 2, { from: c.from, to: nxt.to, startMs: c.startMs, endMs: nxt.endMs })
          continue
        }
      }
    }
    i++
  }

  // 3. กันเวลาทับกัน
  for (let j = 0; j + 1 < drafts.length; j++) {
    drafts[j].endMs = Math.min(drafts[j].endMs, drafts[j + 1].startMs)
  }

  // 4. แบ่งบรรทัด
  return drafts.map((d) => ({ startMs: d.startMs, endMs: d.endMs, lines: splitLines(m, d.from, d.to, o) }))
}

// ---------- outputs (CRLF, ไม่มี BOM) ----------

const pad = (n: number, width: number) => String(n).padStart(width, "0")

/** HH:MM:SS,mmm ปัดลง ชั่วโมงอย่างน้อย 2 หลัก (เกินได้ เช่น 100:00:00,005) */
function ts(ms: number): string {
  const h = Math.floor(ms / 3_600_000)
  const m = Math.floor((ms % 3_600_000) / 60_000)
  const s = Math.floor((ms % 60_000) / 1000)
  return `${pad(h, 2)}:${pad(m, 2)}:${pad(s, 2)},${pad(ms % 1000, 3)}`
}

export function toSrt(cues: readonly Cue[]): string {
  return cues
    .map((c, idx) => `${idx + 1}${CRLF}${ts(c.startMs)} --> ${ts(c.endMs)}${CRLF}` + c.lines.join(CRLF) + CRLF)
    .join(CRLF)
}

function paragraphs(tokens: readonly SubToken[]): string[] {
  const paras: SubToken[][] = []
  for (const tok of tokens) {
    const last = paras[paras.length - 1]
    if (last && tok.s - last[last.length - 1].e < PARAGRAPH_GAP_MS) last.push(tok)
    else paras.push([tok])
  }
  return paras.map(cueText)
}

export function toTxt(tokens: readonly SubToken[]): string {
  if (tokens.length === 0) return ""
  return paragraphs(tokens).join(CRLF + CRLF) + CRLF
}

/** [mm:ss] หรือ [h:mm:ss] เมื่อถึงชั่วโมงแรก วินาทีปัดลง ชั่วโมงไม่เติมศูนย์ */
function mdTime(ms: number): string {
  const total = Math.floor(ms / 1000)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  return ms >= 3_600_000 ? `${h}:${pad(m, 2)}:${pad(s, 2)}` : `${pad(m, 2)}:${pad(s, 2)}`
}

export type MdMeta = { title: string; videoId: string; chapters: { startMs: number; title: string }[] }

/** หัวเรื่อง + ลิงก์คลิป แล้วแบ่งหัวข้อตาม chapter (หรือทุก 2 นาทีถ้าไม่มี chapter) หัวข้อว่างถูกข้าม */
export function toMd(tokens: readonly SubToken[], meta: MdMeta): string {
  const out = ["# " + collapse(meta.title), "", `https://www.youtube.com/watch?v=${meta.videoId}`]
  // Array.prototype.sort เป็น stable: start เท่ากันคงลำดับเดิม
  const ordered = [...meta.chapters].sort((a, b) => a.startMs - b.startMs)

  const sections = new Map<number, { startMs: number; suffix: string; tokens: SubToken[] }>()
  for (const tok of tokens) {
    let key: number
    let startMs: number
    let suffix: string
    if (ordered.length > 0) {
      // chapter สุดท้ายที่เริ่มก่อนหรือตรงกับคำนี้ คำก่อน chapter แรกไปอยู่ chapter แรก
      key = 0
      ordered.forEach((ch, j) => {
        if (ch.startMs <= tok.s) key = j
      })
      startMs = ordered[key].startMs
      suffix = " " + collapse(ordered[key].title)
    } else {
      key = Math.floor(tok.s / MD_SECTION_MS)
      startMs = key * MD_SECTION_MS
      suffix = ""
    }
    let section = sections.get(key)
    if (!section) {
      section = { startMs, suffix, tokens: [] }
      sections.set(key, section)
    }
    section.tokens.push(tok)
  }

  const sorted = [...sections.entries()].sort(([a], [b]) => a - b)
  for (const [, section] of sorted) {
    out.push("", `## [${mdTime(section.startMs)}]${section.suffix}`, "")
    // ย่อหน้านับใหม่ในแต่ละหัวข้อ ขึ้นหัวข้อใหม่ = ขึ้นย่อหน้าใหม่เสมอ
    paragraphs(section.tokens).forEach((para, n) => {
      if (n > 0) out.push("")
      out.push(para)
    })
  }
  return out.join(CRLF) + CRLF
}

/** สรุปสำหรับตัวอย่างซับ: จำนวน, ความยาวเฉลี่ย (ทศนิยม 1 ตำแหน่ง), จำนวนซับที่แสดงไม่ถึง 1 วินาที */
export function cueStats(cues: readonly Cue[]): { count: number; avgChars: number; underOneSecond: number } {
  if (cues.length === 0) return { count: 0, avgChars: 0, underOneSecond: 0 }
  let chars = 0
  let underOneSecond = 0
  for (const c of cues) {
    chars += displayLen(c.lines.join(" "))
    if (c.endMs - c.startMs < 1000) underOneSecond++
  }
  return { count: cues.length, avgChars: Math.round((chars / cues.length) * 10) / 10, underOneSecond }
}
