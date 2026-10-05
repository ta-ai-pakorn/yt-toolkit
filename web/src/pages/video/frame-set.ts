import type { FrameSource } from "@/lib/types"

/**
 * ชุดภาพที่ส่วนภาพเฟรมแสดง (spec 2): ไม่มีชุดภาพคม = ภาพเร็ว · ไม่มีภาพเร็ว (ไม่มี storyboard) = ภาพคม
 * มีทั้งสองชุด = ที่ผู้ใช้กดเลือกไว้ในรอบที่เปิดหน้านี้ ยังไม่เคยเลือก = ภาพคม (ชุดใหม่ที่เพิ่งเสร็จจึงขึ้นเอง)
 */
export function frameSetShown(o: { hasFast: boolean; hasSharp: boolean; chosen: FrameSource | null }): FrameSource {
  if (!o.hasSharp) return "fast"
  if (!o.hasFast) return "sharp"
  return o.chosen ?? "sharp"
}
