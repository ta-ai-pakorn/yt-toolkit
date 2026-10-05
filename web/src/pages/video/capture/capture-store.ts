import { useSyncExternalStore } from "react"

/**
 * สถานะร่วมของการถ่ายภาพคมทั้งแอพ (M5 รอบ B2): ถ่ายได้ครั้งละภาพ (ทุกปุ่มใช้ busy ตัวเดียวกัน)
 * viewing = ภาพที่ต้องเปิดใหญ่ (toast "ดูภาพ" สั่งได้แม้แถบยังไม่ถูกวาด) · flash = ภาพที่เพิ่งถ่าย ให้แถบกระพริบ (n เพิ่มทุกครั้ง)
 */

export type CaptureTarget = { videoId: string; id: string }

export type CaptureUiState = {
  busy: boolean
  viewing: CaptureTarget | null
  flash: (CaptureTarget & { n: number }) | null
}

const INITIAL: CaptureUiState = { busy: false, viewing: null, flash: null }

let state: CaptureUiState = INITIAL
// เลขกระพริบเดินหน้าอย่างเดียว (ใช้แล้วลบ flash ทิ้ง ก็ยังไม่ซ้ำกับครั้งก่อน)
let flashSeq = 0
const listeners = new Set<() => void>()

function set(patch: Partial<CaptureUiState>): void {
  state = { ...state, ...patch }
  for (const listener of listeners) listener()
}

export const captureStore = {
  get: (): CaptureUiState => state,
  subscribe(listener: () => void): () => void {
    listeners.add(listener)
    return () => listeners.delete(listener)
  },
  /** จองการถ่าย · มีการถ่ายค้างอยู่ = false (ไม่ส่งคำขอซ้ำ) */
  tryBegin(): boolean {
    if (state.busy) return false
    set({ busy: true })
    return true
  },
  end(): void {
    if (state.busy) set({ busy: false })
  },
  view(target: CaptureTarget): void {
    set({ viewing: target })
  },
  closeView(): void {
    if (state.viewing) set({ viewing: null })
  },
  flash(target: CaptureTarget): void {
    flashSeq += 1
    set({ flash: { ...target, n: flashSeq } })
  },
  /** กระพริบแล้ว = ใช้ครั้งเดียว (แถบที่ถูกวาดใหม่ภายหลังจะไม่กระพริบภาพเก่าซ้ำ) · n ไม่ตรง = มีภาพใหม่กว่า ไม่แตะ */
  consumeFlash(n: number): void {
    if (state.flash?.n === n) set({ flash: null })
  },
  /** แถบของคลิป videoId ถูกวาดแล้ว: คำสั่งเปิดภาพ/กระพริบที่ค้างของคลิปอื่นไม่ใช่ของแถบนี้ ทิ้งเสีย (กดปุ่ม "ดูภาพ" ช้าจะได้ไม่เปิดภาพตอนเข้ามาดูครั้งหลัง) */
  dropOtherClips(videoId: string): void {
    const viewing = state.viewing && state.viewing.videoId !== videoId ? null : state.viewing
    const flash = state.flash && state.flash.videoId !== videoId ? null : state.flash
    if (viewing !== state.viewing || flash !== state.flash) set({ viewing, flash })
  },
  /** แถบของคลิป videoId หายไป: กระพริบที่ยังไม่ได้ใช้ของคลิปนี้ไม่ต้องรอ */
  dropFlash(videoId: string): void {
    if (state.flash?.videoId === videoId) set({ flash: null })
  },
}

/** คำสั่งเปิดภาพที่ค้างอยู่เป็นของคลิปอื่น (กดปุ่ม "ดูภาพ" ใน toast หลังเปลี่ยนไปดูคลิปอื่นแล้ว) */
export function viewsOtherClip(viewing: CaptureTarget | null, videoId: string): boolean {
  return viewing !== null && viewing.videoId !== videoId
}

/** อ่านเฉพาะค่าที่เลือก (ต้องคืน primitive หรืออ้างอิงเดิม) */
export function useCaptureUi<T>(select: (s: CaptureUiState) => T): T {
  return useSyncExternalStore(
    captureStore.subscribe,
    () => select(state),
    () => select(state),
  )
}

/** ทดสอบเท่านั้น */
export function __resetCaptureStoreForTests(): void {
  state = INITIAL
  flashSeq = 0
  for (const listener of listeners) listener()
}
