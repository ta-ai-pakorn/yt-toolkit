import type { QueryClient } from "@tanstack/react-query"
import { useSyncExternalStore } from "react"

import { JOBS_KEY, mergeJobPatch, QUEUE_KEY, upsertJob } from "./jobs"
import type { Job, JobPatch, QueueState } from "./types"

/** เหตุการณ์จาก GET /api/events (SSE สัญญา C6) ที่อ่านแล้ว */
export type ServerEvent =
  | { type: "job.created"; job: Job }
  | { type: "job.updated"; patch: JobPatch }
  | { type: "queue.paused"; until: string; reason: string }
  | { type: "queue.resumed" }
  | { type: "app.shutdown" }

export const EVENTS_URL = "/api/events"

const EVENT_NAMES = [
  "job.created",
  "job.updated",
  "queue.paused",
  "queue.resumed",
  "app.shutdown",
] as const

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value)

/** อ่านเหตุการณ์หนึ่งชิ้น: ชื่อที่ไม่รู้จัก JSON เสีย หรือรูปร่างผิด = null (ข้ามไป ไม่โยน error) */
export function parseServerEvent(
  name: string,
  data: string
): ServerEvent | null {
  let body: unknown
  try {
    body = JSON.parse(data)
  } catch {
    return null
  }
  if (!isRecord(body)) return null
  switch (name) {
    case "job.created":
      return typeof body.id === "string" && typeof body.status === "string"
        ? { type: "job.created", job: body as Job }
        : null
    case "job.updated":
      return typeof body.id === "string"
        ? { type: "job.updated", patch: body as JobPatch }
        : null
    case "queue.paused":
      return typeof body.until === "string" && typeof body.reason === "string"
        ? { type: "queue.paused", until: body.until, reason: body.reason }
        : null
    case "queue.resumed":
      return { type: "queue.resumed" }
    case "app.shutdown":
      return { type: "app.shutdown" }
    default:
      return null
  }
}

/**
 * ใส่เหตุการณ์ลงแคชของ react-query: งาน → ["jobs"], หยุดพัก/ทำต่อ → ["queue"]
 * คืนงานก่อนและหลังเปลี่ยน (ใช้ตัดสินใจเด้ง toast) · แคชยังไม่เคยโหลด = ไม่สร้างรายการครึ่ง ๆ (รอโหลดจริง)
 */
export function applyServerEvent(
  client: QueryClient,
  event: ServerEvent
): { before?: Job; after?: Job } {
  switch (event.type) {
    case "job.created": {
      const jobs = client.getQueryData<Job[]>(JOBS_KEY)
      if (jobs === undefined) return { after: event.job }
      const before = jobs.find((j) => j.id === event.job.id)
      client.setQueryData<Job[]>(JOBS_KEY, upsertJob(jobs, event.job))
      return { before, after: event.job }
    }
    case "job.updated": {
      const jobs = client.getQueryData<Job[]>(JOBS_KEY)
      const before = jobs?.find((j) => j.id === event.patch.id)
      if (jobs === undefined || before === undefined) return {}
      const next = mergeJobPatch(jobs, event.patch)
      client.setQueryData<Job[]>(JOBS_KEY, next)
      return { before, after: next.find((j) => j.id === event.patch.id) }
    }
    case "queue.paused":
      setQueue(client, { pausedUntil: event.until, reason: event.reason })
      return {}
    case "queue.resumed":
      setQueue(client, { pausedUntil: null, reason: null })
      return {}
    case "app.shutdown":
      return {}
  }
}

function setQueue(
  client: QueryClient,
  patch: Pick<QueueState, "pausedUntil" | "reason">
): void {
  const queue = client.getQueryData<QueueState>(QUEUE_KEY)
  // ยังไม่รู้จำนวนงานพร้อมกัน: ให้โหลดสถานะคิวใหม่ทั้งก้อนแทนการเดา
  if (queue === undefined)
    void client.invalidateQueries({ queryKey: QUEUE_KEY })
  else client.setQueryData<QueueState>(QUEUE_KEY, { ...queue, ...patch })
}

