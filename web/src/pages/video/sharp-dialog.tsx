import { useQuery } from "@tanstack/react-query"
import { useId, useState } from "react"

import { Button } from "@/components/ui/button"
import { Dialog, DialogClose, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { FieldError } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import { Spinner } from "@/components/ui/spinner"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { fill, th } from "@/i18n/th"
import { formatBytes } from "@/lib/format"
import { jobsQuery, useEnqueue } from "@/lib/jobs"
import {
  defaultCustomText,
  sharpDialogModel,
  type SharpFast,
  type SharpMode,
  type SharpResolution,
} from "@/lib/sharp-frames"
import type { VideoInfo } from "@/lib/types"

import { sharpBlock, sharpJobBusy } from "./sharp-request"

const t = th.sharp
// จอแคบ: ปุ่มสูง 44 px ให้นิ้วกดได้ง่าย (แบบเดียวกับปุ่มโหลดทั้งชุด)
const TOUCH = "max-sm:h-11"

const ENQUEUE_MESSAGES = {
  added: th.queue.added,
  addedMany: th.queue.addedMany,
  failed: th.queue.addFailed,
  goHealth: th.queue.goHealth,
}

type Props = {
  videoId: string
  /** ข้อมูลคลิป (ยังไม่มา = ปุ่มปิด) */
  video: VideoInfo | undefined
  /** ภาพเร็วของคลิป · null = ไม่มี storyboard (dialog ไม่มีตัวเลือก "เวลาเดียวกับภาพเร็ว") */
  fast: SharpFast | null
  /** มีชุดภาพคมในแอพแล้ว (dialog เตือนว่าจะถูกแทน) */
  hasSharp: boolean
  /** แถวปุ่มโหลด = secondary · หน้าคลิปไม่มี storyboard = outline */
  variant?: "secondary" | "outline"
}

/**
 * ปุ่ม "ขอภาพคม" (spec 1): เปิด dialog เลือกช่วงเวลา · มีงานภาพคมของคลิปนี้ในคิว = "กำลังดึงภาพคม…" ·
 * คลิปสด/ไม่รู้ความยาว = ปิดพร้อม tooltip (ปุ่มที่ปิดยังโฟกัสได้ ผู้ใช้คีย์บอร์ดจึงเห็นเหตุผล)
 */
export function SharpRequestButton({ videoId, video, fast, hasSharp, variant = "secondary" }: Props) {
  // รายการงานชุดเดียวกับแถบคิว (SSE คอยแก้แคช) ไม่ยิงคำขอเพิ่มเมื่อมีอยู่แล้ว
  const jobs = useQuery({ ...jobsQuery(), staleTime: Infinity })
  const [open, setOpen] = useState(false)
  const size = variant === "secondary" ? "sm" : "default"
  const block = sharpBlock(video)

  const busy = sharpJobBusy(jobs.data, videoId)
  // งานภาพคมเริ่มขณะ dialog เปิดอยู่: dialog ถูกถอดออก ต้องปิด open ด้วย ไม่งั้นจะเด้งขึ้นเองตอนงานจบ
  if (busy && open) setOpen(false)

  if (busy) {
    return (
      <Button variant={variant} size={size} className={TOUCH} disabled focusableWhenDisabled>
        <Spinner aria-hidden />
        {t.busy}
      </Button>
    )
  }
  if (block === "live") {
    return (
      <Tooltip>
        <TooltipTrigger render={<Button variant={variant} size={size} className={TOUCH} disabled focusableWhenDisabled />}>
          {th.frames.requestSharp}
        </TooltipTrigger>
        <TooltipContent>{t.liveDisabled}</TooltipContent>
      </Tooltip>
    )
  }
  return (
    <>
      <Button
        variant={variant}
        size={size}
        className={TOUCH}
        disabled={block !== null}
        focusableWhenDisabled
        onClick={() => setOpen(true)}
      >
        {th.frames.requestSharp}
      </Button>
      {video !== undefined && block === null && (
        <SharpDialog open={open} onOpenChange={setOpen} videoId={videoId} video={video} fast={fast} hasSharp={hasSharp} />
      )}
    </>
  )
}

function resolutionText(r: SharpResolution): string {
  if (r.kind === "low") return fill(t.lowRes, { h: r.h })
  return r.kind === "tall" ? t.tall : t.wide
}

type DialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  videoId: string
  video: VideoInfo
  fast: SharpFast | null
  hasSharp: boolean
}

