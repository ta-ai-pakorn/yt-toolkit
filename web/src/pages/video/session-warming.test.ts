import { QueryClient, QueryObserver } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ApiError } from "@/lib/api"

import {
  announcedSeconds,
  isWarming,
  secondsLeft,
  warmingDeadline,
  warmingSeconds,
  watchWarming,
} from "./session-warming"
import { tokensQuery } from "./subs-queries"

const VIDEO = "88o5Sk8_m1Y"

function warmingError(seconds: unknown = 75) {
  const body = { error: { code: "E_SESSION_WARMING", message: "m", detail: null, retryAfterSeconds: seconds } }
  return new ApiError(503, "E_SESSION_WARMING", "m", null, body)
}

describe("warmingSeconds / isWarming", () => {
  it("อ่าน retryAfterSeconds จาก envelope", () => {
    expect(warmingSeconds(warmingError(42))).toBe(42)
    expect(warmingSeconds(warmingError(1.2))).toBe(2)
    expect(isWarming(warmingError())).toBe(true)
  })

  it("ค่าผิดรูปแบบ = รอ 1 วินาที (ยังนับเป็นกำลังเตรียม)", () => {
    expect(warmingSeconds(warmingError("x"))).toBe(1)
    expect(warmingSeconds(warmingError(-5))).toBe(1)
    expect(warmingSeconds(new ApiError(503, "E_SESSION_WARMING", "m", null, null))).toBe(1)
  })

  it("error อื่นไม่ใช่", () => {
    expect(warmingSeconds(new ApiError(503, "E_TRANSLATION_BLOCKED", "m", null, null))).toBeNull()
    expect(warmingSeconds(new Error("E_SESSION_WARMING"))).toBeNull()
    expect(isWarming(null)).toBe(false)
  })
})

describe("นับถอยหลัง", () => {
  it("deadline นับจากเวลาที่ได้ error (ทุกแท็บได้ค่าเดียวกัน)", () => {
    expect(warmingDeadline(warmingError(10), 1_000)).toBe(11_000)
    expect(warmingDeadline(new Error("x"), 1_000)).toBeNull()
  })

  it("วินาทีที่เหลือปัดขึ้น ไม่ต่ำกว่า 0", () => {
    expect(secondsLeft(11_000, 1_000)).toBe(10)
    expect(secondsLeft(11_000, 10_001)).toBe(1)
    expect(secondsLeft(11_000, 11_000)).toBe(0)
    expect(secondsLeft(11_000, 20_000)).toBe(0)
  })

  it("ประกาศให้โปรแกรมอ่านหน้าจอตอนเริ่ม ทุก 15 วินาที และตอนครบ", () => {
    const spoken = new Set<number>()
    for (let left = 70; left >= 0; left--) spoken.add(announcedSeconds(left, 70))
    expect([...spoken]).toEqual([70, 60, 45, 30, 15, 0])
    expect(announcedSeconds(74, 75)).toBe(75)
    expect(announcedSeconds(3, 3)).toBe(3)
  })
})

