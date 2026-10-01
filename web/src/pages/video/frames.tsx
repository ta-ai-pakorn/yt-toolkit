import { useQuery } from "@tanstack/react-query"
import { Captions, Copy, Download, Flame, ImageIcon, ImageOff, Link2 } from "lucide-react"
import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type RefObject } from "react"
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
import type { ReplaySegment, StoryboardFrame } from "@/lib/types"

import { errorMessage } from "./errors"
import { nearestFrameIndex, revealAndFocus } from "./frame-target"
import { FrameLightbox } from "./lightbox"
import { LoadError } from "./load-error"
import { replayedFrames, segmentFrameIndex } from "./most-replayed"
import { ReplayedMark } from "./replayed-mark"
import { storyboardQuery } from "./queries"
import { subtitlesQuery } from "./subs-queries"
import { trackInEffect } from "./track-label"
import { useVideoParams } from "./url-state"

const t = th.frames

/** grid 6 คอลัมน์ (จอแคบ 3 คอลัมน์) แสดงทุกภาพตั้งแต่แรก ไม่ต้องกด "ดูทั้งหมด" */
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

// content-visibility: ภาพที่อยู่ไกลจอไม่ต้องเรนเดอร์จนกว่าจะเลื่อนใกล้ (คลิปยาวมีภาพเป็นร้อย) · ต้องเว้น padding รอบ li
// เพราะ content-visibility ตัดทุกอย่างที่ล้นกรอบ ไม่งั้นวงโฟกัสของปุ่มในภาพจะถูกตัด (margin ติดลบชดเชยให้ระยะห่างเท่าเดิม)
const TILE = "group relative -m-[3px] p-[3px] [contain-intrinsic-size:auto_80px] [content-visibility:auto]"

// ภาพที่มาจากบรรทัดทรานสคริปต์ (?at=): กรอบ 2px สีอำพันเข้ม (--accent-text ผ่าน 3:1 ทั้งสองธีม BRD 10.7) เว้นช่องจากภาพ 1px
// ต่างจากวงโฟกัส (วงทึบ 3px ติดภาพ) และแสดงเฉพาะตอนไม่มีวงโฟกัส: ผู้ใช้คีย์บอร์ดเห็นวงโฟกัสเสมอ ไม่ถูกกรอบนี้บัง
// ใช้ outline ไม่ใช่ ring: ช่องว่าง 1px + กรอบ 2px = 3px พอดีกับ padding ของ li (content-visibility ตัดส่วนที่ล้น)
const HIGHLIGHT =
  "not-focus-visible:data-highlighted:outline-solid not-focus-visible:data-highlighted:outline-2 not-focus-visible:data-highlighted:outline-offset-1 not-focus-visible:data-highlighted:outline-accent-text"

type FrameTileProps = {
  frame: StoryboardFrame
  videoId: string
  highlighted: boolean
  /** ภาพอยู่ในช่วงที่คนดูซ้ำมากที่สุด (มีป้ายที่มุมขวาบน) */
  replayed: boolean
  onOpen: () => void
  /** "ดูซับช่วงนี้" · undefined = คลิปไม่มีซับหรือยังไม่มีแทร็กที่ใช้อยู่ (ไม่มีรายการนี้ในเมนู เมนูเหมือน M2) */
  onViewSubs?: () => void
  buttonRef: (element: HTMLButtonElement | null) => void
}

function FrameTile({ frame, videoId, highlighted, replayed, onOpen, onViewSubs, buttonRef }: FrameTileProps) {
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
      <ContextMenuTrigger render={<li className={TILE} />}>
        <button
          ref={buttonRef}
          type="button"
          aria-haspopup="dialog"
          data-highlighted={highlighted ? "" : undefined}
          aria-current={highlighted ? "true" : undefined}
          onClick={onOpen}
          onKeyDown={onKeyDown}
          className={`block w-full cursor-zoom-in rounded-md outline-none hover:ring-2 hover:ring-ring/40 focus-visible:ring-3 focus-visible:ring-ring ${HIGHLIGHT}`}
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
            {replayed && (
              <ReplayedMark className="pointer-events-none absolute top-1 right-1 inline-flex rounded-sm bg-background/85 p-0.5" />
            )}
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
        {onViewSubs && (
          <ContextMenuItem onClick={onViewSubs}>
            <Captions aria-hidden />
            {t.viewSubs}
          </ContextMenuItem>
        )}
      </ContextMenuContent>
    </ContextMenu>
  )
}

