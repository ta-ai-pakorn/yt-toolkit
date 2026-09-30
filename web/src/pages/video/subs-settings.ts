import { useCallback, useState } from "react"

import { clampOptions, DEFAULT_PRESET, PRESETS } from "@/lib/sub-options"
import type { SubOptions, SubPreset } from "@/lib/types"

export const SUB_SETTINGS_KEY = "yt-toolkit.subs"

export type SubSettings = { preset: SubPreset | "custom"; options: SubOptions }

const DEFAULTS: SubSettings = { preset: DEFAULT_PRESET, options: PRESETS[DEFAULT_PRESET] }

function isPreset(value: unknown): value is SubPreset {
  return value === "short" || value === "medium" || value === "long"
}

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
    if (isPreset(stored.preset)) return { preset: stored.preset, options: PRESETS[stored.preset] }
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

/** ตัวเลือกความยาวซับที่จำไว้ในเบราว์เซอร์: choosePreset = เลือกสำเร็จรูป, setCustom = ค่าที่ปรับเอง */
export function useSubSettings() {
  const [settings, setSettings] = useState<SubSettings>(() => loadSubSettings(safeLocalStorage()))

  const apply = useCallback((next: SubSettings) => {
    setSettings(next)
    saveSubSettings(safeLocalStorage(), next)
  }, [])

  const choosePreset = useCallback(
    (preset: SubPreset) => apply({ preset, options: PRESETS[preset] }),
    [apply],
  )
  const setCustom = useCallback(
    (options: SubOptions) => apply({ preset: "custom", options: clampOptions(options) }),
    [apply],
  )

  return { preset: settings.preset, options: settings.options, choosePreset, setCustom }
}
