import { QueryClient, QueryObserver } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

import {
  appShutdown,
  applyServerEvent,
  connectEvents,
  EVENTS_URL,
  parseServerEvent,
  sharpRefreshTarget,
} from "./events"
import { ACCOUNT_KEY, INACTIVE } from "./account"
import { JOBS_KEY, QUEUE_KEY } from "./jobs"
import type { AccountStatus, Job, QueueState } from "./types"

/** ปล่อยให้ promise ที่ค้าง (ยกเลิกคำขอ แล้วโหลดใหม่) ทำงานจนจบ */
const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

const JOB: Job = {
  id: "11111111-2222-3333-4444-555555555555",
  videoId: "aqz-KE-bpKQ",
  title: "Big Buck Bunny",
  kind: "video",
  params: {
    maxQuality: false,
    splitChapters: false,
    noAudio: false,
    audioLanguage: "original",
  },
  status: "queued",
  position: 1,
  createdAt: "2026-10-01T10:00:00Z",
}

const QUEUE: QueueState = { pausedUntil: null, reason: null, concurrency: 2 }

describe("parseServerEvent", () => {
  it("อ่านได้ทั้ง 5 ชื่อ", () => {
    expect(parseServerEvent("job.created", JSON.stringify(JOB))).toEqual({
      type: "job.created",
      job: JOB,
    })
    expect(
      parseServerEvent("job.updated", '{"id":"x","progress":0.5,"stage":null}')
    ).toEqual({
      type: "job.updated",
      patch: { id: "x", progress: 0.5, stage: null },
    })
    expect(
      parseServerEvent(
        "queue.paused",
        '{"until":"2026-10-01T10:10:00Z","reason":"E_BOT_CHECK"}'
      )
    ).toEqual({
      type: "queue.paused",
      until: "2026-10-01T10:10:00Z",
      reason: "E_BOT_CHECK",
    })
    expect(parseServerEvent("queue.resumed", "{}")).toEqual({
      type: "queue.resumed",
    })
    expect(parseServerEvent("app.shutdown", "{}")).toEqual({
      type: "app.shutdown",
    })
  })

  it("ชื่อแปลก JSON เสีย หรือรูปร่างผิด = null", () => {
    expect(parseServerEvent("job.deleted", "{}")).toBeNull()
    expect(parseServerEvent("job.created", "not json")).toBeNull()
    expect(parseServerEvent("job.created", "null")).toBeNull()
    expect(parseServerEvent("job.created", "[]")).toBeNull()
    expect(parseServerEvent("job.created", '{"title":"no id"}')).toBeNull()
    expect(parseServerEvent("job.updated", '{"id":5}')).toBeNull()
    expect(parseServerEvent("queue.paused", '{"until":1}')).toBeNull()
    expect(parseServerEvent("queue.resumed", "")).toBeNull()
  })
})

