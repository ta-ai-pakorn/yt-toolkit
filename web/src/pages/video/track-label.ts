import { fill, th } from "@/i18n/th"
import { languageName } from "@/lib/languages"
import type { SubtitleTrack, SubtitleTracks } from "@/lib/types"

/** ชื่อแทร็กซับที่ผู้ใช้เห็น: ชื่อภาษาไทย + บอกกลุ่ม เช่น "ไทย (อัตโนมัติ)", "ฝรั่งเศส (แปลอัตโนมัติ)" */
export function trackLabel(track: SubtitleTrack): string {
  return fill(th.subs.names[track.group], { lang: languageName(track.lang) })
}

/**
 * แทร็กที่ใช้อยู่: แทร็กใน URL ก่อน ไม่มี หรือรหัสใน URL ไม่อยู่ในรายการแทร็กของคลิปนี้ (ลิงก์เก่า พิมพ์ผิด)
 * ใช้แทร็กเริ่มต้นของคลิป · ไม่มีแทร็กเริ่มต้นด้วย = null (ผู้ใช้ต้องเลือกเองที่แท็บซับ)
 */
export function trackInEffect(data: SubtitleTracks, urlTrackId: string | null): SubtitleTrack | null {
  const find = (id: string | null | undefined) => (id ? data.tracks.find((track) => track.id === id) : undefined)
  return find(urlTrackId) ?? find(data.defaultTrackId) ?? null
}
