import { languageName } from "@/lib/languages"
import type { AudioFormat, SubtitleTrack } from "@/lib/types"

import { trackLabel } from "../track-label"

/** กลุ่มในรายการเลือกแทร็ก (ซับแปลอัตโนมัติอยู่ในกล่องค้นหาแยก ไม่อยู่ในรายการนี้) */
export type TrackGroup = { group: "owner" | "original"; tracks: SubtitleTrack[] }

const LISTED_GROUPS = ["owner", "original"] as const

/** รหัสภาษาหลัก ตัวเล็ก: "en-US" → "en" */
const baseLang = (lang: string) => lang.split("-")[0].toLowerCase()

const byThai = (a: string, b: string) => a.localeCompare(b, "th")

/**
 * รายการเลือกแทร็ก: กลุ่มซับจากเจ้าของคลิป แล้วกลุ่มซับอัตโนมัติภาษาต้นฉบับ (กลุ่มที่ว่างไม่ถูกส่งออก)
 * ในกลุ่มเรียงตามชื่อที่ผู้ใช้เห็น (ภาษาไทย) โดยแทร็กที่เป็นภาษาต้นฉบับของคลิปขึ้นก่อน
 */
export function buildTrackGroups(tracks: readonly SubtitleTrack[], originalLang: string | null): TrackGroup[] {
  const original = originalLang?.toLowerCase() ?? null
  const rank = (track: SubtitleTrack) => (original !== null && baseLang(track.lang) === original ? 0 : 1)
  const groups: TrackGroup[] = []
  for (const group of LISTED_GROUPS) {
    const members = tracks
      .filter((track) => track.group === group)
      .map((track) => ({ track, rank: rank(track), label: trackLabel(track) }))
      .sort((a, b) => a.rank - b.rank || byThai(a.label, b.label) || a.track.id.localeCompare(b.track.id))
      .map(({ track }) => track)
    if (members.length > 0) groups.push({ group, tracks: members })
  }
  return groups
}

/**
 * ซับแปลอัตโนมัติที่ตรงคำค้น: คำไทยบางส่วนของชื่อภาษา หรือรหัสภาษา (ไม่สนตัวพิมพ์เล็ก/ใหญ่)
 * คำค้นว่าง = ทั้งหมด · ผลเรียงตามชื่อภาษาไทยเสมอ
 */
export function filterTranslated(tracks: readonly SubtitleTrack[], query: string): SubtitleTrack[] {
  const q = query.trim().toLowerCase()
  return tracks
    .filter((track) => track.group === "translated")
    .map((track) => ({ track, name: languageName(track.lang) }))
    .filter(({ track, name }) => q === "" || name.toLowerCase().includes(q) || track.lang.toLowerCase().includes(q))
    .sort((a, b) => byThai(a.name, b.name) || a.track.lang.localeCompare(b.track.lang))
    .map(({ track }) => track)
}

/**
 * ภาษาต้นฉบับของคลิป (รหัสหลัก) สำหรับเรียงรายการแทร็ก: ภาษาของเสียงต้นฉบับก่อน
 * ไม่มีค่อยใช้แทร็กอัตโนมัติ -orig ตัวแรก ไม่มีทั้งคู่ = null
 */
export function originalLanguage(
  tracks: readonly SubtitleTrack[],
  audio: readonly AudioFormat[] | undefined,
): string | null {
  const spoken = audio?.find((format) => format.isOriginal && format.language)?.language
  if (spoken) return baseLang(spoken)
  const orig = tracks.find((track) => track.group === "original" && track.id.endsWith("-orig"))
  return orig ? baseLang(orig.lang) : null
}

const pad = (n: number, width: number) => String(n).padStart(width, "0")

/** เวลาในตัวอย่างซับ แบบเดียวกับในไฟล์ .srt: HH:MM:SS,mmm (ชั่วโมงอย่างน้อย 2 หลัก) */
export function previewTime(ms: number): string {
  const total = Math.max(0, Math.floor(ms))
  const h = Math.floor(total / 3_600_000)
  const m = Math.floor((total % 3_600_000) / 60_000)
  const s = Math.floor((total % 60_000) / 1000)
  return `${pad(h, 2)}:${pad(m, 2)}:${pad(s, 2)},${pad(total % 1000, 3)}`
}