describe("applyServerEvent", () => {
  it("job.created ใส่งานใน ['jobs'] และคืน before/after", () => {
    const client = new QueryClient()
    client.setQueryData(JOBS_KEY, [])
    expect(applyServerEvent(client, { type: "job.created", job: JOB })).toEqual(
      { before: undefined, after: JOB }
    )
    expect(client.getQueryData(JOBS_KEY)).toEqual([JOB])
  })

  it("job.updated รวมค่าที่เปลี่ยนและคืนงานก่อน/หลัง", () => {
    const client = new QueryClient()
    client.setQueryData(JOBS_KEY, [JOB])
    const result = applyServerEvent(client, {
      type: "job.updated",
      patch: {
        id: JOB.id,
        status: "running",
        startedAt: "2026-10-01T10:00:02Z",
      },
    })
    const running = {
      ...JOB,
      status: "running",
      startedAt: "2026-10-01T10:00:02Z",
    }
    expect(result).toEqual({ before: JOB, after: running })
    expect(client.getQueryData(JOBS_KEY)).toEqual([running])
  })

  it("job.updated ของงานที่ไม่รู้จัก หรือแคชยังไม่โหลด ไม่เปลี่ยนอะไร", () => {
    const client = new QueryClient()
    expect(
      applyServerEvent(client, {
        type: "job.updated",
        patch: { id: JOB.id, progress: 1 },
      })
    ).toEqual({})
    expect(client.getQueryData(JOBS_KEY)).toBeUndefined()
    const jobs = [JOB]
    client.setQueryData(JOBS_KEY, jobs)
    expect(
      applyServerEvent(client, {
        type: "job.updated",
        patch: { id: "other", progress: 1 },
      })
    ).toEqual({})
    expect(client.getQueryData(JOBS_KEY)).toBe(jobs)
  })

  it("job.created ตอนแคชยังไม่โหลด ไม่สร้างรายการครึ่ง ๆ แต่ยังคืน after", () => {
    const client = new QueryClient()
    expect(applyServerEvent(client, { type: "job.created", job: JOB })).toEqual(
      { after: JOB }
    )
    expect(client.getQueryData(JOBS_KEY)).toBeUndefined()
  })

  it("queue.paused / queue.resumed แก้ ['queue']", () => {
    const client = new QueryClient()
    client.setQueryData(QUEUE_KEY, QUEUE)
    expect(
      applyServerEvent(client, {
        type: "queue.paused",
        until: "2026-10-01T10:10:00Z",
        reason: "E_BOT_CHECK",
      })
    ).toEqual({})
    expect(client.getQueryData(QUEUE_KEY)).toEqual({
      pausedUntil: "2026-10-01T10:10:00Z",
      reason: "E_BOT_CHECK",
      concurrency: 2,
    })
    applyServerEvent(client, { type: "queue.resumed" })
    expect(client.getQueryData(QUEUE_KEY)).toEqual(QUEUE)
  })

  it("สถานะคิวยังไม่โหลด = สั่งโหลดใหม่แทนการเดา", () => {
    const client = new QueryClient()
    const invalidate = vi.spyOn(client, "invalidateQueries")
    applyServerEvent(client, { type: "queue.resumed" })
    expect(client.getQueryData(QUEUE_KEY)).toBeUndefined()
    expect(invalidate).toHaveBeenCalledWith({ queryKey: QUEUE_KEY })
  })
})

/** EventSource ปลอม: เก็บ listener ไว้ แล้วให้เทสยิงเหตุการณ์เอง */
class FakeSource {
  url: string
  closed = false
  listeners = new Map<string, Set<(event: Event) => void>>()
  constructor(url: string) {
    this.url = url
  }
  addEventListener(name: string, fn: (event: Event) => void) {
    if (!this.listeners.has(name)) this.listeners.set(name, new Set())
    this.listeners.get(name)!.add(fn)
  }
  removeEventListener(name: string, fn: (event: Event) => void) {
    this.listeners.get(name)?.delete(fn)
  }
  close() {
    this.closed = true
  }
  emit(name: string, data?: unknown) {
    const event =
      data === undefined
        ? new Event(name)
        : new MessageEvent(name, { data: JSON.stringify(data) })
    this.listeners.get(name)?.forEach((fn) => fn(event))
  }
  count() {
    return [...this.listeners.values()].reduce((n, set) => n + set.size, 0)
  }
}

function connect(
  client: QueryClient,
  extra: { onJobChange?: (before: Job | undefined, after: Job) => void } = {}
) {
  let source: FakeSource | undefined
  const onShutdown = vi.fn()
  const disconnect = connectEvents(client, {
    onShutdown,
    ...extra,
    createSource: (url) => {
      source = new FakeSource(url)
      return source as unknown as EventSource
    },
  })
  return { source: source!, onShutdown, disconnect }
}