/**
 * dialog "ขอภาพคม" (spec 1.3): เวลาเดียวกับภาพเร็ว (ค่าเริ่มต้น) หรือ ตั้งเอง ทุก N วินาที · จำนวนภาพ ขนาดวิดีโอชั่วคราว
 * และความละเอียดคำนวณสดจาก sharpDialogModel · เกิน 200 ภาพ = ประโยคปรับช่วงห่างแทนจำนวน แล้วส่ง intervalS = N2
 */
function SharpDialog({ open, onOpenChange, videoId, video, fast, hasSharp }: DialogProps) {
  const [mode, setMode] = useState<SharpMode>("same")
  const [customText, setCustomText] = useState(() => defaultCustomText(video.durationS))
  const { enqueue, pending } = useEnqueue(ENQUEUE_MESSAGES)
  const prefixId = useId()
  const unitId = useId()
  const errorId = useId()
  const model = sharpDialogModel({ durationS: video.durationS, fast, mode, customText, video: video.video, hasSharp })
  const customLabel = `${prefixId} ${unitId}`

  async function start() {
    if (model.params === null || pending) return
    const ok = await enqueue([{ videoId, kind: "frames_sharp", params: model.params, title: video.title }])
    if (ok) onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{th.frames.requestSharp}</DialogTitle>
        </DialogHeader>
        <RadioGroup
          aria-label={th.frames.requestSharp}
          value={model.mode}
          onValueChange={(value) => {
            if (value === "same" || value === "custom") setMode(value)
          }}
          className="gap-3"
        >
          {model.sameAvailable && (
            <label className="flex items-start gap-3">
              <RadioGroupItem value="same" className="mt-0.5" />
              <span className="flex flex-col gap-0.5">
                <span>{t.sameTimes}</span>
                {!(model.mode === "same" && model.overflow) && (
                  <span className="text-muted-foreground">
                    {fill(t.sameTimesDetail, { interval: model.sameInterval ?? "", count: model.sameCount ?? 0 })}
                  </span>
                )}
              </span>
            </label>
          )}
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <RadioGroupItem value="custom" aria-labelledby={customLabel} />
            <span id={prefixId}>{t.customPrefix}</span>
            <Input
              className="h-8 w-20"
              inputMode="numeric"
              autoComplete="off"
              value={customText}
              aria-labelledby={customLabel}
              aria-invalid={model.customError || undefined}
              aria-describedby={model.customError ? errorId : undefined}
              onPointerDown={() => setMode("custom")}
              onChange={(event) => {
                setCustomText(event.target.value)
                setMode("custom")
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") void start()
                // ช่องอยู่ในกลุ่มตัวเลือก: ลูกศรซ้าย/ขวาขณะแก้เลขต้องเลื่อนเคอร์เซอร์ ไม่ใช่ย้ายไปเลือกตัวเลือกอื่น
                else if (event.key.startsWith("Arrow")) event.stopPropagation()
              }}
            />
            <span id={unitId}>{t.customUnit}</span>
            {model.customCount !== null && !(model.mode === "custom" && model.overflow) && (
              <span className="text-muted-foreground">{fill(t.customCount, { count: model.customCount })}</span>
            )}
          </div>
        </RadioGroup>
        {model.customError && <FieldError id={errorId}>{t.intervalError}</FieldError>}
        {/* ประโยคเกิน 200 ภาพแทนจำนวนภาพแบบสด (AC-FRAME-04) · แสดงอยู่ใน DOM เสมอ (ว่าง = sr-only ไม่กินที่) เพื่อให้โปรแกรมอ่านหน้าจออ่านเมื่อข้อความเปลี่ยน */}
        <p role="status" className={model.overflow ? undefined : "sr-only"}>
          {model.overflow && fill(t.overLimit, { N: model.overflow.n, count: model.overflow.count, N2: model.overflow.n2 })}
        </p>
        <ul className="flex flex-col gap-1 text-muted-foreground">
          <li>{model.sizeBytes === null ? t.sizeUnknown : fill(t.size, { size: formatBytes(model.sizeBytes) })}</li>
          <li>{resolutionText(model.resolution)}</li>
          {model.replace && <li>{t.replaceWarning}</li>}
        </ul>
        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>{t.cancel}</DialogClose>
          <Button disabled={model.params === null || pending} onClick={() => void start()}>
            {pending && <Spinner aria-hidden />}
            {t.start}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
