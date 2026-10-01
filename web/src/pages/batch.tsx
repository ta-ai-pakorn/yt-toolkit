import { useQueries, useQuery } from "@tanstack/react-query"
import { ListChecks } from "lucide-react"
import { useCallback, useEffect, useId, useMemo, useState } from "react"
import { Link, useSearchParams } from "react-router"

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogMedia,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"
import { Button, buttonVariants } from "@/components/ui/button"
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty"
import { Spinner } from "@/components/ui/spinner"
import { fill, th } from "@/i18n/th"
import { batchMinutes } from "@/lib/download-options"
import { useEnqueue } from "@/lib/jobs"
import { settingsQuery } from "@/lib/settings-api"
import type { ResolveItem } from "@/lib/types"

import { BatchOptions } from "./batch/batch-options"
import { BatchTable, BatchTableSkeleton } from "./batch/batch-table"
import {
  canSubmit,
  CONFIRM_ABOVE,
  buildBatchJobs,
  clipRows,
  isExpired,
  parseBatchSource,
  playlistRows,
  selectableRows,
  selectedRows,
  type BatchChoice,
  type BatchRow,
  type BatchSource,
} from "./batch/rows"
import { playlistQuery, videoTitleQuery } from "./home/queries"
import { useHomeState } from "./home/state"
import { useSubSettings } from "./video/subs-settings"
import { LoadError } from "./video/load-error"

const t = th.batch

const ENQUEUE_MESSAGES = {
  added: th.queue.added,
  addedMany: th.queue.addedMany,
  failed: th.queue.addFailed,
  goHealth: th.queue.goHealth,
}

// พื้นที่กดสูง 32 px และวงโฟกัสชัด (margin ติดลบให้ตัวอักษรยังตรงแนวเดิม) เหมือน breadcrumb ของ W2
const CRUMB =
  "-mx-1.5 inline-flex min-h-8 items-center rounded-md px-1.5 outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"

/** breadcrumb: หน้าแรก › รายการที่วาง (N ลิงก์) › เลือกคลิป · listCount = undefined (รายการไม่อยู่แล้ว) ไม่มีขั้นกลาง */
function BatchCrumbs({ listCount }: { listCount?: number }) {
  return (
    <Breadcrumb>
      <BreadcrumbList>
        <BreadcrumbItem>
          <BreadcrumbLink className={CRUMB} render={<Link to="/" />}>
            {th.nav.home}
          </BreadcrumbLink>
        </BreadcrumbItem>
        <BreadcrumbSeparator />
        {listCount !== undefined && (
          <>
            <BreadcrumbItem>
              <BreadcrumbLink className={CRUMB} render={<Link to="/" />}>
                {fill(th.video.crumbList, { n: listCount })}
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
          </>
        )}
        <BreadcrumbItem>
          <BreadcrumbPage className="block min-h-8 py-1.5">{t.crumb}</BreadcrumbPage>
        </BreadcrumbItem>
      </BreadcrumbList>
    </Breadcrumb>
  )
}

/** ชื่อคลิปที่ W1 โหลดไว้แล้ว (cache ของ react-query) ไม่ส่งคำขอใหม่: ผู้สังเกตการณ์ปิดการดึง (enabled: false) แค่อ่านและตามการเปลี่ยนแปลง */
function useCachedTitles(videoIds: string[]): ReadonlyMap<string, string> {
  // combine ต้องคงตัวเดิมระหว่างการวาดซ้ำ ไม่งั้นได้ Map ใหม่ทุกรอบและตารางคำนวณแถวใหม่ทุกรอบ
  const combine = useCallback(
    (results: { data?: { title?: string } }[]) => {
      const titles = new Map<string, string>()
      results.forEach((result, index) => {
        if (result.data?.title) titles.set(videoIds[index], result.data.title)
      })
      return titles
    },
    [videoIds]
  )
  return useQueries({
    queries: videoIds.map((id) => ({ ...videoTitleQuery(id), enabled: false })),
    combine,
  })
}

function ExpiredState() {
  return (
    <section className="flex flex-col gap-4 pt-2">
      <BatchCrumbs />
      <Empty className="border py-12">
        <EmptyHeader>
          <EmptyTitle>{t.expired}</EmptyTitle>
        </EmptyHeader>
        <Link to="/" className={buttonVariants({ variant: "outline" })}>
          {th.common.backHome}
        </Link>
      </Empty>
    </section>
  )
}

type BodyProps = { source: BatchSource; results: ResolveItem[] }

