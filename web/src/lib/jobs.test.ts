import { QueryClient } from "@tanstack/react-query"
import { beforeEach, describe, expect, it, vi } from "vitest"

const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))
vi.mock("sonner", () => ({ toast: toastMock }))

import {
  barSummary,
  cancelJob,
  enqueueJobs,
  groupForSheet,
  HEALTH_PATH,
  JOBS_KEY,
  jobsQuery,
  mergeJobPatch,
  outputUrl,
  queueQuery,
  reorderJobs,
  resumeQueue,
  retryJob,
  revealOutput,
  submitEnqueue,
  upsertJob,
} from "./jobs"
import type { Job, NewJob } from "./types"

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

let seq = 0
function job(over: Partial<Job> = {}): Job {
  seq += 1
  return {
    id: `00000000-0000-0000-0000-${String(seq).padStart(12, "0")}`,
    videoId: "aqz-KE-bpKQ",
    title: `คลิป ${seq}`,
    kind: "video",
    params: {
      maxQuality: false,
      splitChapters: false,
      noAudio: false,
      audioLanguage: "original",
    },
    status: "queued",
    position: seq,
    createdAt: "2026-10-01T10:00:00Z",
    ...over,
  }
}

const newJob: NewJob = {
  videoId: "aqz-KE-bpKQ",
  kind: "video",
  params: {
    maxQuality: false,
    splitChapters: false,
    noAudio: false,
    audioLanguage: "original",
  },
  title: "Big Buck Bunny",
}

const messages = {
  added: "เพิ่มเข้าคิวแล้ว",
  addedMany: "เพิ่มเข้าคิวแล้ว {n} งาน",
  failed: "ส่งไม่สำเร็จ",
  goHealth: "ไปหน้าตรวจสุขภาพ",
}

beforeEach(() => {
  toastMock.success.mockReset()
  toastMock.error.mockReset()
})

describe("mergeJobPatch", () => {
  it("รวมค่าที่เปลี่ยนเข้ากับงานเดิม คืนรายการใหม่ งานอื่นเป็นก้อนเดิม", () => {
    const a = job({ status: "running", startedAt: "2026-10-01T10:00:01Z" })
    const b = job()
    const jobs = [a, b]
    const next = mergeJobPatch(jobs, {
      id: a.id,
      progress: 0.5,
      stage: "downloading_video",
    })
    expect(next).not.toBe(jobs)
    expect(next[0]).toEqual({ ...a, progress: 0.5, stage: "downloading_video" })
    expect(next[1]).toBe(b)
    expect(jobs[0]).toBe(a) // ไม่แก้ก้อนเดิม
  })

  it("ค่า null = ลบคีย์นั้นออก", () => {
    const a = job({
      status: "running",
      stage: "merging",
      attempt: 2,
      cancelling: true,
    })
    const [merged] = mergeJobPatch([a], {
      id: a.id,
      status: "done",
      stage: null,
      attempt: null,
      cancelling: null,
    })
    expect(merged.status).toBe("done")
    expect("stage" in merged).toBe(false)
    expect("attempt" in merged).toBe(false)
    expect("cancelling" in merged).toBe(false)
  })

  it("รหัสที่ไม่รู้จักคืนรายการก้อนเดิม", () => {
    const jobs = [job()]
    expect(
      mergeJobPatch(jobs, {
        id: "ffffffff-0000-0000-0000-000000000000",
        progress: 1,
      })
    ).toBe(jobs)
  })
})

describe("upsertJob", () => {
  it("รหัสเดิมแทนที่ตำแหน่งเดิม", () => {
    const a = job()
    const b = job()
    const updated = { ...a, status: "running" as const }
    expect(upsertJob([a, b], updated)).toEqual([updated, b])
  })

  it("รหัสใหม่ต่อท้าย", () => {
    const a = job()
    const b = job()
    expect(upsertJob([a], b)).toEqual([a, b])
  })
})

