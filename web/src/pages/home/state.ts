import { useSyncExternalStore } from "react"

import type { ResolveItem, ResolveKind } from "@/lib/types"

/**
 * สถานะของหน้า W1 ที่ต้องอยู่รอดตอนไปหน้า W2 แล้วกลับมา และตอนโหลดหน้าใหม่ในแท็บเดิม:
 * ข้อความในช่อง, รายการผลล่าสุด และคลิปที่เปิดดูแล้ว (แสดงป้าย "เปิดดูแล้ว")
 *
 * เก็บในหน่วยความจำ และสำเนาลง sessionStorage (ของแท็บนี้เท่านั้น ปิดแท็บแล้วหาย)
 * sessionStorage ใช้ไม่ได้หรือเต็ม ก็ยังจำในหน่วยความจำได้ตามปกติ
 */
export type HomeState = {
  text: string
  /** null = ยังไม่ได้วิเคราะห์ (ซ่อนส่วนผล) */
  results: ResolveItem[] | null
  /** รหัสของรายการผลชุดนี้ (resolveId) ใช้ผูกเบรก E_BOT_CHECK กับรายการ */
  listId: string
  /** videoId ที่เปิดหน้า W2 แล้ว */
  opened: string[]
}

export const EMPTY_HOME: HomeState = { text: "", results: null, listId: "", opened: [] }
export const HOME_STORAGE_KEY = "yt-toolkit.home"

const KINDS: readonly ResolveKind[] = ["video", "playlist", "ambiguous", "invalid"]
const MAX_OPENED = 500

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value)

const optionalString = (value: unknown) => value === undefined || typeof value === "string"

function parseItem(value: unknown): ResolveItem | null {
  if (!isRecord(value)) return null
  const { input, kind, videoId, playlistId, isMix, error } = value
  if (typeof input !== "string" || !KINDS.includes(kind as ResolveKind)) return null
  if (!optionalString(videoId) || !optionalString(playlistId)) return null
  if (isMix !== undefined && typeof isMix !== "boolean") return null
  if (error !== undefined && !(isRecord(error) && typeof error.code === "string" && typeof error.message === "string")) {
    return null
  }
  return value as ResolveItem
}

/** อ่านสถานะที่บันทึกไว้ · ข้อมูลเสียหรือรูปร่างผิด = สถานะเริ่มต้น (แถวผลที่ผิดรูปถูกทิ้งทีละแถว) */
export function parseHomeState(raw: string | null): HomeState {
  if (!raw) return EMPTY_HOME
  let data: unknown
  try {
    data = JSON.parse(raw)
  } catch {
    return EMPTY_HOME
  }
  if (!isRecord(data) || typeof data.text !== "string") return EMPTY_HOME
  const results = Array.isArray(data.results)
    ? data.results.map(parseItem).filter((item): item is ResolveItem => item !== null)
    : null
  const opened = Array.isArray(data.opened)
    ? data.opened.filter((id): id is string => typeof id === "string").slice(-MAX_OPENED)
    : []
  return { text: data.text, results, listId: typeof data.listId === "string" ? data.listId : "", opened }
}

export type HomeStore = {
  get(): HomeState
  set(patch: Partial<HomeState>): void
  markOpened(videoId: string): void
  clear(): void
  subscribe(listener: () => void): () => void
}

export function createHomeStore(getStorage: () => Pick<Storage, "getItem" | "setItem" | "removeItem"> | null): HomeStore {
  let state: HomeState | null = null
  const listeners = new Set<() => void>()

  // ทุกการแตะ storage ห่อ try/catch: โหมดส่วนตัว/ปิดคุกกี้/พื้นที่เต็ม โยน error ได้ทั้งตอนเรียก getter และตอนเขียน
  function storage() {
    try {
      return getStorage()
    } catch {
      return null
    }
  }

  function current(): HomeState {
    if (state === null) {
      let raw: string | null
      try {
        raw = storage()?.getItem(HOME_STORAGE_KEY) ?? null
      } catch {
        raw = null
      }
      state = parseHomeState(raw)
    }
    return state
  }

  function commit(next: HomeState) {
    state = next
    try {
      const target = storage()
      if (next === EMPTY_HOME) target?.removeItem(HOME_STORAGE_KEY)
      else target?.setItem(HOME_STORAGE_KEY, JSON.stringify(next))
    } catch {
      // เก็บในหน่วยความจำอย่างเดียวก็พอ: ไปหน้าอื่นแล้วกลับมายังเห็นเหมือนเดิม แค่โหลดหน้าใหม่แล้วหาย
    }
    listeners.forEach((listener) => listener())
  }

  return {
    get: current,
    set(patch) {
      commit({ ...current(), ...patch })
    },
    markOpened(videoId) {
      const now = current()
      if (now.opened.includes(videoId)) return
      commit({ ...now, opened: [...now.opened, videoId].slice(-MAX_OPENED) })
    },
    clear() {
      commit(EMPTY_HOME)
    },
    subscribe(listener) {
      listeners.add(listener)
      return () => void listeners.delete(listener)
    },
  }
}

/** ตัวเดียวของแอพ ใช้ sessionStorage ของแท็บนี้ */
export const homeStore = createHomeStore(() => window.sessionStorage)

export function useHomeState(): HomeState {
  return useSyncExternalStore(homeStore.subscribe, homeStore.get)
}
