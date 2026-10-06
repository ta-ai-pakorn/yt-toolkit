import { CircleX } from "lucide-react"
import type { Ref } from "react"
import { Link } from "react-router"

import { UseAccountButton } from "@/components/account/account-button"
import { useAccountStatus } from "@/components/account/use-account"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button, buttonVariants } from "@/components/ui/button"
import { th } from "@/i18n/th"
import { showAccountButton } from "@/lib/account"
import { ApiError } from "@/lib/api"

import { errorMessage, showRetry } from "./errors"

type Props = {
  title: string
  error: unknown
  onRetry: () => void
  /** ลิงก์ "กลับหน้าแรก" ใช้เฉพาะ error ของทั้งหน้า (หัวคลิป) ไม่ใช้กับส่วนย่อย */
  showHome?: boolean
  /** ให้กล่องรับโฟกัสจากโค้ดได้ (tabIndex -1) ใช้กับ error ของทั้งหน้าที่ไม่มีชื่อคลิปให้โฟกัส */
  ref?: Ref<HTMLDivElement>
  /** M5 รอบ C: error จำกัดอายุ/ส่วนตัว + ยังไม่ได้ใช้บัญชี = ปุ่มหลัก "ใช้บัญชียูทูปชั่วคราว" แล้วทำ onImported หลังนำเข้า */
  account?: { onImported: () => void }
}

/** กล่อง error ของหน้า W2: ข้อความไทยจาก envelope + ปุ่มลองใหม่ (ซ่อนเมื่อลองใหม่ไม่ช่วย) */
export function LoadError({ title, error, onRetry, showHome = false, ref, account }: Props) {
  const { active } = useAccountStatus()
  const retry = showRetry(error, account !== undefined, active)
  const offerAccount = account !== undefined && showAccountButton(error instanceof ApiError ? error.code : null, active)
  return (
    <Alert ref={ref} tabIndex={ref ? -1 : undefined} variant="destructive" className="outline-none">
      <CircleX aria-hidden />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>{errorMessage(error, th.errors.unknown)}</AlertDescription>
      {(retry || showHome || offerAccount) && (
        <div className="col-start-2 mt-2 flex flex-wrap gap-2">
          {offerAccount && <UseAccountButton variant="default" onImported={account.onImported} />}
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
