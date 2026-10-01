import { useSyncExternalStore } from "react"

import { AUTO_QUALITY } from "./download-options"
import type { Settings } from "./types"

/**
 * ตัวเลือกการโหลดครั้งล่าสุดของแท็บวิดีโอ/เสียง (จำในเบราว์เซอร์ BRD 10.8 #6)
 * quality จำเป็นความสูงของภาพ (ไม่ใช่ formatId) คลิปอื่นจึงใช้ตัวเลือกที่สูงเท่ากันได้ ไม่มีก็กลับเป็น "auto"
 */
export type DownloadPrefs = {
  v: 1
  quality: "auto" | number
  maxQuality: boolean
  noAudio: boolean
  audioFormat: "m4a" | "mp3" | "wav"
  mp3Kbps: 128 | 192 | 320
  audioLanguage: string
}

export const DOWNLOAD_PREFS_KEY = "yt-toolkit.download"

/** ค่าเริ่มต้นจากการตั้งค่า (ยังไม่โหลดการตั้งค่า = ค่ากลางของโปรแกรม) · compat-720 = เริ่มที่ภาพ 720p */
export function prefsFromSettings(s: Settings | undefined): DownloadPrefs {
  return {
    v: 1,
    quality: s?.videoDefault === "compat-720" ? 720 : AUTO_QUALITY,
    maxQuality: s?.videoDefault === "max",
    noAudio: false,
    audioFormat: s?.audioDefault ?? "m4a",
    mp3Kbps: s?.mp3Kbps ?? 192,
    audioLanguage: s?.audioLanguage ?? "original",
  }
}

const LANGUAGE = /^(original|[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*)$/

function isPrefs(value: unknown): value is DownloadPrefs {
  if (typeof value !== "object" || value === null) return false
  const o = value as Record<string, unknown>
  return (
    o.v === 1 &&
    (o.quality === AUTO_QUALITY ||
      (typeof o.quality === "number" &&
        Number.isInteger(o.quality) &&
        o.quality > 0)) &&
    typeof o.maxQuality === "boolean" &&
    typeof o.noAudio === "boolean" &&
    (o.audioFormat === "m4a" ||
      o.audioFormat === "mp3" ||
      o.audioFormat === "wav") &&
    (o.mp3Kbps === 128 || o.mp3Kbps === 192 || o.mp3Kbps === 320) &&
    typeof o.audioLanguage === "string" &&
    LANGUAGE.test(o.audioLanguage)
  )
}

/** อ่านค่าที่จำไว้: ว่าง JSON เสีย เวอร์ชันไม่ตรง หรือรูปร่างผิด = fallback ทั้งก้อน (ไม่โยน error) */
export function parsePrefs(
  raw: string | null,
  fallback: DownloadPrefs
): DownloadPrefs {
  if (!raw) return fallback
  try {
    const data: unknown = JSON.parse(raw)
    if (!isPrefs(data)) return fallback
    const {
      v,
      quality,
      maxQuality,
      noAudio,
      audioFormat,
      mp3Kbps,
      audioLanguage,
    } = data
    return {
      v,
      quality,
      maxQuality,
      noAudio,
      audioFormat,
      mp3Kbps,
      audioLanguage,
    }
  } catch {
    return fallback
  }
}

export type PrefsStore = {
  get(fallback: DownloadPrefs): DownloadPrefs
  set(patch: Partial<DownloadPrefs>): void
  subscribe(fn: () => void): () => void
  /** ลืมค่าในหน่วยความจำแล้วอ่าน storage ใหม่ (อีกแท็บของเบราว์เซอร์เปลี่ยนค่า) */
  reload(): void
}

/**
 * ที่เก็บตัวเลือกการโหลด: ค่าที่ set แล้วอยู่ในหน่วยความจำเสมอ (storage ถูกบล็อกหรือเต็มก็ยังใช้ได้จนปิดแท็บ)
 * get คืนก้อนเดิมตราบที่ค่าไม่เปลี่ยน (useSyncExternalStore ต้องการแบบนี้ ไม่งั้น render วนไม่จบ)
 */
export function createPrefsStore(getStorage: () => Storage | null): PrefsStore {
  let memory: DownloadPrefs | null = null
  let cache: {
    raw: string | null
    fallbackKey: string
    value: DownloadPrefs
  } | null = null
  let lastFallback: DownloadPrefs = prefsFromSettings(undefined)
  const listeners = new Set<() => void>()

  const readRaw = (): string | null => {
    try {
      return getStorage()?.getItem(DOWNLOAD_PREFS_KEY) ?? null
    } catch {
      return null
    }
  }

  const get = (fallback: DownloadPrefs): DownloadPrefs => {
    lastFallback = fallback
    if (memory !== null) return memory
    const raw = readRaw()
    const fallbackKey = JSON.stringify(fallback)
    if (
      cache === null ||
      cache.raw !== raw ||
      cache.fallbackKey !== fallbackKey
    ) {
      cache = { raw, fallbackKey, value: parsePrefs(raw, fallback) }
    }
    return cache.value
  }

  const notify = () => listeners.forEach((listener) => listener())

  return {
    get,
    set(patch) {
      const next: DownloadPrefs = { ...get(lastFallback), ...patch, v: 1 }
      memory = next
      try {
        getStorage()?.setItem(DOWNLOAD_PREFS_KEY, JSON.stringify(next))
      } catch {
        // เก็บไม่ได้ (บล็อก/เต็ม) ก็ไม่เป็นไร ค่ายังอยู่ในหน่วยความจำ
      }
      notify()
    },
    subscribe(listener) {
      listeners.add(listener)
      return () => void listeners.delete(listener)
    },
    reload() {
      if (getStorage() === null) return
      memory = null
      cache = null
      notify()
    },
  }
}

function safeLocalStorage(): Storage | null {
  try {
    return window.localStorage
  } catch {
    return null
  }
}

export const downloadPrefs: PrefsStore = createPrefsStore(safeLocalStorage)

if (typeof window !== "undefined") {
  window.addEventListener("storage", (event) => {
    if (event.key === DOWNLOAD_PREFS_KEY || event.key === null)
      downloadPrefs.reload()
  })
}

/** ตัวเลือกการโหลดที่จำไว้ (ยังไม่เคยจำ = fallback จากการตั้งค่า) และฟังก์ชันจำค่าใหม่ */
export function useDownloadPrefs(
  fallback: DownloadPrefs
): [DownloadPrefs, (patch: Partial<DownloadPrefs>) => void] {
  const snapshot = () => downloadPrefs.get(fallback)
  const prefs = useSyncExternalStore(
    downloadPrefs.subscribe,
    snapshot,
    snapshot
  )
  return [prefs, downloadPrefs.set]
}
