import { playerAdapterHooks, type PlayerAdapter, type PlayerError } from "./player-store"
import type { YTNamespace, YTPlayer } from "./youtube-api"

/** โดเมนของตัวเล่น: แบบไม่เก็บคุกกี้ */
export const PLAYER_HOST = "https://www.youtube-nocookie.com"
/** อ่านเวลาปัจจุบันทุกเท่านี้ระหว่างเล่น */
export const POLL_MS = 250
/** หลัง seek ช่วงสั้น ๆ เวลาที่อ่านได้อาจยังเป็นตำแหน่งเก่า: ข้ามค่าที่ห่างจากจุดที่ seek เกินนี้ */
const SEEK_SETTLE_MS = 1000
const SEEK_TOLERANCE_MS = 2000

// ค่าของ YT.PlayerState (ไม่อ้าง window.YT.PlayerState ตรง ๆ: ทดสอบได้โดยไม่ต้องมีของจริง)
const YT_ENDED = 0
const YT_PLAYING = 1
const YT_PAUSED = 2

/** รหัส onError ของยูทูป → ชนิดข้อผิดพลาดของแอพ: 101/150 = เจ้าของไม่ให้ฝัง · ที่เหลือ (2, 5, 100, 153, …) = เล่นไม่ได้ */
export function mapYouTubeError(code: number): PlayerError {
  return code === 101 || code === 150 ? "embed_blocked" : "unplayable"
}

/** ที่อยู่ของ iframe ตัวเล่น (สร้าง iframe เองเพื่อใส่ referrerpolicy ได้ ยูทูปตอบ 153 ถ้าไม่มี Referer) */
export function embedUrl(videoId: string, origin: string): string {
  const params = new URLSearchParams({ enablejsapi: "1", playsinline: "1", rel: "0", origin })
  return `${PLAYER_HOST}/embed/${encodeURIComponent(videoId)}?${params.toString()}`
}

type IframeDoc = { createElement(tag: "iframe"): HTMLIFrameElement }

/** iframe ตัวเล่น (ยังไม่ผูกกับ API) */
export function createPlayerIframe(doc: IframeDoc, videoId: string, origin: string, title: string): HTMLIFrameElement {
  const iframe = doc.createElement("iframe")
  iframe.src = embedUrl(videoId, origin)
  iframe.title = title
  iframe.setAttribute("referrerpolicy", "strict-origin-when-cross-origin")
  iframe.setAttribute("allow", "autoplay; encrypted-media; picture-in-picture; fullscreen")
  iframe.setAttribute("allowfullscreen", "")
  iframe.setAttribute("frameborder", "0")
  iframe.className = "absolute inset-0 size-full border-0"
  return iframe
}

type Timers = {
  setInterval: (handler: () => void, ms: number) => unknown
  clearInterval: (id: never) => void
  now: () => number
}

const defaultTimers: Timers = {
  setInterval: (handler, ms) => window.setInterval(handler, ms),
  clearInterval: (id) => window.clearInterval(id),
  now: () => performance.now(),
}

export type YouTubeAdapter = PlayerAdapter & {
  /** ตัวเล่นพร้อมแล้ว (onReady) */
  readonly ready: boolean
}

/**
 * ผูก YT.Player กับ iframe ที่สร้างไว้ แล้วลงทะเบียนเป็น adapter ของ player-store ทันที
 * (ก่อนพร้อม คำสั่ง play/pause/seek ถูกเก็บผ่าน pendingSeekMs ของ store และ adapter ไม่ทำอะไร)
 *
 * - onReady: ใช้เวลาที่ขอไว้ (takePendingSeek) แล้วเล่น
 * - ระหว่างเล่นอ่าน currentTime ทุก ~250 ms ส่งเข้า store · หลัง seek ส่งเวลาใหม่ทันที (UI ขยับทันที)
 * - onError: แปลงรหัสแล้วแจ้ง store (store ปลด adapter เอง) · stop() = หยุดอ่านเวลา ทำลายตัวเล่น เอา iframe ออก
 */
export function createYouTubeAdapter(YT: YTNamespace, iframe: HTMLIFrameElement, timers: Timers = defaultTimers): YouTubeAdapter {
  let player: YTPlayer | null = null
  let ready = false
  let stopped = false
  let poll: unknown = null
  let lastSeek: { ms: number; at: number } | null = null
  const hooks = playerAdapterHooks

  const readMs = (): number | null => {
    if (!player || !ready) return null
    const seconds = player.getCurrentTime()
    return Number.isFinite(seconds) ? Math.max(0, Math.round(seconds * 1000)) : null
  }

  const tick = () => {
    if (stopped) return
    const ms = readMs()
    if (ms === null) return
    if (lastSeek && timers.now() - lastSeek.at < SEEK_SETTLE_MS && Math.abs(ms - lastSeek.ms) > SEEK_TOLERANCE_MS) return
    hooks.onTime(ms)
  }

  const startPolling = () => {
    if (poll === null) poll = timers.setInterval(tick, POLL_MS)
  }
  const stopPolling = () => {
    if (poll !== null) timers.clearInterval(poll as never)
    poll = null
  }

  const adapter: YouTubeAdapter = {
    get ready() {
      return ready
    },
    play() {
      if (ready && !stopped) player?.playVideo()
    },
    pause() {
      if (ready && !stopped) player?.pauseVideo()
    },
    seekTo(ms: number) {
      if (!ready || stopped || !player) return
      const target = Math.max(0, Math.round(ms))
      lastSeek = { ms: target, at: timers.now() }
      player.seekTo(target / 1000, true)
      hooks.onTime(target)
    },
    stop() {
      if (stopped) return
      stopped = true
      stopPolling()
      hooks.detach(adapter)
      try {
        player?.destroy()
      } catch {
        // ตัวเล่นถูกทำลายไปแล้ว
      }
      player = null
      iframe.remove()
    },
  }

  hooks.attach(adapter)
  player = new YT.Player(iframe, {
    events: {
      onReady: () => {
        if (stopped) return
        ready = true
        // พร้อมแล้ว: ไม่ค้างที่ "กำลังโหลด" แม้เบราว์เซอร์ไม่ยอมให้เล่นเอง (ผู้ใช้กดปุ่มเล่นของยูทูปได้)
        hooks.onStatus("paused")
        const ms = hooks.takePendingSeek()
        if (ms !== null) adapter.seekTo(ms)
        adapter.play()
      },
      onStateChange: (event) => {
        if (stopped) return
        if (event.data === YT_PLAYING) {
          hooks.onStatus("playing")
          startPolling()
        } else if (event.data === YT_PAUSED || event.data === YT_ENDED) {
          stopPolling()
          tick()
          hooks.onStatus(event.data === YT_ENDED ? "ended" : "paused")
        }
        // BUFFERING / CUED / UNSTARTED: คงสถานะเดิม
      },
      onError: (event) => {
        if (stopped) return
        stopPolling()
        hooks.onError(mapYouTubeError(event.data))
      },
    },
  })
  return adapter
}
