import { CircleCheck, CirclePause, CircleX, Download, FolderOpen, RotateCcw } from "lucide-react"
import { useState, type ComponentProps, type ReactNode } from "react"

import { UseAccountButton } from "@/components/account/account-button"
import { useAccountStatus } from "@/components/account/use-account"
import { ErrorDetails } from "@/components/error-report/error-details"
import { Badge } from "@/components/ui/badge"
import { Button, buttonVariants } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Spinner } from "@/components/ui/spinner"
import { fill, th } from "@/i18n/th"
import { showAccountButton } from "@/lib/account"
import { outputUrl } from "@/lib/jobs"
import type { Job } from "@/lib/types"
import { cn } from "cn"

import { jobTitle, progressLine } from "./job-text"
import { revealWithToast, useJobAction } from "./use-queue"

const ROW = "flex min-w-0 items-start gap-3 py-3"

const INDETERMINATE =
  "[&_[data-slot=progress-indicator][data-indeterminate]]:w-1/3 [&_[data-slot=progress-indicator][data-indeterminate]]:motion-safe:animate-pulse"

/** ชื่อคลิป (ยาวเกินตัดด้วย …) + ป้ายชนิดงาน */
function RowTitle({ job }: { job: Job }) {
  const title = jobTitle(job)
  return (
    <div className="flex min-w-0 items-center gap-2">
      <p className="min-w-0 truncate font-medium" title={title}>
        {title}
      </p>
      <Badge variant="outline" className="shrink-0">
        {th.queue.kinds[job.kind]}
      </Badge>
    </div>
  )
}

/** ปุ่ม "ยกเลิก" ของงานที่รอหรือกำลังทำ · กำลังยกเลิก = ปุ่มกดไม่ได้พร้อมข้อความ */
function CancelButton({ job }: { job: Job }) {
  const cancel = useJobAction("cancel", job.id)
  const cancelling = job.cancelling === true
  return (
    <Button
      variant="outline"
      size="sm"
      className="shrink-0"
      aria-label={cancelling ? undefined : fill(th.queue.cancelJob, { title: jobTitle(job) })}
      disabled={cancelling || cancel.isPending}
      onClick={() => cancel.mutate()}
    >
      {cancel.isPending || cancelling ? <Spinner /> : null}
      {cancelling ? th.queue.cancelling : th.queue.cancel}
    </Button>
  )
}

/** แถวงานที่กำลังทำ: ขั้นตอน · % · ความเร็ว · เวลาที่เหลือ + แถบความคืบหน้า */
export function RunningRow({ job }: { job: Job }) {
  return (
    <li className={ROW} data-job-id={job.id}>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <RowTitle job={job} />
        <p className="text-xs text-muted-foreground tabular-nums">{progressLine(job)}</p>
        {/* ยังไม่รู้ % (เช่นกำลังดึงข้อมูล) = แถบสั้นกะพริบช้า ๆ แทนรางว่าง (ปิดการเคลื่อนไหว = แถบนิ่ง) */}
        <Progress
          aria-label={jobTitle(job)}
          value={job.progress === undefined ? null : Math.round(job.progress * 100)}
          className={cn("mt-1", INDETERMINATE)}
        />
      </div>
      <CancelButton job={job} />
    </li>
  )
}

/** แถวงานที่รอคิว · handle = ปุ่มลากเปลี่ยนลำดับ (มาจาก sortable-queued.tsx) */
export function QueuedRow({ job, handle, className, ...props }: { job: Job; handle: ReactNode } & ComponentProps<"li">) {
  return (
    <li className={cn(ROW, "items-center bg-popover", className)} data-job-id={job.id} {...props}>
      {handle}
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <RowTitle job={job} />
        <p className="text-xs text-muted-foreground">{th.queue.waiting}</p>
      </div>
      <CancelButton job={job} />
    </li>
  )
}

/**
 * แถวงานที่พลาดหรือหยุดกลางคัน: ข้อความผิดพลาด · "ดูรายละเอียด" (รหัส + ข้อความเทคนิค + "คัดลอกข้อมูลแจ้งปัญหา") · "ลองใหม่"
 * M6 รอบ B: ปุ่มคัดลอกรายงานแทนปุ่ม "คัดลอกรายละเอียด" เดิม · เซิร์ฟเวอร์หางานจาก jobId ก่อน code/detail เป็นตัวสำรอง
 */
