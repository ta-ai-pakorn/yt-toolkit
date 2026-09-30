import { useMemo } from "react"

import { buildCues } from "@/lib/srt-builder"
import type { Cue, SubOptions, SubToken } from "@/lib/types"

/** ซับจาก token ตามตัวเลือก ยังไม่มี token (กำลังโหลด) = ไม่มีซับ */
export function cuesFor(tokens: readonly SubToken[] | undefined, options: SubOptions): Cue[] {
  return tokens ? buildCues(tokens, options) : []
}

/**
 * ซับสำหรับตัวอย่างในแท็บซับและทรานสคริปต์ สร้างใหม่เฉพาะเมื่อ tokens หรือ options เปลี่ยน (เทียบแบบอ้างอิง)
 * options ต้องเป็นก้อนเดิมระหว่าง render (useSubSettings ให้แบบนั้นอยู่แล้ว) ไม่อย่างนั้นจะสร้างใหม่ทุก render
 */
export function useCues(tokens: SubToken[] | undefined, options: SubOptions): Cue[] {
  return useMemo(() => cuesFor(tokens, options), [tokens, options])
}
