import { cn } from "cn"
import { useRef, useState, type KeyboardEvent, type PointerEvent } from "react"

import { th } from "@/i18n/th"
import { formatTimecode } from "@/lib/format"
import type { Chapter, ReplaySegment } from "@/lib/types"

import { playerActions, usePlayerValue } from "./player-store"
import { isTap, keyTarget, msAtPoint, percentOf, rangeBox } from "./timeline-geometry"

const t = th.player

type Props = {
  durationMs: number
  chapters: readonly Chapter[]
  replayed: readonly ReplaySegment[] | undefined
  /** แสดงแถบ (ตัวเล่นอยู่ในหัวคลิปและเคยเล่นแล้ว) */
  visible: boolean
  className?: string
}

/**
 * แถบไทม์ไลน์ใต้ตัวเล่น: ช่วงที่ดูซ้ำบ่อย (แถบอำพัน) · จุดเริ่ม chapter (ขีดบาง) · ตำแหน่งที่กำลังเล่น
 * คลิก/แตะ (ปล่อยแทบที่เดิม) = เล่นจากตรงนั้น · ปัดขึ้นลงบนแถบ = เลื่อนหน้า ไม่กระโดด · คีย์บอร์ด (role="slider"): ซ้าย/ขวา ทีละ 5 วินาที Home/End ไปต้น/ท้าย
 * ระหว่างกดค้างตำแหน่งขยับตาม แล้ว seek ตอนปล่อยปุ่ม (ไม่ seek ถี่ ๆ ทุกครั้งที่ปุ่มซ้ำ)
 */
export function Timeline({ durationMs, chapters, replayed, visible, className }: Props) {
  if (!(durationMs > 0) || !visible) return null
  return <TimelineBar durationMs={durationMs} chapters={chapters} replayed={replayed} className={className} />
}

function TimelineBar({ durationMs, chapters, replayed, className }: Omit<Props, "visible">) {
  const currentMs = usePlayerValue((s) => s.currentMs)
  const status = usePlayerValue((s) => s.status)
  // ตำแหน่งที่เลื่อนด้วยคีย์บอร์ดแต่ยังไม่ปล่อยปุ่ม
  const [draftMs, setDraftMs] = useState<number | null>(null)
  // โฟกัสอยู่ที่แถบ: ค่าที่โปรแกรมอ่านหน้าจอได้ยิน (aria-valuenow/valuetext) หยุดนิ่ง ไม่เปลี่ยนทุก 250 ms ระหว่างเล่น
  // (ถ้าเปลี่ยนตลอด โปรแกรมอ่านหน้าจอจะอ่านเวลาซ้ำไม่หยุด) · อัปเดตเมื่อผู้ใช้กระโดดเอง หยุดคลิป หรือโฟกัสใหม่
  const [focused, setFocused] = useState(false)
  const [heardMs, setHeardMs] = useState(0)
  const [seenStatus, setSeenStatus] = useState(status)
  if (seenStatus !== status) {
    setSeenStatus(status)
    if (status === "paused") setHeardMs(currentMs)
  }
  const trackRef = useRef<HTMLDivElement>(null)
  // จุดที่เริ่มกด (เมาส์/นิ้ว) · seek ตอนปล่อยถ้าแทบไม่ขยับ = แตะ ไม่ใช่ปัดเลื่อนหน้า
  const press = useRef<{ id: number; x: number; y: number } | null>(null)
  const shownMs = Math.min(draftMs ?? currentMs, durationMs)
  const ariaMs = Math.min(draftMs ?? (focused ? heardMs : currentMs), durationMs)

  function seek(ms: number) {
    setHeardMs(ms)
    playerActions.playFrom(ms)
  }

  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return
    press.current = { id: event.pointerId, x: event.clientX, y: event.clientY }
  }

  function onPointerUp(event: PointerEvent<HTMLDivElement>) {
    const start = press.current
    press.current = null
    if (!start || start.id !== event.pointerId || !isTap(start, { x: event.clientX, y: event.clientY })) return
    const box = trackRef.current?.getBoundingClientRect()
    if (!box) return
    seek(msAtPoint(event.clientX, box.left, box.width, durationMs))
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const next = keyTarget(event.key, draftMs ?? currentMs, durationMs)
    if (next === null) return
    event.preventDefault()
    setDraftMs(next)
  }

  function onKeyUp(event: KeyboardEvent<HTMLDivElement>) {
    if (draftMs === null || keyTarget(event.key, 0, durationMs) === null) return
    event.preventDefault()
    setDraftMs(null)
    seek(draftMs)
  }

  return (
    <div
      role="slider"
      tabIndex={0}
      aria-label={t.timeline}
      aria-valuemin={0}
      aria-valuemax={Math.floor(durationMs / 1000)}
      aria-valuenow={Math.floor(ariaMs / 1000)}
      aria-valuetext={formatTimecode(ariaMs)}
      aria-orientation="horizontal"
      data-slot="player-timeline"
      onPointerDown={onPointerDown}
      onPointerUp={onPointerUp}
      // เบราว์เซอร์รับไปเลื่อนหน้าเอง (ปัดขึ้นลง) = ยกเลิกการกด ไม่ seek
      onPointerCancel={() => {
        press.current = null
      }}
      // ลากออกนอกแถบแล้วปล่อยข้างนอก = ไม่นับเป็นการแตะ (กันการกดค้างเก่าไปจับคู่กับการปล่อยครั้งหลัง)
      onPointerLeave={() => {
        press.current = null
      }}
      onKeyDown={onKeyDown}
      onKeyUp={onKeyUp}
      onFocus={() => {
        setFocused(true)
        setHeardMs(currentMs)
      }}
      onBlur={() => {
        setFocused(false)
        setDraftMs(null)
      }}
      // pan-y: ปัดขึ้นลงบนแถบ = เลื่อนหน้า (จอสัมผัส) · แตะ = กระโดด
      className={cn(
        "group/timeline relative flex h-6 w-full cursor-pointer touch-pan-y items-center rounded-sm outline-none select-none focus-visible:ring-3 focus-visible:ring-ring max-sm:h-11",
        className,
      )}
    >
      <div ref={trackRef} className="relative h-1.5 w-full rounded-full bg-foreground/15">
        {replayed?.map((range) => {
          const box = rangeBox(range, durationMs)
          return box ? (
            <span
              key={`${range.startMs}-${range.endMs}`}
              data-slot="timeline-replayed"
              className="absolute inset-y-0 rounded-full bg-primary"
              style={box}
            />
          ) : null
        })}
        {chapters.map((chapter) =>
          chapter.startS > 0 && chapter.startS * 1000 < durationMs ? (
            <span
              key={chapter.startS}
              data-slot="timeline-chapter"
              className="absolute -top-1 h-3.5 w-px bg-foreground/60"
              style={{ left: percentOf(chapter.startS * 1000, durationMs) }}
            />
          ) : null,
        )}
        <span
          data-slot="timeline-playhead"
          className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background bg-foreground shadow-sm"
          style={{ left: percentOf(shownMs, durationMs) }}
        />
      </div>
    </div>
  )
}
