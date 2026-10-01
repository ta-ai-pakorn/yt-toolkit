/**
 * โหลด YouTube IFrame Player API (https://www.youtube.com/iframe_api) ครั้งเดียวต่อหน้า
 *
 * - โหลดเมื่อมีคนกดเล่นเท่านั้น (ก่อนนั้นหน้า W2 ไม่ส่งคำขอใดไปยูทูปเลย)
 * - โหลดสำเร็จ = จำไว้ใช้ต่อ · โหลดไม่สำเร็จ (ออฟไลน์ หรือรอนานเกิน) = ลืม เพื่อให้ "ลองอีกครั้ง" โหลดใหม่ได้
 */

export const IFRAME_API_URL = "https://www.youtube.com/iframe_api"
/** รอสคริปต์นานสุดเท่านี้ แล้วถือว่าออฟไลน์ (เน็ตค้างโดยไม่ตัดขาด) */
export const API_TIMEOUT_MS = 15_000

/** ส่วนของ YT.Player ที่แอพใช้ */
export interface YTPlayer {
  playVideo(): void
  pauseVideo(): void
  seekTo(seconds: number, allowSeekAhead: boolean): void
  getCurrentTime(): number
  destroy(): void
}

export type YTEvents = {
  onReady?: (event: { target: YTPlayer }) => void
  onStateChange?: (event: { data: number; target: YTPlayer }) => void
  onError?: (event: { data: number; target: YTPlayer }) => void
}

export type YTPlayerOptions = {
  host?: string
  videoId?: string
  playerVars?: Record<string, string | number>
  events?: YTEvents
}

export interface YTNamespace {
  Player: new (element: HTMLElement | string, options: YTPlayerOptions) => YTPlayer
  loaded?: number
}

type ApiWindow = {
  YT?: YTNamespace
  onYouTubeIframeAPIReady?: () => void
  setTimeout: (handler: () => void, ms: number) => unknown
  clearTimeout: (id: never) => void
}

type ApiDocument = {
  createElement(tag: "script"): HTMLScriptElement
  head: { appendChild(node: HTMLScriptElement): unknown }
}

let pending: Promise<YTNamespace> | null = null

/** โหลด API (ใช้ของเดิมถ้าโหลดแล้วหรือกำลังโหลด) · reject = โหลดไม่ได้ */
export function loadYouTubeApi(
  win: ApiWindow = window as unknown as ApiWindow,
  doc: ApiDocument = document,
): Promise<YTNamespace> {
  if (win.YT?.Player && win.YT.loaded) return Promise.resolve(win.YT)
  if (pending) return pending
  const attempt = new Promise<YTNamespace>((resolve, reject) => {
    const script = doc.createElement("script")
    let settled = false
    const finish = (error: Error | null) => {
      if (settled) return
      settled = true
      win.clearTimeout(timer as never)
      if (error || !win.YT?.Player) {
        script.remove()
        reject(error ?? new Error("YT missing"))
      } else {
        resolve(win.YT)
      }
    }
    // ต่อจาก handler เดิม (ถ้ามีของอื่นในหน้าตั้งไว้) ไม่เขียนทับ
    const previous = win.onYouTubeIframeAPIReady
    win.onYouTubeIframeAPIReady = () => {
      previous?.()
      finish(null)
    }
    const timer = win.setTimeout(() => finish(new Error("timeout")), API_TIMEOUT_MS)
    script.src = IFRAME_API_URL
    script.async = true
    script.onerror = () => finish(new Error("offline"))
    doc.head.appendChild(script)
  })
  pending = attempt
  attempt.catch(() => {
    if (pending === attempt) pending = null
  })
  return attempt
}

/** ทดสอบเท่านั้น */
export function __resetYouTubeApiForTests(): void {
  pending = null
}
