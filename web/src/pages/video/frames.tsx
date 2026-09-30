import { useQuery } from "@tanstack/react-query"
import { ChevronDown, ChevronUp, Copy, Download, ImageIcon, ImageOff, Link2 } from "lucide-react"
import { useEffect, useRef, useState, type KeyboardEvent, type RefObject } from "react"
import { toast } from "sonner"

import { AspectRatio } from "@/components/ui/aspect-ratio"
import { Button } from "@/components/ui/button"
import { ButtonGroup } from "@/components/ui/button-group"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ContextMenu, ContextMenuContent, ContextMenuItem, ContextMenuTrigger } from "@/components/ui/context-menu"
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia } from "@/components/ui/empty"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { fill, th } from "@/i18n/th"
import { ApiError } from "@/lib/api"
import { copyImage } from "@/lib/clipboard"
import { downloadFile } from "@/lib/download"
import { formatTimecode, youtubeLinkAt } from "@/lib/format"
import type { StoryboardFrame } from "@/lib/types"
import { cn } from "cn"

import { errorMessage } from "./errors"
import { FrameLightbox } from "./lightbox"
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

/** คัดลอกภาพเฟรมลงคลิปบอร์ดเป็น PNG (วางใน LINE / Word / PowerPoint ได้ทันที) */
async function copyFrameImage(url: string): Promise<void> {
  try {
    await copyImage(url)
    toast.success(t.imageCopied)
  } catch {
    toast.error(t.copyImageFailed)
  }
}

async function copyText(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text)
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

/** โฟกัสรายการแรกของเมนูที่เพิ่งเปิดด้วยคีย์บอร์ด (Base UI โฟกัสที่ตัวเมนู ต้องกดลูกศรลงอีกครั้งถึงจะถึงรายการแรก) */
function focusFirstItem(itemRef: RefObject<HTMLElement | null>): () => void {
  let frame = 0
  let tries = 0
  const attempt = () => {
    // เมนูอยู่ใน portal จึงอาจยังไม่ถูกสร้างตอนเริ่ม: อ่าน ref ใหม่ทุกครั้งที่ลอง
    const item = itemRef.current
    item?.focus()
    // Base UI ย้ายโฟกัสเข้าเมนูหลังเปิดเล็กน้อย ลองซ้ำจนกว่าโฟกัสจะอยู่ที่รายการจริง
    if (document.activeElement !== item && tries++ < 20) frame = requestAnimationFrame(attempt)
  }
  frame = requestAnimationFrame(attempt)
  return () => cancelAnimationFrame(frame)
}

// content-visibility: ภาพที่อยู่ไกลจอไม่ต้องเรนเดอร์จนกว่าจะเลื่อนใกล้ (ตอนขยาย 128 ภาพ) · ต้องเว้น padding รอบ li
// เพราะ content-visibility ตัดทุกอย่างที่ล้นกรอบ ไม่งั้นวงโฟกัสของปุ่มในภาพจะถูกตัด (margin ติดลบชดเชยให้ระยะห่างเท่าเดิม)
const TILE = "group relative -m-[3px] p-[3px] [contain-intrinsic-size:auto_80px] [content-visibility:auto]"

type FrameTileProps = {
  frame: StoryboardFrame
  videoId: string
  hideOnNarrow: boolean
  onOpen: () => void
  buttonRef: (element: HTMLButtonElement | null) => void
}

