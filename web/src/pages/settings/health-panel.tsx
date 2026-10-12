import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { CircleAlert, CircleCheck, CircleX, FlaskConical, Power, RefreshCw } from "lucide-react"
import { toast } from "sonner"

import { CopyReportButton } from "@/components/error-report/copy-report-button"
import { ErrorDetails } from "@/components/error-report/error-details"
import { showErrorToast } from "@/components/error-report/error-toast"
import { PLAIN_TOAST } from "@/components/error-report/model"
import { ShutdownDialog } from "@/components/queue/shutdown-dialog"
import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Item, ItemActions, ItemContent, ItemDescription, ItemGroup, ItemMedia, ItemTitle } from "@/components/ui/item"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import { fill, th } from "@/i18n/th"
import { localClock } from "@/lib/account"
import { ApiError, api } from "@/lib/api"
import { appShutdown } from "@/lib/events"
import { reportRequest } from "@/lib/report"
import type { AccountHealth, Health, ToolState, ToolStatus } from "@/lib/types"

import { useHealth } from "./use-health"

type RowKey = keyof typeof th.health.rows

const ICON: Record<ToolState, typeof CircleCheck> = { ok: CircleCheck, warn: CircleAlert, error: CircleX }
const TONE: Record<ToolState, string> = { ok: "text-success", warn: "text-warning", error: "text-destructive" }

function rows(health: Health): [RowKey, ToolStatus][] {
  const list: [RowKey, ToolStatus][] = [
    ["ffmpeg", health.tools.ffmpeg],
    ["ytdlp", health.tools.ytdlp],
    ["jsRuntime", health.tools.jsRuntime],
  ]
  if (health.tools.impersonation) list.push(["impersonation", health.tools.impersonation])
  list.push(["disk", health.disk], ["output", health.output], ["network", health.network])
  return list
}

function detail(key: RowKey, tool: ToolStatus): string {
  const parts = [
    key === "jsRuntime" ? tool.name : null,
    tool.version,
    tool.message,
    key === "output" ? tool.path : null,
  ]
  return parts.filter(Boolean).join(" · ")
}

/** แถว "บัญชียูทูป" (M5 รอบ C spec 1.4): สถานะอย่างเดียว พร้อมเสมอ ไม่ต่อเน็ต */
function AccountRow({ account }: { account: AccountHealth }) {
  const text =
    account.active && account.importedAt !== null
      ? fill(th.account.healthOn, { time: localClock(account.importedAt) })
      : th.account.statusOff
  return (
    <Item variant="outline" data-testid="tool-account">
      <ItemMedia>
        <CircleCheck aria-hidden className={TONE.ok} />
      </ItemMedia>
      <ItemContent>
        <ItemTitle>{th.health.rows.account}</ItemTitle>
        <ItemDescription>{text}</ItemDescription>
      </ItemContent>
      <ItemActions>
        <Badge variant="outline">{th.health.status.ok}</Badge>
      </ItemActions>
    </Item>
  )
}

