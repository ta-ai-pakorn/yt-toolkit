import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { __resetPlayerForTests, getPlayerState, playerActions } from "./player-store"
import { createPlayerIframe, createYouTubeAdapter, embedUrl, mapYouTubeError, POLL_MS } from "./youtube-adapter"
import type { YTEvents, YTNamespace, YTPlayerOptions } from "./youtube-api"

/** YT.Player ปลอม: จดคำสั่ง และให้เทสต์ยิง event เองได้ */
class MockPlayer {
  static last: MockPlayer | null = null
  calls: string[] = []
  seconds = 0
  events: YTEvents
  element: unknown
  constructor(element: unknown, options: YTPlayerOptions) {
    this.element = element
    this.events = options.events ?? {}
    MockPlayer.last = this
  }
  playVideo() {
    this.calls.push("play")
  }
  pauseVideo() {
    this.calls.push("pause")
  }
  seekTo(seconds: number) {
    this.calls.push(`seek:${seconds}`)
    this.seconds = seconds
  }
  getCurrentTime() {
    return this.seconds
  }
  destroy() {
    this.calls.push("destroy")
  }
  ready() {
    this.events.onReady?.({ target: this })
  }
  state(data: number) {
    this.events.onStateChange?.({ data, target: this })
  }
  error(data: number) {
    this.events.onError?.({ data, target: this })
  }
}

const YT = { Player: MockPlayer, loaded: 1 } as unknown as YTNamespace

let now = 0
const timers = {
  setInterval: (handler: () => void, ms: number) => setInterval(handler, ms),
  clearInterval: (id: never) => clearInterval(id),
  now: () => now,
}

function setup() {
  const iframe = { remove: vi.fn() } as unknown as HTMLIFrameElement
  const adapter = createYouTubeAdapter(YT, iframe, timers)
  const player = MockPlayer.last as MockPlayer
  return { adapter, player, iframe }
}

beforeEach(() => {
  vi.useFakeTimers()
  now = 0
  __resetPlayerForTests()
  playerActions.reset("vid")
})

afterEach(() => {
  vi.useRealTimers()
})

describe("mapYouTubeError", () => {
  it("101/150 = เจ้าของไม่ให้ฝัง · ที่เหลือ = เล่นไม่ได้", () => {
    expect(mapYouTubeError(101)).toBe("embed_blocked")
    expect(mapYouTubeError(150)).toBe("embed_blocked")
    for (const code of [2, 5, 100, 153, 999]) expect(mapYouTubeError(code)).toBe("unplayable")
  })
})

describe("iframe", () => {
  it("youtube-nocookie + enablejsapi + playsinline + rel=0 + origin · referrerpolicy", () => {
    const url = new URL(embedUrl("abc-_1", "http://127.0.0.1:8799"))
    expect(url.origin).toBe("https://www.youtube-nocookie.com")
    expect(url.pathname).toBe("/embed/abc-_1")
    expect(Object.fromEntries(url.searchParams)).toEqual({
      enablejsapi: "1",
      playsinline: "1",
      rel: "0",
      origin: "http://127.0.0.1:8799",
    })
    const attrs: Record<string, string> = {}
    const fake = { setAttribute: (k: string, v: string) => (attrs[k] = v) } as unknown as HTMLIFrameElement
    const iframe = createPlayerIframe({ createElement: () => fake }, "abc", "http://x", "ตัวเล่นคลิป: ชื่อ")
    expect(iframe.title).toBe("ตัวเล่นคลิป: ชื่อ")
    expect(attrs.referrerpolicy).toBe("strict-origin-when-cross-origin")
    expect(attrs.allow).toContain("autoplay")
  })
})

