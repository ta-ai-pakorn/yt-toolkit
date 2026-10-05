import type { VideoInfo } from "@/lib/types"

/**
 * โหมดโรงภาพยนตร์ของหัวคลิป W2 (M5 รอบ B2 spec 1): ส่วนที่ไม่แตะ React (เทสได้ใน node)
 * ค่าที่จำไว้ (localStorage) · ตัวลดสถานะ · คลิปแนวตั้ง · เลย์เอาต์ · ปุ่ม T · การสลับด้วย View Transition
 */

export const THEATER_KEY = "yt-toolkit:theater"
/** ใส่ที่ <html> เฉพาะระหว่างสลับ: CSS ตั้งชื่อ view transition ให้ช่องตัวเล่นและคอลัมน์ข้อมูลเฉพาะช่วงนี้ */
export const SWITCHING_ATTR = "data-theater-switching"

export type TheaterState = { videoId: string | null; on: boolean }

export type TheaterAction =
  /** กด ▶ ในช่องตัวเล่น: ค่าที่จำไว้เป็นโรงภาพยนตร์ = ขยาย */
  | { type: "play"; videoId: string; preference: boolean }
  /** ปุ่มหรือปุ่ม T */
  | { type: "toggle"; videoId: string }

/** สถานะของคลิปที่เปิดอยู่: เปิดคลิปอื่น = แบบปกติจนกว่าจะกด ▶ (ค่าของคลิปเดิมไม่ติดมา) */
export function isTheaterOn(state: TheaterState, videoId: string): boolean {
  return state.videoId === videoId && state.on
}

export function theaterReducer(state: TheaterState, action: TheaterAction): TheaterState {
  const current = isTheaterOn(state, action.videoId)
  if (action.type === "toggle") return { videoId: action.videoId, on: !current }
  const on = current || action.preference
  return state.videoId === action.videoId && state.on === on ? state : { videoId: action.videoId, on }
}

export type PreferenceStorage = Pick<Storage, "getItem" | "setItem">

/** localStorage ของเบราว์เซอร์ · เบราว์เซอร์ที่ปิดการเก็บข้อมูลโยน error ตั้งแต่แตะชื่อ = null (ใช้ค่าเริ่มต้น) */
export function safeStorage(): PreferenceStorage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage
  } catch {
    return null
  }
}

/** "0" = แบบปกติ · ไม่มีค่า ค่าอื่น หรืออ่านไม่ได้ = โรงภาพยนตร์ (ค่าเริ่มต้น spec 1.1) */
export function readTheaterPreference(storage: PreferenceStorage | null): boolean {
  if (!storage) return true
  try {
    return storage.getItem(THEATER_KEY) !== "0"
  } catch {
    return true
  }
}

export function writeTheaterPreference(storage: PreferenceStorage | null, on: boolean): void {
  if (!storage) return
  try {
    storage.setItem(THEATER_KEY, on ? "1" : "0")
  } catch {
    // ที่เก็บเต็มหรือถูกปิด: ไม่จำ ครั้งหน้าใช้ค่าเริ่มต้น
  }
}

/** คลิปแนวตั้ง (Shorts/Reel): รายการภาพที่สูงที่สุด (สูงเท่ากันดูความกว้าง) รู้ความกว้างและกว้างน้อยกว่าสูง */
export function isPortraitVideo(video: Pick<VideoInfo, "video">): boolean {
  let best: VideoInfo["video"][number] | null = null
  for (const format of video.video) {
    if (best === null || format.height > best.height || (format.height === best.height && (format.width ?? 0) > (best.width ?? 0))) {
      best = format
    }
  }
  return best !== null && best.width !== undefined && best.width > 0 && best.width < best.height
}

export type HeaderLayout = "compact" | "theater-wide" | "theater-tall"

/** จอแคบ (< 640 px) เต็มความกว้างอยู่แล้ว: โหมดโรงภาพยนตร์ไม่เปลี่ยนอะไร */
export function headerLayout(o: { on: boolean; narrow: boolean; portrait: boolean }): HeaderLayout {
  if (!o.on || o.narrow) return "compact"
  return o.portrait ? "theater-tall" : "theater-wide"
}

export type KeyLike = {
  key: string
  ctrlKey: boolean
  altKey: boolean
  metaKey: boolean
  repeat: boolean
  defaultPrevented: boolean
  target: unknown
}

const EDITABLE_TAGS = new Set(["INPUT", "TEXTAREA", "SELECT"])

/** โฟกัสอยู่ในช่องกรอก (input, textarea, select, contenteditable) */
export function isEditableTarget(target: unknown): boolean {
  if (typeof target !== "object" || target === null) return false
  const node = target as { tagName?: unknown; isContentEditable?: unknown }
  return (typeof node.tagName === "string" && EDITABLE_TAGS.has(node.tagName.toUpperCase())) || node.isContentEditable === true
}

/**
 * ปุ่ม T / t สลับโหมดเมื่อ: เริ่มเล่นแล้วและจอไม่แคบ (canToggle) · ไม่มีกล่องหรือเมนูเปิดอยู่ · ไม่ได้พิมพ์อยู่ในช่องกรอก
 * · ไม่กด Ctrl/Alt/Meta · ไม่ใช่การกดค้าง · Shift ไม่นับ (Shift+T ได้ "T" ซึ่ง spec ให้ใช้ได้)
 */
export function theaterKeyAllowed(event: KeyLike, ctx: { canToggle: boolean; overlayOpen: boolean }): boolean {
  if (event.key !== "t" && event.key !== "T") return false
  if (!ctx.canToggle || ctx.overlayOpen) return false
  if (event.ctrlKey || event.altKey || event.metaKey || event.repeat || event.defaultPrevented) return false
  return !isEditableTarget(event.target)
}

export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches
}

export type TransitionDoc = {
  documentElement: { setAttribute(name: string, value: string): void; removeAttribute(name: string): void }
  startViewTransition?: (update: () => void) => { finished: Promise<unknown> }
}

/**
 * สลับเลย์เอาต์ (spec 1.3): มี document.startViewTransition และ animate = ทำผ่าน View Transition (ชื่อของช่องตัวเล่นกับคอลัมน์ข้อมูล
 * ใส่ด้วย SWITCHING_ATTR เฉพาะระหว่างนั้น) · ไม่มี API, ผู้ใช้ขอลดการเคลื่อนไหว หรือตัวเล่นลอยอยู่ (animate false) = สลับทันที
 * apply ต้องอัปเดต DOM ให้เสร็จในตัว (React: flushSync) ภาพหลังสลับจึงถูกจับหลัง DOM เปลี่ยนแล้ว
 */
export function runLayoutTransition(apply: () => void, env: { doc: TransitionDoc; animate: boolean }): void {
  const start = env.doc.startViewTransition
  if (!env.animate || typeof start !== "function") {
    apply()
    return
  }
  const root = env.doc.documentElement
  const clear = () => root.removeAttribute(SWITCHING_ATTR)
  root.setAttribute(SWITCHING_ATTR, "")
  try {
    start.call(env.doc, apply).finished.then(clear, clear)
  } catch {
    clear()
    apply()
  }
}
