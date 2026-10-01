import { useQuery } from "@tanstack/react-query"
import { Captions, Copy, Download, ExternalLink, Flame, ImageIcon, ImageOff, Link2 } from "lucide-react"
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type RefObject } from "react"
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
import { formatTimecode, youtubeLinkAt, youtubeWatchUrl } from "@/lib/format"
import type { ReplaySegment, StoryboardFrame } from "@/lib/types"

import { errorMessage } from "./errors"
import { nearestFrameIndex, revealAndFocus } from "./frame-target"
import { FrameLightbox } from "./lightbox"
import { LoadError } from "./load-error"
import { replayedFrameIndexes } from "./most-replayed"
import { ReplayedMark } from "./replayed-mark"
import { storyboardQuery } from "./queries"
import { subtitlesQuery } from "./subs-queries"
import { trackInEffect } from "./track-label"
import { useVideoParams } from "./url-state"

const t = th.frames

/** grid 6 คอลัมน์ (จอแคบ 3 คอลัมน์) แสดงทุกภาพตั้งแต่แรก ไม่ต้องกด "ดูทั้งหมด" */
const SKELETON_CELLS = 6
const GRID = "grid grid-cols-3 gap-2 sm:grid-cols-6"
// จอแคบ (มือถือ) ปุ่มในแถวเครื่องมือสูง 44 px ให้นิ้วกดได้ง่าย (แบบเดียวกับแท็บข้อมูลคลิป)
const TOUCH = "max-sm:h-11"

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

/** เปิดลิงก์ยูทูปในแท็บใหม่ แยกจากหน้านี้ (noopener, noreferrer) */
function openInYoutube(url: string): void {
  window.open(url, "_blank", "noopener,noreferrer")
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

// ภาพในช่วงที่คนดูซ้ำบ่อย (owner round 5): กรอบอำพันสด (--primary) 2px "ด้านในภาพ" + เส้นเข้มบาง 1px ด้านในอีกชั้น
// ให้เห็นได้ทั้งบนภาพสว่างและภาพมืด · ต่างจากกรอบ ?at= (เส้นนอกภาพ เว้นช่อง 1px) และวงโฟกัส (วงนอกภาพ 3px)
// จึงเห็นซ้อนกันได้ทั้งสามแบบ · ป้าย "ดูซ้ำบ่อย" มุมขวาบนบอกความหมายเป็นคำ ไม่พึ่งสีอย่างเดียว
const REPLAYED_FRAME =
  "pointer-events-none absolute inset-0 rounded-md shadow-[inset_0_0_0_2px_var(--primary),inset_0_0_0_3px_rgb(0_0_0/0.45)]"

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
            {replayed && <span aria-hidden data-replayed-frame="" className={REPLAYED_FRAME} />}
            {replayed && <ReplayedMark variant="badge" className="pointer-events-none absolute top-1 right-1" />}
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
        <ContextMenuItem onClick={() => openInYoutube(youtubeWatchUrl(videoId, frame.tMs))}>
          <ExternalLink aria-hidden />
          {t.openYoutubeAt}
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
  /** ตำแหน่ง (ใน frames) ของภาพที่มีป้าย "ดูซ้ำบ่อย" เรียงตามลำดับ */
  marked: readonly number[]
  /** เปิดตัวกรอง "ดูซ้ำบ่อย" อยู่: เห็นเฉพาะภาพใน marked */
  filtered: boolean
  /** ปิดตัวกรอง (ใช้เมื่อภาพของเวลาใน URL ถูกตัวกรองซ่อนอยู่) */
  onUnfilter: () => void
  onViewSubs?: (tMs: number) => void
}

