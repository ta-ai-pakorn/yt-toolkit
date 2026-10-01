import { Flame } from "lucide-react"

import { th } from "@/i18n/th"

/**
 * ป้ายเล็ก "ดูซ้ำบ่อย" ของภาพเฟรม/บรรทัดทรานสคริปต์ในช่วงที่คนดูซ้ำมากที่สุด
 * ตาเห็นแค่ไอคอน (ความหมายอยู่ในส่วน "ช่วงที่คนดูซ้ำบ่อย" ของแท็บข้อมูลคลิป ซึ่งใช้ไอคอนเดียวกัน)
 * เอาเมาส์ชี้ได้คำอธิบาย (title) ทั้งที่ภาพเฟรมและบรรทัดทรานสคริปต์ (review M-3)
 * โปรแกรมอ่านหน้าจออ่านคำว่า "ดูซ้ำบ่อย" ต่อท้ายชื่อปุ่ม
 */
export function ReplayedMark({ className }: { className?: string }) {
  return (
    <span data-replayed="" title={th.frames.replayedHint} className={className}>
      <Flame aria-hidden className="size-3.5 text-accent-text" />
      <span className="sr-only"> {th.frames.replayed}</span>
    </span>
  )
}
