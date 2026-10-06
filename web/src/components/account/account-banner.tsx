import { UserRound } from "lucide-react"

import { Button } from "@/components/ui/button"
import { th } from "@/i18n/th"
import { deleteTime } from "@/lib/account"

import { useAccountStatus, useDeleteAccount, useNow } from "./use-account"

/**
 * แถบบาง ๆ ใต้เมนูบนทุกหน้าเมื่อถือบัญชีชั่วคราวอยู่ (spec 1.3): "กำลังใช้บัญชียูทูปชั่วคราว · ลบอัตโนมัติภายใน 1 ชม. 59 นาที"
 * + ปุ่มแบบลิงก์ "ลบออกตอนนี้" (ไม่ต้องยืนยัน) · ตามสถานะของเซิร์ฟเวอร์ผ่าน SSE (ลบเอง = แถบหายในทุกแท็บ)
 * เวลาเป็นคำ ("2 ชม.") มาจาก deleteTime · ตัวเลขนับถอยหลังไม่ถูกอ่านซ้ำทุกครั้งที่เปลี่ยน (aria-live off)
 */
export function AccountBanner() {
  const status = useAccountStatus()
  const now = useNow(status.active)
  const remove = useDeleteAccount()
  if (!status.active || status.expiresAt === undefined) return null
  const [before, after] = th.account.banner.split("{time}")
  return (
    <div data-testid="account-banner" className="border-y border-primary/30 bg-primary/10">
      <div className="mx-auto flex max-w-[960px] flex-wrap items-center gap-x-3 gap-y-1 px-4 py-1 text-sm">
        <UserRound aria-hidden className="size-4 shrink-0 text-accent-text" />
        <p className="min-w-0 flex-1">
          {before}
          <span aria-live="off" className="tabular-nums">
            {deleteTime({ expiresAt: status.expiresAt, importedAt: status.importedAt }, now)}
          </span>
          {after}
        </p>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 shrink-0 px-1.5 underline underline-offset-4"
          disabled={remove.pending}
          onClick={remove.remove}
        >
          {th.account.removeNow}
        </Button>
      </div>
    </div>
  )
}
