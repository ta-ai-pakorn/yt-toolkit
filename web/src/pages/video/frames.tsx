import { useQuery } from "@tanstack/react-query"
import { ChevronDown, ChevronUp, Copy, Download, ImageOff } from "lucide-react"
import { useState, type KeyboardEvent, type MouseEvent } from "react"
import { toast } from "sonner"

import { AspectRatio } from "@/components/ui/aspect-ratio"
import { Button } from "@/components/ui/button"
import { ButtonGroup } from "@/components/ui/button-group"
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ContextMenu, ContextMenuContent, ContextMenuItem, ContextMenuTrigger } from "@/components/ui/context-menu"
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia } from "@/components/ui/empty"
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { fill, th } from "@/i18n/th"
import { ApiError } from "@/lib/api"
import { downloadFile } from "@/lib/download"
import { formatTimecode } from "@/lib/format"
import type { StoryboardFrame } from "@/lib/types"
import { cn } from "cn"

import { errorMessage } from "./errors"
import { LoadError } from "./load-error"
import { storyboardQuery } from "./queries"

const t = th.frames

/** grid 6 คอลัมน์ x 2 แถวแรก = 12 ภาพ (จอแคบ 3 คอลัมน์ x 2 แถว = 6 ภาพ ซ่อนด้วย CSS) */
const COLLAPSED_COUNT = 12
const NARROW_COUNT = 6
const SKELETON_CELLS = 6
const GRID = "grid grid-cols-3 gap-2 sm:grid-cols-6"

/** โหลดไฟล์ผ่านเบราว์เซอร์ พร้อม toast บอกสถานะ: error ขึ้นข้อความไทยจาก backend แทนที่จะได้ไฟล์ JSON */
async function downloadWithToast(url: string, fallbackName: string): Promise<void> {
  const id = toast.loading(t.preparing)
  try {
    await downloadFile(url, fallbackName)
    toast.dismiss(id)
  } catch (error) {
    toast.error(errorMessage(error, th.errors.downloadFailed), { id })
  }
}

async function copyTimecode(time: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(time)
    toast.success(t.copied)
  } catch {
    toast.error(t.copyFailed)
  }
}

/** url ของภาพเฟรมมี ?v=<token> อยู่แล้ว ต่อ download ด้วย & (ถ้าไม่มี query ค่อยใช้ ?) */
const frameDownloadUrl = (url: string) => `${url}${url.includes("?") ? "&" : "?"}download=1`

/** ชื่อไฟล์สำรองถ้า backend ไม่ส่งชื่อมา: frame_HH-MM-SS.jpg */
const frameFileName = (time: string) => `frame_${time.replaceAll(":", "-")}.jpg`

/**
 * เมนูของ Base UI เปิดจากเหตุการณ์ contextmenu เท่านั้น เบราว์เซอร์ส่งเหตุการณ์นี้ให้เองเมื่อกด Shift+F10 หรือปุ่ม Menu
 * แต่ไม่ทุกเบราว์เซอร์/ระบบ (เช่น Playwright) จึงยิงเหตุการณ์เองที่กลางภาพ เมนูจะเปิดตรงนั้น
 */
function openContextMenuAt(target: HTMLElement, x?: number, y?: number): void {
  const rect = target.getBoundingClientRect()
  target.dispatchEvent(
    new MouseEvent("contextmenu", {
      bubbles: true,
      cancelable: true,
      button: 2,
      clientX: x ?? rect.left + rect.width / 2,
      clientY: y ?? rect.top + rect.height / 2,
    }),
  )
}

function FrameTile({ frame, hideOnNarrow }: { frame: StoryboardFrame; hideOnNarrow: boolean }) {
  const time = formatTimecode(frame.tMs)
  const [menuOpen, setMenuOpen] = useState(false)
  const [previewOpen, setPreviewOpen] = useState(false)

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
      event.preventDefault()
      openContextMenuAt(event.currentTarget)
    }
  }

  // คลิกซ้าย/Enter/Space ที่ภาพ = เปิดเมนูเดียวกัน (คนที่ไม่รู้ว่าคลิกขวาได้ก็เจอ และใช้บนจอสัมผัสได้)
  function onClick(event: MouseEvent<HTMLButtonElement>) {
    if (event.detail === 0) openContextMenuAt(event.currentTarget)
    else openContextMenuAt(event.currentTarget, event.clientX, event.clientY)
  }

  return (
    <ContextMenu onOpenChange={setMenuOpen}>
      <ContextMenuTrigger render={<li className={cn("group relative", hideOnNarrow && "max-sm:hidden")} />}>
        <HoverCard open={previewOpen && !menuOpen} onOpenChange={setPreviewOpen}>
          <HoverCardTrigger
            delay={250}
            closeDelay={100}
            render={
              <button
                type="button"
                onClick={onClick}
                onKeyDown={onKeyDown}
                className="block w-full cursor-pointer rounded-md outline-none focus-visible:ring-3 focus-visible:ring-ring"
              />
            }
          >
            <AspectRatio ratio={16 / 9} className="overflow-hidden rounded-md bg-muted">
              <img
                src={frame.url}
                alt={fill(t.frameAlt, { time })}
                width={320}
                height={180}
                loading="lazy"
                decoding="async"
                className="size-full object-cover"
              />
              {/* ผู้ใช้คีย์บอร์ดไม่มีเมาส์ชี้ ให้เห็นเวลาตอนโฟกัสด้วย */}
              <span className="pointer-events-none absolute bottom-1 left-1 hidden rounded-sm bg-background/85 px-1 font-mono text-[11px] text-foreground group-has-[:focus-visible]:block">
                {time}
              </span>
            </AspectRatio>
          </HoverCardTrigger>
          <HoverCardContent side="top" className="w-[min(492px,calc(100vw-1.5rem))] p-1.5">
            <img src={frame.url} alt="" width={480} height={270} decoding="async" className="aspect-video w-full rounded-md" />
            <p className="pt-1.5 text-center font-mono text-xs">{time}</p>
          </HoverCardContent>
        </HoverCard>
      </ContextMenuTrigger>
      <ContextMenuContent>
        <ContextMenuItem onClick={() => void downloadWithToast(frameDownloadUrl(frame.url), frameFileName(time))}>
          <Download aria-hidden />
          {t.downloadFrame}
        </ContextMenuItem>
        <ContextMenuItem onClick={() => void copyTimecode(time)}>
          <Copy aria-hidden />
          {t.copyTime}
        </ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
  )
}

