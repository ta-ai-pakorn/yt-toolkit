import { Dialog as DialogPrimitive } from "@base-ui/react/dialog"
import { useState, type KeyboardEvent } from "react"

import { fill, th } from "@/i18n/th"
import { formatTimecode } from "@/lib/format"
import type { StoryboardFrame } from "@/lib/types"

/** ขยายภาพได้ไม่เกิน 2 เท่าของขนาดจริง: ภาพ storyboard เล็ก (160-320 px) ขยายมากกว่านี้จะเบลอ */
const MAX_UPSCALE = 2
// ขนาดภาพ storyboard ที่พบบ่อย ใช้ก่อนภาพโหลดเสร็จ (ภาพมาจาก cache ของเบราว์เซอร์ ปกติโหลดทันที)
const DEFAULT_SIZE = { width: 320, height: 180 }

type Props = {
  frames: StoryboardFrame[]
  /** ตำแหน่งของภาพที่เปิดอยู่ใน frames · null = ปิด */
  index: number | null
  onIndexChange: (index: number | null) => void
  /** ปิดแล้วโฟกัสกลับที่ไหน (รับตำแหน่งภาพสุดท้ายที่ดู) */
  returnFocus: (last: number) => HTMLElement | null
}

/**
 * ภาพเฟรมขนาดใหญ่บนพื้นหลังมืด: มีแต่ภาพ ไม่มีกรอบ ไม่มีปุ่ม ไม่มีคำบรรยาย
 * ปิดด้วย Esc, คลิกพื้นหลัง หรือคลิกที่ภาพ · ←/→ = ภาพก่อนหน้า/ถัดไป (ไม่มีปุ่มบนจอ)
 * โปรแกรมอ่านหน้าจอได้ชื่อกล่อง "ภาพเฟรมที่ HH:MM:SS" และได้ยินเวลาใหม่ทุกครั้งที่เลื่อนภาพ
 */
export function FrameLightbox({ frames, index, onIndexChange, returnFocus }: Props) {
  // จำภาพล่าสุดไว้ ให้ภาพยังอยู่ระหว่างแอนิเมชันปิด (ตอนนั้น index เป็น null แล้ว)
  const [last, setLast] = useState(0)
  if (index !== null && index !== last) setLast(index)
  const position = index ?? last
  const frame = frames[Math.min(position, frames.length - 1)]
  const [natural, setNatural] = useState<{ url: string; width: number; height: number } | null>(null)

  if (!frame) return null
  const time = formatTimecode(frame.tMs)
  const size = natural?.url === frame.url ? natural : DEFAULT_SIZE
  // ใหญ่ที่สุดที่ยังอยู่ในกรอบ 90vw × 85vh และไม่เกิน 2 เท่าของขนาดจริง (คงสัดส่วนภาพ)
  const width = `min(90vw, calc(85vh * ${size.width} / ${size.height}), ${size.width * MAX_UPSCALE}px)`

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "ArrowRight" && position < frames.length - 1) {
      event.preventDefault()
      onIndexChange(position + 1)
    } else if (event.key === "ArrowLeft" && position > 0) {
      event.preventDefault()
      onIndexChange(position - 1)
    }
  }

  return (
    <DialogPrimitive.Root open={index !== null} onOpenChange={(open) => !open && onIndexChange(null)}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Backdrop
          data-slot="lightbox-backdrop"
          className="fixed inset-0 z-50 bg-black/85 duration-150 data-open:animate-in data-open:fade-in-0 data-closed:animate-out data-closed:fade-out-0"
        />
        <DialogPrimitive.Popup
          data-slot="lightbox"
          aria-label={fill(th.frames.frameAlt, { time })}
          finalFocus={() => returnFocus(position)}
          onKeyDown={onKeyDown}
          className="fixed top-1/2 left-1/2 z-50 -translate-x-1/2 -translate-y-1/2 outline-none duration-150 data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95 data-closed:animate-out data-closed:fade-out-0 data-closed:zoom-out-95"
        >
          <img
            src={frame.url}
            alt=""
            draggable={false}
            onClick={() => onIndexChange(null)}
            onLoad={(event) =>
              setNatural({
                url: frame.url,
                width: event.currentTarget.naturalWidth || DEFAULT_SIZE.width,
                height: event.currentTarget.naturalHeight || DEFAULT_SIZE.height,
              })
            }
            style={{ width }}
            className="block h-auto max-w-none cursor-zoom-out rounded-sm select-none"
          />
          <span className="sr-only" aria-live="polite">
            {time}
          </span>
        </DialogPrimitive.Popup>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