export function HealthPanel({ onShutdown }: { onShutdown: () => void }) {
  const queryClient = useQueryClient()
  const health = useHealth()
  // มีงานค้าง (409) = ถามยืนยันก่อน พร้อมจำนวนงานจาก backend
  const [pendingJobs, setPendingJobs] = useState<number | null>(null)

  const install = useMutation({
    mutationFn: () => api<ToolStatus>("/tools/ffmpeg/install", { method: "POST" }),
    // ...PLAIN_TOAST: id "ffmpeg" เดียวกับ toast error ของการติดตั้งครั้งก่อน ไม่ให้ปุ่มคัดลอก/เวลาค้างติดมา (P5)
    onMutate: () => toast.loading(th.health.installing, { ...PLAIN_TOAST, id: "ffmpeg" }),
    onSuccess: (status) => {
      // backend ตอบ 200 ทั้งที่ติดตั้งไม่สำเร็จได้ ดูสถานะจริงก่อนบอกว่าสำเร็จ
      // warn = มีการโหลดค้างอยู่แล้ว เป็นแค่ข้อมูล ไม่ใช่ข้อผิดพลาด จึงไม่ต้องค้างบนจอ
      if (status.status === "ok") toast.success(th.health.installed, { ...PLAIN_TOAST, id: "ffmpeg" })
      else if (status.status === "warn") toast.info(status.message ?? th.health.installing, { ...PLAIN_TOAST, id: "ffmpeg" })
      else {
        // ไม่มี ApiError (ตอบ 200 แต่ status error): ใช้รหัสของ PRD ข้อ 7 สำหรับกรณีนี้ (spec 1.3)
        showErrorToast(status.message ?? th.errors.unknown, {
          id: "ffmpeg",
          request: { code: "E_TOOL_INSTALL_FAILED", detail: status.message ?? undefined, context: "ffmpeg-install" },
        })
      }
      void queryClient.invalidateQueries({ queryKey: ["health"] })
    },
    onError: (error) =>
      showErrorToast(error.message, { id: "ffmpeg", request: reportRequest(error, { context: "ffmpeg-install" }) }),
  })

  const shutdown = useMutation({
    mutationFn: () => api<{ ok: boolean }>("/shutdown", { method: "POST", body: JSON.stringify({ force: false }) }),
    onSuccess: () => {
      toast.dismiss()
      onShutdown()
      appShutdown.set()
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) {
        setPendingJobs((error.body as { pendingJobs?: number } | null)?.pendingJobs ?? 0)
        return
      }
      showErrorToast(error.message, { id: "shutdown-error", request: reportRequest(error, { context: "shutdown" }) })
    },
  })

  if (health.isPending) {
    return (
      <div className="flex flex-col gap-2" aria-busy="true">
        {Array.from({ length: 7 }, (_, i) => (
          <Skeleton key={i} className="h-14 w-full" />
        ))}
      </div>
    )
  }

  if (health.isError) {
    return (
      <Alert variant="destructive">
        <CircleX aria-hidden />
        <AlertTitle>{th.health.loadError}</AlertTitle>
        <AlertDescription>{health.error.message}</AlertDescription>
        <ErrorDetails key={health.errorUpdatedAt} error={health.error} context="health-load" className="col-start-2" />
        <AlertAction>
          <Button variant="outline" size="sm" onClick={() => void health.refetch()}>
            {th.health.retry}
          </Button>
        </AlertAction>
      </Alert>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      {health.data.mode === "fake" && (
        <Alert role="status" data-testid="fake-mode">
          <FlaskConical aria-hidden />
          <AlertTitle>{th.health.fakeMode.title}</AlertTitle>
          <AlertDescription>{th.health.fakeMode.description}</AlertDescription>
        </Alert>
      )}
      <ItemGroup className="gap-2">
        {rows(health.data).map(([key, tool]) => {
          const Icon = ICON[tool.status]
          const text = detail(key, tool)
          return (
            <Item key={key} variant="outline" data-testid={`tool-${key}`}>
              <ItemMedia>
                <Icon aria-hidden className={TONE[tool.status]} />
              </ItemMedia>
              <ItemContent>
                <ItemTitle>{th.health.rows[key]}</ItemTitle>
                {text && <ItemDescription className="font-mono text-xs">{text}</ItemDescription>}
              </ItemContent>
              <ItemActions>
                {key === "ffmpeg" && tool.status === "error" && (
                  <Button variant="outline" size="sm" disabled={install.isPending} onClick={() => install.mutate()}>
                    {install.isPending ? <Spinner /> : null}
                    {th.health.reinstallFfmpeg}
                  </Button>
                )}
                <Badge variant={tool.status === "error" ? "destructive" : "outline"}>{th.health.status[tool.status]}</Badge>
              </ItemActions>
            </Item>
          )
        })}
        {health.data.account && <AccountRow account={health.data.account} />}
      </ItemGroup>
      <div data-testid="health-actions" className="flex flex-wrap justify-end gap-2">
        <Button variant="outline" onClick={() => void health.refetch()} disabled={health.isFetching}>
          <RefreshCw aria-hidden />
          {th.health.recheck}
        </Button>
        {/* M6 รอบ B (D4): รายงานของหน้าตรวจสุขภาพไม่มีหัวข้อ error · ถัดจาก "ตรวจอีกครั้ง" ก่อน "ปิดโปรแกรม" */}
        <CopyReportButton request={{ context: "health" }} size="default" />
        <Button variant="outline" onClick={() => shutdown.mutate()} disabled={shutdown.isPending}>
          {shutdown.isPending ? <Spinner /> : <Power aria-hidden />}
          {th.health.shutdown}
        </Button>
      </div>
      <ShutdownDialog
        open={pendingJobs !== null}
        pendingJobs={pendingJobs ?? 0}
        onClose={() => setPendingJobs(null)}
        onShutdown={onShutdown}
      />
    </div>
  )
}
