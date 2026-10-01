import { cn } from "cn"
import { Flame } from "lucide-react"

import { th } from "@/i18n/th"

/**
 * ป้ายเล็ก "ดูซ้ำบ่อย" ของภาพเฟรม/บรรทัดทรานสคริปต์ในช่วงที่คนดูซ้ำมากที่สุด
 * - icon (บรรทัดทรานสคริปต์): ตาเห็นแค่ไอคอน (ความหมายอยู่ในส่วน "ช่วงที่คนดูซ้ำบ่อย" ของแท็บข้อมูลคลิป ซึ่งใช้ไอคอนเดียวกัน)
 * - badge (ภาพเฟรม, owner round 5): ป้ายพื้นอำพัน (--primary) ตัวอักษรเข้ม (--primary-foreground) ไอคอน + คำว่า "ดูซ้ำบ่อย"
 *   สีพื้นและตัวอักษรเหมือนกันทั้งสองธีม (contrast ราว 11:1) ไม่ขึ้นกับภาพข้างใต้
 * เอาเมาส์ชี้ได้คำอธิบาย (title) ทั้งสองแบบ (review M-3)
 * โปรแกรมอ่านหน้าจออ่านคำว่า "ดูซ้ำบ่อย" ต่อท้ายชื่อปุ่มครั้งเดียว (คำที่ตาเห็นของ badge ซ่อนจากโปรแกรมอ่านหน้าจอ
 * ชื่อปุ่มจึงยังเป็น "ภาพเฟรมที่ HH:MM:SS ดูซ้ำบ่อย" เหมือนเดิม)
 */
export function ReplayedMark({ className, variant = "icon" }: { className?: string; variant?: "icon" | "badge" }) {
  if (variant === "badge") {
    return (
      <span
        data-replayed=""
        title={th.frames.replayedHint}
        className={cn(
          "inline-flex items-center gap-0.5 rounded-sm bg-primary px-1 py-px text-[11px] leading-4 font-medium text-primary-foreground shadow-sm",
          className,
        )}
      >
        <Flame aria-hidden className="size-3" />
        <span aria-hidden>{th.frames.replayed}</span>
        <span className="sr-only"> {th.frames.replayed}</span>
      </span>
    )
  }
  return (
    <span data-replayed="" title={th.frames.replayedHint} className={className}>
      <Flame aria-hidden className="size-3.5 text-accent-text" />
      <span className="sr-only"> {th.frames.replayed}</span>
    </span>
  )
}
