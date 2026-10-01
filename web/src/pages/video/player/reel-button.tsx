import { cn } from "cn"
import { Flame, Square } from "lucide-react"

import { Button } from "@/components/ui/button"
import { th } from "@/i18n/th"
import type { ReplaySegment } from "@/lib/types"

import { playerActions } from "./player-store"
import { stopReel, useReelStatus } from "./reel"

const t = th.player

/**
 * ปุ่มรอง "เล่นเฉพาะช่วงที่ดูซ้ำบ่อย" ใต้ตัวเล่น (มีเฉพาะคลิปที่มี mostReplayed)
 * กำลังเล่นช่วงไฮไลต์ = ปุ่มเดิมกลายเป็น "หยุดเล่นช่วงไฮไลต์" (ปุ่มเดียวกัน โฟกัสไม่หลุด) และมีข้อความ "ช่วง i จาก n"
 */
export function ReelButton({ ranges, className }: { ranges: readonly ReplaySegment[] | undefined; className?: string }) {
  const status = useReelStatus()
  if (!ranges || ranges.length === 0) return null
  const running = status !== null
  return (
    <div className={cn("flex flex-wrap items-center gap-x-2 gap-y-1", className)}>
      <Button
        variant="secondary"
        size="sm"
        data-slot="player-reel"
        className="h-auto min-h-7 whitespace-normal max-sm:min-h-11"
        onClick={() => (running ? stopReel() : playerActions.playReel([...ranges]))}
      >
        {running ? <Square aria-hidden /> : <Flame aria-hidden />}
        {running ? t.reelStop : t.reel}
      </Button>
      <span aria-live="polite" className="text-xs text-muted-foreground tabular">
        {status}
      </span>
    </div>
  )
}
