import type { LucideIcon } from "lucide-react"

/**
 * ตัวเลขหนึ่งตัวแบบย่อพร้อมไอคอน เช่น 👁 "1.2 แสน ครั้ง"
 * ตาเห็นตัวเลขย่อ โปรแกรมอ่านหน้าจอได้ตัวเลขเต็ม (aria-label) และชี้เมาส์ก็เห็นตัวเลขเต็ม (title)
 * role="img": ไอคอนกับข้อความข้างในรวมเป็นภาพเดียวที่มีชื่อเดียว (aria-label บน span เปล่าใช้ไม่ได้)
 */
export function Stat({ icon: Icon, text, label }: { icon: LucideIcon; text: string; label: string }) {
  return (
    <span role="img" aria-label={label} title={label} className="inline-flex items-center gap-1">
      <Icon aria-hidden className="size-3.5 shrink-0" />
      <span className="tabular-nums">{text}</span>
    </span>
  )
}
