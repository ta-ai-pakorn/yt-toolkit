import { ChevronDown } from "lucide-react"
import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { fill, th } from "@/i18n/th"
import { cn } from "cn"

import { CopyReportButton } from "./copy-report-button"
import { detailsOpenByDefault, detailsRequest, type DetailsSource } from "./model"

type Props = DetailsSource & {
  /** กางตั้งแต่แรกไหม (ไม่ส่ง = กางเมื่อรหัสเป็น E_UNKNOWN) */
  defaultOpen?: boolean
  /** คุมจากข้างนอก (แถวงานในคิว: ปุ่ม "ดูรายละเอียด" ใน toast สั่งกาง) */
  open?: boolean
  onOpenChange?: (open: boolean) => void
  /** ใน Alert ที่มีไอคอน ส่ง "col-start-2" ให้ตรงกับข้อความ */
  className?: string
}

/**
 * ส่วนพับ "ดูรายละเอียด" ของ error ทุกจุด (PRD 7.1 ชั้นหน้าเว็บ · spec 1.1): รหัส · ข้อความเทคนิคดิบ · "คัดลอกข้อมูลแจ้งปัญหา"
 * หน้าตาเดียวกับแถวงานที่พลาดในคิวเดิม · <pre> ตัดคำได้ทุกตัว หน้าต่าง 640 px ไม่เลื่อนซ้ายขวา
 */
export function ErrorDetails(props: Props) {
  const { defaultOpen, open, onOpenChange, className } = props
  const request = detailsRequest(props)
  const code = request.code ?? "E_UNKNOWN"
  const [ownOpen, setOwnOpen] = useState(() => detailsOpenByDefault(code, defaultOpen))
  return (
    <Collapsible
      data-testid="error-details"
      className={cn("min-w-0", className)}
      open={open ?? ownOpen}
      onOpenChange={(next) => {
        setOwnOpen(next)
        onOpenChange?.(next)
      }}
    >
      <CollapsibleTrigger
        data-details-trigger=""
        render={<Button variant="link" size="sm" className="group/details h-7 px-0 text-muted-foreground" />}
      >
        {th.errors.details}
        <ChevronDown aria-hidden className="transition-transform group-data-[panel-open]/details:rotate-180" />
      </CollapsibleTrigger>
      <CollapsibleContent className="flex flex-col items-start gap-2 pt-1 text-foreground">
        <p className="font-mono text-xs">{fill(th.errors.code, { code })}</p>
        {request.detail && (
          <pre className="max-h-40 w-full overflow-auto rounded-md bg-muted p-2 font-mono text-xs break-all whitespace-pre-wrap">
            {request.detail}
          </pre>
        )}
        <CopyReportButton request={request} />
      </CollapsibleContent>
    </Collapsible>
  )
}