describe("watchWarming: โหลดใหม่ให้เองเมื่อครบเวลา", () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  function stubResponses(...bodies: { status: number; body: unknown }[]) {
    const fetch = vi.fn(async () => {
      const next = bodies.length > 1 ? bodies.shift()! : bodies[0]
      return new Response(JSON.stringify(next.body), { status: next.status })
    })
    vi.stubGlobal("fetch", fetch)
    return fetch
  }

  const warming = (seconds: number) => ({
    status: 503,
    body: { error: { code: "E_SESSION_WARMING", message: "m", detail: null, retryAfterSeconds: seconds } },
  })
  const tokens = { status: 200, body: { hasWordTiming: false, tokens: [{ t: "hi", s: 0, e: 1 }] } }

  async function firstFetch(client: QueryClient) {
    const observer = new QueryObserver(client, tokensQuery(VIDEO, "t.en"))
    const unsubscribe = observer.subscribe(() => undefined)
    await vi.waitFor(() => expect(observer.getCurrentResult().isFetching).toBe(false))
    return { observer, unsubscribe }
  }

  it("ครบเวลาแล้วยิงครั้งเดียว แม้ไม่มีแท็บไหนเปิดอยู่ (ไม่มี observer)", async () => {
    const fetch = stubResponses(warming(2), tokens)
    const client = new QueryClient()
    const stop = watchWarming(client)
    const { observer, unsubscribe } = await firstFetch(client)
    expect(isWarming(observer.getCurrentResult().error)).toBe(true)
    unsubscribe() // ผู้ใช้ไปแท็บภาพเฟรม
    await vi.advanceTimersByTimeAsync(1_900)
    expect(fetch).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(200)
    await vi.waitFor(() => expect(client.getQueryState(tokensQuery(VIDEO, "t.en").queryKey)?.status).toBe("success"))
    expect(fetch).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(10_000)
    expect(fetch).toHaveBeenCalledTimes(2)
    stop()
  })

  it("ยิงได้แม้มีแค่ observer แบบปิด (ปุ่มโน้ตที่หัวคลิปดูสถานะอยู่ตอนผู้ใช้อยู่แท็บภาพเฟรม)", async () => {
    const fetch = stubResponses(warming(1), tokens)
    const client = new QueryClient()
    const stop = watchWarming(client)
    const { unsubscribe } = await firstFetch(client)
    unsubscribe()
    const header = new QueryObserver(client, { ...tokensQuery(VIDEO, "t.en"), enabled: false })
    const unsubscribeHeader = header.subscribe(() => undefined)
    await vi.advanceTimersByTimeAsync(1_100)
    await vi.waitFor(() => expect(header.getCurrentResult().isSuccess).toBe(true))
    expect(fetch).toHaveBeenCalledTimes(2)
    unsubscribeHeader()
    stop()
  })

  it("ได้ E_SESSION_WARMING อีก = นับรอบใหม่แล้วยิงอีกครั้ง", async () => {
    const fetch = stubResponses(warming(1), warming(3), tokens)
    const client = new QueryClient()
    const stop = watchWarming(client)
    const { unsubscribe } = await firstFetch(client)
    await vi.advanceTimersByTimeAsync(1_100)
    expect(fetch).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(2_000)
    expect(fetch).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(1_100)
    expect(fetch).toHaveBeenCalledTimes(3)
    unsubscribe()
    stop()
  })

  it("เลิกดูแล้วไม่ยิง", async () => {
    const fetch = stubResponses(warming(1), tokens)
    const client = new QueryClient()
    const stop = watchWarming(client)
    const { unsubscribe } = await firstFetch(client)
    stop()
    await vi.advanceTimersByTimeAsync(5_000)
    expect(fetch).toHaveBeenCalledTimes(1)
    unsubscribe()
  })

  it("เปลี่ยนแทร็กไปแล้วกลับมา (observer เดิมเปลี่ยน key) ระหว่างนับไม่ยิงซ้ำ (fix round 3)", async () => {
    const fetch = stubResponses(warming(30), tokens)
    const client = new QueryClient()
    const { observer, unsubscribe } = await firstFetch(client)
    observer.setOptions(tokensQuery(VIDEO, "a.th-orig"))
    await vi.waitFor(() => expect(observer.getCurrentResult().isFetching).toBe(false))
    expect(fetch).toHaveBeenCalledTimes(2) // แทร็กไทยโหลดตามปกติ
    observer.setOptions(tokensQuery(VIDEO, "t.en"))
    await vi.advanceTimersByTimeAsync(100)
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(isWarming(observer.getCurrentResult().error)).toBe(true)
    unsubscribe()
  })

  it("สลับแท็บกลับมา (mount ใหม่) ระหว่างนับไม่ยิงซ้ำ", async () => {
    const fetch = stubResponses(warming(30), tokens)
    const client = new QueryClient()
    const first = await firstFetch(client)
    first.unsubscribe()
    const again = new QueryObserver(client, tokensQuery(VIDEO, "t.en"))
    const unsubscribe = again.subscribe(() => undefined)
    await vi.advanceTimersByTimeAsync(100)
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(isWarming(again.getCurrentResult().error)).toBe(true)
    unsubscribe()
  })
})
