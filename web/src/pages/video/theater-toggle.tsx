import { Expand, Shrink } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { th } from "@/i18n/th"

/**
 * ปุ่ม "ขยายตัวเล่น (T)" / "ย่อตัวเล่น (T)" ในแถวใต้ตัวเล่น (M5 รอบ B2 spec 1.1) aria-pressed = อยู่ในโหมดโรงภาพยนตร์
 * tooltip "โหมดโรงภาพยนตร์" · มีเฉพาะหลังเริ่มเล่นและจอไม่แคบ (หัวคลิปตัดสิน)
 */
export function TheaterToggle({ on, onToggle }: { on: boolean; onToggle: () => void }) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            variant="outline"
            size="sm"
            aria-pressed={on}
            aria-keyshortcuts="T"
            data-slot="theater-toggle"
            onClick={onToggle}
          />
        }
      >
        {on ? <Shrink aria-hidden /> : <Expand aria-hidden />}
        {on ? th.theater.collapse : th.theater.expand}
      </TooltipTrigger>
      <TooltipContent>{th.theater.tooltip}</TooltipContent>
    </Tooltip>
  )
}
