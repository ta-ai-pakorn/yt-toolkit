/* eslint-disable react-refresh/only-export-components */
import { cn } from "cn"
import { ChevronFirst, ChevronLast } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { fill, th } from "@/i18n/th"
import { formatDuration } from "@/lib/format"

import { advancedActions } from "../advanced/advanced-store"
import { getPlayerState } from "./player-store"

const t = th.advanced

/**
 * ตั้งจุดเริ่ม/จบของช่วงเวลา (ค่าเดียวกับช่องในแท็บวิดีโอ เสียง ซับ D7) แล้วแจ้งด้วย toast
 * แยกไฟล์ตาม chapter เปิดอยู่ = แจ้งเหตุผล ไม่เปลี่ยนค่า · เวลาปัดลงเป็นวินาที
 */
export function markRange(videoId: string, which: "start" | "end", ms: number): void {
  if (advancedActions.mark(videoId, which, ms) === "blocked") {
    toast.error(t.blocked.chapters)
    return
  }
  const time = formatDuration(Math.floor(Math.max(0, ms) / 1000))
  toast.success(fill(which === "start" ? t.startSet : t.endSet, { time }))
}

type Props = { videoId: string; size?: "sm" | "xs"; className?: string }

/** ปุ่ม "ตั้งจุดเริ่ม" / "ตั้งจุดจบ" ใต้ตัวเล่นและบนตัวเล่นลอย: ใช้เวลาที่ตัวเล่นอยู่ตอนนี้ */
export function RangeMarkButtons({ videoId, size = "sm", className }: Props) {
  const mark = (which: "start" | "end") => markRange(videoId, which, getPlayerState().currentMs)
  return (
    <div data-slot="range-marks" className={cn("flex flex-wrap items-center gap-1", className)}>
      <Button variant="outline" size={size} onClick={() => mark("start")}>
        <ChevronFirst aria-hidden />
        {t.setStart}
      </Button>
      <Button variant="outline" size={size} onClick={() => mark("end")}>
        <ChevronLast aria-hidden />
        {t.setEnd}
      </Button>
    </div>
  )
}