describe("connectEvents", () => {
  it("ต่อ /api/events และใส่เหตุการณ์ลงแคช", () => {
    const client = new QueryClient()
    client.setQueryData(JOBS_KEY, [])
    const { source } = connect(client)
    expect(source.url).toBe(EVENTS_URL)
    expect(EVENTS_URL).toBe("/api/events")
    source.emit("job.created", JOB)
    expect(client.getQueryData(JOBS_KEY)).toEqual([JOB])
  })

  it("เรียก onJobChange เฉพาะเมื่อสถานะเปลี่ยน", () => {
    const client = new QueryClient()
    client.setQueryData(JOBS_KEY, [])
    const onJobChange = vi.fn()
    const { source } = connect(client, { onJobChange })
    source.emit("job.created", JOB)
    expect(onJobChange).toHaveBeenLastCalledWith(undefined, JOB)
    source.emit("job.updated", { id: JOB.id, status: "running" })
    expect(onJobChange).toHaveBeenCalledTimes(2)
    expect(onJobChange).toHaveBeenLastCalledWith(JOB, {
      ...JOB,
      status: "running",
    })
    source.emit("job.updated", { id: JOB.id, progress: 0.4 })
    expect(onJobChange).toHaveBeenCalledTimes(2)
    source.emit("job.updated", { id: JOB.id, status: "done", progress: null })
    expect(onJobChange).toHaveBeenCalledTimes(3)
    expect(onJobChange.mock.lastCall?.[1]).toEqual({ ...JOB, status: "done" })
  })

  it("ข้อมูลเสียถูกข้ามไป ไม่โยน error", () => {
    const client = new QueryClient()
    client.setQueryData(JOBS_KEY, [])
    const { source } = connect(client)
    const bad = new MessageEvent("job.created", { data: "{oops" })
    expect(() =>
      source.listeners.get("job.created")!.forEach((fn) => fn(bad))
    ).not.toThrow()
    expect(client.getQueryData(JOBS_KEY)).toEqual([])
  })

  it("app.shutdown เรียก onShutdown ตั้ง appShutdown และปิดการเชื่อมต่อ", () => {
    const client = new QueryClient()
    const { source, onShutdown } = connect(client)
    const listener = vi.fn()
    const unsubscribe = appShutdown.subscribe(listener)
    source.emit("app.shutdown", {})
    expect(onShutdown).toHaveBeenCalledTimes(1)
    expect(appShutdown.get()).toBe(true)
    expect(listener).toHaveBeenCalledTimes(1)
    expect(source.closed).toBe(true)
    unsubscribe()
  })

  it("open ครั้งแรกโหลดรายการงานและสถานะคิวใหม่หนึ่งครั้ง (เหตุการณ์ที่มาก่อนแคชพร้อมถูกข้ามไป)", async () => {
    const client = new QueryClient()
    const invalidate = vi.spyOn(client, "invalidateQueries")
    const { source } = connect(client)
    source.emit("open")
    await flush()
    expect(invalidate).toHaveBeenCalledWith({ queryKey: JOBS_KEY })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: QUEUE_KEY })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ACCOUNT_KEY })
    expect(invalidate).toHaveBeenCalledTimes(3)
    source.emit("open")
    await flush()
    expect(invalidate).toHaveBeenCalledTimes(3)
  })

  it("open ระหว่างที่คำขอรายการงานแรกยังไม่ตอบ: ยกเลิกคำขอนั้นแล้วโหลดใหม่ (คำตอบเดิมคำนวณก่อนต่อติด)", async () => {
    const client = new QueryClient()
    const answers: Array<(jobs: Job[]) => void> = []
    const observer = new QueryObserver(client, {
      queryKey: JOBS_KEY,
      queryFn: () => new Promise<Job[]>((resolve) => answers.push(resolve)),
    })
    const unsubscribeObserver = observer.subscribe(() => {})
    await flush()
    expect(answers).toHaveLength(1)
    const { source } = connect(client)
    source.emit("open")
    await flush()
    expect(answers).toHaveLength(2)
    unsubscribeObserver()
  })

  it("ต่อใหม่หลังหลุด (error แล้ว open) โหลดใหม่อีกครั้ง · open ซ้ำโดยไม่หลุดไม่โหลด", async () => {
    const client = new QueryClient()
    const { source } = connect(client)
    source.emit("open")
    await flush()
    const invalidate = vi.spyOn(client, "invalidateQueries")
    source.emit("open")
    await flush()
    expect(invalidate).not.toHaveBeenCalled()
    source.emit("error")
    source.emit("open")
    await flush()
    expect(invalidate).toHaveBeenCalledWith({ queryKey: JOBS_KEY })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: QUEUE_KEY })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ACCOUNT_KEY })
    expect(invalidate).toHaveBeenCalledTimes(3)
    source.emit("open")
    await flush()
    expect(invalidate).toHaveBeenCalledTimes(3)
  })

  it("ฟังก์ชันที่คืนมาถอด listener ทั้งหมดและปิดการเชื่อมต่อ", () => {
    const client = new QueryClient()
    const { source, disconnect } = connect(client)
    expect(source.count()).toBe(8)
    disconnect()
    expect(source.count()).toBe(0)
    expect(source.closed).toBe(true)
  })
})

