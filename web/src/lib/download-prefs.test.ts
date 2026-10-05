import { describe, expect, it, vi } from "vitest"

import {
  createPrefsStore,
  DOWNLOAD_PREFS_KEY,
  parsePrefs,
  prefsFromSettings,
  type DownloadPrefs,
} from "./download-prefs"
import { PRESETS } from "./sub-options"
import type { Settings } from "./types"

const SETTINGS: Settings = {
  outputDir: "C:\\Users\\u\\Downloads\\YT-Toolkit",
  videoDefault: "compat-1080",
  audioDefault: "m4a",
  audioLanguage: "original",
  mp3Kbps: 192,
  subPreset: "medium",
  subCustom: PRESETS.medium,
  concurrency: 2,
  sponsorblockDefault: [],
  autoSharpFrames: true,
  captureQuality: "max",
  theme: "system",
  filenameStyle: "title",
  cookies: { enabled: false, source: null, warningAccepted: false },
  statsResetAt: null,
  lastUsed: {},
}

const DEFAULTS: DownloadPrefs = {
  v: 1,
  quality: "auto",
  maxQuality: false,
  noAudio: false,
  audioFormat: "m4a",
  mp3Kbps: 192,
  audioLanguage: "original",
}

/** localStorage ปลอมในหน่วยความจำ */
function memoryStorage(initial: Record<string, string> = {}): Storage {
  const data = new Map(Object.entries(initial))
  return {
    get length() {
      return data.size
    },
    clear: () => data.clear(),
    getItem: (key) => data.get(key) ?? null,
    key: (index) => [...data.keys()][index] ?? null,
    removeItem: (key) => void data.delete(key),
    setItem: (key, value) => void data.set(key, value),
  }
}

describe("prefsFromSettings", () => {
  it("ยังไม่โหลดการตั้งค่า = ค่ากลางของโปรแกรม", () => {
    expect(prefsFromSettings(undefined)).toEqual(DEFAULTS)
    expect(prefsFromSettings(SETTINGS)).toEqual(DEFAULTS)
  })

  it("ค่าเริ่มต้นตามการตั้งค่า", () => {
    expect(
      prefsFromSettings({
        ...SETTINGS,
        videoDefault: "max",
        audioDefault: "mp3",
        mp3Kbps: 320,
        audioLanguage: "en",
      })
    ).toEqual({
      ...DEFAULTS,
      maxQuality: true,
      audioFormat: "mp3",
      mp3Kbps: 320,
      audioLanguage: "en",
    })
    expect(
      prefsFromSettings({ ...SETTINGS, videoDefault: "compat-720" })
    ).toEqual({ ...DEFAULTS, quality: 720 })
  })
})

describe("parsePrefs", () => {
  const fallback = { ...DEFAULTS, audioFormat: "wav" as const }

  it("อ่านค่าที่จำไว้ (ตัดคีย์แปลกปลอมทิ้ง)", () => {
    const stored = {
      ...DEFAULTS,
      quality: 1080,
      noAudio: true,
      audioLanguage: "en-US",
      extra: 1,
    }
    expect(parsePrefs(JSON.stringify(stored), fallback)).toEqual({
      ...DEFAULTS,
      quality: 1080,
      noAudio: true,
      audioLanguage: "en-US",
    })
  })

  it("ว่าง เวอร์ชันไม่ตรง หรือข้อมูลเสีย = fallback", () => {
    for (const raw of [
      null,
      "",
      "not json",
      "null",
      "[]",
      "42",
      JSON.stringify({ ...DEFAULTS, v: 2 }),
      JSON.stringify({ ...DEFAULTS, v: undefined }),
      JSON.stringify({ ...DEFAULTS, quality: "1080" }),
      JSON.stringify({ ...DEFAULTS, quality: -1 }),
      JSON.stringify({ ...DEFAULTS, audioFormat: "flac" }),
      JSON.stringify({ ...DEFAULTS, mp3Kbps: 256 }),
      JSON.stringify({ ...DEFAULTS, noAudio: "yes" }),
      JSON.stringify({ ...DEFAULTS, audioLanguage: "../../etc" }),
    ]) {
      expect(parsePrefs(raw, fallback)).toBe(fallback)
    }
  })
})

describe("createPrefsStore", () => {
  it("ยังไม่เคยจำ = fallback และคืนก้อนเดิมทุกครั้งที่ค่าไม่เปลี่ยน", () => {
    const store = createPrefsStore(() => memoryStorage())
    const first = store.get(prefsFromSettings(SETTINGS))
    expect(first).toEqual(DEFAULTS)
    expect(store.get(prefsFromSettings(SETTINGS))).toBe(first)
    expect(store.get({ ...DEFAULTS, audioFormat: "mp3" }).audioFormat).toBe(
      "mp3"
    )
  })

  it("อ่านค่าที่จำไว้ใน storage", () => {
    const stored = { ...DEFAULTS, quality: 720, audioFormat: "wav" }
    const store = createPrefsStore(() =>
      memoryStorage({ [DOWNLOAD_PREFS_KEY]: JSON.stringify(stored) })
    )
    expect(store.get(DEFAULTS)).toEqual(stored)
  })

  it("set เขียน storage แจ้งผู้ฟัง และค่าใหม่ชนะ fallback", () => {
    const storage = memoryStorage()
    const store = createPrefsStore(() => storage)
    const listener = vi.fn()
    const unsubscribe = store.subscribe(listener)
    store.get(DEFAULTS)
    store.set({ quality: 1080, audioLanguage: "en" })
    expect(listener).toHaveBeenCalledTimes(1)
    const expected = { ...DEFAULTS, quality: 1080, audioLanguage: "en" }
    expect(store.get({ ...DEFAULTS, audioFormat: "mp3" })).toEqual(expected)
    expect(JSON.parse(storage.getItem(DOWNLOAD_PREFS_KEY)!)).toEqual(expected)
    unsubscribe()
    store.set({ noAudio: true })
    expect(listener).toHaveBeenCalledTimes(1)
  })

  it("storage โยน error ตอนอ่านและเขียน = ใช้หน่วยความจำอย่างเดียว ไม่โยนต่อ", () => {
    const broken = {
      getItem: () => {
        throw new Error("blocked")
      },
      setItem: () => {
        throw new Error("quota")
      },
    } as unknown as Storage
    const store = createPrefsStore(() => broken)
    expect(store.get(DEFAULTS)).toBe(DEFAULTS)
    expect(() => store.set({ audioFormat: "mp3" })).not.toThrow()
    expect(store.get(DEFAULTS)).toEqual({ ...DEFAULTS, audioFormat: "mp3" })
  })

  it("ไม่มี storage เลย (getStorage คืน null) ก็ใช้หน่วยความจำ", () => {
    const store = createPrefsStore(() => null)
    store.set({ mp3Kbps: 128 })
    expect(store.get(DEFAULTS).mp3Kbps).toBe(128)
  })

  it("reload อ่าน storage ใหม่หลังอีกแท็บเปลี่ยนค่า", () => {
    const storage = memoryStorage()
    const store = createPrefsStore(() => storage)
    store.set({ quality: 480 })
    storage.setItem(
      DOWNLOAD_PREFS_KEY,
      JSON.stringify({ ...DEFAULTS, quality: 360 })
    )
    const listener = vi.fn()
    store.subscribe(listener)
    store.reload()
    expect(listener).toHaveBeenCalledTimes(1)
    expect(store.get(DEFAULTS).quality).toBe(360)
  })
})
