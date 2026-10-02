import { fill, th } from "@/i18n/th"
import { paramsFromSettings } from "@/lib/download-options"
import type { NewJob, PlaylistEntry, ResolveItem, Settings, SubOptions } from "@/lib/types"

import type { BatchSource } from "./path"

export { batchPath, parseBatchSource, type BatchSource } from "./path"

/** เพลย์ลิสต์ที่ backend ส่งมาไม่เกิน 200 คลิป: ตารางก็ไม่เกินนี้ */
export const MAX_BATCH_ROWS = 200

/** เลือกเกินกี่คลิปแล้วต้องถามยืนยันก่อนส่งเข้าคิว */
export const CONFIRM_ABOVE = 20

/** ข้อมูลคลิปที่รู้จาก cache ของ react-query */
export type ClipInfo = { title?: string; durationS?: number }

/**
 * แถวของตารางเลือกคลิป · แถวลิงก์ที่อ่านไม่ออก (`invalid`) ไม่มี videoId (ว่าง) และเลือกไม่ได้
 * ไม่รู้ชื่อ = ไม่มี title (หน้าเว็บแสดงรหัสคลิปแทน)
 */
export type BatchRow = {
  videoId: string
  title?: string
  durationS?: number
  invalid?: { input: string }
}

/**
 * รายการผลของ W1 ที่ลิงก์นี้อ้างถึงไม่อยู่แล้ว (ล้างรายการ วิเคราะห์ใหม่ หรือเปิดแท็บใหม่ที่ไม่มีรายการ):
 * `src` ต้องตรงกับ listId ที่เก็บไว้ และต้องยังมีรายการผลอยู่
 */
export function isExpired(source: BatchSource | null, listId: string, results: ResolveItem[] | null): boolean {
  return source === null || results === null || listId === "" || source.src !== listId
}

const isClip = (item: ResolveItem) => item.kind === "video" || item.kind === "ambiguous"
// แถวเพลย์ลิสต์ที่ไม่มีรหัสเพลย์ลิสต์ W1 แสดงเป็นแถวผิดพลาด ที่นี่ก็เช่นกัน
const isInvalid = (item: ResolveItem) => item.kind === "invalid" || (item.kind === "playlist" && !item.playlistId)

/**
 * แถวคลิปจากรายการผลของ W1 (ไม่ได้เลือกเพลย์ลิสต์): คลิปกับลิงก์กำกวม ไม่ซ้ำรหัสตามลำดับที่เจอครั้งแรก
 * (กฎเดียวกับลำดับก่อนหน้า/ถัดไปของ W2) · ลิงก์อ่านไม่ออกเป็นแถวแดงที่เลือกไม่ได้ ตามตำแหน่งเดิม
 * · แถวเพลย์ลิสต์ไม่เข้าตาราง (`hasPlaylists` = ให้หน้าเว็บบอกว่าเลือกคลิปของมันได้จากปุ่มที่หน้าแรก)
 * `infoOf` = ชื่อและความยาวจาก cache ของ react-query (ไม่รู้ = undefined) ไม่มีการขอข้อมูลใหม่ · เกิน 200 คลิปตัดทิ้ง
 */
export function clipRows(
  items: readonly ResolveItem[],
  infoOf: (videoId: string) => ClipInfo | undefined
): { rows: BatchRow[]; hasPlaylists: boolean } {
  const seen = new Set<string>()
  const rows: BatchRow[] = []
  let clips = 0
  let hasPlaylists = false
  for (const item of items) {
    if (isInvalid(item)) {
      rows.push({ videoId: "", invalid: { input: item.input } })
    } else if (item.kind === "playlist") {
      hasPlaylists = true
    } else if (isClip(item) && item.videoId && !seen.has(item.videoId) && clips < MAX_BATCH_ROWS) {
      // ไม่เกิน 200 คลิป (FR-IN-3): งานต่อคลิปไม่เกิน 6 งาน (หลัก + ไฟล์เพิ่มเติม 5 อย่าง) จึงไม่เกินขีด 1200 งานต่อคำขอ
      seen.add(item.videoId)
      clips += 1
      const row: BatchRow = { videoId: item.videoId }
      const info = infoOf(item.videoId)
      if (info?.title) row.title = info.title
      if (info?.durationS !== undefined) row.durationS = info.durationS
      rows.push(row)
    }
  }
  return { rows, hasPlaylists }
}

