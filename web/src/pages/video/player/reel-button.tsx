import { cn } from "cn"
import { Flame, Square } from "lucide-react"
import { useLayoutEffect, useRef } from "react"

import { Button } from "@/components/ui/button"
import { th } from "@/i18n/th"
import type { ReplaySegment } from "@/lib/types"

import { playerActions } from "./player-store"
import { stopReel, useReelStatus } from "./reel"

const t = th.player

/**
 * ปุ่มรอง "เล่นเฉพาะช่วงที่ดูซ้ำบ่อย" ในแถวปุ่มของหัวคลิป (ข้าง "ดูภาพปก") มีเฉพาะคลิปที่มี mostReplayed
 * อยู่ในแถวปุ่มที่มีตั้งแต่ก่อนเล่น หัวคลิปจึงสูงเท่าเดิมไม่ว่าคลิปจะมีช่วงดูซ้ำหรือไม่ (ไม่ต้องจองแถวใต้ตัวเล่น)
 * กดระหว่างเล่นช่วงไฮไลต์ = เริ่มช่วงที่ 1 ใหม่ · สถานะ "ช่วง i จาก n" กับปุ่มหยุดอยู่แถวไทม์ไลน์ใต้ตัวเล่น (ReelStatus)
 * ข้อความ "ช่วง i จาก n" สำหรับโปรแกรมอ่านหน้าจอประกาศจากที่นี่ (aria-live อยู่ตลอด ไม่หายตอนตัวเล่นลอย)
 */
export function ReelButton({ ranges, className }: { ranges: readonly ReplaySegment[] | undefined; className?: string }) {
  const status = useReelStatus()
  if (!ranges || ranges.length === 0) return null
  return (
    <>
      <Button
        variant="secondary"
        size="sm"
        data-slot="player-reel"
        className={cn("max-sm:h-11", className)}
        onClick={() => playerActions.playReel([...ranges])}
      >
        <Flame aria-hidden />
        {t.reel}
      </Button>
      <span aria-live="polite" className="sr-only">
        {status}
      </span>
    </>
  )
}

type StatusProps = {
  /** ปุ่มหยุดหายไปพร้อมสถานะ: โฟกัสอยู่ที่ปุ่มนี้ตอนหาย = ย้ายโฟกัสไปที่นี่ (ไม่ให้หลุดไป body) */
  fallbackFocus: () => HTMLElement | null | undefined
  className?: string
  buttonClassName?: string
  size?: "xs" | "sm"
}

/**
 * "ช่วง i จาก n" + ปุ่ม "หยุดเล่นช่วงไฮไลต์" ระหว่างเล่นช่วงไฮไลต์ (แถวไทม์ไลน์ใต้ตัวเล่น และแถบเครื่องมือของตัวเล่นลอย)
 * ตัวเลขที่เห็นเป็น aria-hidden เพราะโปรแกรมอ่านหน้าจอได้ยินจาก aria-live ของ ReelButton แล้ว (ไม่อ่านซ้ำ)
 */
export function ReelStatus({ fallbackFocus, className, buttonClassName, size = "sm" }: StatusProps) {
  const status = useReelStatus()
  if (status === null) return null
  return (
    <span data-slot="reel-status" className={cn("flex min-w-0 items-center gap-2 text-xs text-muted-foreground tabular", className)}>
      <span aria-hidden>{status}</span>
      <StopButton size={size} className={buttonClassName} fallbackFocus={fallbackFocus} />
    </span>
  )
}

function StopButton({ size, className, fallbackFocus }: Pick<StatusProps, "fallbackFocus" | "className" | "size">) {
  const ref = useRef<HTMLButtonElement>(null)
  const fallback = useRef(fallbackFocus)
  useLayoutEffect(() => {
    fallback.current = fallbackFocus
  })
  // หายไปตอนกดหยุดหรือเล่นจบช่วงสุดท้าย: ถ้าโฟกัสอยู่ที่ปุ่ม ย้ายไปที่ใกล้ ๆ หลังวาดเสร็จ
  useLayoutEffect(() => {
    const button = ref.current
    return () => {
      if (button === null || document.activeElement !== button) return
      requestAnimationFrame(() => {
        if (document.activeElement === null || document.activeElement === document.body) fallback.current()?.focus({ preventScroll: true })
      })
    }
  }, [])
  return (
    <Button ref={ref} variant={size === "xs" ? "ghost" : "secondary"} size={size} onClick={stopReel} className={className}>
      <Square aria-hidden />
      {t.reelStop}
    </Button>
  )
}
