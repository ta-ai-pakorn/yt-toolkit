import { th } from "@/i18n/th"
import { ApiError } from "@/lib/api"
import { audioLanguageName } from "@/lib/languages"
import type { Settings } from "@/lib/types"

/** ค่าที่หน้า "ทั่วไป" แก้ได้ (ทั้งหกช่อง) */
export type GeneralKey = "outputDir" | "concurrency" | "audioLanguage" | "videoDefault" | "audioDefault" | "autoSharpFrames"
export type GeneralPatch = Partial<Pick<Settings, GeneralKey>>

export const CONCURRENCY_CHOICES = [1, 2, 3] as const
export const AUDIO_FORMATS = ["m4a", "mp3", "wav"] as const
export const VIDEO_DEFAULTS = ["compat-1080", "compat-720", "max"] as const

/** ที่อยู่โฟลเดอร์ที่พิมพ์ → ค่าที่จะส่ง: ตัดช่องว่างหัวท้าย · ว่างหรือเท่าค่าที่บันทึกอยู่ = null (ไม่ต้องบันทึก) */
export function outputDirPatch(draft: string, saved: string): GeneralPatch | null {
  const value = draft.trim()
  if (value === "" || value === saved) return null
  return { outputDir: value }
}

/** ช่องอื่นที่เลือกจากรายการ: ค่าเท่าที่บันทึกอยู่ = null (ไม่ส่ง PATCH) ตัวที่เปลี่ยนจริงส่งเฉพาะช่องนั้น */
export function choicePatch<K extends Exclude<GeneralKey, "outputDir">>(
  key: K,
  value: Settings[K],
  saved: Settings
): GeneralPatch | null {
  return saved[key] === value ? null : { [key]: value }
}

/** ค่าที่แสดงบนจอ: ระหว่างรอเซิร์ฟเวอร์ตอบ แสดงค่าที่เพิ่งเลือกไว้ก่อน (ไม่ให้ปุ่มกระโดดกลับ) */
export function displayed(saved: Settings, pending: GeneralPatch | null): Settings {
  return pending ? { ...saved, ...pending } : saved
}

export type LanguageOption = { value: string; label: string }

/** ภาษาเสียงให้เลือก: "ต้นฉบับ" ก่อน แล้วภาษาในรายการ · ค่าที่บันทึกไว้แต่ไม่อยู่ในรายการ (เช่น en-US) ยังแสดงชื่อได้ */
export function languageOptions(current: string): LanguageOption[] {
  const options: LanguageOption[] = Object.entries<string>(th.general.languages).map(([value, label]) => ({ value, label }))
  if (!options.some((o) => o.value === current)) options.push({ value: current, label: audioLanguageName(current) })
  return options
}

/** ข้อความผิดพลาดจากเซิร์ฟเวอร์ (ภาษาไทยอยู่แล้ว) · ไม่ใช่ ApiError = ข้อความกลาง */
export function serverMessage(error: unknown): string {
  return error instanceof ApiError && error.message ? error.message : th.general.saveFailed
}
