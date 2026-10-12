import { toast } from "sonner"

import { CopyReportButton } from "./copy-report-button"
import { errorToastSettings, type ErrorToastOptions } from "./model"

/**
 * toast ของ error ทุกตัว (D1): ค้างจนกดปิด · ปุ่ม "คัดลอกข้อมูลแจ้งปัญหา" อยู่ในแถว description ไม่ใช่ช่อง action ของ sonner
 * (sonner ปิด toast เมื่อกด action แต่ toast ต้องอยู่ต่อให้กด "ดูรายละเอียด" / ปุ่มบัญชีได้ และ action/cancel มีเจ้าของแล้ว)
 * ส่ง id คงที่ของแหล่ง error เสมอ: error ครั้งใหม่จากที่เดิมแทนที่ toast เดิม ไม่ซ้อนเป็นกอง
 */
export function showErrorToast(message: string, opts: ErrorToastOptions): string | number {
  return toast.error(message, {
    ...errorToastSettings(opts),
    description: (
      <div className="mt-1 flex flex-col items-start gap-2">
        {opts.description}
        <CopyReportButton request={opts.request} />
      </div>
    ),
  })
}
