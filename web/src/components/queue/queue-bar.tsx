import { lazy, Suspense, useEffect, useId, useLayoutEffect, useRef, useState, type ComponentType, type RefObject } from "react"

import { fill, th } from "@/i18n/th"
import { barSummary, type BarSummary } from "@/lib/jobs"
import { importWithReload } from "@/lib/lazy-import"
import { cn } from "cn"

import { jobTitle, progressLine } from "./job-text"
import { PauseAlert } from "./pause-alert"
import { queueSheet, useQueueData, useQueueSheet } from "./use-queue"

const OFFSET_VAR = "--dock-bottom-offset"

// ชีตคิว (รวม dnd-kit) แยกไฟล์ โหลดเมื่อแถบคิวขึ้นครั้งแรก หน้าแรกจึงเบา · โหลดไม่ได้ = ไม่มีชีต (แถบยังใช้ได้)
const importSheet = () => import("./queue-sheet")
const QueueSheet = lazy(() =>
  importWithReload(importSheet)
    .then((m): { default: ComponentType } => ({ default: m.QueueSheet }))
    .catch((error: unknown) => {
      console.warn("[queue] failed to load the queue sheet", error)
      return { default: () => null }
    }),
)

/**
 * บอกความสูงของแถบคิวให้ของที่ลอยอยู่ข้างบน (ตัวเล่นลอย M3.5, toast) ผ่าน --dock-bottom-offset ที่ :root
 * แถบเปลี่ยนความสูง (ขึ้นสองบรรทัด, แจ้งหยุดพัก) = อัปเดตตาม · แถบหายไป = กลับเป็น 0px
 */
function useDockOffset(ref: RefObject<HTMLElement | null>): void {
  useLayoutEffect(() => {
    const element = ref.current
    if (element === null) return
    const root = document.documentElement
    const apply = () => root.style.setProperty(OFFSET_VAR, `${Math.ceil(element.getBoundingClientRect().height)}px`)
    apply()
    const observer = new ResizeObserver(apply)
    observer.observe(element)
    return () => {
      observer.disconnect()
      root.style.setProperty(OFFSET_VAR, "0px")
    }
  }, [ref])
}

function BarPanel({ summary, pausedUntil }: { summary: BarSummary; pausedUntil: string | null }) {
  const ref = useRef<HTMLDivElement>(null)
  const summaryId = useId()
  const { open } = useQueueSheet()
  useDockOffset(ref)

  const current = summary.current
  const line = current ? progressLine(current) : summary.queued > 0 ? th.queue.waiting : null
  const progress = current?.progress

  return (
    <div
      ref={ref}
      role="region"
      aria-label={th.queue.region}
      className="fixed inset-x-0 bottom-0 z-40 border-t bg-background shadow-[0_-4px_12px_rgb(0_0_0/0.06)]"
    >
      {pausedUntil && (
        <div className="mx-auto max-w-[960px] border-b px-4 py-1">
          <PauseAlert pausedUntil={pausedUntil} variant="bar" />
        </div>
      )}
      <button
        type="button"
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={th.queue.open}
        aria-describedby={summaryId}
        onClick={() => queueSheet.open()}
        className="relative block w-full text-left transition-colors outline-none hover:bg-muted/60 focus-visible:ring-3 focus-visible:ring-ring focus-visible:ring-inset"
      >
        {/* เส้นอำพัน 4 px: รู้ % = ยาวตาม % · ยังไม่รู้ = เต็มเส้นกะพริบช้า ๆ (ปิดการเคลื่อนไหว = นิ่ง) */}
        {current && (
          <span
            aria-hidden
            data-testid="queue-bar-progress"
            data-indeterminate={progress === undefined ? "" : undefined}
            className={cn(
              "absolute top-0 left-0 h-1 bg-primary",
              progress === undefined ? "w-full motion-safe:animate-pulse" : "transition-[width] duration-300",
            )}
            style={progress === undefined ? undefined : { width: `${Math.min(100, Math.max(0, progress * 100))}%` }}
          />
        )}
        <span
          id={summaryId}
          className="mx-auto flex max-w-[960px] min-w-0 flex-wrap items-center gap-x-3 gap-y-0.5 px-4 py-2.5 text-sm"
        >
          {current && (
            <span className="min-w-0 flex-1 basis-48 truncate font-medium" title={jobTitle(current)}>
              {jobTitle(current)}
            </span>
          )}
          {line && <span className="min-w-0 text-muted-foreground tabular-nums">{line}</span>}
          <span className="ml-auto min-w-0 text-muted-foreground tabular-nums">
            {fill(th.queue.counts, { running: summary.running, queued: summary.queued, done: summary.done })}
          </span>
        </span>
      </button>
    </div>
  )
}

/**
 * แถบคิวงานติดขอบล่างของทุกหน้า (ซ่อนเมื่อไม่มีงาน) · ทั้งแถบเป็นปุ่ม "เปิดคิวงาน" ที่เปิดชีตคิว
 * บรรทัดเดียว: ชื่องานล่าสุดที่กำลังทำ · ขั้นตอน % ความเร็ว เวลาที่เหลือ · จำนวนงาน (จอแคบขึ้นสองบรรทัด ไม่ล้นจอ)
 */
export function QueueBar() {
  const { jobs, queue } = useQueueData()
  const { open } = useQueueSheet()
  const summary = barSummary(jobs ?? [])
  // สร้างชีตเมื่อถูกเปิดครั้งแรก แล้วคงไว้ (ปิดแล้วเปิดใหม่ไม่ต้องโหลดซ้ำ)
  const [sheetWanted, setSheetWanted] = useState(open)
  if (open && !sheetWanted) setSheetWanted(true)

  // โหลดโค้ดชีตล่วงหน้าเมื่อแถบขึ้น ตอนกดเปิดจะได้ไม่ต้องรอ (พลาดก็ไม่เป็นไร ตอนเปิดจริงจะลองอีกครั้ง)
  useEffect(() => {
    if (summary.visible) importSheet().catch(() => undefined)
  }, [summary.visible])

  return (
    <>
      {summary.visible && <BarPanel summary={summary} pausedUntil={queue?.pausedUntil ?? null} />}
      {sheetWanted && (
        <Suspense fallback={null}>
          <QueueSheet />
        </Suspense>
      )}
    </>
  )
}
