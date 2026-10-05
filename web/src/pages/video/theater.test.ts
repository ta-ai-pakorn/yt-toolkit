import { describe, expect, it, vi } from "vitest"

import {
  headerLayout,
  isEditableTarget,
  isPortraitVideo,
  isTheaterOn,
  readTheaterPreference,
  runLayoutTransition,
  SWITCHING_ATTR,
  THEATER_KEY,
  theaterKeyAllowed,
  theaterReducer,
  writeTheaterPreference,
  type KeyLike,
  type PreferenceStorage,
  type TheaterState,
  type TransitionDoc,
} from "./theater"

const BBB = "aqz-KE-bpKQ"
const THAI = "88o5Sk8_m1Y"
const START: TheaterState = { videoId: null, on: false }

describe("theaterReducer", () => {
  it("▶ กับค่าที่จำไว้เป็นโรงภาพยนตร์ = ขยาย · ค่าที่จำไว้เป็นแบบปกติ = คงเดิม", () => {
    expect(theaterReducer(START, { type: "play", videoId: BBB, preference: true })).toEqual({ videoId: BBB, on: true })
    expect(theaterReducer(START, { type: "play", videoId: BBB, preference: false })).toEqual({ videoId: BBB, on: false })
  })

  it("ปุ่ม/T สลับ · ▶ ซ้ำตอนขยายอยู่ไม่ย่อแม้ค่าที่จำไว้เป็นแบบปกติ", () => {
    const on = theaterReducer(START, { type: "toggle", videoId: BBB })
    expect(on).toEqual({ videoId: BBB, on: true })
    expect(theaterReducer(on, { type: "play", videoId: BBB, preference: false })).toBe(on)
    expect(theaterReducer(on, { type: "toggle", videoId: BBB })).toEqual({ videoId: BBB, on: false })
  })

  it("เปิดคลิปอื่น = แบบปกติจนกว่าจะกด ▶", () => {
    const on: TheaterState = { videoId: BBB, on: true }
    expect(isTheaterOn(on, BBB)).toBe(true)
    expect(isTheaterOn(on, THAI)).toBe(false)
    expect(theaterReducer(on, { type: "toggle", videoId: THAI })).toEqual({ videoId: THAI, on: true })
    expect(theaterReducer(on, { type: "play", videoId: THAI, preference: false })).toEqual({ videoId: THAI, on: false })
  })
})

function memory(initial?: string): PreferenceStorage & { items: Map<string, string> } {
  const items = new Map<string, string>()
  if (initial !== undefined) items.set(THEATER_KEY, initial)
  return {
    items,
    getItem: (key: string) => items.get(key) ?? null,
    setItem: (key: string, value: string) => void items.set(key, value),
  }
}

const throwing: PreferenceStorage = {
  getItem: () => {
    throw new Error("blocked")
  },
  setItem: () => {
    throw new Error("blocked")
  },
}

describe("ค่าที่จำไว้", () => {
  it("ไม่มีค่า = โรงภาพยนตร์ · '0' = แบบปกติ · '1' = โรงภาพยนตร์", () => {
    expect(readTheaterPreference(memory())).toBe(true)
    expect(readTheaterPreference(memory("0"))).toBe(false)
    expect(readTheaterPreference(memory("1"))).toBe(true)
  })

  it("เขียน '1' / '0' ใต้ key yt-toolkit:theater", () => {
    const storage = memory()
    writeTheaterPreference(storage, false)
    expect(storage.items.get("yt-toolkit:theater")).toBe("0")
    writeTheaterPreference(storage, true)
    expect(storage.items.get("yt-toolkit:theater")).toBe("1")
  })

  it("ที่เก็บใช้ไม่ได้ (null หรือโยน error) = โรงภาพยนตร์ และเขียนไม่พัง", () => {
    expect(readTheaterPreference(null)).toBe(true)
    expect(readTheaterPreference(throwing)).toBe(true)
    expect(() => writeTheaterPreference(throwing, false)).not.toThrow()
    expect(() => writeTheaterPreference(null, false)).not.toThrow()
  })
})

const fmt = (height: number, width?: number) => ({ formatId: `f${height}x${width ?? 0}`, height, width, fps: 30, vcodec: "avc1", compat: true })

describe("isPortraitVideo", () => {
  it("ดูรายการที่สูงที่สุด ต้องรู้ความกว้างและกว้างน้อยกว่าสูง", () => {
    expect(isPortraitVideo({ video: [] })).toBe(false)
    expect(isPortraitVideo({ video: [fmt(1080, 1920), fmt(720, 1280)] })).toBe(false)
    expect(isPortraitVideo({ video: [fmt(1920, 1080), fmt(1280, 720)] })).toBe(true)
    expect(isPortraitVideo({ video: [fmt(1920)] })).toBe(false)
    expect(isPortraitVideo({ video: [fmt(1080, 1920), fmt(1280, 720)] })).toBe(true)
    expect(isPortraitVideo({ video: [fmt(1080, 1080)] })).toBe(false)
  })
})

