import { beforeEach, describe, expect, it } from "vitest"

import {
  __resetPlayerForTests,
  getPlayerState,
  playerActions,
  playerAdapterHooks,
  type PlayerAdapter,
} from "./player-store"

type Call = ["play"] | ["pause"] | ["seek", number] | ["stop"]

function fakeAdapter() {
  const calls: Call[] = []
  const adapter: PlayerAdapter = {
    play: () => calls.push(["play"]),
    pause: () => calls.push(["pause"]),
    seekTo: (ms) => calls.push(["seek", ms]),
    stop: () => calls.push(["stop"]),
  }
  return { adapter, calls }
}

/** adapter พร้อมเล่นแล้ว (ผ่าน onReady) */
function readyAdapter() {
  const fake = fakeAdapter()
  playerAdapterHooks.attach(fake.adapter)
  playerAdapterHooks.onStatus("playing")
  return fake
}

const RANGES = [
  { startMs: 60_000, endMs: 66_000 },
  { startMs: 20_000, endMs: 30_000 },
]

beforeEach(() => {
  __resetPlayerForTests()
  playerActions.reset("vid")
})

describe("เริ่มเล่น", () => {
  it("ยังไม่มีตัวเล่น: playFrom = loading + จำเวลาไว้ให้ adapter ใช้ตอนพร้อม", () => {
    playerActions.playFrom(12_345.6)
    const s = getPlayerState()
    expect(s.status).toBe("loading")
    expect(s.started).toBe(true)
    expect(s.pendingSeekMs).toBe(12_346)
    expect(playerAdapterHooks.takePendingSeek()).toBe(12_346)
    expect(getPlayerState().pendingSeekMs).toBeNull()
  })

  it("ขอเล่นอีกครั้งระหว่างโหลด (ไม่ส่งเวลา) ไม่ล้างเวลาที่ขอไว้", () => {
    playerActions.playFrom(5000)
    playerActions.playFrom()
    expect(getPlayerState().pendingSeekMs).toBe(5000)
  })

  it("adapter พร้อมแล้ว: playFrom = seek + play ทันที และ currentMs ขยับทันที", () => {
    playerActions.playFrom()
    const { calls } = readyAdapter()
    playerActions.playFrom(42_000)
    expect(calls).toEqual([["seek", 42_000], ["play"]])
    expect(getPlayerState().currentMs).toBe(42_000)
  })
})

describe("ช่วงไฮไลต์ (reel)", () => {
  it("เรียงตามเวลา ข้ามช่วงผิดรูป แล้วเริ่มที่ช่วงแรก", () => {
    playerActions.playReel([...RANGES, { startMs: 5, endMs: 5 }])
    const s = getPlayerState()
    expect(s.reel?.ranges).toEqual([RANGES[1], RANGES[0]])
    expect(s.reel?.index).toBe(0)
    expect(s.pendingSeekMs).toBe(20_000)
  })

  it("ไม่มีช่วง = ไม่ทำอะไร", () => {
    playerActions.playReel([])
    expect(getPlayerState().status).toBe("idle")
  })

  it("ถึงท้ายช่วง = seek ไปช่วงถัดไป · ช่วงสุดท้ายจบ = pause และเลิก reel", () => {
    playerActions.playFrom()
    const { calls } = readyAdapter()
    playerActions.playReel(RANGES)
    calls.length = 0
    playerAdapterHooks.onTime(25_000)
    expect(getPlayerState().reel?.index).toBe(0)
    playerAdapterHooks.onTime(30_000)
    expect(getPlayerState().reel?.index).toBe(1)
    expect(calls).toEqual([["seek", 60_000]])
    playerAdapterHooks.onTime(66_100)
    expect(getPlayerState().reel).toBeNull()
    expect(calls.at(-1)).toEqual(["pause"])
  })

  it("seek เอง (playFrom) ยกเลิก reel · stopReel ก็ยกเลิก", () => {
    playerActions.playFrom()
    readyAdapter()
    playerActions.playReel(RANGES)
    playerActions.playFrom(1000)
    expect(getPlayerState().reel).toBeNull()
    playerActions.playReel(RANGES)
    playerActions.stopReel()
    expect(getPlayerState().reel).toBeNull()
  })

  it("คลิปจบ (ended) = เลิก reel", () => {
    playerActions.playFrom()
    readyAdapter()
    playerActions.playReel(RANGES)
    playerAdapterHooks.onStatus("ended")
    expect(getPlayerState().reel).toBeNull()
    expect(getPlayerState().status).toBe("ended")
  })
})

describe("ผิดพลาด", () => {
  it("embed_blocked: ปลด adapter จำเวลาที่ขอไว้ · ขอเล่นอีก = แค่ขยับ errorNudge และเวลา", () => {
    playerActions.playFrom(7000)
    playerAdapterHooks.onError("embed_blocked")
    let s = getPlayerState()
    expect(s.status).toBe("error")
    expect(s.error).toBe("embed_blocked")
    expect(s.errorAtMs).toBe(7000)
    expect(s.errorNudge).toBe(0)
    playerActions.playFrom(9000)
    s = getPlayerState()
    expect(s.status).toBe("error")
    expect(s.errorAtMs).toBe(9000)
    expect(s.errorNudge).toBe(1)
  })

  it("offline: retry และ playFrom กลับไป loading", () => {
    playerActions.playFrom()
    playerAdapterHooks.onError("offline")
    playerActions.retry()
    expect(getPlayerState().status).toBe("loading")
    playerAdapterHooks.onError("offline")
    playerActions.playFrom(3000)
    expect(getPlayerState()).toMatchObject({ status: "loading", error: null, pendingSeekMs: 3000 })
  })
})

describe("ปิด / เปลี่ยนคลิป", () => {
  it("close = stop adapter กลับเป็น idle started=false ตำแหน่งกลับเป็น 0", () => {
    playerActions.playFrom()
    const { calls } = readyAdapter()
    playerAdapterHooks.onTime(42_000)
    playerActions.close()
    expect(calls.at(-1)).toEqual(["stop"])
    expect(getPlayerState()).toMatchObject({ status: "idle", started: false, currentMs: 0 })
    // ไม่มี adapter แล้ว: ขอเล่นใหม่ = โหลดใหม่
    playerActions.playFrom(1000)
    expect(getPlayerState().status).toBe("loading")
  })

  it("reset คลิปใหม่ = stop adapter ล้างสถานะ · reset คลิปเดิมไม่ทำอะไร", () => {
    playerActions.playFrom()
    const { calls } = readyAdapter()
    playerActions.reset("vid")
    expect(calls).toEqual([])
    playerActions.reset("other")
    expect(calls).toEqual([["stop"]])
    expect(getPlayerState()).toMatchObject({ videoId: "other", status: "idle", started: false, currentMs: 0 })
  })

  it("detach adapter ตัวเก่าไม่กระทบตัวใหม่", () => {
    const old = fakeAdapter()
    const current = fakeAdapter()
    playerAdapterHooks.attach(old.adapter)
    playerAdapterHooks.attach(current.adapter)
    playerAdapterHooks.detach(old.adapter)
    playerAdapterHooks.onStatus("paused")
    playerActions.pause()
    expect(current.calls).toEqual([["pause"]])
  })
})
