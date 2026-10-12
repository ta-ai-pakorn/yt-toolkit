import { CircleX } from "lucide-react"

import { CopyReportButton } from "@/components/error-report/copy-report-button"
import {
  Alert,
  AlertAction,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { th } from "@/i18n/th"
import { isChunkLoadError } from "@/lib/lazy-import"
import { reportRequest } from "@/lib/report"

// หน้าแทนเมื่อเปิดหน้าไม่สำเร็จ: ไฟล์โค้ดของหน้าหายหลังอัปเดตโปรแกรม (แท็บเก่า) หรือโค้ดหน้านั้นพัง
// M6 รอบ B: ปุ่ม "คัดลอกข้อมูลแจ้งปัญหา" ก่อนปุ่มโหลดหน้าใหม่ (E_UNKNOWN + ชื่อ: ข้อความ + stack) ยังใช้ได้หลังหน้าพัง
// เพราะใช้แค่ api() กับ <meta> ของ token · ปุ่มสองปุ่มเรียงเป็นแถวใต้ข้อความ (หน้าต่าง 640 px ไม่ทับหัวข้อ)
export function ErrorPanel({ error }: { error: unknown }) {
  const chunk = isChunkLoadError(error)
  return (
    <div className="pt-8">
      <Alert variant="destructive">
        <CircleX aria-hidden />
        <AlertTitle>{th.errors.pageTitle}</AlertTitle>
        <AlertDescription>
          {chunk ? th.errors.chunk : th.errors.crash}
        </AlertDescription>
        <AlertAction className="static col-start-2 mt-2 flex flex-wrap gap-2">
          <CopyReportButton request={reportRequest(error, { context: chunk ? "chunk" : "crash" })} />
          <Button variant="outline" size="sm" onClick={() => location.reload()}>
            {th.common.reload}
          </Button>
        </AlertAction>
      </Alert>
    </div>
  )
}
