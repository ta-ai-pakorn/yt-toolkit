import { describe, expect, it, vi } from "vitest"

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), dismiss: vi.fn() } }))

import type { Job } from "@/lib/types"

import { applyActionResult, applyReorder, jobToast, queueSheet, rollbackReorder } from "./use-queue"

function job(id: string, over: Partial<Job> = {}): Job {
  return {
    id,
    videoId: `VID-${id}`,
    title: `คลิป ${id}`,
    kind: "video",
    params: { maxQuality: false, splitChapters: false, noAudio: false, audioLanguage: "original" },
    status: "queued",
    position: 0,
    createdAt: "2026-10-01T10:00:00Z",
    ...over,
  }
}

const positions = (jobs: Job[]) => Object.fromEntries(jobs.map((j) => [j.id, j.position]))

describe("applyReorder", () => {
  const jobs = [
    job("r", { status: "running", position: 1 }),
    job("a", { position: 2 }),
    job("b", { position: 3 }),
    job("c", { position: 5 }),
    job("d", { position: 8 }),
  ]

  it("งานที่ส่งมารับตำแหน่งเดิมของกลุ่มตัวเองตามลำดับใหม่", () => {
    const { jobs: next, snapshot } = applyReorder(jobs, ["a", "b", "d", "c"])
    expect(positions(next)).toEqual({ r: 1, a: 2, b: 3, c: 8, d: 5 })
    expect(snapshot).toEqual({ c: 5, d: 8 })
  })

  it("งานที่ไม่ได้รอคิวถูกข้าม และงานรอคิวที่ไม่ได้ส่งมาคงตำแหน่งเดิม", () => {
    const { jobs: next } = applyReorder(jobs, ["r", "d", "b"])
    expect(positions(next)).toEqual({ r: 1, a: 2, b: 8, c: 5, d: 3 })
  })

  it("ลำดับเดิม = ไม่มีอะไรเปลี่ยน (คืนงานตัวเดิม)", () => {
    const { jobs: next, snapshot } = applyReorder(jobs, ["a", "b", "c", "d"])
    expect(snapshot).toEqual({})
    next.forEach((j, i) => expect(j).toBe(jobs[i]))
  })

  it("รหัสซ้ำหรือไม่รู้จักไม่ทำให้พัง", () => {
    const { jobs: next } = applyReorder(jobs, ["b", "b", "zzz", "a"])
    expect(positions(next)).toMatchObject({ a: 3, b: 2 })
  })
})

describe("rollbackReorder", () => {
  it("คืนตำแหน่งเดิมให้งานที่ยังรอคิว", () => {
    const start = [job("a", { position: 2 }), job("b", { position: 3 })]
    const { jobs: moved, snapshot } = applyReorder(start, ["b", "a"])
    expect(positions(rollbackReorder(moved, snapshot))).toEqual({ a: 2, b: 3 })
  })

  it("งานที่เริ่มไปแล้วระหว่างนั้นไม่ย้อน", () => {
    const start = [job("a", { position: 2 }), job("b", { position: 3 })]
    const { jobs: moved, snapshot } = applyReorder(start, ["b", "a"])
    const started = moved.map((j) => (j.id === "b" ? { ...j, status: "running" as const } : j))
    const back = rollbackReorder(started, snapshot)
    expect(positions(back)).toEqual({ a: 2, b: 2 })
    expect(back[1]).toBe(started[1])
  })
})

describe("applyActionResult (ห้ามเอาคำตอบของปุ่มไปทับแคชทั้งก้อน)", () => {
  it("ยังไม่มีในแคช = ใส่เพิ่ม · แคชยังไม่โหลด = รายการใหม่", () => {
    const a = job("a")
    expect(applyActionResult([], a)).toEqual([a])
    expect(applyActionResult(undefined, a)).toEqual([a])
  })

  it("ยกเลิกงานที่กำลังทำ: ติดป้ายกำลังยกเลิกอย่างเดียว ไม่แตะความคืบหน้าที่ใหม่กว่า", () => {
    const cached = job("a", { status: "running", progress: 0.6, stage: "merging" })
    const response = job("a", { status: "running", progress: 0.2, cancelling: true })
    const [next] = applyActionResult([cached], response)
    expect(next).toEqual({ ...cached, cancelling: true })
  })

  it("SSE ยกเลิกเสร็จมาก่อนคำตอบ = คงแคช", () => {
    const list = [job("a", { status: "cancelled" })]
    expect(applyActionResult(list, job("a", { status: "running", cancelling: true }))).toBe(list)
  })

  it("ลองใหม่: แคชยังพลาดอยู่ = ใช้คำตอบ (กลับเข้าคิว)", () => {
    const list = [job("a", { status: "failed", error: { code: "E_YT_REFUSED", message: "x" } })]
    const response = job("a", { status: "queued", position: 9 })
    expect(applyActionResult(list, response)).toEqual([response])
    const interrupted = [job("a", { status: "interrupted" })]
    expect(applyActionResult(interrupted, response)).toEqual([response])
  })

  it("ลองใหม่: SSE บอกว่าเริ่มทำแล้ว = คงแคช", () => {
    const list = [job("a", { status: "running", progress: 0.3 })]
    expect(applyActionResult(list, job("a", { status: "queued" }))).toBe(list)
  })

  it("ยกเลิกงานที่รอคิว: ใช้คำตอบ cancelled (สถานะสุดท้าย ไม่มีอะไรใหม่กว่า) · ยกเลิกไปแล้ว = คงแคช", () => {
    const cancelled = job("a", { status: "cancelled", finishedAt: "2026-10-01T10:00:09+00:00" })
    expect(applyActionResult([job("a", { status: "queued" })], cancelled)).toEqual([cancelled])
    const list = [job("a", { status: "cancelled" })]
    expect(applyActionResult(list, cancelled)).toBe(list)
  })
})

describe("jobToast", () => {
  it("เสร็จ / พลาด เมื่อสถานะเพิ่งเปลี่ยน", () => {
    expect(jobToast(job("a", { status: "running" }), job("a", { status: "done" }))).toBe("finished")
    expect(jobToast(job("a", { status: "running" }), job("a", { status: "failed" }))).toBe("failed")
  })
  it("สถานะเดิม หรือสถานะอื่น ไม่เด้ง", () => {
    expect(jobToast(job("a", { status: "done" }), job("a", { status: "done" }))).toBeNull()
    expect(jobToast(job("a", { status: "running" }), job("a", { status: "cancelled" }))).toBeNull()
    expect(jobToast(job("a", { status: "running" }), job("a", { status: "interrupted" }))).toBeNull()
    expect(jobToast(undefined, job("a", { status: "queued" }))).toBeNull()
  })
})

describe("queueSheet", () => {
  it("เปิดพร้อมงานที่ต้องเลื่อนไปหา แล้วปิด", () => {
    const listener = vi.fn()
    const unsubscribe = queueSheet.subscribe(listener)
    queueSheet.open("a")
    expect(queueSheet.get()).toEqual({ open: true, focusId: "a" })
    queueSheet.close()
    expect(queueSheet.get()).toEqual({ open: false, focusId: null })
    expect(listener).toHaveBeenCalledTimes(2)
    unsubscribe()
    queueSheet.open()
    expect(listener).toHaveBeenCalledTimes(2)
    queueSheet.close()
  })
})