describe("groupForSheet", () => {
  it("จัดกลุ่มและเรียงตามสัญญา งานที่ยกเลิกไม่แสดง", () => {
    const r1 = job({ status: "running", startedAt: "2026-10-01T10:00:05Z" })
    const r2 = job({ status: "running", startedAt: "2026-10-01T10:00:01Z" })
    const q1 = job({ status: "queued", position: 9 })
    const q2 = job({ status: "queued", position: 3 })
    const f1 = job({ status: "failed", finishedAt: "2026-10-01T09:00:00Z" })
    const i1 = job({
      status: "interrupted",
      finishedAt: "2026-10-01T09:30:00Z",
    })
    const c1 = job({ status: "cancelled", finishedAt: "2026-10-01T09:45:00Z" })
    const d1 = job({ status: "done", finishedAt: "2026-10-01T08:00:00Z" })
    const d2 = job({ status: "done", finishedAt: "2026-10-01T08:30:00Z" })
    const groups = groupForSheet([d1, q1, r1, f1, c1, i1, q2, d2, r2])
    expect(groups.running).toEqual([r2, r1])
    expect(groups.queued).toEqual([q2, q1])
    expect(groups.failed).toEqual([i1, f1])
    expect(groups.done).toEqual([d2, d1])
    expect(Object.values(groups).flat()).not.toContain(c1)
  })

  it("งานที่เสร็จแสดงแค่ 20 งานล่าสุด", () => {
    const done = Array.from({ length: 25 }, (_, i) =>
      job({
        status: "done",
        finishedAt: `2026-10-01T08:${String(i).padStart(2, "0")}:00Z`,
      })
    )
    const groups = groupForSheet(done)
    expect(groups.done).toHaveLength(20)
    expect(groups.done[0]).toBe(done[24])
    expect(groups.done[19]).toBe(done[5])
  })
})

describe("barSummary", () => {
  it("นับแต่ละสถานะ (พลาดรวมงานค้าง) current = งานที่เริ่มล่าสุด", () => {
    const early = job({ status: "running", startedAt: "2026-10-01T10:00:01Z" })
    const late = job({ status: "running", startedAt: "2026-10-01T10:00:09Z" })
    const summary = barSummary([
      early,
      late,
      job({ status: "queued" }),
      job({ status: "queued" }),
      job({ status: "queued" }),
      job({ status: "done" }),
      job({ status: "failed" }),
      job({ status: "interrupted" }),
      job({ status: "cancelled" }),
    ])
    expect(summary).toEqual({
      visible: true,
      current: late,
      running: 2,
      queued: 3,
      done: 1,
      failed: 2,
    })
  })

  it("ไม่มีงานหรือมีแต่งานที่ยกเลิก = ซ่อนแถบ", () => {
    expect(barSummary([])).toEqual({
      visible: false,
      current: null,
      running: 0,
      queued: 0,
      done: 0,
      failed: 0,
    })
    expect(barSummary([job({ status: "cancelled" })]).visible).toBe(false)
  })

  it("มีแต่งานที่เสร็จ = ยังแสดงแถบ แต่ไม่มีงานปัจจุบัน", () => {
    const summary = barSummary([job({ status: "done" })])
    expect(summary.visible).toBe(true)
    expect(summary.current).toBeNull()
  })
})

describe("API ของคิว", () => {
  it("enqueueJobs ส่ง {items} แบบ POST พร้อม token และคืนงานที่สร้าง", async () => {
    const created = job()
    const fetch = vi
      .fn()
      .mockResolvedValue(jsonResponse(200, { jobs: [created] }))
    await expect(
      enqueueJobs([newJob], { fetch, token: "tok" })
    ).resolves.toEqual([created])
    const [url, init] = fetch.mock.calls[0]
    expect(url).toBe("/api/jobs")
    expect(init.method).toBe("POST")
    expect(new Headers(init.headers).get("X-Toolkit-Token")).toBe("tok")
    expect(JSON.parse(init.body)).toEqual({ items: [newJob] })
  })

  it("jobsQuery / queueQuery อ่าน GET /jobs และ GET /queue", async () => {
    const jobs = [job()]
    const fetch = vi.fn().mockResolvedValueOnce(jsonResponse(200, { jobs }))
    const query = jobsQuery({ fetch })
    expect(query.queryKey).toBe(JOBS_KEY)
    await expect(query.queryFn()).resolves.toEqual(jobs)
    expect(fetch.mock.calls[0][0]).toBe("/api/jobs")

    const state = { pausedUntil: null, reason: null, concurrency: 2 }
    fetch.mockResolvedValueOnce(jsonResponse(200, state))
    await expect(queueQuery({ fetch }).queryFn()).resolves.toEqual(state)
    expect(fetch.mock.calls[1][0]).toBe("/api/queue")
  })

  it("ปุ่มของแต่ละงานเรียก path ตามสัญญา C4", async () => {
    const id = "0f0e0d0c-0b0a-0908-0706-050403020100"
    const fetch = vi
      .fn()
      .mockImplementation(async () => jsonResponse(200, { ok: true }))
    const deps = { fetch, token: "tok" }
    await cancelJob(id, deps)
    await retryJob(id, deps)
    await reorderJobs([id], deps)
    await resumeQueue(deps)
    await revealOutput(id, 1, deps)
    const calls = fetch.mock.calls.map(([url, init]) => `${init.method} ${url}`)
    expect(calls).toEqual([
      `POST /api/jobs/${id}/cancel`,
      `POST /api/jobs/${id}/retry`,
      "PUT /api/jobs/order",
      "POST /api/queue/resume",
      `POST /api/jobs/${id}/outputs/1/reveal`,
    ])
    expect(JSON.parse(fetch.mock.calls[2][1].body)).toEqual({ ids: [id] })
    for (const [, init] of fetch.mock.calls)
      expect(new Headers(init.headers).get("X-Toolkit-Token")).toBe("tok")
  })

  it("outputUrl", () => {
    expect(outputUrl("abc", 0)).toBe("/api/jobs/abc/outputs/0")
  })
})

