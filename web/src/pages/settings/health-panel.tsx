import { useMutation, useQueryClient } from "@tanstack/react-query"
import { CircleAlert, CircleCheck, CircleX, Power, RefreshCw } from "lucide-react"
import { toast } from "sonner"

import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Item, ItemActions, ItemContent, ItemDescription, ItemGroup, ItemMedia, ItemTitle } from "@/components/ui/item"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import { fill, th } from "@/i18n/th"
import { ApiError, api } from "@/lib/api"
import type { Health, ToolState, ToolStatus } from "@/lib/types"

import { useHealth } from "./use-health"

type RowKey = keyof typeof th.health.rows

const ICON: Record<ToolState, typeof CircleCheck> = { ok: CircleCheck, warn: CircleAlert, error: CircleX }
const TONE: Record<ToolState, string> = { ok: "text-success", warn: "text-warning", error: "text-destructive" }

function rows(health: Health): [RowKey, ToolStatus][] {
  return [
    ["ffmpeg", health.tools.ffmpeg],
    ["ytdlp", health.tools.ytdlp],
    ["jsRuntime", health.tools.jsRuntime],
    ["disk", health.disk],
    ["output", health.output],
    ["network", health.network],
  ]
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

export function HealthPanel({ onShutdown }: { onShutdown: () => void }) {
  const queryClient = useQueryClient()
  const health = useHealth()

  const install = useMutation({
    mutationFn: () => api<ToolStatus>("/tools/ffmpeg/install", { method: "POST" }),
    onMutate: () => toast.loading(th.health.installing, { id: "ffmpeg" }),
    onSuccess: (status) => {
      // backend ตอบ 200 ทั้งที่ติดตั้งไม่สำเร็จได้ ดูสถานะจริงก่อนบอกว่าสำเร็จ
      // warn = มีการโหลดค้างอยู่แล้ว เป็นแค่ข้อมูล ไม่ใช่ข้อผิดพลาด จึงไม่ต้องค้างบนจอ
      if (status.status === "ok") toast.success(th.health.installed, { id: "ffmpeg" })
      else if (status.status === "warn") toast.info(status.message ?? th.health.installing, { id: "ffmpeg" })
      else toast.error(status.message ?? th.errors.unknown, { id: "ffmpeg", duration: Infinity })
      void queryClient.invalidateQueries({ queryKey: ["health"] })
    },
    onError: (error) => toast.error(error.message, { id: "ffmpeg", duration: Infinity }),
  })

  const shutdown = useMutation({
    mutationFn: () => api<{ ok: boolean }>("/shutdown", { method: "POST", body: JSON.stringify({ force: false }) }),
    onSuccess: () => {
      toast.dismiss()
      onShutdown()
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) {
        const pending = (error.body as { pendingJobs?: number }).pendingJobs ?? 0
        toast.warning(fill(th.shutdown.pending, { n: pending }))
        return
      }
      toast.error(error.message)
    },
  })

  if (health.isPending) {
    return (
      <div className="flex flex-col gap-2" aria-busy="true">
        {Array.from({ length: 6 }, (_, i) => (
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
      </ItemGroup>
      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="outline" onClick={() => void health.refetch()} disabled={health.isFetching}>
          <RefreshCw aria-hidden />
          {th.health.recheck}
        </Button>
        <Button variant="outline" onClick={() => shutdown.mutate()} disabled={shutdown.isPending}>
          {shutdown.isPending ? <Spinner /> : <Power aria-hidden />}
          {th.health.shutdown}
        </Button>
      </div>
    </div>
  )
}
