import { useQueryClient } from "@tanstack/react-query"
import { TriangleAlert } from "lucide-react"
import { useId, useReducer, useRef } from "react"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Dialog, DialogClose, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Field, FieldError, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { th } from "@/i18n/th"
import { ACCOUNT_KEY, importAccount } from "@/lib/account"
import { ApiError } from "@/lib/api"
import type { AccountStatus } from "@/lib/types"

import { accountDialog, useAccountDialog } from "./account-store"
import { canImport, dialogReducer, EMPTY_DIALOG, importLabel, pickAction } from "./dialog-model"

const t = th.account

/**
 * dialog "ใช้บัญชียูทูปชั่วคราว" (spec 1.2) ตัวเดียวทั้งแอพ: คำเตือน (สีอันตราย) · คลิปส่วนตัว · ขั้นตอนส่งออก · ช่องเลือกไฟล์
 * ยกเลิก / Esc / ปิด = ไม่ส่งอะไร · ไฟล์เกิน 1 MB หรือ backend ไม่รับ = ข้อความใต้ช่อง dialog ยังเปิด
 * สำเร็จ = ปิด dialog แคชสถานะเป็นใช้บัญชีอยู่ (แถบบนหน้าขึ้นทันที) แล้วทำสิ่งที่ผู้เปิดขอไว้ (onImported)
 * กำลังนำเข้า = ปิดไม่ได้ (Esc / พื้นหลัง / ยกเลิก) ผลที่มาช้าจึงไม่ทำต่อหลังผู้ใช้ปิดไปแล้ว · เลือกไฟล์ซ้อนกัน = ใช้อันล่าสุด
 * ช่องเลือกไฟล์มีป้าย "เลือกไฟล์ cookies.txt" ที่มองเห็น (label + htmlFor) เป็นชื่อของช่อง (ข้อความ error ผูกด้วย aria-describedby)
 */
export function AccountDialog() {
  const { open, request } = useAccountDialog()
  const client = useQueryClient()
  const [state, dispatch] = useReducer(dialogReducer, EMPTY_DIALOG)
  const inputId = useId()
  const errorId = useId()
  const latestPick = useRef(0)

  const close = () => {
    latestPick.current += 1
    accountDialog.close()
    dispatch({ type: "reset" })
  }

  async function pick(file: File | undefined) {
    const mine = ++latestPick.current
    const action = await pickAction(file)
    if (mine === latestPick.current) dispatch(action)
  }

  async function submit() {
    if (!canImport(state) || state.text === null) return
    dispatch({ type: "submitting" })
    try {
      const status = await importAccount(state.text)
      client.setQueryData<AccountStatus>(ACCOUNT_KEY, status)
      const then = request?.onImported
      close()
      then?.()
    } catch (error) {
      dispatch({ type: "failed", message: error instanceof ApiError ? error.message : th.errors.unknown })
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (next || state.pending ? undefined : close())}>
      <DialogContent data-testid="account-dialog" className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t.title}</DialogTitle>
        </DialogHeader>
        <Alert variant="destructive">
          <TriangleAlert aria-hidden />
          <AlertDescription>{t.warning}</AlertDescription>
        </Alert>
        <p>{t.privateClips}</p>
        <ol className="flex list-decimal flex-col gap-1 pl-5">
          {t.steps.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
        <Field data-invalid={state.error !== null || undefined}>
          <FieldLabel htmlFor={inputId}>{t.fileLabel}</FieldLabel>
          <Input
            id={inputId}
            type="file"
            accept=".txt,text/plain"
            aria-invalid={state.error !== null || undefined}
            aria-describedby={state.error !== null ? errorId : undefined}
            disabled={state.pending}
            onChange={(event) => void pick(event.target.files?.[0])}
          />
          {state.error !== null && <FieldError id={errorId}>{state.error}</FieldError>}
        </Field>
        <DialogFooter>
          <DialogClose render={<Button variant="outline" disabled={state.pending} />}>{t.cancel}</DialogClose>
          <Button disabled={!canImport(state)} onClick={() => void submit()}>
            {state.pending && <Spinner aria-hidden />}
            {importLabel(request)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
