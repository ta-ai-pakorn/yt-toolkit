import type { VideoInfo } from "@/lib/types"

/** แท็กที่ใช้ได้ (ตัดช่องว่างหัวท้าย ข้ามแท็กว่าง) */
export const cleanTags = (tags: readonly string[] | undefined) =>
  (tags ?? []).map((tag) => tag.trim()).filter((tag) => tag !== "")

/** ส่วนไหนของแท็บข้อมูลคลิปมีข้อมูล (ส่วนที่ไม่มีข้อมูลไม่แสดง) */
export function infoSections(video: VideoInfo) {
  const comments = video.stats?.comments
  return {
    description: (video.description ?? "").trim() !== "",
    chapters: video.chapters.length > 0,
    replayed: (video.mostReplayed?.length ?? 0) > 0,
    // คอมเมนต์ปักหมุดรู้ผลหลังขอข้อมูล: แสดงเมื่อคลิปมีคอมเมนต์ (หรือไม่รู้จำนวน) · ปิดคอมเมนต์หรือ 0 คอมเมนต์ = ไม่มีส่วนนี้
    pinned: comments === undefined || comments > 0,
    tags: cleanTags(video.tags).length > 0,
  }
}
