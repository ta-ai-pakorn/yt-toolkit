import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { toast } from "sonner"

import { th } from "@/i18n/th"
import { ACCOUNT_KEY, accountQuery, deleteAccount, INACTIVE } from "@/lib/account"
import type { AccountStatus } from "@/lib/types"

/** toast หลังลบบัญชี (ทุกเหตุผล ทุกแท็บ): ไม่หายเอง มีปุ่ม "ปิด" · id เดียว = ลบในแท็บนี้แล้วข่าว SSE ตามมาไม่เด้งซ้ำ */
export const REMOVED_TOAST_ID = "account-removed"

export function showRemovedToast(): void {
  toast.info(th.account.removed, {
    id: REMOVED_TOAST_ID,
    duration: Infinity,
    action: { label: th.common.close, onClick: () => undefined },
  })
}

/** สถานะบัญชีชั่วคราว (ยังโหลดไม่เสร็จหรือโหลดไม่ได้ = ถือว่าไม่ได้ใช้บัญชี) */
export function useAccountStatus(): AccountStatus {
  return useQuery(accountQuery()).data ?? INACTIVE
}

/** "ลบออกตอนนี้": ไม่ต้องยืนยัน (spec 1.3) · สำเร็จ = แคชเป็นไม่ได้ใช้บัญชี + toast · ไม่สำเร็จ = toast ทั่วไป */
export function useDeleteAccount(): { remove: () => void; pending: boolean } {
  const client = useQueryClient()
  const mutation = useMutation({
    mutationFn: () => deleteAccount(),
    onSuccess: (status) => {
      client.setQueryData<AccountStatus>(ACCOUNT_KEY, status)
      showRemovedToast()
    },
    onError: () => toast.error(th.queue.actionFailed),
  })
  return { remove: () => mutation.mutate(), pending: mutation.isPending }
}

/** เวลาปัจจุบันที่เดินทุก intervalMs เฉพาะตอน active (นับถอยหลังของแถบบนหน้าและแท็บขั้นสูง) */
export function useNow(active: boolean, intervalMs = 15_000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const timer = window.setInterval(() => setNow(Date.now()), intervalMs)
    return () => window.clearInterval(timer)
  }, [active, intervalMs])
  return now
}
