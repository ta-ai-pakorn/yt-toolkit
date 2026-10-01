import { CircleX, XIcon } from "lucide-react"
import { useEffect, useRef, type ReactNode } from "react"

import { Button } from "@/components/ui/button"
import { Sheet, SheetClose, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import { th } from "@/i18n/th"
import { groupForSheet } from "@/lib/jobs"

import { DoneRow, FailedRow, RunningRow } from "./job-row"
import { PauseAlert } from "./pause-alert"
import { SortableQueued } from "./sortable-queued"
import { queueDrag, queueSheet, useQueueData, useQueueSheet } from "./use-queue"

function Group({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="flex flex-col">
      <h3 id={id} className="pt-3 text-sm font-medium text-muted-foreground">
        {title}
      </h3>
      {children}
    </section>
  )
}

/** ปุ่ม "ดูรายละเอียด" ของแถวที่ toast ชี้มา · แถวไม่มีรายละเอียด = ตัวแถว · ยังไม่ได้วาด = null */
function focusTarget(body: HTMLElement | null, focusId: string | null): HTMLElement | null {
  if (body === null || focusId === null) return null
  const row = body.querySelector<HTMLElement>(`[data-job-id="${CSS.escape(focusId)}"]`)
  return row?.querySelector<HTMLElement>("[data-details-trigger]") ?? row ?? null
}

/**
 * ชีตคิวงาน (เลื่อนขึ้นจากล่าง สูงไม่เกิน 80% ของจอ เลื่อนดูข้างในได้)
 * แจ้งหยุดพักอยู่บนสุด แล้วเป็นกลุ่ม: กำลังทำ · รอ (ลากเรียงได้) · ผิดพลาด · เสร็จแล้ว
 * เปิดจากปุ่ม "ดูรายละเอียด" ใน toast = เลื่อนไปที่แถวของงานนั้นและกางรายละเอียดไว้
 */
export function QueueSheet() {
  const { open, focusId } = useQueueSheet()
  const { jobs, jobsError, queue } = useQueueData()
  const bodyRef = useRef<HTMLDivElement>(null)
  const loaded = jobs !== undefined

  useEffect(() => {
    if (!open || focusId === null || !loaded) return
    // รอชีตวาดเสร็จก่อน (portal) แล้วเลื่อนไปหาแถว และย้ายโฟกัสไปที่ปุ่มรายละเอียดของแถวนั้น
    const timer = window.setTimeout(() => {
      const target = focusTarget(bodyRef.current, focusId)
      target?.scrollIntoView({ block: "center" })
      if (target?.hasAttribute("data-details-trigger")) target.focus({ preventScroll: true })
    }, 50)
    return () => window.clearTimeout(timer)
  }, [open, focusId, loaded])

  const onOpenChange = (next: boolean, details: { reason: string }) => {
    if (next) return queueSheet.open()
    // Esc ระหว่างลากเปลี่ยนลำดับ = ยกเลิกการลาก (dnd-kit) ไม่ใช่ปิดชีต
    if (details.reason === "escape-key" && queueDrag.active) return
    queueSheet.close()
  }

  const groups = groupForSheet(jobs ?? [])
  const paused = queue?.pausedUntil ?? null

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="bottom"
        showCloseButton={false}
        initialFocus={() => {
          const target = focusTarget(bodyRef.current, focusId)
          return target?.hasAttribute("data-details-trigger") ? target : true
        }}
        className="max-h-[80vh] gap-0 overflow-y-auto"
      >
        <div ref={bodyRef} className="mx-auto flex w-full max-w-[960px] min-w-0 flex-col px-4 pb-4">
          <SheetHeader className="flex-row items-start justify-between gap-2 px-0">
            <div className="flex min-w-0 flex-col gap-0.5">
              <SheetTitle>{th.queue.sheetTitle}</SheetTitle>
              <SheetDescription>{th.queue.sheetHint}</SheetDescription>
            </div>
            <SheetClose render={<Button variant="ghost" size="icon-sm" aria-label={th.queue.close} className="shrink-0" />}>
              <XIcon aria-hidden />
            </SheetClose>
          </SheetHeader>
          {paused && <PauseAlert pausedUntil={paused} variant="sheet" />}
          {!loaded && jobsError && (
            <p role="alert" className="flex items-center gap-2 py-3 text-sm text-destructive">
              <CircleX aria-hidden className="size-4" />
              {th.queue.actionFailed}
            </p>
          )}
          {!loaded && !jobsError && (
            <div className="flex flex-col gap-2 py-3" aria-busy="true">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          )}
          {loaded && Object.values(groups).every((group) => group.length === 0) && (
            <p className="py-6 text-center text-sm text-muted-foreground">{th.queue.empty}</p>
          )}
          {groups.running.length > 0 && (
            <Group id="queue-group-running" title={th.queue.groups.running}>
              <ul className="divide-y">
                {groups.running.map((job) => (
                  <RunningRow key={job.id} job={job} />
                ))}
              </ul>
            </Group>
          )}
          {groups.queued.length > 0 && (
            <Group id="queue-group-queued" title={th.queue.groups.queued}>
              <SortableQueued jobs={groups.queued} />
            </Group>
          )}
          {groups.failed.length > 0 && (
            <Group id="queue-group-failed" title={th.queue.groups.failed}>
              <ul className="divide-y">
                {groups.failed.map((job) => (
                  <FailedRow key={job.id} job={job} expanded={job.id === focusId} />
                ))}
              </ul>
            </Group>
          )}
          {groups.done.length > 0 && (
            <Group id="queue-group-done" title={th.queue.groups.done}>
              <ul className="divide-y">
                {groups.done.map((job) => (
                  <DoneRow key={job.id} job={job} />
                ))}
              </ul>
            </Group>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}