function FrameGrid({ frames }: { frames: StoryboardFrame[] }) {
  const [expanded, setExpanded] = useState(false)
  const shown = expanded ? frames : frames.slice(0, COLLAPSED_COUNT)
  // 12 ภาพหรือน้อยกว่าบนจอกว้างเห็นครบแล้ว ปุ่มจึงจำเป็นเฉพาะจอแคบ (ที่เห็นแค่ 6 ภาพ)
  const toggleNeeded = frames.length > COLLAPSED_COUNT
  return (
    <div className="flex flex-col gap-3">
      <ul className={GRID} aria-label={t.listLabel}>
        {shown.map((frame, index) => (
          <FrameTile key={frame.index} frame={frame} hideOnNarrow={!expanded && index >= NARROW_COUNT} />
        ))}
      </ul>
      {frames.length > NARROW_COUNT && (
        <Button
          variant="ghost"
          size="sm"
          className={cn("self-center", !toggleNeeded && "sm:hidden")}
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? <ChevronUp aria-hidden /> : <ChevronDown aria-hidden />}
          {expanded ? t.collapse : fill(t.showAll, { n: frames.length })}
        </Button>
      )}
    </div>
  )
}

function FrameSkeleton() {
  return (
    <div className={GRID} aria-busy="true">
      <span className="sr-only" role="status">
        {t.loading}
      </span>
      {Array.from({ length: SKELETON_CELLS }, (_, index) => (
        <Skeleton key={index} className="aspect-video w-full" />
      ))}
    </div>
  )
}

function NoStoryboard() {
  return (
    <Empty className="border">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <ImageOff aria-hidden />
        </EmptyMedia>
        <EmptyDescription>{t.noStoryboard}</EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        {/* ปุ่มที่ปิดใช้งานยังต้องโฟกัสได้ ไม่งั้นผู้ใช้คีย์บอร์ดไม่เห็นคำอธิบายว่าเปิดเมื่อไร */}
        <Tooltip>
          <TooltipTrigger render={<Button variant="outline" disabled focusableWhenDisabled />}>{t.requestSharp}</TooltipTrigger>
          <TooltipContent>{t.availableLater}</TooltipContent>
        </Tooltip>
      </EmptyContent>
    </Empty>
  )
}

type Bulk = "sheet" | "zip"

function BulkDownloads({ videoId }: { videoId: string }) {
  const [busy, setBusy] = useState<Bulk | null>(null)

  async function run(kind: Bulk, path: string, fallbackName: string) {
    setBusy(kind)
    try {
      await downloadWithToast(`/api/videos/${videoId}/storyboard/${path}`, fallbackName)
    } finally {
      setBusy(null)
    }
  }

  return (
    <ButtonGroup aria-label={t.downloadGroup}>
      <Button
        variant="secondary"
        size="sm"
        disabled={busy !== null}
        focusableWhenDisabled
        onClick={() => void run("sheet", "contact-sheet.jpg", "contact-sheet.jpg")}
      >
        {busy === "sheet" && <Spinner aria-hidden />}
        {t.contactSheet}
      </Button>
      <Button
        variant="secondary"
        size="sm"
        disabled={busy !== null}
        focusableWhenDisabled
        onClick={() => void run("zip", "frames.zip", "frames.zip")}
      >
        {busy === "zip" && <Spinner aria-hidden />}
        {t.zip}
      </Button>
    </ButtonGroup>
  )
}

/** ส่วน "ภาพเฟรม" ของ W2 · เริ่มโหลด storyboard เมื่อ `enabled` (หลังข้อมูลคลิปมาแล้ว) */
export function FramesSection({ videoId, enabled }: { videoId: string; enabled: boolean }) {
  const storyboard = useQuery(storyboardQuery(videoId, enabled))
  const frames = storyboard.data?.frames ?? []
  const noStoryboard =
    (storyboard.isError && storyboard.error instanceof ApiError && storyboard.error.code === "E_NO_STORYBOARD") ||
    (storyboard.isSuccess && frames.length === 0)

  let body
  if (noStoryboard) body = <NoStoryboard />
  else if (storyboard.isError) {
    body = <LoadError title={t.loadError} error={storyboard.error} onRetry={() => void storyboard.refetch()} />
  } else if (storyboard.isSuccess) body = <FrameGrid frames={frames} />
  else body = <FrameSkeleton />

  return (
    <section aria-labelledby="frames-title">
      <Card>
        <CardHeader>
          <CardTitle>
            <h2 id="frames-title" className="text-base font-medium">
              {t.title}
            </h2>
          </CardTitle>
          {storyboard.isSuccess && frames.length > 0 && (
            <CardAction>
              <BulkDownloads videoId={videoId} />
            </CardAction>
          )}
        </CardHeader>
        <CardContent>{body}</CardContent>
      </Card>
    </section>
  )
}
