import { CircleX } from "lucide-react"
import { Link } from "react-router"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button, buttonVariants } from "@/components/ui/button"
import { th } from "@/i18n/th"

import { canRetry, errorMessage } from "./errors"

type Props = {
  title: string
  error: unknown
  onRetry: () => void
  /** ลิงก์ "กลับหน้าแรก" ใช้เฉพาะ error ของทั้งหน้า (หัวคลิป) ไม่ใช้กับส่วนย่อย */
  showHome?: boolean
}

/** กล่อง error ของหน้า W2: ข้อความไทยจาก envelope + ปุ่มลองใหม่ (ซ่อนเมื่อลองใหม่ไม่ช่วย) */
export function LoadError({ title, error, onRetry, showHome = false }: Props) {
  const retry = canRetry(error)
  return (
    <Alert variant="destructive">
      <CircleX aria-hidden />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>{errorMessage(error, th.errors.unknown)}</AlertDescription>
      {(retry || showHome) && (
        <div className="col-start-2 mt-2 flex flex-wrap gap-2">
          {retry && (
            <Button variant="outline" size="sm" onClick={onRetry}>
              {th.common.retry}
            </Button>
          )}
          {showHome && (
            <Link to="/" className={buttonVariants({ variant: "outline", size: "sm" })}>
              {th.common.backHome}
            </Link>
          )}
        </div>
      )}
    </Alert>
  )
}