describe("submitEnqueue", () => {
  it("สำเร็จ 1 งาน: toast added และใส่งานลงแคชรายการงาน", async () => {
    const client = new QueryClient()
    const old = job({ status: "done" })
    client.setQueryData(JOBS_KEY, [old])
    const created = job()
    const fetch = vi
      .fn()
      .mockResolvedValue(jsonResponse(200, { jobs: [created] }))
    const ok = await submitEnqueue(client, [newJob], messages, {
      navigate: vi.fn(),
      deps: { fetch, token: "t" },
    })
    expect(ok).toBe(true)
    expect(toastMock.success).toHaveBeenCalledWith("เพิ่มเข้าคิวแล้ว")
    expect(client.getQueryData(JOBS_KEY)).toEqual([old, created])
  })

  it("สำเร็จหลายงาน: toast addedMany พร้อมจำนวน และแคชที่ยังไม่โหลดก็ได้รายการ", async () => {
    const client = new QueryClient()
    const created = [job(), job(), job()]
    const fetch = vi
      .fn()
      .mockResolvedValue(jsonResponse(200, { jobs: created }))
    await submitEnqueue(client, [newJob, newJob, newJob], messages, {
      navigate: vi.fn(),
      deps: { fetch, token: "t" },
    })
    expect(toastMock.success).toHaveBeenCalledWith("เพิ่มเข้าคิวแล้ว 3 งาน")
    expect(client.getQueryData(JOBS_KEY)).toEqual(created)
  })

  it("409 E_FFMPEG_MISSING: toast error พร้อมปุ่มไปหน้าตรวจสุขภาพ", async () => {
    const client = new QueryClient()
    const body = {
      error: {
        code: "E_FFMPEG_MISSING",
        message: "ยังไม่มี ffmpeg",
        detail: null,
      },
    }
    const fetch = vi.fn().mockResolvedValue(jsonResponse(409, body))
    const navigate = vi.fn()
    const ok = await submitEnqueue(client, [newJob], messages, {
      navigate,
      deps: { fetch, token: "t" },
    })
    expect(ok).toBe(false)
    const [text, options] = toastMock.error.mock.calls[0]
    expect(text).toBe("ยังไม่มี ffmpeg")
    expect(options.action.label).toBe("ไปหน้าตรวจสุขภาพ")
    options.action.onClick()
    expect(navigate).toHaveBeenCalledWith(HEALTH_PATH)
    expect(HEALTH_PATH).toBe("/settings/health")
    expect(client.getQueryData(JOBS_KEY)).toBeUndefined()
  })

  it("error อื่น: toast ข้อความจาก backend ไม่มีข้อความ = ข้อความกลาง", async () => {
    const client = new QueryClient()
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(422, {
          error: { code: "E_BAD_REQUEST", message: "ค่าไม่ถูกต้อง" },
        })
      )
      .mockResolvedValueOnce(
        jsonResponse(500, { error: { code: "E_X", message: "" } })
      )
    const env = { navigate: vi.fn(), deps: { fetch, token: "t" } }
    await expect(submitEnqueue(client, [newJob], messages, env)).resolves.toBe(
      false
    )
    await expect(submitEnqueue(client, [newJob], messages, env)).resolves.toBe(
      false
    )
    expect(toastMock.error.mock.calls).toEqual([
      ["ค่าไม่ถูกต้อง"],
      ["ส่งไม่สำเร็จ"],
    ])
  })
})
