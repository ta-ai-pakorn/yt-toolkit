import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Hourglass } from "lucide-react"
import { useEffect, useState } from "react"

import { showErrorToast } from "@/components/error-report/error-toast"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import { th } from "@/i18n/th"
import { QUEUE_KEY, resumeQueue } from "@/lib/jobs"
import { reportRequest } from "@/lib/report"
import type { QueueState } from "@/lib/types"
import { cn } from "cn"

import { pausedCountdown, pausedRemainingMs } from "./job-text"

/** เวลาปัจจุบันที่อัปเดตทุกวินาที (ใช้นับถอยหลัง) */
function useNow(): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])
  return now
}

/**
 * แจ้งว่าคิวหยุดพัก (ยูทูปขอยืนยันว่าไม่ใช่บอท) พร้อมนับถอยหลัง m:ss และปุ่ม "ลองต่อเลย"
 * ครบเวลาแล้วซ่อนเอง (backend ส่ง queue.resumed ตามมา) · ตัวเลขนับถอยหลังไม่ถูกอ่านซ้ำทุกวินาที (aria-live off)
 */
export function PauseAlert({ pausedUntil, variant }: { pausedUntil: string; variant: "bar" | "sheet" }) {
  const now = useNow()
  const client = useQueryClient()
  const resume = useMutation({
    mutationFn: () => resumeQueue(),
    onSuccess: () =>
      client.setQueryData<QueueState>(QUEUE_KEY, (old) => (old === undefined ? old : { ...old, pausedUntil: null, reason: null })),
    onError: (error) =>
      showErrorToast(th.queue.actionFailed, { id: "queue-resume", request: reportRequest(error, { context: "queue-resume" }) }),
  })

  if (pausedRemainingMs(pausedUntil, now) <= 0) return null

  const [before, after] = th.queue.paused.body.split("{time}")
  return (
    <Alert
      role="status"
      data-testid="queue-paused"
      className={cn(
        "flex flex-wrap items-center gap-x-3 gap-y-1.5 *:[svg]:translate-y-0 *:[svg]:text-warning",
        variant === "bar" && "rounded-none border-0 bg-transparent px-0",
      )}
    >
      <Hourglass aria-hidden />
      <div className="min-w-0 flex-1">
        <AlertTitle>{th.queue.paused.title}</AlertTitle>
        <AlertDescription>
          {before}
          <span aria-live="off" className="font-mono tabular-nums">
            {pausedCountdown(pausedUntil, now)}
          </span>
          {after}
        </AlertDescription>
      </div>
      <Button
        variant="outline"
        size="sm"
        className="shrink-0"
        disabled={resume.isPending}
        onClick={() => resume.mutate()}
      >
        {resume.isPending ? <Spinner /> : null}
        {th.queue.paused.resume}
      </Button>
    </Alert>
  )
}

