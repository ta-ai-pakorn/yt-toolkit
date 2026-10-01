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
  /** ความเร็วที่ผู้ใช้ตั้งในตัวเล่น (1 = ปกติ) */
  getPlaybackRate?(): number
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
  /** iframe_api ตั้งเป็น 1 ก่อนโหลด www-widgetapi.js (ตั้งไว้แล้ว = iframe_api รอบถัดไปไม่โหลดซ้ำ) */
  loading?: number
}

type ApiWindow = {
  YT?: Partial<YTNamespace>
  onYouTubeIframeAPIReady?: () => void
  setTimeout: (handler: () => void, ms: number) => unknown
  clearTimeout: (id: never) => void
}

type ApiDocument = {
  createElement(tag: "script"): HTMLScriptElement
  head: { appendChild(node: HTMLScriptElement): unknown }
  querySelectorAll?(selector: string): ArrayLike<{ remove(): void }>
}

/** สคริปต์ส่วนที่สองที่ iframe_api โหลดต่อ (เช่น https://www.youtube.com/s/player/…/www-widgetapi.js) */
const WIDGET_API_SCRIPT = 'script[src*="www-widgetapi"]'

/**
 * ล้างของที่ iframe_api ทิ้งไว้เมื่อโหลดไม่ครบ (โหลด iframe_api ได้ แต่ www-widgetapi.js ไม่มา)
 * iframe_api ตั้ง window.YT = { loading: 1 } แล้วโหลด widgetapi และข้ามทั้งหมดถ้า YT.loading ตั้งไว้แล้ว
 * ถ้าไม่ล้าง "ลองอีกครั้ง" จะโหลด iframe_api ใหม่ที่ไม่ทำอะไรเลย และไม่มีวันเล่นได้
 */
function clearPartialApi(win: ApiWindow, doc: ApiDocument): void {
  if (!win.YT || win.YT.loaded) return
  try {
    delete win.YT
  } catch {
    // window.YT ที่ประกาศด้วย var ในสคริปต์ลบไม่ได้ (strict mode โยน error) แต่ตั้งค่าทับได้
  }
  if (win.YT) win.YT = undefined
  const scripts = doc.querySelectorAll?.(WIDGET_API_SCRIPT) ?? []
  for (const node of Array.from(scripts)) node.remove()
}

let pending: Promise<YTNamespace> | null = null

/** โหลด API (ใช้ของเดิมถ้าโหลดแล้วหรือกำลังโหลด) · reject = โหลดไม่ได้ */
export function loadYouTubeApi(
  win: ApiWindow = window as unknown as ApiWindow,
  doc: ApiDocument = document,
): Promise<YTNamespace> {
  if (win.YT?.Player && win.YT.loaded) return Promise.resolve(win.YT as YTNamespace)
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
        clearPartialApi(win, doc)
        reject(error ?? new Error("YT missing"))
      } else {
        resolve(win.YT as YTNamespace)
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
