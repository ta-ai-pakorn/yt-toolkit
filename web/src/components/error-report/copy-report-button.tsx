import { Copy } from "lucide-react"
import { useRef, useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import { th } from "@/i18n/th"
import { copyReport, type ReportRequest } from "@/lib/report"

import { REPORT_TOAST_ID } from "./model"

type Props = {
  request: ReportRequest
  variant?: "outline" | "default"
  size?: "sm" | "default"
  className?: string
}

/**
 * ปุ่ม "คัดลอกข้อมูลแจ้งปัญหา" (PRD 7.1): ขอรายงานจากเซิร์ฟเวอร์แล้วคัดลอก → toast "คัดลอกแล้ว"
 * ระหว่างรอ = ปิดปุ่ม + วงหมุน (กดสองครั้งส่งคำขอเดียว) · ใช้แค่ useState/useRef กับ api() ไม่มี React Query
 * ไม่มี store ไม่มี router จึงยังใช้ได้ใน ErrorPanel หลังหน้าพัง · ความล้มเหลวของปุ่มนี้ไม่มีปุ่มรายงานซ้อน
 */
export function CopyReportButton({ request, variant = "outline", size = "sm", className }: Props) {
  const [pending, setPending] = useState(false)
  const busy = useRef(false)

  function onClick() {
    if (busy.current) return
    busy.current = true
    setPending(true)
    // เรียกทันทีในจังหวะที่กด (ไม่มี await ก่อนหน้า): ClipboardItem ยังนับเป็นการกระทำของผู้ใช้
    void copyReport(request).then((outcome) => {
      busy.current = false
      setPending(false)
      if (outcome.ok) toast.success(th.errors.copied, { id: REPORT_TOAST_ID })
      else toast.error(outcome.message, { id: REPORT_TOAST_ID })
    })
  }

  return (
    // aria-disabled แทน disabled: ปุ่มที่ disabled ตอนโฟกัสอยู่ทำให้โฟกัสคีย์บอร์ดหลุดไป <body> (Chromium)
    // การกดซ้ำถูกกันด้วย busy · วงหมุนซ่อนจาก a11y (role="status" ไม่ซ้อนในชื่อปุ่ม) สถานะรอบอกด้วย aria-busy แทน
    <Button
      type="button"
      variant={variant}
      size={size}
      className={className}
      aria-disabled={pending || undefined}
      aria-busy={pending || undefined}
      onClick={onClick}
    >
      {pending ? <Spinner aria-hidden role={undefined} aria-label={undefined} /> : <Copy aria-hidden />}
      {th.errors.copyReport}
    </Button>
  )
}
