import { fill, th } from "@/i18n/th"
import { languageName } from "@/lib/languages"
import type { SubtitleTrack, SubtitleTracks } from "@/lib/types"

/** ชื่อแทร็กซับที่ผู้ใช้เห็น: ชื่อภาษาไทย + บอกกลุ่ม เช่น "ไทย (อัตโนมัติ)", "ฝรั่งเศส (แปลอัตโนมัติ)" */
export function trackLabel(track: SubtitleTrack): string {
  return fill(th.subs.names[track.group], { lang: languageName(track.lang) })
}

/**
 * แทร็กที่ใช้อยู่: แทร็กใน URL ก่อน ไม่มีค่อยใช้แทร็กเริ่มต้นของคลิป
 * ไม่มีทั้งคู่ หรือรหัสไม่อยู่ในรายการแทร็กของคลิปนี้ = null (ผู้ใช้ต้องเลือกเองที่แท็บซับ)
 */
export function trackInEffect(data: SubtitleTracks, urlTrackId: string | null): SubtitleTrack | null {
  const id = urlTrackId ?? data.defaultTrackId
  if (!id) return null
  return data.tracks.find((track) => track.id === id) ?? null
}
