import { TriangleAlert } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { th } from "@/i18n/th"

const t = th.subs

type Props = {
  /** เปลี่ยนไปใช้แทร็กเริ่มต้นของคลิป null = คลิปไม่มีแทร็กเริ่มต้น (ไม่มีปุ่ม) */
  onUseOriginal: (() => void) | null
}

/**
 * ยูทูปไม่ให้โหลดซับแปลอัตโนมัติ (E_TRANSLATION_BLOCKED) ใช้ทั้งแท็บซับและทรานสคริปต์
 * ลองใหม่ไม่ช่วย (ได้ 429 เหมือนเดิม) จึงไม่มีปุ่มลองใหม่ มีแต่ปุ่มพาไปซับภาษาต้นฉบับ (แทร็กเริ่มต้นของคลิป)
 */
export function TranslationBlocked({ onUseOriginal }: Props) {
  return (
    <Alert>
      <TriangleAlert aria-hidden />
      <AlertTitle>{t.loadError}</AlertTitle>
      <AlertDescription>{t.translationBlocked}</AlertDescription>
      {onUseOriginal && (
        <div className="col-start-2 mt-2">
          <Button variant="secondary" size="sm" className="max-sm:h-11" onClick={onUseOriginal}>
            {t.useOriginal}
          </Button>
        </div>
      )}
    </Alert>
  )
}
