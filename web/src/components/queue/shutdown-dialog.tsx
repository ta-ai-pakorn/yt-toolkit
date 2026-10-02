import { useMutation } from "@tanstack/react-query"
import { Power } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogMedia,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Spinner } from "@/components/ui/spinner"
import { fill, th } from "@/i18n/th"
import { api } from "@/lib/api"
import { appShutdown } from "@/lib/events"

import { useQueueData } from "./use-queue"

type Props = {
  open: boolean
  /** "กลับไปก่อน" / Esc: ผู้เรียกปิดหน้าต่างเอง (AlertDialogAction ไม่ปิดให้) */
  onClose: () => void
  /** จำนวนงานค้างจากคำตอบ 409 ของ POST /shutdown · ไม่ส่ง = นับงานที่กำลังทำ + รอคิว จากแคช */
  pendingJobs?: number
  /** ปิดโปรแกรมสำเร็จ (หน้าเว็บเปลี่ยนเป็นหน้าปิดโปรแกรมแล้วผ่าน appShutdown ให้อยู่แล้ว) */
  onShutdown?: () => void
}

/**
 * ยืนยันปิดโปรแกรมทั้งที่ยังมีงานค้าง (W7): บอกจำนวนงาน · "กลับไปก่อน" · "ปิดเลย" = POST /shutdown {force: true}
 * งานที่ค้างจะหยุดกลางคัน และลองใหม่ได้เมื่อเปิดโปรแกรมครั้งหน้า
 */
export function ShutdownDialog({ open, onClose, pendingJobs, onShutdown }: Props) {
  const { jobs, jobsError } = useQueueData()
  const count = pendingJobs ?? (jobs ?? []).filter((job) => job.status === "running" || job.status === "queued").length
  // ยังไม่รู้จำนวนงาน = รอรายการงานก่อน จะได้ไม่ขึ้น "0 งาน" แวบหนึ่ง
  const ready = pendingJobs !== undefined || jobs !== undefined || jobsError
  // จำจำนวนล่าสุดตอนเปิดอยู่: ระหว่างหน้าต่างค่อย ๆ ปิด ผู้เรียกล้างค่าไปแล้ว ไม่ให้ข้อความกลายเป็น "0 งาน" แวบหนึ่ง
  const [shownCount, setShownCount] = useState(count)
  if (open && ready && count !== shownCount) setShownCount(count)

  const shutdown = useMutation({
    mutationFn: () => api<{ ok: boolean }>("/shutdown", { method: "POST", body: JSON.stringify({ force: true }) }),
    onSuccess: () => {
      toast.dismiss()
      onClose()
      onShutdown?.()
      appShutdown.set()
    },
    onError: (error) => toast.error(error.message),
  })

  return (
    <AlertDialog
      open={open && ready}
      onOpenChange={(next) => {
        if (!next && !shutdown.isPending) onClose()
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogMedia>
            <Power aria-hidden />
          </AlertDialogMedia>
          <AlertDialogTitle>{th.shutdown.confirmTitle}</AlertDialogTitle>
          <AlertDialogDescription>{fill(th.shutdown.confirmBody, { n: shownCount })}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={shutdown.isPending}>{th.shutdown.back}</AlertDialogCancel>
          <AlertDialogAction variant="destructive" disabled={shutdown.isPending} onClick={() => shutdown.mutate()}>
            {shutdown.isPending ? <Spinner /> : <Power aria-hidden />}
            {th.shutdown.force}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