export function FailedRow({ job, expanded }: { job: Job; expanded: boolean }) {
  const retry = useJobAction("retry", job.id)
  // เปิดจาก toast "ดูรายละเอียด" = กางรายละเอียด แม้แถวนี้จะแสดงอยู่แล้วก่อนหน้า
  // E_UNKNOWN กางตั้งแต่แรก (R1): ข้อความของรหัสนี้บอกให้กดปุ่มคัดลอก ปุ่มจึงต้องเห็นเลย
  const [open, setOpen] = useState(expanded || job.error?.code === "E_UNKNOWN")
  const [lastExpanded, setLastExpanded] = useState(expanded)
  if (expanded !== lastExpanded) {
    setLastExpanded(expanded)
    if (expanded) setOpen(true)
  }
  const interrupted = job.status === "interrupted"
  const Icon = interrupted ? CirclePause : CircleX
  const code = job.error?.code
  const detail = job.error?.detail
  // M5 รอบ C: จำกัดอายุ/ส่วนตัว + ยังไม่ได้ใช้บัญชี = ปุ่ม "ใช้บัญชียูทูปชั่วคราว" นำเข้าแล้วลองงานนี้ใหม่ (params เดิม)
  const { active } = useAccountStatus()
  const offerAccount = showAccountButton(code, active)
  return (
    <li className={ROW} data-job-id={job.id}>
      <Icon aria-hidden className={cn("mt-0.5 size-4 shrink-0", interrupted ? "text-warning" : "text-destructive")} />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <RowTitle job={job} />
        <p className={cn("text-sm", !interrupted && "text-destructive")}>{job.error?.message ?? th.queue.interrupted}</p>
        {offerAccount && (
          <div className="pt-1">
            <UseAccountButton onImported={() => retry.mutate()} />
          </div>
        )}
        {code && (
          <ErrorDetails
            key={`${code}:${detail ?? ""}`}
            request={{ jobId: job.id, code, detail: detail ?? undefined, context: "queue" }}
            open={open}
            onOpenChange={setOpen}
          />
        )}
      </div>
      <Button
        variant="outline"
        size="sm"
        className="shrink-0"
        aria-label={fill(th.queue.retryJob, { title: jobTitle(job) })}
        disabled={retry.isPending}
        onClick={() => retry.mutate()}
      >
        {retry.isPending ? <Spinner /> : <RotateCcw aria-hidden />}
        {th.queue.retry}
      </Button>
    </li>
  )
}

/** แถวงานที่เสร็จแล้ว: ชื่อไฟล์ · หมายเหตุสีเทา · "เปิดโฟลเดอร์" · "ดาวน์โหลด" (ผ่านเบราว์เซอร์) */
export function DoneRow({ job }: { job: Job }) {
  const outputs = job.outputs ?? []
  const title = jobTitle(job)
  return (
    <li className={ROW} data-job-id={job.id}>
      <CircleCheck
        aria-hidden
        className="mt-0.5 size-4 shrink-0 text-success motion-safe:duration-300 motion-safe:animate-in motion-safe:zoom-in-50"
      />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <RowTitle job={job} />
        {outputs.length > 0 && (
          <ul className="flex flex-col gap-1">
            {outputs.map((output) => (
              <li key={output.index} className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
                <span className="min-w-0 flex-1 truncate text-sm" title={output.name}>
                  {output.name}
                </span>
                {/* ผลแบบโฟลเดอร์ (ภาพคม) ดาวน์โหลดผ่านเบราว์เซอร์ไม่ได้: ใช้ "เปิดโฟลเดอร์" */}
                {output.files === undefined && (
                  <a
                    href={outputUrl(job.id, output.index)}
                    download={output.name}
                    aria-label={fill(th.queue.downloadOf, { file: output.name })}
                    className={buttonVariants({ variant: "ghost", size: "sm", className: "shrink-0" })}
                  >
                    <Download aria-hidden />
                    {th.queue.download}
                  </a>
                )}
              </li>
            ))}
          </ul>
        )}
        {job.notes?.map((note) => (
          <p key={note.code} className="text-xs text-muted-foreground">
            {note.message}
          </p>
        ))}
      </div>
      {outputs.length > 0 && (
        <Button
          variant="outline"
          size="sm"
          className="shrink-0"
          aria-label={fill(th.queue.openFolderOf, { title })}
          onClick={() => void revealWithToast(job.id, outputs[0].index)}
        >
          <FolderOpen aria-hidden />
          {th.queue.openFolder}
        </Button>
      )}
    </li>
  )
}
