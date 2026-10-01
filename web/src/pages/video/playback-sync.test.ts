import { afterEach, beforeEach, describe, expect, it } from "vitest"

import type { Cue, StoryboardFrame } from "@/lib/types"

import { hasPlayhead, lineAt, nowPlayingFrame, nowPlayingLine } from "./playback-sync"
import {
  __resetPlayerForTests,
  getPlayerState,
  playerActions,
  playerAdapterHooks,
  type PlayerAdapter,
  type PlayerState,
} from "./player/player-store"

const frame = (index: number, tMs: number): StoryboardFrame => ({ index, tMs, url: `/f/${index}.jpg` })
const cue = (startMs: number, endMs: number): Cue => ({ startMs, endMs, lines: [`${startMs}`] })

const at = (status: PlayerState["status"], currentMs: number) => ({ status, currentMs })

describe("lineAt (ค้นแบบแบ่งครึ่ง)", () => {
  // 1-3 วินาที · 4-6 วินาที (ช่องว่าง 3-4) · 10-12 วินาที (ช่องว่าง 6-10)
  const CUES = [cue(1000, 3000), cue(4000, 6000), cue(10000, 12000)]

  it("เวลาที่อยู่ในช่วงของบรรทัดได้บรรทัดนั้น (เริ่มนับรวม จบไม่นับ)", () => {
    expect(lineAt(CUES, 1000)).toBe(0)
    expect(lineAt(CUES, 2999)).toBe(0)
    expect(lineAt(CUES, 4000)).toBe(1)
    expect(lineAt(CUES, 5500)).toBe(1)
    expect(lineAt(CUES, 11999)).toBe(2)
  })

  it("ช่องว่างเงียบระหว่างบรรทัด: บรรทัดก่อนหน้ายังติดไฟจนบรรทัดถัดไปเริ่ม", () => {
    expect(lineAt(CUES, 3000)).toBe(0)
    expect(lineAt(CUES, 3500)).toBe(0)
    expect(lineAt(CUES, 3999)).toBe(0)
    expect(lineAt(CUES, 6000)).toBe(1)
    expect(lineAt(CUES, 8000)).toBe(1)
    expect(lineAt(CUES, 9999)).toBe(1)
  })

  it("ก่อนบรรทัดแรก และตั้งแต่เวลาจบของบรรทัดสุดท้าย = -1", () => {
    expect(lineAt(CUES, 0)).toBe(-1)
    expect(lineAt(CUES, 999)).toBe(-1)
    expect(lineAt(CUES, 12000)).toBe(-1)
    expect(lineAt(CUES, 99_000)).toBe(-1)
  })

  it("ไม่มีบรรทัด = -1 · บรรทัดเดียวก็หาเจอ", () => {
    expect(lineAt([], 1000)).toBe(-1)
    expect(lineAt([cue(0, 500)], 0)).toBe(0)
    expect(lineAt([cue(0, 500)], 499)).toBe(0)
    expect(lineAt([cue(0, 500)], 500)).toBe(-1)
  })

  it("บรรทัดติดกันพอดี (จบ = เริ่มบรรทัดถัดไป) ได้บรรทัดถัดไปที่ขอบ", () => {
    const touching = [cue(0, 1000), cue(1000, 2000), cue(2000, 3000)]
    expect(lineAt(touching, 999)).toBe(0)
    expect(lineAt(touching, 1000)).toBe(1)
    expect(lineAt(touching, 2000)).toBe(2)
  })

  it("ตรงกับการค้นทีละบรรทัดทุกเวลา (พันบรรทัด มีช่องว่างสลับ)", () => {
    const many: Cue[] = []
    for (let i = 0; i < 1000; i++) many.push(cue(i * 1000, i * 1000 + (i % 3 === 0 ? 600 : 1000)))
    // แบบตรงไปตรงมา: บรรทัดสุดท้ายที่เริ่มแล้ว · เลยเวลาจบของบรรทัดสุดท้าย = -1
    const last = many[many.length - 1]
    const linear = (ms: number) => (ms >= last.endMs ? -1 : many.findLastIndex((c) => c.startMs <= ms))
    for (let ms = -500; ms < 1_002_000; ms += 137) expect(lineAt(many, ms)).toBe(linear(ms))
  })
})

describe("hasPlayhead / nowPlayingLine / nowPlayingFrame", () => {
  const CUES = [cue(1000, 3000), cue(4000, 6000)]
  const FRAMES = [0, 5000, 10000, 15000].map((tMs, index) => frame(index, tMs))

  it("มีตำแหน่งเฉพาะตอนเล่นหรือหยุดชั่วคราว", () => {
    expect(hasPlayhead({ status: "playing" })).toBe(true)
    expect(hasPlayhead({ status: "paused" })).toBe(true)
    for (const status of ["idle", "loading", "ended", "error"] as const) expect(hasPlayhead({ status })).toBe(false)
  })

  it("บรรทัดที่กำลังเล่น: ไม่มีตำแหน่ง = -1 แม้เวลาอยู่ในบรรทัด", () => {
    expect(nowPlayingLine(CUES, at("playing", 2000))).toBe(0)
    expect(nowPlayingLine(CUES, at("paused", 5000))).toBe(1)
    expect(nowPlayingLine(CUES, at("idle", 2000))).toBe(-1)
    expect(nowPlayingLine(CUES, at("loading", 2000))).toBe(-1)
  })

  it("ภาพที่กำลังเล่น = ภาพที่ใกล้ที่สุด (เหมือน nearestFrameIndex) · ไม่มีตำแหน่ง = -1", () => {
    expect(nowPlayingFrame(FRAMES, at("playing", 0))).toBe(0)
    expect(nowPlayingFrame(FRAMES, at("playing", 7400))).toBe(1)
    expect(nowPlayingFrame(FRAMES, at("playing", 7600))).toBe(2)
    expect(nowPlayingFrame(FRAMES, at("paused", 99_000))).toBe(3)
    expect(nowPlayingFrame(FRAMES, at("ended", 7600))).toBe(-1)
    expect(nowPlayingFrame([], at("playing", 7600))).toBe(-1)
  })

  it("ชุดภาพเปลี่ยนแต่เวลาเดิม: คิดใหม่ ไม่ใช้ค่าที่จำไว้ของชุดเก่า", () => {
    const other = [frame(0, 7000), frame(1, 50_000)]
    expect(nowPlayingFrame(FRAMES, at("playing", 8000))).toBe(2)
    expect(nowPlayingFrame(other, at("playing", 8000))).toBe(0)
  })
})