function BatchBody({ source, results }: BodyProps) {
  const settings = useQuery(settingsQuery())
  const { options: subOptions } = useSubSettings()
  const { enqueue, pending } = useEnqueue(ENQUEUE_MESSAGES)

  // เลือกเฉพาะเพลย์ลิสต์/มิกซ์ = ข้อมูลเดียวกับที่ W1 โหลดไว้ (cache เดียวกัน ไม่ขอใหม่ถ้ายังสด)
  const playlistSource = source.playlist
  const playlist = useQuery({
    ...playlistQuery(playlistSource?.id ?? "", undefined, playlistSource?.v),
    enabled: playlistSource !== undefined,
  })

  const clipIds = useMemo(
    () => (playlistSource ? [] : clipRows(results, () => undefined).rows.flatMap((row) => (row.invalid ? [] : [row.videoId]))),
    [playlistSource, results]
  )
  const titles = useCachedTitles(clipIds)

  const fromList = useMemo(() => clipRows(results, (id) => titles.get(id)), [results, titles])
  const rows: BatchRow[] = useMemo(
    () => (playlistSource ? (playlist.data ? playlistRows(playlist.data.entries) : []) : fromList.rows),
    [playlistSource, playlist.data, fromList.rows]
  )

  // ค่าเริ่มต้นเลือกทั้งหมด: เก็บเฉพาะคลิปที่ผู้ใช้เอาออก
  const [deselected, setDeselected] = useState<ReadonlySet<string>>(new Set())
  const [choice, setChoice] = useState<BatchChoice>({ what: "video", sub: "none" })
  const [confirmOpen, setConfirmOpen] = useState(false)
  const nothingId = useId()

  const selectable = selectableRows(rows)
  const clips = selectedRows(rows, deselected)
  const count = clips.length
  const ready = settings.data !== undefined
  const allowed = canSubmit(count, choice)

  function toggle(videoId: string) {
    setDeselected((previous) => {
      const next = new Set(previous)
      if (!next.delete(videoId)) next.add(videoId)
      return next
    })
  }

  function toggleAll(selected: boolean) {
    setDeselected(selected ? new Set() : new Set(selectable.map((row) => row.videoId)))
  }

  async function send() {
    if (!settings.data) return
    await enqueue(buildBatchJobs(clips, choice, settings.data, subOptions))
  }

  function submit() {
    if (!allowed || !ready || pending) return
    if (count > CONFIRM_ABOVE) setConfirmOpen(true)
    else void send()
  }

  const loadingPlaylist = playlistSource !== undefined && playlist.isPending
  const failure = playlistSource !== undefined && playlist.isError ? playlist : settings.isError ? settings : null
  const heading = playlistSource
    ? (playlist.data ? playlist.data.title || th.home.results.playlistUntitled : loadingPlaylist ? t.loading : t.crumb)
    : t.multiTitle

  return (
    <section className="flex flex-col gap-5 pt-2">
      <BatchCrumbs listCount={results.length} />

      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold [overflow-wrap:anywhere]">{heading}</h1>
        {!loadingPlaylist && !failure && (
          <p role="status" className="text-sm text-muted-foreground">
            {fill(t.counts, { total: selectable.length, selected: count })}
          </p>
        )}
      </div>

      {failure ? (
        <LoadError title={t.loadError} error={failure.error} onRetry={() => void failure.refetch()} />
      ) : loadingPlaylist ? (
        <div aria-busy="true">
          <span className="sr-only" role="status">
            {t.loading}
          </span>
          <BatchTableSkeleton />
        </div>
      ) : (
        <>
          <div className="flex flex-col gap-4 rounded-xl border p-4">
            <BatchOptions choice={choice} onChange={setChoice} />
            <div className="flex flex-col gap-2">
              {/* aria-disabled แทน disabled เพื่อให้โฟกัสยังอยู่ที่ปุ่ม (submit() กันการกดเองอยู่แล้ว) */}
              <Button
                className="w-fit max-w-full"
                aria-disabled={!allowed || !ready || pending}
                aria-describedby={allowed ? undefined : nothingId}
                onClick={submit}
              >
                {pending && <Spinner data-icon="inline-start" />}
                {fill(t.submit, { n: count })}
              </Button>
              {!allowed && (
                <p id={nothingId} className="text-sm text-muted-foreground">
                  {t.nothing}
                </p>
              )}
            </div>
          </div>

          {fromList.hasPlaylists && !playlistSource && (
            <p className="text-sm text-muted-foreground">{t.playlistsNote}</p>
          )}

          {rows.length === 0 ? (
            <Empty className="border py-12">
              <EmptyHeader>
                <EmptyDescription>{th.home.results.playlistEmpty}</EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : (
            <BatchTable rows={rows} deselected={deselected} onToggle={toggle} onToggleAll={toggleAll} />
          )}
        </>
      )}

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogMedia>
              <ListChecks aria-hidden />
            </AlertDialogMedia>
            <AlertDialogTitle>{fill(t.confirmTitle, { n: count })}</AlertDialogTitle>
            <AlertDialogDescription>
              {fill(t.confirmBody, { minutes: batchMinutes(count, settings.data?.concurrency ?? 1) })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t.confirmCancel}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                // AlertDialogAction ไม่ปิดหน้าต่างเอง
                setConfirmOpen(false)
                void send()
              }}
            >
              {t.confirmOk}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  )
}

/** หน้า W3 (/batch): เลือกคลิปจากรายการที่วางที่หน้าแรก หรือจากเพลย์ลิสต์/มิกซ์ แล้วส่งเข้าคิวทีเดียว */
export function BatchPage() {
  const [params] = useSearchParams()
  const source = parseBatchSource(params)
  const { results, listId } = useHomeState()

  useEffect(() => {
    const previous = document.title
    document.title = fill(t.pageTitle, { app: th.app.name })
    return () => {
      document.title = previous
    }
  }, [])

  if (source === null || results === null || isExpired(source, listId, results)) return <ExpiredState />
  // key: เปลี่ยนที่มา (รายการอื่น / เพลย์ลิสต์อื่น) = ล้างการเลือกและตัวเลือกใหม่
  const key = `${source.src}|${source.playlist?.id ?? ""}|${source.playlist?.v ?? ""}`
  return <BatchBody key={key} source={source} results={results} />
}
