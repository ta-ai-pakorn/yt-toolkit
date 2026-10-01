import { useId, useLayoutEffect, useRef, type RefObject } from "react"

import { fill, th } from "@/i18n/th"
import { barSummary, type BarSummary } from "@/lib/jobs"

import { jobTitle, progressLine } from "./job-text"
import { PauseAlert } from "./pause-alert"
import { QueueSheet } from "./queue-sheet"
import { queueSheet, useQueueData, useQueueSheet } from "./use-queue"

const OFFSET_VAR = "--dock-bottom-offset"

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
        className="relative block w-full text-left transition-colors outline-none hover:bg-muted/60 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:ring-inset"
      >
        {current && progress !== undefined && (
          <span
            aria-hidden
            data-testid="queue-bar-progress"
            className="absolute top-0 left-0 h-1 bg-primary transition-[width] duration-300"
            style={{ width: `${Math.min(100, Math.max(0, progress * 100))}%` }}
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
  const summary = barSummary(jobs ?? [])
  return (
    <>
      {summary.visible && <BarPanel summary={summary} pausedUntil={queue?.pausedUntil ?? null} />}
      <QueueSheet />
    </>
  )
}