/** adapter ปลอม: จดคำสั่งที่ได้รับ */
function fakeAdapter() {
  const calls: string[] = []
  const adapter: PlayerAdapter = {
    play: () => calls.push("play"),
    pause: () => calls.push("pause"),
    seekTo: (ms) => calls.push(`seek:${ms}`),
    stop: () => calls.push("stop"),
  }
  return { adapter, calls }
}

describe("ภาพเฟรมตามการเล่น กับ store จริง + adapter ปลอม", () => {
  // คลิปยาว: 600 ภาพ ห่างกัน 2 วินาที
  const FRAMES = Array.from({ length: 600 }, (_, index) => frame(index, index * 2000))

  beforeEach(() => __resetPlayerForTests())
  afterEach(() => __resetPlayerForTests())

  /**
   * จำลอง usePlayerValue ของทุกภาพ: แต่ละภาพเลือก "ฉันคือภาพที่กำลังเล่นไหม" แล้วนับว่าค่าของภาพไหนเปลี่ยนต่อครั้งที่ store แจ้ง
   * (useSyncExternalStore เรนเดอร์ภาพใหม่เฉพาะเมื่อค่าที่เลือกเปลี่ยน)
   */
  function selections() {
    return FRAMES.map((_, index) => nowPlayingFrame(FRAMES, getPlayerState()) === index)
  }
  function changed(before: boolean[], after: boolean[]): number[] {
    return before.flatMap((value, index) => (value !== after[index] ? [index] : []))
  }

  it("ยังไม่เล่น = ไม่มีภาพที่กำลังเล่น · playFrom ก่อน adapter พร้อม = รอโหลด (ยังไม่มีภาพ) และจำเวลาไว้", () => {
    expect(selections().some(Boolean)).toBe(false)
    playerActions.playFrom(30_000)
    expect(getPlayerState().status).toBe("loading")
    expect(getPlayerState().pendingSeekMs).toBe(30_000)
    expect(selections().some(Boolean)).toBe(false)
  })

  it("กด ▶ ของภาพ (playFrom เวลาของภาพ) = adapter seek ไปเวลานั้นแล้วเล่น · ภาพนั้นเป็นภาพที่กำลังเล่น", () => {
    const { adapter, calls } = fakeAdapter()
    playerAdapterHooks.attach(adapter)
    playerAdapterHooks.onStatus("paused")
    playerActions.playFrom(FRAMES[42].tMs)
    expect(calls).toEqual([`seek:${FRAMES[42].tMs}`, "play"])
    playerAdapterHooks.onStatus("playing")
    expect(selections().indexOf(true)).toBe(42)
  })

  it("เวลาเดินทีละ 250 ms: ข้ามภาพเมื่อไร มีแค่ 2 ภาพที่ค่าเปลี่ยน (ภาพเดิมกับภาพใหม่) ระหว่างนั้นไม่มีภาพไหนเปลี่ยน", () => {
    const { adapter } = fakeAdapter()
    playerAdapterHooks.attach(adapter)
    playerAdapterHooks.onStatus("playing")
    playerAdapterHooks.onTime(0)
    let before = selections()
    let crossings = 0
    for (let ms = 250; ms <= 20_000; ms += 250) {
      playerAdapterHooks.onTime(ms)
      const after = selections()
      const diff = changed(before, after)
      expect(diff.length === 0 || diff.length === 2).toBe(true)
      if (diff.length === 2) crossings += 1
      before = after
    }
    // 0-20 วินาที ภาพห่าง 2 วินาที: ภาพที่ใกล้ที่สุดเปลี่ยนที่ 1, 3, 5 ... 19 วินาที = 10 ครั้ง
    expect(crossings).toBe(10)
  })

  it("หยุดชั่วคราวยังมีภาพที่กำลังเล่น · ปิดตัวเล่นแล้วไม่มี (ภาพเดียวที่ค่าเปลี่ยน)", () => {
    const { adapter } = fakeAdapter()
    playerAdapterHooks.attach(adapter)
    playerAdapterHooks.onStatus("playing")
    playerAdapterHooks.onTime(10_000)
    playerAdapterHooks.onStatus("paused")
    const paused = selections()
    expect(paused.indexOf(true)).toBe(5)
    playerActions.close()
    expect(changed(paused, selections())).toEqual([5])
  })
})
