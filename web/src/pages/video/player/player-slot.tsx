import { cn } from "cn"
import { ArrowUpToLine, Play, X } from "lucide-react"
import { useCallback, useEffect, useLayoutEffect, useRef, type RefObject } from "react"

import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import { fill, th } from "@/i18n/th"
import type { VideoInfo } from "@/lib/types"
import { Thumbnail } from "@/pages/home/thumbnail"

import { PlayerErrorView } from "./player-error"
import { playerActions, playerAdapterHooks, usePlayerValue, type PlayerStatus } from "./player-store"
import { ReelStatus } from "./reel-button"
import { Timeline } from "./timeline"
import { createPlayerIframe, createYouTubeAdapter, type YouTubeAdapter } from "./youtube-adapter"
import { loadYouTubeApi } from "./youtube-api"

const t = th.player

/** สถานะที่ต้องมีตัวเล่น (iframe) อยู่ */
const ACTIVE: ReadonlySet<PlayerStatus> = new Set(["loading", "playing", "paused", "ended"])

const reducedMotion = () => typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches

/** เลื่อนกลับบนสุดของหน้า (ตัวเล่นกลับเข้าช่องในหัวคลิปเอง) แล้วโฟกัสช่องตัวเล่น */
function scrollToHeader(box: HTMLElement | null) {
  window.scrollTo({ top: 0, behavior: reducedMotion() ? "auto" : "smooth" })
  box?.focus({ preventScroll: true })
}

/**
 * ตอนลอย: เว้นที่ท้ายหน้าเท่าความสูงตัวเล่นลอย (ไม่บังเนื้อหาล่างสุด)
 * ตั้ง html[data-player-docked] กับ --player-dock-h ส่วนกฎ padding อยู่ใน index.css (บวก --dock-bottom-offset ให้แถบคิวของ M4)
 */
function useDockSpace(docked: boolean, ref: RefObject<HTMLElement | null>) {
  useLayoutEffect(() => {
    const node = ref.current
    if (!docked || !node) return
    const root = document.documentElement
    const update = () => root.style.setProperty("--player-dock-h", `${Math.ceil(node.getBoundingClientRect().height)}px`)
    update()
    root.setAttribute("data-player-docked", "")
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update)
    observer?.observe(node)
    return () => {
      observer?.disconnect()
      root.removeAttribute("data-player-docked")
      root.style.removeProperty("--player-dock-h")
    }
  }, [docked, ref])
}

/**
 * สร้าง iframe ตัวเล่นใน host เมื่อ mount (โหลด API ก่อนถ้ายังไม่โหลด) แล้วทำลายเมื่อ unmount
 * iframe ถูกใส่ใน host ครั้งเดียว ไม่ย้ายที่ (ย้าย iframe = โหลดใหม่) การลอยมุมจอเปลี่ยนแค่ CSS ของกล่องที่ครอบ
 */
function usePlayerIframe(host: RefObject<HTMLDivElement | null>, videoId: string, title: string) {
  const titleRef = useRef(title)
  useEffect(() => {
    titleRef.current = title
  }, [title])
  useEffect(() => {
    let cancelled = false
    let adapter: YouTubeAdapter | null = null
    loadYouTubeApi().then(
      (YT) => {
        const node = host.current
        if (cancelled || !node) return
        const iframe = createPlayerIframe(document, videoId, window.location.origin, fill(t.iframeTitle, { title: titleRef.current }))
        node.appendChild(iframe)
        adapter = createYouTubeAdapter(YT, iframe)
      },
      () => {
        if (!cancelled) playerAdapterHooks.onError("offline")
      },
    )
    return () => {
      cancelled = true
      adapter?.stop()
    }
  }, [host, videoId])
}

type FrameProps = {
  videoId: string
  title: string
  thumbnailUrl: string
  docked: boolean
  loading: boolean
  boxRef: RefObject<HTMLDivElement | null>
  onClose: () => void
}

/**
 * กล่องครอบตัวเล่น: ในหัวคลิป = เต็มช่องปก · ลอย = position: fixed มุมขวาล่าง (จอกว้าง ~320 px)
 * หรือแถบเต็มความกว้างล่างจอ (จอแคบ < 640 px วิดีโอราว 40% ของความกว้าง)
 * เป็น element เดิมตลอด (เปลี่ยนแค่ class) iframe ข้างในจึงไม่ถูกย้ายและไม่โหลดใหม่
 */
