import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Eraser } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { ErrorDetails } from "@/components/error-report/error-details"
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
import { Empty, EmptyHeader, EmptyTitle } from "@/components/ui/empty"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { fill, th } from "@/i18n/th"
import { formatBytes } from "@/lib/format"
import { reportRequest } from "@/lib/report"
import { resetStats, STATS_KEY, statsQuery } from "@/lib/stats-api"
import type { Stats } from "@/lib/types"

import { serverMessage } from "./general-form"
import { count, isEmpty, kindLabel, monthLabel, RESET_TOAST_ID, sinceLabel, topKind } from "./stats"

const t = th.stats

/** แท็บ "สถิติของฉัน" (M6 รอบ C spec §3.4, PRD :309 :326) · คำนวณในเครื่อง โหลดใหม่ทุกครั้งที่เปิดแท็บ */
export function StatsPanel() {
  const queryClient = useQueryClient()
  const stats = useQuery(statsQuery())
  const [confirmOpen, setConfirmOpen] = useState(false)

  const reset = useMutation({
    mutationFn: () => resetStats(),
    onSuccess: () => {
      setConfirmOpen(false)
      toast.success(t.resetDone, { ...PLAIN_TOAST, id: RESET_TOAST_ID })
      void queryClient.invalidateQueries({ queryKey: STATS_KEY })
    },
    onError: (error) => {
      setConfirmOpen(false)
      showErrorToast(serverMessage(error), { id: RESET_TOAST_ID, request: reportRequest(error, { context: "stats-reset" }) })
    },
  })

  if (stats.isPending) {
    return (
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4" aria-busy="true">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-20 w-full" />
        ))}
      </div>
    )
  }
  if (stats.isError) return <ErrorDetails error={stats.error} context="stats" />

  const data = stats.data
  return (
    <div className="flex flex-col gap-6">
      {isEmpty(data) ? (
        <Empty className="border py-12">
          <EmptyHeader>
            <EmptyTitle>{t.empty}</EmptyTitle>
          </EmptyHeader>
        </Empty>
      ) : (
        <>
          <Tiles stats={data} />
          <Months stats={data} />
        </>
      )}
      <div className="flex flex-col gap-1 text-sm text-muted-foreground">
        <p>{t.privacy}</p>
        {data.since && <p>{fill(t.since, { date: sinceLabel(data.since) })}</p>}
      </div>
      {!isEmpty(data) && (
        <div>
          <Button type="button" variant="ghost" disabled={reset.isPending} onClick={() => setConfirmOpen(true)}>
            <Eraser data-icon="inline-start" aria-hidden />
            {t.reset}
          </Button>
        </div>
      )}
      <AlertDialog
        open={confirmOpen}
        onOpenChange={(next) => {
          if (!next && !reset.isPending) setConfirmOpen(false)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t.resetTitle}</AlertDialogTitle>
            <AlertDialogDescription>{t.resetBody}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={reset.isPending}>{t.resetCancel}</AlertDialogCancel>
            <AlertDialogAction
              disabled={reset.isPending}
              onClick={(event) => {
                event.preventDefault() // ค้างกล่องไว้ระหว่างรอ ปิดเองตอนสำเร็จหรือพลาด
                if (!reset.isPending) reset.mutate()
              }}
            >
              {reset.isPending && <Spinner />}
              {t.resetConfirm}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

function Tiles({ stats }: { stats: Stats }) {
  const top = topKind(stats)
  const tiles: { label: string; value: string; sub?: string }[] = [
    { label: t.clips, value: count(stats.clips) },
    { label: t.files, value: count(stats.files) },
    { label: t.totalSize, value: formatBytes(stats.totalBytes) },
    { label: t.topKind, value: top ? kindLabel(top.kind) : "-", sub: top ? fill(t.topKindFiles, { n: count(top.files) }) : undefined },
  ]
  return (
    <dl className="grid grid-cols-2 gap-3 md:grid-cols-4" data-testid="stats-tiles">
      {tiles.map((tile) => (
        <div key={tile.label} className="flex min-w-0 flex-col gap-1 rounded-lg border p-4">
          <dt className="text-sm text-muted-foreground">{tile.label}</dt>
          <dd className="text-2xl font-semibold tabular-nums">{tile.value}</dd>
          {tile.sub && <dd className="text-sm text-muted-foreground">{tile.sub}</dd>}
        </div>
      ))}
    </dl>
  )
}

function Months({ stats }: { stats: Stats }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead scope="col">{t.month}</TableHead>
          <TableHead scope="col" className="text-right">{t.clips}</TableHead>
          <TableHead scope="col" className="text-right">{t.files}</TableHead>
          <TableHead scope="col" className="text-right">{t.size}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {stats.byMonth.map((row) => (
          <TableRow key={row.month}>
            <TableCell>{monthLabel(row.month)}</TableCell>
            <TableCell className="text-right tabular-nums">{count(row.clips)}</TableCell>
            <TableCell className="text-right tabular-nums">{count(row.files)}</TableCell>
            <TableCell className="text-right tabular-nums">{formatBytes(row.bytes)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