function FrameTile({ frame, videoId, hideOnNarrow, onOpen, buttonRef }: FrameTileProps) {
  const time = formatTimecode(frame.tMs)
  const [menuOpen, setMenuOpen] = useState(false)
  const keyboardOpenRef = useRef(false)
  const firstItemRef = useRef<HTMLDivElement>(null)
  const downloadingRef = useRef(false)

  useEffect(() => {
    if (!menuOpen) {
      keyboardOpenRef.current = false
      return
    }
    if (keyboardOpenRef.current) return focusFirstItem(firstItemRef)
  }, [menuOpen])

  // Shift+F10 / ปุ่ม Menu = เปิดเมนูเหมือนคลิกขวา (คลิกซ้าย/Enter/Space = ดูภาพใหญ่)
  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
      event.preventDefault()
      keyboardOpenRef.current = true
      openContextMenuAt(event.currentTarget)
    }
  }

  // กดซ้ำระหว่างรอไม่ส่งคำขอซ้ำ
  async function downloadFrame() {
    if (downloadingRef.current) return
    downloadingRef.current = true
    try {
      await downloadWithToast(frameDownloadUrl(frame.url), frameFileName(time))
    } finally {
      downloadingRef.current = false
    }
  }

  return (
    <ContextMenu onOpenChange={setMenuOpen}>
      <ContextMenuTrigger render={<li className={cn(TILE, hideOnNarrow && "max-sm:hidden")} />}>
        <button
          ref={buttonRef}
          type="button"
          aria-haspopup="dialog"
          onClick={onOpen}
          onKeyDown={onKeyDown}
          className="block w-full cursor-zoom-in rounded-md outline-none hover:ring-2 hover:ring-ring/40 focus-visible:ring-3 focus-visible:ring-ring"
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
            {/* เวลาของภาพ: เห็นตอนชี้เมาส์ และตอนโฟกัสด้วยคีย์บอร์ด (ผู้ใช้คีย์บอร์ดไม่มีเมาส์ชี้) */}
            <span className="pointer-events-none absolute bottom-1 left-1 hidden rounded-sm bg-background/85 px-1 font-mono text-[11px] text-foreground group-hover:block group-has-[:focus-visible]:block">
              {time}
            </span>
          </AspectRatio>
        </button>
      </ContextMenuTrigger>
      <ContextMenuContent>
        <ContextMenuItem ref={firstItemRef} onClick={() => void copyFrameImage(frame.url)}>
          <ImageIcon aria-hidden />
          {t.copyImage}
        </ContextMenuItem>
        <ContextMenuItem onClick={() => void downloadFrame()}>
          <Download aria-hidden />
          {t.downloadFrame}
        </ContextMenuItem>
        <ContextMenuItem onClick={() => void copyText(time)}>
          <Copy aria-hidden />
          {t.copyTime}
        </ContextMenuItem>
        <ContextMenuItem onClick={() => void copyText(youtubeLinkAt(videoId, frame.tMs))}>
          <Link2 aria-hidden />
          {t.copyLink}
        </ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
  )
}

function FrameGrid({ frames, videoId }: { frames: StoryboardFrame[]; videoId: string }) {
  const [expanded, setExpanded] = useState(false)
  // ภาพที่เปิดดูใหญ่อยู่ (ตำแหน่งใน frames) · null = ปิด
  const [viewing, setViewing] = useState<number | null>(null)
  const openerRef = useRef<number>(0)
  const buttons = useRef(new Map<number, HTMLButtonElement>())
  const shown = expanded ? frames : frames.slice(0, COLLAPSED_COUNT)
  // 12 ภาพหรือน้อยกว่าบนจอกว้างเห็นครบแล้ว ปุ่มจึงจำเป็นเฉพาะจอแคบ (ที่เห็นแค่ 6 ภาพ)
  const toggleNeeded = frames.length > COLLAPSED_COUNT

  // ปิดภาพใหญ่แล้วโฟกัสกลับที่ภาพเฟรมที่ดูอยู่ล่าสุด (ถ้าภาพนั้นอยู่ในตารางและมองเห็นได้) ไม่งั้นกลับภาพที่กดเปิด
  function returnFocus(last: number): HTMLElement | null {
    const current = buttons.current.get(last)
    if (current && current.offsetParent !== null) return current
    return buttons.current.get(openerRef.current) ?? null
  }

  return (
    <div className="flex flex-col gap-3">
      <ul className={GRID} aria-label={t.listLabel}>
        {shown.map((frame, index) => (
          <FrameTile
            key={frame.index}
            frame={frame}
            videoId={videoId}
            hideOnNarrow={!expanded && index >= NARROW_COUNT}
            onOpen={() => {
              openerRef.current = index
              setViewing(index)
            }}
            buttonRef={(element) => {
              if (element) buttons.current.set(index, element)
              else buttons.current.delete(index)
            }}
          />
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
      <FrameLightbox frames={frames} index={viewing} onIndexChange={setViewing} returnFocus={returnFocus} />
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
      {/* "Contact sheet" เป็นคำเฉพาะ: ชี้แล้วมีคำอธิบายภาษาไทย */}
      <Tooltip>
        <TooltipTrigger
          render={
            <Button
              variant="secondary"
              size="sm"
              disabled={busy !== null}
              focusableWhenDisabled
              onClick={() => void run("sheet", "contact-sheet.jpg", "contact-sheet.jpg")}
            />
          }
        >
          {busy === "sheet" && <Spinner aria-hidden />}
          {t.contactSheet}
        </TooltipTrigger>
        <TooltipContent>{t.contactSheetHint}</TooltipContent>
      </Tooltip>
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
  } else if (storyboard.isSuccess) body = <FrameGrid frames={frames} videoId={videoId} />
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
          {/* บอกว่าภาพเฟรมทำอะไรได้บ้าง (คลิกดูใหญ่ / คลิกขวาคัดลอก-โหลด) คนที่ไม่รู้ว่าคลิกขวาได้จะได้เจอ */}
          {storyboard.isSuccess && frames.length > 0 && (
            // จอแคบ: ลงไปอยู่ใต้ปุ่มโหลดเต็มความกว้าง ไม่ถูกบีบข้างปุ่ม
            <CardDescription className="col-span-2 sm:col-span-1">{t.hint}</CardDescription>
          )}
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
