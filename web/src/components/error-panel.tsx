import { CircleX } from "lucide-react"

import {
  Alert,
  AlertAction,
  AlertDescription,
  AlertTitle,
} from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { th } from "@/i18n/th"
import { isChunkLoadError } from "@/lib/lazy-import"

// หน้าแทนเมื่อเปิดหน้าไม่สำเร็จ: ไฟล์โค้ดของหน้าหายหลังอัปเดตโปรแกรม (แท็บเก่า) หรือโค้ดหน้านั้นพัง
export function ErrorPanel({ error }: { error: unknown }) {
  return (
    <div className="pt-8">
      <Alert variant="destructive">
        <CircleX aria-hidden />
        <AlertTitle>{th.errors.pageTitle}</AlertTitle>
        <AlertDescription>
          {isChunkLoadError(error) ? th.errors.chunk : th.errors.crash}
        </AlertDescription>
        <AlertAction>
          <Button variant="outline" size="sm" onClick={() => location.reload()}>
            {th.common.reload}
          </Button>
        </AlertAction>
      </Alert>
    </div>
  )
}