type FrameGridProps = {
  frames: StoryboardFrame[]
  videoId: string
  /** เวลาใน URL (?at=) · null = ไม่มีภาพที่ไฮไลต์ */
  at: number | null
  /** ช่วงที่คนดูซ้ำมากที่สุด (ภาพในช่วงมีป้าย) */
  segments?: ReplaySegment[]
  onViewSubs?: (tMs: number) => void
}

function FrameGrid({ frames, videoId, at, segments, onViewSubs }: FrameGridProps) {
  // ภาพที่เปิดดูใหญ่อยู่ (ตำแหน่งใน frames) · null = ปิด
  const [viewing, setViewing] = useState<number | null>(null)
  const openerRef = useRef<number>(0)
  const buttons = useRef(new Map<number, HTMLButtonElement>())
  // ภาพของเวลาใน URL: เลื่อนมาให้เห็นตรงกลางและโฟกัสครั้งเดียวต่อค่า at (เลือกภาพอื่นต่อได้โดยไม่ถูกดึงกลับ)
  const highlighted = at === null ? -1 : nearestFrameIndex(frames, at)
  const revealed = useRef<number | null>(null)
  // ภาพที่มีป้าย "ดูซ้ำบ่อย" (รวมภาพแทนของช่วงสั้นที่ไม่มีภาพอยู่ข้างใน) คิดครั้งเดียวต่อชุดภาพ
  const marked = useMemo(() => replayedFrames(frames, segments), [frames, segments])

  useEffect(() => {
    if (at === null) {
      revealed.current = null
      return
    }
    if (revealed.current === at || highlighted < 0) return
    return revealAndFocus(
      () => buttons.current.get(highlighted),
      () => {
        revealed.current = at
      },
    )
  }, [at, highlighted])

  // ปิดภาพใหญ่แล้วโฟกัสกลับที่ภาพเฟรมที่ดูอยู่ล่าสุด (ถ้าภาพนั้นอยู่ในตารางและมองเห็นได้) ไม่งั้นกลับภาพที่กดเปิด
  function returnFocus(last: number): HTMLElement | null {
    const current = buttons.current.get(last)
    if (current && current.offsetParent !== null) return current
    return buttons.current.get(openerRef.current) ?? null
  }

  return (
    <div className="flex flex-col gap-3">
      <ul className={GRID} aria-label={t.listLabel}>
        {frames.map((frame, index) => (
          <FrameTile
            key={frame.index}
            frame={frame}
            videoId={videoId}
            highlighted={index === highlighted}
            replayed={marked.has(index)}
            onViewSubs={onViewSubs && (() => onViewSubs(frame.tMs))}
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
      {/* "โหลดภาพรวมเฟรม" (contact sheet): ชี้แล้วมีคำอธิบายว่าได้ไฟล์แบบไหน */}
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

/**
 * บรรทัด "ช่วงที่คนดูซ้ำมากที่สุด: 00:01:20, 00:05:10" ใต้หัวข้อภาพเฟรม (ไอคอนเดียวกับป้ายบนภาพ จึงอธิบายป้ายไปในตัว)
 * กดเวลาแล้วไฮไลต์ภาพแรกในช่วงนั้น (ไม่มีภาพในช่วง = ภาพที่ใกล้กลางช่วงที่สุด ซึ่งก็มีป้าย) เลื่อนมาให้เห็นและโฟกัส
 * (กลไกเดียวกับ ?at= จากทรานสคริปต์) ตัวเลขบนปุ่มยังเป็นเวลาเริ่มของช่วง
 */
function ReplayedTimes({
  segments,
  frames,
  onPick,
}: {
  segments: ReplaySegment[]
  frames: StoryboardFrame[]
  onPick: (ms: number) => void
}) {
  return (
    <p className="flex flex-wrap items-center gap-x-1 gap-y-1 text-sm text-muted-foreground">
      <Flame aria-hidden className="size-4 shrink-0 text-accent-text" />
      <span className="mr-1">{t.replayedTitle}</span>
      {segments.map((segment, index) => {
        const time = formatTimecode(segment.startMs)
        return (
          <span key={`${segment.startMs}-${index}`} className="inline-flex items-center">
            <Button
              variant="outline"
              size="xs"
              className="font-mono text-foreground tabular-nums max-sm:h-11 max-sm:px-3"
              aria-label={fill(t.goToReplayed, { time })}
              onClick={() => {
                const index = segmentFrameIndex(frames, segment)
                onPick(index >= 0 ? frames[index].tMs : segment.startMs)
              }}
            >
              {time}
            </Button>
            {index < segments.length - 1 && <span aria-hidden>,</span>}
          </span>
        )
      })}
    </p>
  )
}

type FramesSectionProps = {
  videoId: string
  enabled: boolean
  /** ช่วงที่คนดูซ้ำมากที่สุดจากข้อมูลคลิป · ไม่มี = ไม่มีบรรทัดนี้และไม่มีป้ายบนภาพ */
  mostReplayed?: ReplaySegment[]
}

/** ส่วน "ภาพเฟรม" ของ W2 · เริ่มโหลด storyboard เมื่อ `enabled` (หลังข้อมูลคลิปมาแล้ว) */
export function FramesSection({ videoId, enabled, mostReplayed }: FramesSectionProps) {
  const storyboard = useQuery(storyboardQuery(videoId, enabled))
  const sectionRef = useRef<HTMLElement>(null)
  // รายการแทร็กซับ (cache เดียวกับป้ายแทร็กที่หัวคลิป) ใช้ตัดสินว่าเมนูภาพเฟรมมี "ดูซับช่วงนี้" ไหม
  const subtitles = useQuery(subtitlesQuery(videoId, enabled))
  const { trackId, at, update } = useVideoParams()
  const hasTrack =
    subtitles.isSuccess && subtitles.data.tracks.length > 0 && trackInEffect(subtitles.data, trackId) !== null
  // Q6 = ก: ไปแท็บทรานสคริปต์ที่บรรทัดของเวลานั้น (patch เดียว เพราะ update อ่าน URL ตอนสร้าง)
  const onViewSubs = hasTrack ? (tMs: number) => update({ tab: "transcript", at: tMs }) : undefined
  const frames = storyboard.data?.frames ?? []
  const noStoryboard =
    (storyboard.isError && storyboard.error instanceof ApiError && storyboard.error.code === "E_NO_STORYBOARD") ||
    (storyboard.isSuccess && frames.length === 0)

  let body
  if (noStoryboard) body = <NoStoryboard />
  else if (storyboard.isError) {
    body = <LoadError title={t.loadError} error={storyboard.error} onRetry={() => void storyboard.refetch()} />
  } else if (storyboard.isSuccess) {
    body = <FrameGrid frames={frames} videoId={videoId} at={at} segments={mostReplayed} onViewSubs={onViewSubs} />
  } else body = <FrameSkeleton />
  const showReplayed = storyboard.isSuccess && frames.length > 0 && (mostReplayed?.length ?? 0) > 0

  return (
    <section ref={sectionRef} aria-labelledby="frames-title">
      <Card>
        {/* จอแคบ: หัวข้อ แถวปุ่มโหลด และคำแนะนำ เรียงกันคนละบรรทัด หัวข้อจะได้ไม่ถูกบีบจนขึ้นบรรทัดใหม่ */}
        <CardHeader className="max-sm:grid-cols-1!">
          <CardTitle>
            <h2 id="frames-title" className="text-base font-medium">
              {t.title}
            </h2>
          </CardTitle>
          {/* บอกว่าภาพเฟรมทำอะไรได้บ้าง (คลิกดูใหญ่ / คลิกขวาคัดลอก-โหลด) คนที่ไม่รู้ว่าคลิกขวาได้จะได้เจอ */}
          {storyboard.isSuccess && frames.length > 0 && (
            // จอแคบ: ลงไปอยู่ใต้ปุ่มโหลดเต็มความกว้าง ไม่ถูกบีบข้างปุ่ม
            <CardDescription className="sm:col-span-1">{t.hint}</CardDescription>
          )}
          {storyboard.isSuccess && frames.length > 0 && (
            <CardAction className="max-sm:col-start-1 max-sm:row-span-1 max-sm:row-start-2 max-sm:justify-self-start">
              <BulkDownloads videoId={videoId} />
            </CardAction>
          )}
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {showReplayed && mostReplayed && (
            <ReplayedTimes
              segments={mostReplayed}
              frames={frames}
              onPick={(ms) => {
                // กดเวลาเดิมซ้ำ (at ไม่เปลี่ยน) ก็ยังพาไปที่ภาพที่ไฮไลต์อยู่
                if (ms === at) {
                  const current = sectionRef.current?.querySelector<HTMLElement>("button[data-highlighted]")
                  current?.focus({ preventScroll: true })
                  current?.scrollIntoView({ block: "center" })
                } else update({ at: ms })
              }}
            />
          )}
          {body}
        </CardContent>
      </Card>
    </section>
  )
}
