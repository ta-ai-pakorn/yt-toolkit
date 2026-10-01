import { useSyncExternalStore } from "react"

import { clampOptions, DEFAULT_PRESET, isPresetName, PRESETS } from "@/lib/sub-options"
import type { SubOptions, SubPreset } from "@/lib/types"

export const SUB_SETTINGS_KEY = "yt-toolkit.subs"

export type SubSettings = { preset: SubPreset | "custom"; options: SubOptions }

const DEFAULTS: SubSettings = { preset: DEFAULT_PRESET, options: PRESETS[DEFAULT_PRESET] }

const isNum = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value)

function isSubOptions(value: unknown): value is SubOptions {
  if (typeof value !== "object" || value === null) return false
  const o = value as Record<string, unknown>
  return (
    isNum(o.maxChars) &&
    (o.lines === 1 || o.lines === 2) &&
    isNum(o.minMs) &&
    isNum(o.maxMs) &&
    (o.mode === "chars" || o.mode === "tokens") &&
    (o.tokensPerCue === undefined || isNum(o.tokensPerCue))
  )
}

/** localStorage ที่ใช้ได้จริง หรือ null เมื่อเบราว์เซอร์บล็อก (แตะชื่อ localStorage เองก็โยน error ได้) */
export function safeLocalStorage(): Storage | null {
  try {
    return window.localStorage
  } catch {
    return null
  }
}

/** อ่านค่าที่จำไว้ ข้อมูลเสีย เวอร์ชันไม่ตรง รูปร่างผิด หรืออ่านไม่ได้ = ค่ากลาง (medium) โดยไม่โยน error */
export function loadSubSettings(storage: Pick<Storage, "getItem"> | null): SubSettings {
  try {
    const raw = storage?.getItem(SUB_SETTINGS_KEY)
    if (!raw) return DEFAULTS
    const data: unknown = JSON.parse(raw)
    if (typeof data !== "object" || data === null) return DEFAULTS
    const stored = data as { v?: unknown; preset?: unknown; custom?: unknown }
    if (stored.v !== 1) return DEFAULTS
    if (isPresetName(stored.preset)) return { preset: stored.preset, options: PRESETS[stored.preset] }
    if (stored.preset === "custom" && isSubOptions(stored.custom)) {
      return { preset: "custom", options: clampOptions(stored.custom) }
    }
    return DEFAULTS
  } catch {
    return DEFAULTS
  }
}

/** จำค่าไว้ เก็บไม่ได้ (บล็อก/เต็ม) ก็ไม่เป็นไร ค่ายังใช้ได้ในหน่วยความจำ */
export function saveSubSettings(storage: Pick<Storage, "setItem"> | null, value: SubSettings): void {
  try {
    const custom = value.preset === "custom" ? value.options : undefined
    storage?.setItem(SUB_SETTINGS_KEY, JSON.stringify({ v: 1, preset: value.preset, custom }))
  } catch {
    // เก็บไม่ได้ก็ไม่เป็นไร
  }
}

export type SubSettingsStore = {
  get: () => SubSettings
  subscribe: (listener: () => void) => () => void
  choosePreset: (preset: SubPreset) => void
  setCustom: (options: SubOptions) => void
  /** อ่านค่าจาก storage ใหม่ (อีกแท็บของเบราว์เซอร์เปลี่ยนค่า) storage ใช้ไม่ได้ = คงค่าในหน่วยความจำไว้ */
  reload: () => void
}

/**
 * ที่เก็บค่าความยาวซับก้อนเดียวของทั้งหน้า: แท็บซับและทรานสคริปต์อ่านก้อนเดียวกันเสมอ (Q4 เห็นอะไรในทรานสคริปต์
 * ได้แบบนั้นในไฟล์ .srt) แม้เบราว์เซอร์บล็อก storage ค่าที่ปรับไว้ก็อยู่ในหน่วยความจำ ไม่หายตอนสลับแท็บ
 * อ่าน storage ครั้งแรกเมื่อมีคนขอค่า · ค่าใหม่ = ก้อนใหม่ (ก้อนเดิมไม่ถูกแก้ ซับจึงสร้างใหม่เฉพาะเมื่อค่าเปลี่ยนจริง)
 */
export function createSubSettingsStore(getStorage: () => Storage | null): SubSettingsStore {
  let current: SubSettings | null = null
  const listeners = new Set<() => void>()

  const get = () => (current ??= loadSubSettings(getStorage()))
  const notify = () => listeners.forEach((listener) => listener())
  const apply = (next: SubSettings) => {
    current = next
    saveSubSettings(getStorage(), next)
    notify()
  }

  return {
    get,
    subscribe(listener) {
      listeners.add(listener)
      return () => void listeners.delete(listener)
    },
    choosePreset: (preset) => apply({ preset, options: PRESETS[preset] }),
    setCustom: (options) => apply({ preset: "custom", options: clampOptions(options) }),
    reload() {
      const storage = getStorage()
      if (!storage) return
      current = loadSubSettings(storage)
      notify()
    },
  }
}

const store = createSubSettingsStore(safeLocalStorage)

// อีกแท็บของเบราว์เซอร์เปลี่ยนค่า: แท็บนี้ตามด้วย (เดิมอ่านใหม่ทุกครั้งที่เปิดแท็บซับหรือทรานสคริปต์)
if (typeof window !== "undefined") {
  window.addEventListener("storage", (event) => {
    if (event.key === SUB_SETTINGS_KEY || event.key === null) store.reload()
  })
}

/** ตัวเลือกความยาวซับที่จำไว้ในเบราว์เซอร์ (ก้อนเดียวกันทั้งหน้า): choosePreset = เลือกสำเร็จรูป, setCustom = ค่าที่ปรับเอง */
export function useSubSettings() {
  const settings = useSyncExternalStore(store.subscribe, store.get, store.get)
  return {
    preset: settings.preset,
    options: settings.options,
    choosePreset: store.choosePreset,
    setCustom: store.setCustom,
  }
}