/** แถวคลิปจากเพลย์ลิสต์/มิกซ์ (ข้อมูลเดียวกับที่ W1 โหลดไว้): ไม่ซ้ำรหัส ไม่เกิน 200 คลิป · ชื่อว่าง = ไม่รู้ชื่อ */
export function playlistRows(entries: readonly PlaylistEntry[]): BatchRow[] {
  const seen = new Set<string>()
  const rows: BatchRow[] = []
  for (const entry of entries) {
    if (seen.has(entry.videoId)) continue
    seen.add(entry.videoId)
    const row: BatchRow = { videoId: entry.videoId }
    if (entry.title) row.title = entry.title
    if (entry.durationS !== undefined) row.durationS = entry.durationS
    rows.push(row)
    if (rows.length === MAX_BATCH_ROWS) break
  }
  return rows
}

/** แถวที่เลือกได้ (ไม่รวมแถวลิงก์อ่านไม่ออก) */
export const selectableRows = (rows: readonly BatchRow[]): BatchRow[] => rows.filter((row) => !row.invalid)

/** คลิปที่เลือกอยู่ตามลำดับในตาราง: ค่าเริ่มต้นเลือกทั้งหมด จึงเก็บเฉพาะรหัสที่ผู้ใช้เอาออก */
export function selectedRows(rows: readonly BatchRow[], deselected: ReadonlySet<string>): BatchRow[] {
  return selectableRows(rows).filter((row) => !deselected.has(row.videoId))
}

/** สถานะของช่อง "เลือกทั้งหมด": ครบ = all · บางส่วน = some (ติ๊กครึ่ง) · ไม่มี = none */
export function headerState(selectable: number, selected: number): "all" | "some" | "none" {
  if (selected <= 0) return "none"
  return selected >= selectable ? "all" : "some"
}

export type WhatChoice = "video" | "audio" | "none"

/** ไฟล์เพิ่มเติมของแต่ละคลิป (ติ๊กได้หลายอย่าง ค่าเริ่มต้นไม่ติ๊กเลย) */
export type ExtraChoice = "srt" | "txt" | "note" | "contactSheet" | "framesZip"

/** ลำดับของช่องติ๊กบนหน้า และลำดับงานของแต่ละคลิป (ต่อจากงานวิดีโอ/เสียง) */
export const EXTRAS: readonly ExtraChoice[] = ["srt", "txt", "note", "contactSheet", "framesZip"]

export type BatchChoice = { what: WhatChoice; extras: ReadonlySet<ExtraChoice> }

/** ชื่อโฟลเดอร์กลุ่มยาวได้ไม่เกินกี่ตัวอักษร (หลังตัดช่องว่างหัวท้าย) ตรงกับ backend */
export const FOLDER_MAX = 80

/** นับตัวอักษรแบบเดียวกับ backend (Python นับ code point ไม่ใช่ UTF-16) */
const charCount = (text: string) => Array.from(text).length

/** ชื่อโฟลเดอร์ใช้ได้ = ตัดช่องว่างหัวท้ายแล้วยาว 1..80 ตัวอักษร */
export function folderValid(folder: string): boolean {
  const length = charCount(folder.trim())
  return length > 0 && length <= FOLDER_MAX
}

const pad = (n: number) => String(n).padStart(2, "0")