describe("headerLayout", () => {
  it("ปิด หรือจอแคบ = แบบปกติ · แนวนอน = กว้าง · แนวตั้ง = สูง", () => {
    expect(headerLayout({ on: false, narrow: false, portrait: false })).toBe("compact")
    expect(headerLayout({ on: true, narrow: true, portrait: false })).toBe("compact")
    expect(headerLayout({ on: true, narrow: false, portrait: false })).toBe("theater-wide")
    expect(headerLayout({ on: true, narrow: false, portrait: true })).toBe("theater-tall")
  })
})

describe("ปุ่ม T", () => {
  const key = (patch: Partial<KeyLike> = {}): KeyLike => ({
    key: "t",
    ctrlKey: false,
    altKey: false,
    metaKey: false,
    repeat: false,
    defaultPrevented: false,
    target: { tagName: "BODY" },
    ...patch,
  })
  const ready = { canToggle: true, overlayOpen: false }

  it("t และ T สลับได้ (Shift ไม่นับเป็นปุ่มเสริม)", () => {
    expect(theaterKeyAllowed(key(), ready)).toBe(true)
    expect(theaterKeyAllowed(key({ key: "T" }), ready)).toBe(true)
    expect(theaterKeyAllowed(key({ key: "y" }), ready)).toBe(false)
  })

  it("ยังไม่เล่น/จอแคบ หรือมีกล่อง/เมนูเปิดอยู่ = ไม่สลับ", () => {
    expect(theaterKeyAllowed(key(), { canToggle: false, overlayOpen: false })).toBe(false)
    expect(theaterKeyAllowed(key(), { canToggle: true, overlayOpen: true })).toBe(false)
  })

  it("Ctrl/Alt/Meta กดค้าง หรือมีคนจัดการไปแล้ว = ไม่สลับ", () => {
    for (const patch of [{ ctrlKey: true }, { altKey: true }, { metaKey: true }, { repeat: true }, { defaultPrevented: true }]) {
      expect(theaterKeyAllowed(key(patch), ready)).toBe(false)
    }
  })

  it("พิมพ์อยู่ในช่องกรอก = ไม่สลับ", () => {
    for (const target of [{ tagName: "INPUT" }, { tagName: "textarea" }, { tagName: "SELECT" }, { tagName: "DIV", isContentEditable: true }]) {
      expect(isEditableTarget(target)).toBe(true)
      expect(theaterKeyAllowed(key({ target }), ready)).toBe(false)
    }
    expect(isEditableTarget(null)).toBe(false)
    expect(isEditableTarget({ tagName: "BUTTON" })).toBe(false)
  })
})

describe("runLayoutTransition", () => {
  function fakeDoc(withApi: boolean, fail = false) {
    const attrs = new Map<string, string>()
    let settle: () => void = () => undefined
    const finished = new Promise<void>((resolve, reject) => {
      settle = fail ? () => reject(new Error("skipped")) : resolve
    })
    const start = vi.fn((update: () => void) => {
      update()
      return { finished }
    })
    const doc: TransitionDoc = {
      documentElement: { setAttribute: (name, value) => void attrs.set(name, value), removeAttribute: (name) => void attrs.delete(name) },
      ...(withApi ? { startViewTransition: start } : {}),
    }
    return { doc, attrs, start, settle: () => settle() }
  }

  it("ไม่มี API = สลับทันที ไม่ใส่ชื่อ", () => {
    const { doc, attrs } = fakeDoc(false)
    const apply = vi.fn()
    runLayoutTransition(apply, { doc, animate: true })
    expect(apply).toHaveBeenCalledOnce()
    expect(attrs.size).toBe(0)
  })

  it("ลดการเคลื่อนไหวหรือตัวเล่นลอย (animate false) = สลับทันทีแม้มี API", () => {
    const { doc, start } = fakeDoc(true)
    const apply = vi.fn()
    runLayoutTransition(apply, { doc, animate: false })
    expect(apply).toHaveBeenCalledOnce()
    expect(start).not.toHaveBeenCalled()
  })

  it("มี API: ใส่ชื่อระหว่างสลับ แล้วเอาออกเมื่อจบ", async () => {
    const { doc, attrs, start, settle } = fakeDoc(true)
    const apply = vi.fn()
    runLayoutTransition(apply, { doc, animate: true })
    expect(start).toHaveBeenCalledOnce()
    expect(apply).toHaveBeenCalledOnce()
    expect(attrs.has(SWITCHING_ATTR)).toBe(true)
    settle()
    await vi.waitFor(() => expect(attrs.has(SWITCHING_ATTR)).toBe(false))
  })

  it("transition ถูกข้าม (reject) ก็เอาชื่อออก", async () => {
    const { doc, attrs, settle } = fakeDoc(true, true)
    runLayoutTransition(() => undefined, { doc, animate: true })
    settle()
    await vi.waitFor(() => expect(attrs.has(SWITCHING_ATTR)).toBe(false))
  })
})
