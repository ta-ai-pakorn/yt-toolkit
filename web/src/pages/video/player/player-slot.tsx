import { cn } from "cn"
import { ArrowUpToLine, Play, X } from "lucide-react"
import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react"

import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import { fill, th } from "@/i18n/th"
import type { VideoInfo } from "@/lib/types"
import { Thumbnail } from "@/pages/home/thumbnail"

import { PlayerErrorView } from "./player-error"
import { playerActions, playerAdapterHooks, usePlayerValue, type PlayerStatus } from "./player-store"
import { stopReel, useReelStatus } from "./reel"
import { ReelButton } from "./reel-button"
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

/** เห็นช่องตัวเล่นน้อยกว่าครึ่งหนึ่ง = ลอย (ช่องที่เหลือในจอจึงเห็นปกจาง ๆ "กำลังเล่นที่มุมจอ" ให้กดกลับได้) */
const VISIBLE_RATIO = 0.5

/** ช่องตัวเล่นอยู่ในจอหรือไม่ (IntersectionObserver) · เบราว์เซอร์ไม่มี IO = ถือว่าอยู่ในจอ (ไม่ลอย) */
function useInView(ref: RefObject<HTMLElement | null>): boolean {
  const [inView, setInView] = useState(true)
  useEffect(() => {
    const node = ref.current
    if (!node || typeof IntersectionObserver === "undefined") return
    // ช่องสูงคงที่ตอนลอย (ตัวเล่นออกไปเป็น position: fixed) สัดส่วนจึงขึ้นกับการเลื่อนจออย่างเดียว ไม่สลับไปมาเอง
    const observer = new IntersectionObserver(
      ([entry]) => setInView(entry.isIntersecting && entry.intersectionRatio >= VISIBLE_RATIO),
      { threshold: [0, VISIBLE_RATIO, 1] },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [ref])
  return inView
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
  usePlayerIframe(host, videoId, title)
  useDockSpace(docked, wrapper)
  const reelStatus = useReelStatus()

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
          {reelStatus && (
            <span className="flex min-w-0 items-center gap-1 px-1 text-xs text-muted-foreground tabular">
              {reelStatus}
              <Button variant="ghost" size="xs" onClick={stopReel} className="max-sm:h-11">
                {t.reelStop}
              </Button>
            </span>
          )}
          <div className="ml-auto flex items-center gap-1 max-sm:ml-0 max-sm:justify-end">
            <Button variant="ghost" size="sm" className="max-sm:h-11" onClick={() => scrollToHeader(boxRef.current)}>
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
 * - ผิดพลาด: ข้อความในช่อง (ดู PlayerErrorView)
 * ใต้ตัวเล่น: แถบไทม์ไลน์ (เฉพาะตอนอยู่ในหัวคลิปและเคยเล่นแล้ว) และปุ่ม "เล่นเฉพาะช่วงที่ดูซ้ำบ่อย"
 * จอแคบ: ช่องอยู่คอลัมน์แคบข้างชื่อคลิป ส่วนแถบไทม์ไลน์กับปุ่มลงไปเต็มความกว้างแถวถัดไป (กดง่ายกว่า)
 */
export function PlayerSlot({ video, className }: { video: VideoInfo; className?: string }) {
  const { videoId, title, thumbnailUrl } = video
  const storeVideoId = usePlayerValue((s) => s.videoId)
  const status = usePlayerValue((s) => s.status)
  const started = usePlayerValue((s) => s.started)
  const error = usePlayerValue((s) => s.error)
  const mine = storeVideoId === videoId
  const active = mine && ACTIVE.has(status)
  const boxRef = useRef<HTMLDivElement>(null)
  const playRef = useRef<HTMLButtonElement>(null)
  const inView = useInView(boxRef)
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
    <div className={cn("max-sm:contents sm:flex sm:w-72 sm:shrink-0 sm:flex-col sm:gap-2", className)}>
      <div
        ref={boxRef}
        tabIndex={-1}
        data-slot="player-slot"
        className={cn("relative w-full rounded-md outline-none", failed ? "sm:aspect-video" : "aspect-video")}
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
            title={title}
            thumbnailUrl={thumbnailUrl}
            docked={docked}
            loading={status === "loading"}
            boxRef={boxRef}
            onClose={close}
          />
        )}
      </div>
      <PlayerControls video={video} timeline={active && started && !docked} />
    </div>
  )
}

function PlayerControls({ video, timeline }: { video: VideoInfo; timeline: boolean }) {
  const durationMs = Math.max(0, video.durationS) * 1000
  const hasReel = (video.mostReplayed?.length ?? 0) > 0
  if (!(timeline && durationMs > 0) && !hasReel) return null
  return (
    <div className="flex flex-col gap-2 max-sm:col-span-2 max-sm:row-start-2">
      <Timeline durationMs={durationMs} chapters={video.chapters} replayed={video.mostReplayed} visible={timeline} />
      <ReelButton ranges={video.mostReplayed} />
    </div>
  )
}