/** เวลาท้ายชื่อโฟลเดอร์เริ่มต้น: YYYY-MM-DD HH.mm ตามเวลาเครื่อง (ใช้จุดแทน : เพราะ Windows ห้ามใช้ : ในชื่อโฟลเดอร์) */
export function folderStamp(now: Date): string {
  const date = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
  return `${date} ${pad(now.getHours())}.${pad(now.getMinutes())}`
}

/**
 * ชื่อโฟลเดอร์เริ่มต้นของหน้า W3: มาจากเพลย์ลิสต์ = ชื่อเพลย์ลิสต์ (ยาวเกิน 80 ตัวอักษรตัดท้าย)
 * วางหลายลิงก์ หรือเพลย์ลิสต์ไม่มีชื่อ = "หลายคลิป YYYY-MM-DD HH.mm" (`openedAt` = เวลาที่เปิดหน้า)
 */
export function defaultFolder(playlistTitle: string | undefined, openedAt: Date): string {
  const title = playlistTitle?.trim() ?? ""
  if (title !== "") return Array.from(title).slice(0, FOLDER_MAX).join("").trim()
  return fill(th.batch.folderDefault, { date: folderStamp(openedAt) })
}

/** ส่งเข้าคิวได้ = เลือกอย่างน้อย 1 คลิป · เลือกวิดีโอ/เสียง หรือติ๊กไฟล์เพิ่มเติมอย่างน้อยหนึ่งอย่าง · และชื่อโฟลเดอร์ใช้ได้ */
export function canSubmit(count: number, choice: BatchChoice, folder: string): boolean {
  return count > 0 && (choice.what !== "none" || choice.extras.size > 0) && folderValid(folder)
}

/** ค่าของงานไฟล์เพิ่มเติมแต่ละอย่าง (ซับไม่ระบุแทร็ก = backend ใช้แทร็กเริ่มต้นของคลิป · ภาพใช้ค่าเริ่มต้น) */
function extraJob(extra: ExtraChoice, subOptions: SubOptions, folder: string): Pick<NewJob, "kind" | "params"> {
  switch (extra) {
    case "srt":
    case "txt":
      return { kind: "subtitle", params: { format: extra, options: subOptions, folder } }
    case "note":
      return { kind: "note", params: { folder } }
    case "contactSheet":
      return { kind: "contact_sheet", params: { source: "fast", columns: 5, folder } }
    case "framesZip":
      return { kind: "frames_zip", params: { source: "fast", folder } }
  }
}

/**
 * งานที่จะส่งเข้าคิว ทีละคลิปตามลำดับในตาราง: งานวิดีโอหรือเสียง (ค่าจากการตั้งค่า) แล้วไฟล์เพิ่มเติมตามลำดับ
 * .srt → .txt → โน้ต → ภาพรวมเฟรม → ภาพเฟรมทั้งหมด (ไม่ขึ้นกับลำดับที่ติ๊ก) · ซับใช้ความยาวซับปัจจุบันของแท็บซับ
 * ทุกงานมี `folder` (ตัดช่องว่างหัวท้ายแล้ว) = ไฟล์ของทุกคลิปอยู่ในโฟลเดอร์กลุ่มเดียวกัน · มีชื่อคลิปก็ส่งชื่อไปด้วย
 */
export function buildBatchJobs(
  clips: readonly BatchRow[],
  choice: BatchChoice,
  folder: string,
  settings: Settings,
  subOptions: SubOptions
): NewJob[] {
  const group = folder.trim()
  const extras = EXTRAS.filter((extra) => choice.extras.has(extra))
  const jobs: NewJob[] = []
  for (const clip of clips) {
    const base = clip.title ? { videoId: clip.videoId, title: clip.title } : { videoId: clip.videoId }
    if (choice.what !== "none") {
      jobs.push({ ...base, kind: choice.what, params: { ...paramsFromSettings(choice.what, settings), folder: group } })
    }
    for (const extra of extras) jobs.push({ ...base, ...extraJob(extra, subOptions, group) })
  }
  return jobs
}
