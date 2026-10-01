import { describe, expect, it, vi } from "vitest"

import { PRESETS } from "@/lib/sub-options"
import {
  createSubSettingsStore,
  loadSubSettings,
  saveSubSettings,
  SUB_SETTINGS_KEY,
  type SubSettings,
} from "./subs-settings"

const store = (value: string | null) => ({ getItem: vi.fn(() => value) })
const medium: SubSettings = { preset: "medium", options: PRESETS.medium }

describe("loadSubSettings", () => {
  it("ไม่มี storage หรือยังไม่เคยจำ = ค่ากลาง", () => {
    expect(loadSubSettings(null)).toEqual(medium)
    expect(loadSubSettings(store(null))).toEqual(medium)
  })

  it("อ่านชื่อสำเร็จรูปที่จำไว้", () => {
    expect(loadSubSettings(store('{"v":1,"preset":"short"}'))).toEqual({ preset: "short", options: PRESETS.short })
    expect(loadSubSettings(store('{"v":1,"preset":"long"}'))).toEqual({ preset: "long", options: PRESETS.long })
    expect(loadSubSettings(store('{"v":1,"preset":"word"}'))).toEqual({ preset: "word", options: PRESETS.word })
  })

  it("ค่าที่ปรับเองได้ preset custom และถูกบีบให้อยู่ในช่วง", () => {
    const custom = { maxChars: 30, lines: 2, minMs: 1000, maxMs: 6000, mode: "chars" }
    expect(loadSubSettings(store(JSON.stringify({ v: 1, preset: "custom", custom })))).toEqual({
      preset: "custom",
      options: custom,
    })
    const wild = { ...custom, maxChars: 999, minMs: 5, maxMs: 10 }
    expect(loadSubSettings(store(JSON.stringify({ v: 1, preset: "custom", custom: wild }))).options).toMatchObject({
      maxChars: 60,
      minMs: 300,
      maxMs: 1000,
    })
  })

  it("JSON เสีย เวอร์ชันไม่ตรง หรือรูปร่างผิด = ค่ากลาง", () => {
    for (const raw of [
      "not json",
      "null",
      "[]",
      '{"v":2,"preset":"short"}',
      '{"preset":"short"}',
      '{"v":1,"preset":"huge"}',
      '{"v":1,"preset":"custom"}',
      '{"v":1,"preset":"custom","custom":{"maxChars":"30"}}',
      '{"v":1,"preset":"custom","custom":{"maxChars":30,"lines":3,"minMs":1,"maxMs":2,"mode":"chars"}}',
    ]) {
      expect(loadSubSettings(store(raw))).toEqual(medium)
    }
  })

  it("getItem โยน error ก็ได้ค่ากลาง ไม่โยนต่อ", () => {
    const boom = {
      getItem: () => {
        throw new Error("blocked")
      },
    }
    expect(loadSubSettings(boom)).toEqual(medium)
  })
})

describe("saveSubSettings", () => {
  it("เขียนรูปแบบ {v:1,…} ลงคีย์ yt-toolkit.subs", () => {
    const setItem = vi.fn()
    saveSubSettings({ setItem }, { preset: "short", options: PRESETS.short })
    expect(setItem).toHaveBeenCalledWith(SUB_SETTINGS_KEY, '{"v":1,"preset":"short"}')
    expect(SUB_SETTINGS_KEY).toBe("yt-toolkit.subs")
  })

  it("preset custom เก็บค่าที่ปรับเองไว้ด้วย และอ่านกลับได้เท่าเดิม", () => {
    const options = { maxChars: 30, lines: 2 as const, minMs: 1000, maxMs: 6000, mode: "chars" as const }
    let saved = ""
    saveSubSettings({ setItem: (_k: string, v: string) => (saved = v) }, { preset: "custom", options })
    expect(JSON.parse(saved)).toEqual({ v: 1, preset: "custom", custom: options })
    expect(loadSubSettings(store(saved))).toEqual({ preset: "custom", options })
  })

  it("setItem โยน error ก็กลืน ไม่โยนต่อ และ storage เป็น null ก็ไม่เป็นไร", () => {
    const boom = {
      setItem: () => {
        throw new Error("quota")
      },
    }
    expect(() => saveSubSettings(boom, medium)).not.toThrow()
    expect(() => saveSubSettings(null, medium)).not.toThrow()
  })
})

/** localStorage ปลอมในหน่วยความจำ (ใช้แค่ getItem/setItem) */
function memoryStorage(initial: Record<string, string> = {}): Storage {
  const data = new Map(Object.entries(initial))
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
  } as unknown as Storage
}

const custom = { maxChars: 18, lines: 2 as const, minMs: 900, maxMs: 4000, mode: "chars" as const }

describe("createSubSettingsStore", () => {
  it("storage ถูกบล็อก: ค่าที่ปรับเองอยู่ในหน่วยความจำ ทุกคนที่อ่าน (แท็บซับ + ทรานสคริปต์) ได้ก้อนเดียวกัน", () => {
    const store = createSubSettingsStore(() => null)
    expect(store.get()).toEqual(medium)
    store.setCustom(custom)
    // เปิดแท็บทรานสคริปต์ทีหลัง (อ่านใหม่) ยังได้ค่าที่ปรับเอง ไม่ถอยกลับเป็นกลาง
    expect(store.get()).toEqual({ preset: "custom", options: custom })
    expect(store.get()).toBe(store.get())
  })

  it("แจ้งผู้ฟังทุกคนเมื่อค่าเปลี่ยน · ถอนการฟังแล้วไม่ได้รับแจ้ง · ค่าใหม่เป็นก้อนใหม่", () => {
    const store = createSubSettingsStore(() => null)
    const first = vi.fn()
    const second = vi.fn()
    const off = store.subscribe(first)
    store.subscribe(second)
    const before = store.get()
    store.choosePreset("short")
    expect(first).toHaveBeenCalledTimes(1)
    expect(second).toHaveBeenCalledTimes(1)
    expect(store.get()).not.toBe(before)
    expect(store.get()).toEqual({ preset: "short", options: PRESETS.short })
    off()
    store.choosePreset("long")
    expect(first).toHaveBeenCalledTimes(1)
    expect(second).toHaveBeenCalledTimes(2)
  })

  it("อ่านค่าที่จำไว้ครั้งแรก และเขียนลง storage เมื่อเปลี่ยน", () => {
    const storage = memoryStorage({ [SUB_SETTINGS_KEY]: '{"v":1,"preset":"long"}' })
    const store = createSubSettingsStore(() => storage)
    expect(store.get()).toEqual({ preset: "long", options: PRESETS.long })
    store.setCustom(custom)
    expect(loadSubSettings(storage)).toEqual({ preset: "custom", options: custom })
  })

  it("reload: อ่านค่าที่อีกแท็บของเบราว์เซอร์เขียนไว้ · storage ใช้ไม่ได้ = คงค่าในหน่วยความจำ", () => {
    const storage = memoryStorage()
    const store = createSubSettingsStore(() => storage)
    expect(store.get()).toEqual(medium)
    storage.setItem(SUB_SETTINGS_KEY, '{"v":1,"preset":"short"}')
    const listener = vi.fn()
    store.subscribe(listener)
    store.reload()
    expect(listener).toHaveBeenCalledTimes(1)
    expect(store.get()).toEqual({ preset: "short", options: PRESETS.short })

    const blocked = createSubSettingsStore(() => null)
    blocked.setCustom(custom)
    blocked.reload()
    expect(blocked.get()).toEqual({ preset: "custom", options: custom })
  })
})
