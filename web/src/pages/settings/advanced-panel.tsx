import { useQuery } from "@tanstack/react-query"
import { CircleX, UserRound } from "lucide-react"

import { UseAccountButton } from "@/components/account/account-button"
import { useDeleteAccount, useNow } from "@/components/account/use-account"
import { ErrorDetails } from "@/components/error-report/error-details"
import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { fill, th } from "@/i18n/th"
import { accountQuery, deleteTime } from "@/lib/account"
import { ApiError } from "@/lib/api"

const t = th.account

/**
 * แท็บ "ขั้นสูง" (W6 /settings/advanced · M5 รอบ C spec 1.1): คำอธิบายสั้น · สถานะบัญชีชั่วคราว · ปุ่ม "ใช้บัญชียูทูปชั่วคราว"
 * (dialog ตัวกลาง ปุ่มนำเข้าเป็น "นำเข้า") · ถือบัญชีอยู่ = ปุ่มรอง "ลบออกตอนนี้" · ไม่มี Switch ไม่มีตัวเลือกแหล่งคุกกี้
 */
export function AdvancedPanel() {
  const account = useQuery(accountQuery())
  const now = useNow(account.data?.active === true)
  const remove = useDeleteAccount()

  if (account.isPending) {
    return (
      <div className="flex max-w-xl flex-col gap-4" aria-busy="true">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-14 w-full" />
        <Skeleton className="h-9 w-56" />
      </div>
    )
  }

  if (account.isError) {
    return (
      <Alert variant="destructive">
        <CircleX aria-hidden />
        <AlertTitle>{th.general.loadError}</AlertTitle>
        <AlertDescription>{account.error instanceof ApiError ? account.error.message : th.errors.unknown}</AlertDescription>
        <ErrorDetails key={account.errorUpdatedAt} error={account.error} context="settings-advanced" className="col-start-2" />
        <AlertAction>
          <Button variant="outline" size="sm" onClick={() => void account.refetch()}>
            {th.common.retry}
          </Button>
        </AlertAction>
      </Alert>
    )
  }

  const { active, expiresAt, importedAt } = account.data
  const held = active && expiresAt !== undefined
  return (
    <div className="flex max-w-xl flex-col gap-4">
      <p>{t.intro}</p>
      <div data-testid="account-status" className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border p-3">
        <UserRound aria-hidden className="size-4 shrink-0 text-muted-foreground" />
        <p className="min-w-0 flex-1">
          {held ? fill(t.statusOn, { time: deleteTime({ expiresAt, importedAt }, now) }) : t.statusOff}
        </p>
        {held && (
          <Button variant="outline" size="sm" disabled={remove.pending} onClick={remove.remove}>
            {t.removeNow}
          </Button>
        )}
      </div>
      <div>
        <UseAccountButton origin="settings" variant="default" size="default" />
      </div>
    </div>
  )
}
