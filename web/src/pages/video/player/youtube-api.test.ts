import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { __resetYouTubeApiForTests, API_TIMEOUT_MS, IFRAME_API_URL, loadYouTubeApi, type YTNamespace } from "./youtube-api"

type FakeScript = { src: string; async: boolean; onerror: (() => void) | null; remove: () => void; removed: boolean }

function env() {
  const scripts: FakeScript[] = []
  const win = {
    YT: undefined as YTNamespace | undefined,
    onYouTubeIframeAPIReady: undefined as (() => void) | undefined,
    setTimeout: (handler: () => void, ms: number) => setTimeout(handler, ms),
    clearTimeout: (id: never) => clearTimeout(id),
  }
  const doc = {
    createElement: () => {
      const script: FakeScript = {
        src: "",
        async: false,
        onerror: null,
        removed: false,
        remove() {
          script.removed = true
        },
      }
      return script as unknown as HTMLScriptElement
    },
    head: { appendChild: (node: HTMLScriptElement) => scripts.push(node as unknown as FakeScript) },
  }
  const ready = () => {
    win.YT = { Player: class {} as unknown as YTNamespace["Player"], loaded: 1 }
    win.onYouTubeIframeAPIReady?.()
  }
  return { win, doc, scripts, ready }
}

beforeEach(() => {
  vi.useFakeTimers()
  __resetYouTubeApiForTests()
})

afterEach(() => {
  vi.useRealTimers()
})

describe("loadYouTubeApi", () => {
  it("ใส่สคริปต์ครั้งเดียว · เรียกซ้ำระหว่างโหลดได้ promise เดิม · โหลดเสร็จ resolve เป็น YT", async () => {
    const e = env()
    const a = loadYouTubeApi(e.win, e.doc)
    const b = loadYouTubeApi(e.win, e.doc)
    expect(a).toBe(b)
    expect(e.scripts).toHaveLength(1)
    expect(e.scripts[0].src).toBe(IFRAME_API_URL)
    e.ready()
    await expect(a).resolves.toBe(e.win.YT)
    // โหลดแล้ว: ไม่ใส่สคริปต์ใหม่
    await loadYouTubeApi(e.win, e.doc)
    expect(e.scripts).toHaveLength(1)
  })

  it("ต่อ handler onYouTubeIframeAPIReady เดิม ไม่เขียนทับ", async () => {
    const e = env()
    const previous = vi.fn()
    e.win.onYouTubeIframeAPIReady = previous
    const promise = loadYouTubeApi(e.win, e.doc)
    e.ready()
    await promise
    expect(previous).toHaveBeenCalledTimes(1)
  })

  it("โหลดไม่ได้ (onerror) = reject เอาสคริปต์ออก แล้วลองใหม่ได้", async () => {
    const e = env()
    const first = loadYouTubeApi(e.win, e.doc)
    e.scripts[0].onerror?.()
    await expect(first).rejects.toThrow("offline")
    expect(e.scripts[0].removed).toBe(true)
    const second = loadYouTubeApi(e.win, e.doc)
    expect(second).not.toBe(first)
    expect(e.scripts).toHaveLength(2)
    e.ready()
    await expect(second).resolves.toBe(e.win.YT)
  })

  it("รอนานเกินกำหนด = reject (ถือว่าออฟไลน์)", async () => {
    const e = env()
    const promise = loadYouTubeApi(e.win, e.doc)
    vi.advanceTimersByTime(API_TIMEOUT_MS)
    await expect(promise).rejects.toThrow("timeout")
  })

  it("โหลด iframe_api ได้แต่ www-widgetapi.js ไม่มา (YT = { loading: 1 } ค้าง) → ล้าง YT และสคริปต์ widgetapi · ลองใหม่โหลดได้จริง", async () => {
    const e = env()
    const widget = { removed: false, remove: () => (widget.removed = true) }
    const other = { removed: false, remove: () => (other.removed = true) }
    const selectors: string[] = []
    const doc = {
      ...e.doc,
      querySelectorAll: (selector: string) => {
        selectors.push(selector)
        return selector.includes("www-widgetapi") ? [widget] : [other]
      },
    }
    const first = loadYouTubeApi(e.win, doc)
    // iframe_api ทำงานแล้ว: ตั้ง YT.loading แล้วใส่สคริปต์ widgetapi ซึ่งโหลดไม่สำเร็จ ไม่มีใครเรียก onYouTubeIframeAPIReady
    ;(e.win as { YT?: unknown }).YT = { loading: 1, loaded: 0 }
    vi.advanceTimersByTime(API_TIMEOUT_MS)
    await expect(first).rejects.toThrow("timeout")
    expect(e.win.YT).toBeUndefined()
    expect(widget.removed).toBe(true)
    expect(other.removed).toBe(false)
    expect(selectors.every((selector) => selector.includes("www-widgetapi"))).toBe(true)

    // ลองอีกครั้ง: ใส่ iframe_api ใหม่ (ซึ่งจะเห็นว่าไม่มี YT แล้วโหลด widgetapi ใหม่) และเล่นได้
    const second = loadYouTubeApi(e.win, doc)
    expect(e.scripts).toHaveLength(2)
    e.ready()
    await expect(second).resolves.toBe(e.win.YT)
  })

  it("YT ที่โหลดครบแล้ว (loaded = 1) ไม่ถูกล้างแม้ผิดพลาด", async () => {
    const e = env()
    const promise = loadYouTubeApi(e.win, e.doc)
    const loaded = { loaded: 1 }
    ;(e.win as { YT?: unknown }).YT = loaded
    vi.advanceTimersByTime(API_TIMEOUT_MS)
    await expect(promise).rejects.toThrow("timeout")
    expect(e.win.YT).toBe(loaded)
  })
})