describe("createYouTubeAdapter", () => {
  it("พร้อมแล้ว: seek ไปเวลาที่ขอไว้แล้วเล่น", () => {
    playerActions.playFrom(30_000)
    const { player } = setup()
    expect(getPlayerState().status).toBe("loading")
    player.ready()
    expect(player.calls).toEqual(["seek:30", "play"])
    expect(getPlayerState().currentMs).toBe(30_000)
    expect(getPlayerState().pendingSeekMs).toBeNull()
    expect(getPlayerState().status).toBe("paused")
    player.state(1)
    expect(getPlayerState().status).toBe("playing")
  })

  it("ก่อนพร้อม คำสั่งของ store ไม่ไปถึงตัวเล่น (เก็บเป็น pendingSeek)", () => {
    playerActions.playFrom()
    const { player } = setup()
    playerActions.playFrom(5000)
    playerActions.pause()
    expect(player.calls).toEqual([])
    player.ready()
    expect(player.calls).toEqual(["seek:5", "play"])
  })

  it("ระหว่างเล่นอ่านเวลาทุก 250 ms · pause แล้วหยุดอ่าน", () => {
    playerActions.playFrom()
    const { player } = setup()
    player.ready()
    player.state(1)
    player.seconds = 12.3456
    vi.advanceTimersByTime(POLL_MS)
    expect(getPlayerState().currentMs).toBe(12_346)
    player.seconds = 20
    player.state(2)
    expect(getPlayerState()).toMatchObject({ status: "paused", currentMs: 20_000 })
    player.seconds = 40
    vi.advanceTimersByTime(POLL_MS * 4)
    expect(getPlayerState().currentMs).toBe(20_000)
  })

  it("seekTo ส่งเวลาใหม่เข้า store ทันที · ค่าเก่าที่ค้างหลัง seek ถูกข้าม", () => {
    playerActions.playFrom()
    const { adapter, player } = setup()
    player.ready()
    player.state(1)
    adapter.seekTo(90_000)
    expect(getPlayerState().currentMs).toBe(90_000)
    player.seconds = 10 // ตัวเล่นยังรายงานตำแหน่งเก่า
    vi.advanceTimersByTime(POLL_MS)
    expect(getPlayerState().currentMs).toBe(90_000)
    now = 2000
    vi.advanceTimersByTime(POLL_MS)
    expect(getPlayerState().currentMs).toBe(10_000)
  })

  it("ช่วงไฮไลต์: ถึงท้ายช่วงแล้วตัวเล่น seek ไปช่วงถัดไป", () => {
    playerActions.playReel([
      { startMs: 10_000, endMs: 20_000 },
      { startMs: 50_000, endMs: 55_000 },
    ])
    const { player } = setup()
    player.ready()
    player.state(1)
    expect(player.calls).toEqual(["seek:10", "play"])
    now = 5000
    player.seconds = 20.1
    vi.advanceTimersByTime(POLL_MS)
    expect(player.calls.at(-1)).toBe("seek:50")
    expect(getPlayerState().reel?.index).toBe(1)
    now = 10_000
    player.seconds = 55
    vi.advanceTimersByTime(POLL_MS)
    expect(player.calls.at(-1)).toBe("pause")
    expect(getPlayerState().reel).toBeNull()
  })

  it("onError แปลงรหัสแล้วแจ้ง store", () => {
    playerActions.playFrom(4000)
    const { player } = setup()
    player.ready()
    player.error(150)
    expect(getPlayerState()).toMatchObject({ status: "error", error: "embed_blocked", errorAtMs: 4000 })
  })

  it("stop: ทำลายตัวเล่น เอา iframe ออก ปลดจาก store · เรียกซ้ำได้", () => {
    playerActions.playFrom()
    const { adapter, player, iframe } = setup()
    player.ready()
    adapter.stop()
    adapter.stop()
    expect(player.calls.filter((c) => c === "destroy")).toHaveLength(1)
    expect(iframe.remove).toHaveBeenCalledTimes(1)
    player.calls.length = 0
    playerActions.pause()
    expect(player.calls).toEqual([])
  })

  it("close ของ store หยุด adapter", () => {
    playerActions.playFrom()
    const { player } = setup()
    player.ready()
    playerActions.close()
    expect(player.calls).toContain("destroy")
  })
})
