import { paramsFromSettings } from "@/lib/download-options"
import type {
  NewJob,
  PlaylistEntry,
  ResolveItem,
  Settings,
  SubExportFormat,
  SubOptions,
} from "@/lib/types"

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
      // ไม่เกิน 200 คลิป (FR-IN-3): งานวิดีโอ/เสียง + ซับ ต่อคลิปจึงไม่เกินขีด 500 งานต่อคำขอ
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
export type SubChoice = SubExportFormat | "none"
export type BatchChoice = { what: WhatChoice; sub: SubChoice }

/** ส่งเข้าคิวได้ = เลือกอย่างน้อย 1 คลิป และเลือกวิดีโอ เสียง หรือซับอย่างน้อยหนึ่งอย่าง */
export function canSubmit(count: number, choice: BatchChoice): boolean {
  return count > 0 && (choice.what !== "none" || choice.sub !== "none")
}

/**
 * งานที่จะส่งเข้าคิว ทีละคลิปตามลำดับในตาราง: งานวิดีโอหรือเสียงหนึ่งงาน (ค่าจากการตั้งค่า) ตามด้วยงานซับหนึ่งงาน
 * (ตัวเลือกความยาวซับปัจจุบันของแท็บซับ ไม่ระบุแทร็ก = backend ใช้แทร็กเริ่มต้นของคลิป) · มีชื่อก็ส่งชื่อไปด้วย
 */
export function buildBatchJobs(
  clips: readonly BatchRow[],
  choice: BatchChoice,
  settings: Settings,
  subOptions: SubOptions
): NewJob[] {
  const jobs: NewJob[] = []
  for (const clip of clips) {
    const base = clip.title ? { videoId: clip.videoId, title: clip.title } : { videoId: clip.videoId }
    if (choice.what !== "none") {
      jobs.push({ ...base, kind: choice.what, params: paramsFromSettings(choice.what, settings) })
    }
    if (choice.sub !== "none") {
      jobs.push({ ...base, kind: "subtitle", params: { format: choice.sub, options: subOptions } })
    }
  }
  return jobs
}