function PlayerFrame({ videoId, title, thumbnailUrl, docked, loading, boxRef, onClose }: FrameProps) {
  const host = useRef<HTMLDivElement>(null)
  const wrapper = useRef<HTMLDivElement>(null)
  const backToTop = useRef<HTMLButtonElement>(null)
  usePlayerIframe(host, videoId, title)
  useDockSpace(docked, wrapper)

  return (
    <div
      ref={wrapper}
      data-slot="player-frame"
      data-docked={docked ? "" : undefined}
      role={docked ? "region" : undefined}
      aria-label={docked ? t.dockRegion : undefined}
      className={cn(
        "overflow-hidden bg-black",
        docked
          ? "fixed right-4 bottom-[calc(1rem+var(--dock-bottom-offset))] z-40 flex w-80 flex-col rounded-lg border border-border bg-background shadow-2xl motion-safe:animate-in motion-safe:fade-in-0 motion-safe:slide-in-from-bottom-4 max-sm:inset-x-0 max-sm:bottom-[var(--dock-bottom-offset)] max-sm:w-auto max-sm:flex-row max-sm:items-center max-sm:rounded-none max-sm:border-x-0 max-sm:border-b-0"
          : "absolute inset-0 rounded-md",
      )}
    >
      <div
        ref={host}
        data-slot="player-host"
        className={cn("relative bg-black", docked ? "aspect-video w-full shrink-0 max-sm:w-[40%]" : "size-full")}
      >
        {loading && (
          <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center">
            {thumbnailUrl && <Thumbnail src={thumbnailUrl} className="absolute inset-0 size-full rounded-none opacity-50" />}
            <Spinner aria-label={t.loading} className="relative size-6 text-white" />
          </div>
        )}
      </div>
      {docked && (
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1 p-1.5 max-sm:flex-col max-sm:items-stretch max-sm:p-2">
          <ReelStatus size="xs" className="gap-1 px-1" buttonClassName="max-sm:h-11" fallbackFocus={() => backToTop.current} />
          <div className="ml-auto flex items-center gap-1 max-sm:ml-0 max-sm:justify-end">
            <Button ref={backToTop} variant="ghost" size="sm" className="max-sm:h-11" onClick={() => scrollToHeader(boxRef.current)}>
              <ArrowUpToLine aria-hidden />
              {t.backToTop}
            </Button>
            <Button variant="ghost" size="icon-sm" aria-label={t.close} title={t.close} className="max-sm:size-11" onClick={onClose}>
              <X aria-hidden />
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * ช่องตัวเล่นที่หัวคลิป (แทนที่ปกเดิม ขนาดเท่าเดิม)
 * - ยังไม่เล่น: ปก + ปุ่ม ▶ "เล่นคลิป" ตรงกลาง (ยังไม่โหลดอะไรจากยูทูปจนกว่าจะกด)
 * - เล่นแล้ว: ตัวเล่นยูทูปในกล่องเดิม · เลื่อนจอจนช่องพ้นจอ = ตัวเล่นลอยมุมจอ ช่องว่างเหลือปกจาง ๆ "กำลังเล่นที่มุมจอ"
 *   สั่งเล่นจากที่อื่น (ภาพเฟรม ทรานสคริปต์) ตอนช่องพ้นจออยู่แล้ว = ลอยทันทีตั้งแต่กำลังโหลด
 * - ผิดพลาด: ข้อความในช่อง (ดู PlayerErrorView)
 * แถวไทม์ไลน์ใต้ตัวเล่นแยกเป็น PlayerControls (หัวคลิปวางเองตามความกว้างจอ ให้ลำดับ DOM ตรงกับที่ตาเห็น)
 * inView: ช่องนี้อยู่ในจอไหม หัวคลิปวัดเอง (useSlotInView กับกล่องที่ได้จาก onBox) แล้วส่งให้ทั้งช่องนี้และ PlayerControls
 */
export function PlayerSlot({
  video,
  inView,
  onBox,
  className,
}: {
  video: VideoInfo
  inView: boolean
  onBox?: (node: HTMLDivElement | null) => void
  className?: string
}) {
  const { videoId, thumbnailUrl } = video
  const storeVideoId = usePlayerValue((s) => s.videoId)
  const status = usePlayerValue((s) => s.status)
  const started = usePlayerValue((s) => s.started)
  const error = usePlayerValue((s) => s.error)
  const mine = storeVideoId === videoId
  const active = mine && ACTIVE.has(status)
  const boxRef = useRef<HTMLDivElement | null>(null)
  const setBox = useCallback(
    (node: HTMLDivElement | null) => {
      boxRef.current = node
      onBox?.(node)
    },
    [onBox],
  )
  const playRef = useRef<HTMLButtonElement>(null)
  const docked = active && started && !inView
  const failed = mine && status === "error" && error !== null

  // ปิดตัวเล่นแล้วโฟกัสปุ่ม ▶ (ปุ่มปิดหายไปพร้อมตัวเล่นลอย โฟกัสไม่หลุดไป body)
  const focusPlay = useRef(false)
  useEffect(() => {
    if (status === "idle" && focusPlay.current) {
      focusPlay.current = false
      playRef.current?.focus({ preventScroll: true })
    }
  }, [status])
  const close = () => {
    focusPlay.current = true
    playerActions.close()
  }

  return (
    <div
      ref={setBox}
      tabIndex={-1}
      data-slot="player-slot"
      className={cn("relative w-full rounded-md outline-none", failed ? "sm:aspect-video" : "aspect-video", className)}
    >
      {failed ? (
        <div className="sm:absolute sm:inset-0">
          <PlayerErrorView videoId={videoId} error={error} />
        </div>
      ) : !active ? (
        <button
          ref={playRef}
          type="button"
          aria-label={t.play}
          data-slot="player-play"
          onClick={() => playerActions.playFrom()}
          className="group/play absolute inset-0 block cursor-pointer rounded-md outline-none hover:ring-2 hover:ring-ring/40 focus-visible:ring-3 focus-visible:ring-ring"
        >
          <Thumbnail src={thumbnailUrl} className="size-full" />
          <span aria-hidden className="pointer-events-none absolute inset-0 flex items-center justify-center">
            <span className="flex size-12 items-center justify-center rounded-full bg-black/70 text-white shadow-md transition-transform group-hover/play:scale-110 group-focus-visible/play:scale-110 motion-reduce:transition-none max-sm:size-10">
              <Play className="ml-0.5 size-6 fill-current max-sm:size-5" />
            </span>
          </span>
        </button>
      ) : null}
      {docked && (
        <button
          type="button"
          data-slot="player-docked-placeholder"
          onClick={() => scrollToHeader(boxRef.current)}
          className="absolute inset-0 block cursor-pointer overflow-hidden rounded-md outline-none focus-visible:ring-3 focus-visible:ring-ring"
        >
          <Thumbnail src={thumbnailUrl} className="size-full opacity-35" />
          <span className="absolute inset-0 flex items-center justify-center p-1 text-center text-sm font-medium text-foreground max-sm:text-xs">
            {t.playingInCorner}
          </span>
        </button>
      )}
      {active && (
        <PlayerFrame
          videoId={videoId}
          title={video.title}
          thumbnailUrl={thumbnailUrl}
          docked={docked}
          loading={status === "loading"}
          boxRef={boxRef}
          onClose={close}
        />
      )}
    </div>
  )
}

/**
 * แถวใต้ตัวเล่นในหัวคลิป: แถบไทม์ไลน์ + "ช่วง i จาก n" กับปุ่มหยุด (ตอนเล่นช่วงไฮไลต์)
 * มีเฉพาะหลังเริ่มเล่นและตัวเล่นอยู่ในหัวคลิป (ลอยอยู่ = ไม่มี สถานะช่วงไฮไลต์ไปอยู่บนตัวเล่นลอยแทน)
 * ก่อนเล่นไม่จองที่ไว้ หัวคลิปก่อนเล่นจึงสูงเท่ากันทุกคลิป (ปุ่มช่วงไฮไลต์อยู่ในแถวปุ่มของหัวคลิป)
 */
export function PlayerControls({ video, inView, className }: { video: VideoInfo; inView: boolean; className?: string }) {
  const storeVideoId = usePlayerValue((s) => s.videoId)
  const status = usePlayerValue((s) => s.status)
  const started = usePlayerValue((s) => s.started)
  const reel = usePlayerValue((s) => s.reel !== null)
  const row = useRef<HTMLDivElement>(null)
  const active = storeVideoId === video.videoId && ACTIVE.has(status)
  const durationMs = Math.max(0, video.durationS) * 1000
  const timeline = durationMs > 0
  // ลอยอยู่ (เริ่มเล่นแล้วแต่ช่องพ้นจอ) = ไม่มีแถวนี้ · เงื่อนไขเดียวกับ docked ของ PlayerSlot
  if (!active || !started || !inView || !(timeline || reel)) return null
  return (
    <div ref={row} data-slot="player-controls" className={cn("flex flex-col gap-2", className)}>
      {timeline && <Timeline durationMs={durationMs} chapters={video.chapters} replayed={video.mostReplayed} visible />}
      <ReelStatus
        buttonClassName="max-sm:h-11"
        // ปุ่มหยุดหายไป: โฟกัสแถบไทม์ไลน์ในแถวเดียวกัน (ไม่มีแถบ = ปุ่มช่วงไฮไลต์ในแถวปุ่ม)
        fallbackFocus={() =>
          row.current?.querySelector<HTMLElement>('[role="slider"]') ?? document.querySelector<HTMLElement>('[data-slot="player-reel"]')
        }
      />
    </div>
  )
}