export type ConnectOptions = {
  /** backend กำลังปิดตัว (หน้าเว็บแสดงหน้าปิดโปรแกรมแล้ว) */
  onShutdown: () => void
  /** สถานะของงานเปลี่ยนในแท็บนี้ (before = ไม่รู้จักงานนี้มาก่อน) */
  onJobChange?: (before: Job | undefined, after: Job) => void
  /** สำหรับเทส: สร้าง EventSource ปลอม */
  createSource?: (url: string) => EventSource
}

/**
 * ต่อ SSE ครั้งเดียวต่อหน้า แล้วคอยใส่เหตุการณ์ลงแคช คืนฟังก์ชันตัดการเชื่อมต่อ
 * เบราว์เซอร์ต่อใหม่เองเมื่อหลุด ("error" แล้ว "open") ระหว่างหลุดอาจพลาดเหตุการณ์ จึงโหลดรายการงานและสถานะคิวใหม่
 * open ครั้งแรกก็โหลดใหม่หนึ่งครั้ง: เหตุการณ์ที่มาถึงก่อนรายการงานแรกโหลดเสร็จถูกข้ามไป (แคชยังไม่มี)
 * app.shutdown = ปิดการเชื่อมต่อถาวร (backend ไม่กลับมาแล้ว ไม่ต้องลองต่อใหม่ทุก 3 วิ)
 */
export function connectEvents(
  client: QueryClient,
  opts: ConnectOptions
): () => void {
  const source = (opts.createSource ?? ((url: string) => new EventSource(url)))(
    EVENTS_URL
  )
  // ยังไม่เคยต่อติด = ต้องโหลดใหม่ตอน open ครั้งแรกด้วย: เหตุการณ์ที่มาก่อนรายการงานโหลดเสร็จ (แคชว่าง) ถูกข้ามไป
  let lostConnection = true

  const handlers = EVENT_NAMES.map((name) => {
    const handler = (message: Event) => {
      const event = parseServerEvent(
        name,
        String((message as MessageEvent).data)
      )
      if (event === null) return
      if (event.type === "app.shutdown") {
        source.close()
        appShutdown.set()
        opts.onShutdown()
        return
      }
      const { before, after } = applyServerEvent(client, event)
      if (after !== undefined && before?.status !== after.status)
        opts.onJobChange?.(before, after)
    }
    return [name, handler] as const
  })

  const onError = () => {
    lostConnection = true
  }
  const onOpen = () => {
    if (!lostConnection) return
    lostConnection = false
    void client.invalidateQueries({ queryKey: JOBS_KEY })
    void client.invalidateQueries({ queryKey: QUEUE_KEY })
  }

  for (const [name, handler] of handlers) source.addEventListener(name, handler)
  source.addEventListener("error", onError)
  source.addEventListener("open", onOpen)

  return () => {
    for (const [name, handler] of handlers)
      source.removeEventListener(name, handler)
    source.removeEventListener("error", onError)
    source.removeEventListener("open", onOpen)
    source.close()
  }
}

function createFlag() {
  let value = false
  const listeners = new Set<() => void>()
  return {
    get: () => value,
    set() {
      if (value) return
      value = true
      listeners.forEach((listener) => listener())
    },
    subscribe(listener: () => void) {
      listeners.add(listener)
      return () => void listeners.delete(listener)
    },
  }
}

/** backend ประกาศปิดโปรแกรมแล้ว (ตั้งครั้งเดียว ไม่กลับเป็น false) */
export const appShutdown: {
  get(): boolean
  set(): void
  subscribe(fn: () => void): () => void
} = createFlag()

export function useAppShutdown(): boolean {
  return useSyncExternalStore(
    appShutdown.subscribe,
    appShutdown.get,
    appShutdown.get
  )
}
