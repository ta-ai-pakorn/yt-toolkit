import { Camera } from "lucide-react"
import type { ComponentProps } from "react"

import { Button } from "@/components/ui/button"
import { ContextMenuItem } from "@/components/ui/context-menu"
import { Spinner } from "@/components/ui/spinner"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { th } from "@/i18n/th"

import { markTimeMs } from "../player/player-store"
import { blockTooltip } from "./capture-model"
import { useCapture } from "./use-capture"

type Props = { videoId: string; variant?: "row" | "dock" }

/**
 * "ถ่ายภาพคมตรงนี้" (M5 รอบ B2 spec 2.1-2.2): ใช้เวลาที่ตัวเล่นอยู่ (markTimeMs กำลังโหลด = เวลาที่ขอไว้) ปัดทีละ 100 ms
 * row = ปุ่มมีข้อความในแถวใต้ตัวเล่น · dock = ปุ่มไอคอนบนตัวเล่นลอย (ชื่อปุ่มเดียวกัน + tooltip)
 * กำลังถ่าย (ทั้งแอพ) = วงหมุน + "กำลังถ่าย…" · คลิปสด / คิวพัก = กดไม่ได้แต่โฟกัสได้ พร้อม tooltip บอกเหตุผล
 */
export function CaptureButton({ videoId, variant = "row" }: Props) {
  const { busy, block, capture } = useCapture(videoId)
  const reason = blockTooltip(block)
  const label = busy ? th.capture.busy : th.capture.button
  const dock = variant === "dock"
  const props: ComponentProps<typeof Button> = {
    variant: dock ? "ghost" : "outline",
    size: dock ? "icon-xs" : "sm",
    "aria-label": dock ? label : undefined,
    className: dock ? "max-sm:size-11" : "max-sm:h-11",
    disabled: busy || reason !== null,
    focusableWhenDisabled: true,
    onClick: () => capture(markTimeMs()),
  }
  const content = (
    <>
      {busy ? <Spinner aria-hidden /> : <Camera aria-hidden />}
      {dock ? null : label}
    </>
  )
  const tip = reason ?? (dock ? label : null)
  if (tip === null) {
    return (
      <Button {...props} data-slot="capture-button">
        {content}
      </Button>
    )
  }
  return (
    <Tooltip>
      <TooltipTrigger render={<Button {...props} data-slot="capture-button" />}>{content}</TooltipTrigger>
      <TooltipContent>{tip}</TooltipContent>
    </Tooltip>
  )
}

/** รายการ "ถ่ายภาพคมตรงนี้" ในเมนูคลิกขวาของภาพเฟรม: ใช้เวลาของภาพ · กดไม่ได้ระหว่างถ่ายหรือเมื่อถ่ายไม่ได้ (เมนูไม่มี tooltip) */
export function CaptureMenuItem({ videoId, tMs }: { videoId: string; tMs: number }) {
  const { busy, block, capture } = useCapture(videoId)
  return (
    <ContextMenuItem disabled={busy || block !== null} onClick={() => capture(tMs)}>
      <Camera aria-hidden />
      {th.capture.button}
    </ContextMenuItem>
  )
}
