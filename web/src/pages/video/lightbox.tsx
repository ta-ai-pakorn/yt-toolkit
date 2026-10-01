import { Dialog as DialogPrimitive } from "@base-ui/react/dialog"
import { useState, type KeyboardEvent, type ReactNode } from "react"

import { fill, th } from "@/i18n/th"
import { formatTimecode } from "@/lib/format"
import type { StoryboardFrame } from "@/lib/types"

/** ขยายภาพได้ไม่เกิน 2 เท่าของขนาดจริง: ภาพ storyboard เล็ก (160-320 px) ขยายมากกว่านี้จะเบลอ */
const MAX_UPSCALE = 2
// ขนาดสำรองเผื่อเบราว์เซอร์บอกขนาดภาพไม่ได้
const DEFAULT_SIZE = { width: 320, height: 180 }

type LightboxProps = {
  open: boolean
  src: string
  /** ชื่อกล่องสำหรับโปรแกรมอ่านหน้าจอ */
  label: string
  onClose: () => void
  /** ปิดแล้วโฟกัสกลับที่ไหน */
  finalFocus: () => HTMLElement | null
  /** ภาพชุดเดียวกันขนาดเท่ากัน: ค่านี้เปลี่ยน (ชุดภาพใหม่) = วัดขนาดจริงใหม่ */
  sizeKey: unknown
  onKeyDown?: (event: KeyboardEvent<HTMLDivElement>) => void
  /** ของเพิ่มในกล่อง เช่นข้อความที่อ่านออกเสียงเมื่อเลื่อนภาพ */
  children?: ReactNode
}

/**
 * ภาพขนาดใหญ่บนพื้นหลังมืด: มีแต่ภาพ ไม่มีกรอบ ไม่มีปุ่ม ไม่มีคำบรรยาย
 * ปิดด้วย Esc, คลิกพื้นหลัง หรือคลิกที่ภาพ · ใช้กับภาพเฟรม (FrameLightbox) และภาพปกที่หัวคลิป
 */
export function Lightbox({ open, src, label, onClose, finalFocus, sizeKey, onKeyDown, children }: LightboxProps) {
  // ขนาดจริงของภาพ: ทุกภาพในชุดเดียวกันขนาดเท่ากัน จึงใช้ขนาดของภาพที่โหลดแล้วกับภาพถัดไปได้เลย
  // ยังไม่รู้ขนาด (เปิดครั้งแรก) = ซ่อนภาพไว้จนโหลดเสร็จ ภาพเล็กจะได้ไม่แวบขึ้นมาใหญ่เกินก่อน
  const [natural, setNatural] = useState<{ key: unknown; width: number; height: number } | null>(null)
  const known = natural?.key === sizeKey ? natural : null
  const size = known ?? DEFAULT_SIZE
  // ใหญ่ที่สุดที่ยังอยู่ในกรอบ 90vw × 85vh และไม่เกิน 2 เท่าของขนาดจริง (คงสัดส่วนภาพ)
  const width = `min(90vw, calc(85vh * ${size.width} / ${size.height}), ${size.width * MAX_UPSCALE}px)`

  return (
    <DialogPrimitive.Root open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Backdrop
          data-slot="lightbox-backdrop"
          className="fixed inset-0 z-50 bg-black/85 duration-150 data-open:animate-in data-open:fade-in-0 data-closed:animate-out data-closed:fade-out-0"
        />
        <DialogPrimitive.Popup
          data-slot="lightbox"
          aria-label={label}
          finalFocus={finalFocus}
          onKeyDown={onKeyDown}
          className="fixed top-1/2 left-1/2 z-50 -translate-x-1/2 -translate-y-1/2 outline-none duration-150 data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95 data-closed:animate-out data-closed:fade-out-0 data-closed:zoom-out-95"
        >
          <img
            src={src}
            alt=""
            draggable={false}
            referrerPolicy="no-referrer"
            onClick={onClose}
            onLoad={(event) => {
              const loaded = {
                width: event.currentTarget.naturalWidth || DEFAULT_SIZE.width,
                height: event.currentTarget.naturalHeight || DEFAULT_SIZE.height,
              }
              if (known?.width !== loaded.width || known.height !== loaded.height) setNatural({ key: sizeKey, ...loaded })
            }}
            onError={() => {
              // โหลดภาพไม่ได้: เลิกซ่อน ใช้ขนาดสำรอง ให้เห็นกรอบภาพ (ไม่ค้างเป็นพื้นมืดเปล่า ๆ) คลิกหรือ Esc ปิดได้ตามปกติ
              if (!known) setNatural({ key: sizeKey, ...DEFAULT_SIZE })
            }}
            style={{ width, aspectRatio: `${size.width} / ${size.height}`, visibility: known ? undefined : "hidden" }}
            className="block h-auto max-w-none cursor-zoom-out rounded-sm bg-muted select-none"
          />
          {children}
        </DialogPrimitive.Popup>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}

type Props = {
  frames: StoryboardFrame[]
  /** ตำแหน่งของภาพที่เปิดอยู่ใน frames · null = ปิด */
  index: number | null
  onIndexChange: (index: number | null) => void
  /** ปิดแล้วโฟกัสกลับที่ไหน (รับตำแหน่งภาพสุดท้ายที่ดู) */
  returnFocus: (last: number) => HTMLElement | null
}

/**
 * ภาพเฟรมขนาดใหญ่ (Lightbox) · ←/→ = ภาพก่อนหน้า/ถัดไป (ไม่มีปุ่มบนจอ)
 * โปรแกรมอ่านหน้าจอได้ชื่อกล่อง "ภาพเฟรมที่ HH:MM:SS" และได้ยินเวลาใหม่ทุกครั้งที่เลื่อนภาพ
 */
export function FrameLightbox({ frames, index, onIndexChange, returnFocus }: Props) {
  // จำภาพล่าสุดไว้ ให้ภาพยังอยู่ระหว่างแอนิเมชันปิด (ตอนนั้น index เป็น null แล้ว)
  const [last, setLast] = useState(0)
  if (index !== null && index !== last) setLast(index)
  const position = index ?? last
  const frame = frames[Math.min(position, frames.length - 1)]

  if (!frame) return null
  const time = formatTimecode(frame.tMs)

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
    <Lightbox
      open={index !== null}
      src={frame.url}
      label={fill(th.frames.frameAlt, { time })}
      onClose={() => onIndexChange(null)}
      finalFocus={() => returnFocus(position)}
      sizeKey={frames}
      onKeyDown={onKeyDown}
    >
      <span className="sr-only" aria-live="polite">
        {time}
      </span>
    </Lightbox>
  )
}
