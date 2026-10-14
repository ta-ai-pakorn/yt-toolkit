import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Download, Eraser, Upload } from "lucide-react"
import { useRef, useState, type ChangeEvent } from "react"
import { toast } from "sonner"

import { showErrorToast } from "@/components/error-report/error-toast"
import { PLAIN_TOAST } from "@/components/error-report/model"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { FieldLegend, FieldSet } from "@/components/ui/field"
import { Spinner } from "@/components/ui/spinner"
import { fill, th } from "@/i18n/th"
import { formatBytes } from "@/lib/format"
import { reportRequest } from "@/lib/report"
import { clearStorage, exportSettings, importSettings, SETTINGS_KEY, storageQuery } from "@/lib/settings-api"
import type { Settings } from "@/lib/types"

import { serverMessage } from "./general-form"
import {
  CLEAR_TOAST_ID,
  clearButton,
  EXPORT_TOAST_ID,
  forgetClipCaches,
  IMPORT_TOAST_ID,
  importNotice,
  readImportFile,
} from "./local-data"

const t = th.general

/**
 * "ข้อมูลในเครื่อง" ในแท็บทั่วไป (M6 รอบ A spec 5, PRD :307): ล้างข้อมูลชั่วคราว · สำรองค่าตั้ง · นำเข้าค่าตั้ง
 * ขนาดเป็นข้อมูลรอง: โหลดไม่ได้ = ปุ่มไม่มีขนาดและกดไม่ได้ ไม่แจ้ง error (แบบเดียวกับ "ล่าสุด" ใน W1)
 */
export function LocalDataSection() {
  const queryClient = useQueryClient()
  const usage = useQuery(storageQuery())
  const button = clearButton(usage.isSuccess ? usage.data : undefined)
  const [confirmOpen, setConfirmOpen] = useState(false)
  // ขนาดบนหัวกล่องยืนยัน = ขนาดบนปุ่มตอนกด (ไม่เปลี่ยนกลางทางเมื่อขนาดโหลดใหม่)
  const [confirmSize, setConfirmSize] = useState("")
  const fileInput = useRef<HTMLInputElement>(null)

  const clear = useMutation({
    mutationFn: () => clearStorage(),
    onSuccess: ({ freedBytes }) => {
      setConfirmOpen(false)
      // ...PLAIN_TOAST: id เดียวกับ toast error ของการล้าง ไม่ให้ปุ่มคัดลอก/เวลาค้างติดมา (M6 รอบ B P5)
      toast.success(fill(t.cleared, { size: formatBytes(freedBytes) }), { ...PLAIN_TOAST, id: CLEAR_TOAST_ID })
      forgetClipCaches(queryClient)
    },
    onError: (error) => {
      setConfirmOpen(false)
      void queryClient.invalidateQueries({ queryKey: storageQuery().queryKey })
      showErrorToast(serverMessage(error), {
        id: CLEAR_TOAST_ID,
        request: reportRequest(error, { context: "storage-clear" }),
      })
    },
  })

  const exporting = useMutation({
    mutationFn: () => exportSettings(),
    // สำเร็จไม่มี toast: เบราว์เซอร์แสดงการดาวน์โหลดเอง
    onError: (error) =>
      showErrorToast(error.message, { id: EXPORT_TOAST_ID, request: reportRequest(error, { context: "settings-export" }) }),
  })

  const importing = useMutation({
    mutationFn: (text: string) => importSettings(text),
    onSuccess: (result) => {
      // ธีมและค่าเริ่มต้นของการโหลดเปลี่ยนตามทันที
      queryClient.setQueryData<Settings>(SETTINGS_KEY, result.settings)
      const notice = importNotice(result)
      if (notice.kind === "warning") {
        // ต้องอ่าน: ค้างจนกดปิด (แบบ toast หลังลบบัญชี) ไม่มีปุ่มคัดลอก เพราะไม่มีอะไรพลาด
        toast.warning(notice.message, {
          ...PLAIN_TOAST,
          id: IMPORT_TOAST_ID,
          duration: Infinity,
          action: { label: th.common.close, onClick: () => undefined },
        })
      } else {
        toast.success(notice.message, { ...PLAIN_TOAST, id: IMPORT_TOAST_ID })
      }
    },
    onError: (error) =>
      showErrorToast(serverMessage(error), {
        id: IMPORT_TOAST_ID,
        request: reportRequest(error, { context: "settings-import" }),
      }),
  })

  async function onFile(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget
    const file = input.files?.[0]
    input.value = "" // เลือกไฟล์เดิมซ้ำได้
    if (!file) return
    const read = await readImportFile(file)
    if (!read.ok) {
      showErrorToast(t.settingsInvalid, { id: IMPORT_TOAST_ID, request: read.request })
      return
    }
    importing.mutate(read.text)
  }

  return (
    <FieldSet>
      <FieldLegend>{t.localData}</FieldLegend>
      <div className="flex flex-wrap gap-2" data-testid="local-data-actions">
        <Button
          type="button"
          variant="secondary"
          disabled={button.disabled || clear.isPending}
          onClick={() => {
            setConfirmSize(button.size ?? "")
            setConfirmOpen(true)
          }}
        >
          <Eraser data-icon="inline-start" aria-hidden />
          {button.label}
        </Button>
        <Button type="button" variant="secondary" disabled={exporting.isPending} onClick={() => exporting.mutate()}>
          {exporting.isPending ? <Spinner data-icon="inline-start" /> : <Download data-icon="inline-start" aria-hidden />}
          {t.backup}
        </Button>
        <Button
          type="button"
          variant="secondary"
          disabled={importing.isPending}
          onClick={() => fileInput.current?.click()}
        >
          {importing.isPending ? <Spinner data-icon="inline-start" /> : <Upload data-icon="inline-start" aria-hidden />}
          {t.import}
        </Button>
        <input
          ref={fileInput}
          type="file"
          accept=".json,application/json"
          className="hidden"
          tabIndex={-1}
          aria-hidden
          onChange={(event) => void onFile(event)}
        />
      </div>
      <AlertDialog
        open={confirmOpen}
        onOpenChange={(next) => {
          if (!next && !clear.isPending) setConfirmOpen(false)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{fill(t.clearConfirmTitle, { size: confirmSize })}</AlertDialogTitle>
            <AlertDialogDescription>{t.clearConfirmBody}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={clear.isPending}>{t.clearCancel}</AlertDialogCancel>
            <AlertDialogAction disabled={clear.isPending} onClick={() => clear.mutate()}>
              {clear.isPending && <Spinner />}
              {t.clearConfirm}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </FieldSet>
  )
}