describe("sharpRefreshTarget", () => {
  const sharpJob: Job = { ...JOB, kind: "frames_sharp", params: {} }
  it("a frames_sharp or video job that just finished refreshes its clip", () => {
    expect(sharpRefreshTarget({ ...sharpJob, status: "running" }, { ...sharpJob, status: "done" })).toBe("aqz-KE-bpKQ")
    expect(sharpRefreshTarget({ ...JOB, status: "running" }, { ...JOB, status: "done" })).toBe("aqz-KE-bpKQ")
  })
  it("anything else does not", () => {
    expect(sharpRefreshTarget({ ...sharpJob, status: "done" }, { ...sharpJob, status: "done" })).toBeNull()
    expect(sharpRefreshTarget({ ...sharpJob, status: "running" }, { ...sharpJob, status: "failed" })).toBeNull()
    const zip: Job = { ...JOB, kind: "frames_zip", params: { source: "sharp" } }
    expect(sharpRefreshTarget({ ...zip, status: "running" }, { ...zip, status: "done" })).toBeNull()
  })
  it("connectEvents invalidates ['sharp', id] when such a job finishes", () => {
    const client = new QueryClient()
    client.setQueryData(JOBS_KEY, [{ ...sharpJob, status: "running" }])
    const spy = vi.spyOn(client, "invalidateQueries")
    const { source } = connect(client)
    source.emit("job.updated", { id: JOB.id, status: "done" })
    expect(spy).toHaveBeenCalledWith({ queryKey: ["sharp", "aqz-KE-bpKQ"] })
  })
})

describe("ข่าวบัญชียูทูปชั่วคราว (M5 รอบ C)", () => {
  const ACTIVE: AccountStatus = {
    active: true,
    importedAt: "2026-10-06T03:00:00+00:00",
    expiresAt: "2026-10-06T05:00:00+00:00",
    used: true,
  }

  it("parseServerEvent อ่าน account (ไม่มีอย่างอื่นนอกจาก active / expiresAt / reason)", () => {
    expect(parseServerEvent("account", '{"active":false,"reason":"queue_done"}')).toEqual({
      type: "account",
      active: false,
      reason: "queue_done",
    })
    expect(parseServerEvent("account", '{"active":true,"expiresAt":"2026-10-06T03:10:00+00:00","x":1}')).toEqual({
      type: "account",
      active: true,
      expiresAt: "2026-10-06T03:10:00+00:00",
    })
    expect(parseServerEvent("account", '{"active":"yes"}')).toBeNull()
  })

  it("ลบแล้ว: แคชเป็นไม่ได้ใช้บัญชี และเรียก onAccount พร้อม reason", () => {
    const client = new QueryClient()
    client.setQueryData(ACCOUNT_KEY, ACTIVE)
    const onAccount = vi.fn()
    let source: FakeSource | undefined
    connectEvents(client, {
      onShutdown: vi.fn(),
      onAccount,
      createSource: (url) => {
        source = new FakeSource(url)
        return source as unknown as EventSource
      },
    })
    source!.emit("account", { active: true, expiresAt: "2026-10-06T03:10:00+00:00" })
    expect(client.getQueryData(ACCOUNT_KEY)).toEqual({ ...ACTIVE, expiresAt: "2026-10-06T03:10:00+00:00" })
    source!.emit("account", { active: false, reason: "expired" })
    expect(client.getQueryData(ACCOUNT_KEY)).toEqual(INACTIVE)
    expect(onAccount).toHaveBeenLastCalledWith({ type: "account", active: false, reason: "expired" })
  })

  it("นำเข้าจากแท็บอื่น: โหลดสถานะเต็มใหม่", () => {
    const client = new QueryClient()
    client.setQueryData(ACCOUNT_KEY, INACTIVE)
    const invalidate = vi.spyOn(client, "invalidateQueries")
    applyServerEvent(client, { type: "account", active: true, expiresAt: "2026-10-06T05:00:00+00:00" })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ACCOUNT_KEY })
  })
})
