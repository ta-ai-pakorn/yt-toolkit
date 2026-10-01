import { fill, th } from "@/i18n/th"
import type { VideoInfo } from "@/lib/types"

/** ยุบช่องว่างทุกชนิด (รวมขึ้นบรรทัดใหม่) เป็นช่องเดียวแล้วตัดหัวท้าย: เหมือน _one_line ของ core/files.py (C10) */
const oneLine = (text: string) => text.replace(/\s+/g, " ").trim()

/** บรรทัดเครดิต "ที่มา: <ชื่อคลิป> — <ช่อง> (YouTube) https://youtu.be/<id>" บรรทัดเดียว ตรงกับ credit_line ของ core/files.py */
export const creditLine = (video: Pick<VideoInfo, "title" | "channel" | "videoId">) =>
  fill(th.video.info.creditLine, { title: oneLine(video.title), channel: oneLine(video.channel), id: video.videoId })

/** แท็กที่ใช้ได้ (ตัดช่องว่างหัวท้าย ข้ามแท็กว่าง) */
export const cleanTags = (tags: readonly string[] | undefined) =>
  (tags ?? []).map((tag) => tag.trim()).filter((tag) => tag !== "")

/**
 * ส่วนไหนของแท็บข้อมูลคลิปมีข้อมูล (ส่วนที่ไม่มีข้อมูลไม่แสดง)
 * credit = มีชื่อคลิปก็มีเครดิตเสมอ (M4: ส่วน "เครดิต" อยู่บนสุดของแท็บ) · ส่วนอื่นว่างหมด = ขึ้น "คลิปนี้ไม่มีข้อมูลเพิ่มเติม" ใต้ส่วนเครดิต
 */
export function infoSections(video: VideoInfo) {
  const comments = video.stats?.comments
  return {
    credit: video.title.trim() !== "",
    description: (video.description ?? "").trim() !== "",
    chapters: video.chapters.length > 0,
    replayed: (video.mostReplayed?.length ?? 0) > 0,
    // คอมเมนต์ปักหมุดรู้ผลหลังขอข้อมูล: แสดงเมื่อคลิปมีคอมเมนต์ (หรือไม่รู้จำนวน) · ปิดคอมเมนต์หรือ 0 คอมเมนต์ = ไม่มีส่วนนี้
    pinned: comments === undefined || comments > 0,
    tags: cleanTags(video.tags).length > 0,
  }
}
