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
    set({ flash: { ...target, n: (state.flash?.n ?? 0) + 1 } })
  },
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
  for (const listener of listeners) listener()
}
