import { formatTimecode } from "./format"
import type { Chapter } from "./types"

/**
 * รายการ chapter สำหรับคัดลอก: บรรทัดละ "HH:MM:SS ชื่อตอน" เรียงตามเวลาเริ่ม คั่นด้วย LF (ไม่มีบรรทัดว่างท้าย)
 * วางลงคำอธิบายคลิปยูทูปแล้วกลายเป็น chapter ได้ทันที · ไม่มี chapter = สตริงว่าง
 */
export function formatChapters(chapters: Chapter[]): string {
  return [...chapters]
    .sort((a, b) => a.startS - b.startS)
    .map((chapter) => `${formatTimecode(chapter.startS * 1000)} ${chapter.title}`)
    .join("\n")
}