function FrameGrid({ frames, videoId, at, marked, filtered, onUnfilter, onViewSubs }: FrameGridProps) {
  // ภาพที่เห็นในตาราง (ตำแหน่งใน frames): เปิดตัวกรอง = เฉพาะภาพที่มีป้าย ไม่งั้นทุกภาพ
  // ตำแหน่งในตาราง ภาพใหญ่ (←/→) และโฟกัส นับตามภาพที่เห็นเท่านั้น ภาพที่ถูกกรองออกจึงถูกข้ามไป
  const shown = useMemo(() => (filtered ? [...marked] : frames.map((_, index) => index)), [filtered, marked, frames])
  const shownFrames = useMemo(() => shown.map((index) => frames[index]), [shown, frames])
  const markedSet = useMemo(() => new Set(marked), [marked])
  // ภาพที่เปิดดูใหญ่อยู่ (ตำแหน่งใน shownFrames) · null = ปิด
  const [viewing, setViewing] = useState<number | null>(null)
  const openerRef = useRef<number>(0)
  const buttons = useRef(new Map<number, HTMLButtonElement>())
  // ภาพของเวลาใน URL: หาจากทุกภาพ (เวลาตรงภาพจริงเสมอ) แล้วดูว่าอยู่ตำแหน่งไหนของภาพที่เห็น
  // เลื่อนมาให้เห็นตรงกลางและโฟกัสครั้งเดียวต่อค่า at (เลือกภาพอื่นต่อได้โดยไม่ถูกดึงกลับ)
  const target = at === null ? -1 : nearestFrameIndex(frames, at)
  const highlighted = target < 0 ? -1 : shown.indexOf(target)
  const hiddenTarget = target >= 0 && highlighted < 0
  const revealed = useRef<number | null>(null)

  // ภาพของเวลาใน URL ถูกตัวกรองซ่อนอยู่ (เวลาใหม่จาก chapter หรือบรรทัดทรานสคริปต์นอกช่วงระหว่างที่กรองอยู่ หรือเปิดหน้า
  // ด้วย ?at=…&replayed=1): ปิดตัวกรองให้เห็นภาพนั้น · การกดเปิดตัวกรองเองล้าง at ไปพร้อมกัน จึงไม่เข้าเงื่อนไขนี้
  useEffect(() => {
    if (hiddenTarget) onUnfilter()
  }, [hiddenTarget, onUnfilter])

  // ชุดภาพที่เห็นเปลี่ยน (เปิด/ปิดตัวกรอง) = ปิดภาพใหญ่ ตำแหน่งเดิมจะได้ไม่ชี้ผิดภาพ
  const [viewingSet, setViewingSet] = useState(shownFrames)
  if (viewingSet !== shownFrames) {
    setViewingSet(shownFrames)
    if (viewing !== null) setViewing(null)
  }

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
        {shownFrames.map((frame, position) => (
          <FrameTile
            key={frame.index}
            frame={frame}
            videoId={videoId}
            highlighted={position === highlighted}
            replayed={markedSet.has(shown[position])}
            onViewSubs={onViewSubs && (() => onViewSubs(frame.tMs))}
            onOpen={() => {
              openerRef.current = position
              setViewing(position)
            }}
            buttonRef={(element) => {
              if (element) buttons.current.set(position, element)
              else buttons.current.delete(position)
            }}
          />
        ))}
      </ul>
      <FrameLightbox frames={shownFrames} index={viewing} onIndexChange={setViewing} returnFocus={returnFocus} />
    </div>
  )
}

/**
 * ปุ่มเปิด/ปิดตัวกรอง "ดูซ้ำบ่อย (n ภาพ)" (aria-pressed) ข้างปุ่มโหลด · ไอคอนเดียวกับป้ายบนภาพ
 * เปิดอยู่ = พื้นอำพันจาง กรอบอำพันเข้ม · สถานะเก็บใน URL (?replayed=1)
 */
function ReplayedFilterButton({ count, pressed, onToggle }: { count: number; pressed: boolean; onToggle: () => void }) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            variant="outline"
            size="sm"
            aria-pressed={pressed}
            onClick={onToggle}
            className="max-sm:h-11 aria-pressed:border-accent-text aria-pressed:bg-primary/15 dark:aria-pressed:border-accent-text dark:aria-pressed:bg-primary/15"
          />
        }
      >
        <Flame aria-hidden className="text-accent-text" />
        {fill(t.replayedFilter, { n: count })}
      </TooltipTrigger>
      <TooltipContent>{t.replayedFilterHint}</TooltipContent>
    </Tooltip>
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
              className={TOUCH}
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
        className={TOUCH}
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

