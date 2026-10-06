import { UserRound } from "lucide-react"

import { Button } from "@/components/ui/button"
import { th } from "@/i18n/th"

import { openAccountDialog, type AccountDialogRequest } from "./account-store"

type Props = {
  /** หลังนำเข้าสำเร็จ (ลองสิ่งที่เพิ่งพลาดใหม่) · ไม่มี = เปิดจากหน้าตั้งค่า */
  onImported?: () => void
  origin?: AccountDialogRequest["origin"]
  variant?: "default" | "outline"
  size?: "sm" | "default"
  className?: string
}

/** ปุ่ม "ใช้บัญชียูทูปชั่วคราว" (spec 1.1): เปิด dialog ตัวกลาง ผู้วางปุ่มตัดสินเองว่าควรแสดงไหม (showAccountButton) */
export function UseAccountButton({ onImported, origin = "error", variant = "outline", size = "sm", className }: Props) {
  return (
    <Button variant={variant} size={size} className={className} onClick={() => openAccountDialog({ origin, onImported })}>
      <UserRound aria-hidden />
      {th.account.use}
    </Button>
  )
}