type FramesSectionProps = {
  videoId: string
  enabled: boolean
  /** ช่วงที่คนดูซ้ำมากที่สุดจากข้อมูลคลิป · ไม่มี = ไม่มีป้ายบนภาพ (ปุ่มเวลาของช่วงอยู่ในแท็บข้อมูลคลิป) */
  mostReplayed?: ReplaySegment[]
}

/** ส่วน "ภาพเฟรม" ของ W2 · เริ่มโหลด storyboard เมื่อ `enabled` (หลังข้อมูลคลิปมาแล้ว) */
export function FramesSection({ videoId, enabled, mostReplayed }: FramesSectionProps) {
  const storyboard = useQuery(storyboardQuery(videoId, enabled))
  // รายการแทร็กซับ (cache เดียวกับป้ายแทร็กที่หัวคลิป) ใช้ตัดสินว่าเมนูภาพเฟรมมี "ดูซับช่วงนี้" ไหม
  const subtitles = useQuery(subtitlesQuery(videoId, enabled))
  const { trackId, at, replayed, update } = useVideoParams()
  const hasTrack =
    subtitles.isSuccess && subtitles.data.tracks.length > 0 && trackInEffect(subtitles.data, trackId) !== null
  // Q6 = ก: ไปแท็บทรานสคริปต์ที่บรรทัดของเวลานั้น (patch เดียว เพราะ update อ่าน URL ตอนสร้าง)
  const onViewSubs = hasTrack ? (tMs: number) => update({ tab: "transcript", at: tMs }) : undefined
  const frames = useMemo(() => storyboard.data?.frames ?? [], [storyboard.data])
  // ภาพที่มีป้าย "ดูซ้ำบ่อย" (รวมภาพแทนของช่วงสั้นที่ไม่มีภาพอยู่ข้างใน) คิดครั้งเดียวต่อชุดภาพ
  const marked = useMemo(() => replayedFrameIndexes(frames, mostReplayed), [frames, mostReplayed])
  // ?replayed=1 แต่คลิปไม่มีช่วงหรือไม่มีภาพในช่วง = ไม่สนใจ (เห็นทุกภาพ ไม่มีปุ่ม)
  const filtered = replayed && marked.length > 0
  const unfilter = useCallback(() => update({ replayed: false }), [update])
  const noStoryboard =
    (storyboard.isError && storyboard.error instanceof ApiError && storyboard.error.code === "E_NO_STORYBOARD") ||
    (storyboard.isSuccess && frames.length === 0)

  let body
  if (noStoryboard) body = <NoStoryboard />
  else if (storyboard.isError) {
    body = <LoadError title={t.loadError} error={storyboard.error} onRetry={() => void storyboard.refetch()} />
  } else if (storyboard.isSuccess) {
    body = (
      <FrameGrid
        frames={frames}
        videoId={videoId}
        at={at}
        marked={marked}
        filtered={filtered}
        onUnfilter={unfilter}
        onViewSubs={onViewSubs}
      />
    )
  } else body = <FrameSkeleton />

  return (
    <section aria-labelledby="frames-title">
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
              {/* ตัวกรองไม่มีผลกับไฟล์ที่โหลด: .zip และภาพรวมเฟรมได้ทุกภาพเสมอ */}
              <div className="flex flex-wrap items-center gap-2">
                {marked.length > 0 && (
                  <ReplayedFilterButton
                    count={marked.length}
                    pressed={filtered}
                    // เปิดตัวกรอง = ล้างเวลาที่ไฮไลต์ไว้ (?at=) ในก้าวเดียวกัน ไม่งั้นภาพของเวลานั้นที่อยู่นอกช่วง
                    // จะทำให้ตัวกรองปิดตัวเองทันที (ปุ่มดูเหมือนกดไม่ติด) · ปิดตัวกรองไม่แตะเวลา
                    onToggle={() => update(filtered ? { replayed: false } : { replayed: true, at: null })}
                  />
                )}
                <BulkDownloads videoId={videoId} />
              </div>
            </CardAction>
          )}
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {body}
        </CardContent>
      </Card>
    </section>
  )
}
