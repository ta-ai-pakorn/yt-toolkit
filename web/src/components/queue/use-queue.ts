import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback, useEffect, useSyncExternalStore } from "react"
import { toast } from "sonner"

import { fill, th } from "@/i18n/th"
import { ApiError } from "@/lib/api"
import { connectEvents } from "@/lib/events"
import { cancelJob, JOBS_KEY, jobsQuery, queueQuery, reorderJobs, retryJob, revealOutput } from "@/lib/jobs"
import type { Job } from "@/lib/types"

import { jobTitle } from "./job-text"

// ---------- ฟังก์ชันล้วน (เทสได้โดยไม่ต้องมีหน้าเว็บ) ----------

/** ตำแหน่งเดิมของงานที่ถูกย้าย (ใช้ย้อนกลับเมื่อบันทึกลำดับใหม่ไม่สำเร็จ) */
export type PositionSnapshot = Record<string, number>

/**
 * เรียงลำดับคิวใหม่ทันทีในแคช (ก่อน backend ตอบ) แบบเดียวกับ PUT /jobs/order:
 * งานที่ไม่ได้รอคิวแล้วข้ามไป · งานที่เหลือรับตำแหน่งเดิมของกลุ่มตัวเอง (เรียงน้อยไปมาก) ตามลำดับที่ส่งมา
 * · งานรอคิวอื่นคงตำแหน่งเดิม · คืนรายการใหม่ และตำแหน่งเดิมของงานที่ถูกเปลี่ยน
 */
export function applyReorder(jobs: readonly Job[], ids: readonly string[]): { jobs: Job[]; snapshot: PositionSnapshot } {
  const queued = new Map(jobs.filter((j) => j.status === "queued").map((j) => [j.id, j]))
  const order = [...new Set(ids)].filter((id) => queued.has(id))
  const slots = order.map((id) => queued.get(id)!.position).sort((a, b) => a - b)
  const target = new Map(order.map((id, i) => [id, slots[i]]))
  const snapshot: PositionSnapshot = {}
  const next = jobs.map((job) => {
    const position = target.get(job.id)
    if (position === undefined || position === job.position) return job
    snapshot[job.id] = job.position
    return { ...job, position }
  })
  return { jobs: next, snapshot }
}

/** ย้อนตำแหน่งของงานที่ย้ายไว้กลับที่เดิม (เฉพาะงานที่ยังรอคิวอยู่ งานที่เริ่มหรือจบไปแล้วไม่ต้องย้อน) */
export function rollbackReorder(jobs: readonly Job[], snapshot: PositionSnapshot): Job[] {
  return jobs.map((job) =>
    job.status === "queued" && snapshot[job.id] !== undefined && snapshot[job.id] !== job.position
      ? { ...job, position: snapshot[job.id] }
      : job,
  )
}

/**
 * ใส่ผลของปุ่มยกเลิก/ลองใหม่ลงแคชแบบไม่ทับข้อมูลที่ใหม่กว่า (SSE มาถึงก่อนคำตอบได้)
 * - ยังไม่มีงานนี้ในแคช = ใส่เพิ่ม
 * - งานยังทำอยู่ และคำตอบบอกว่ากำลังยกเลิก = ติดป้ายกำลังยกเลิกอย่างเดียว
 * - งานในแคชยังพลาดหรือหยุดกลางคัน และคำตอบบอกว่ากลับเข้าคิวแล้ว = ใช้คำตอบ (SSE ยังไม่มา)
 * - คำตอบบอกว่ายกเลิกแล้ว (งานที่รอคิว) = ใช้คำตอบ: ยกเลิกแล้วเปลี่ยนสถานะต่อไม่ได้ จึงไม่มีอะไรใหม่กว่านี้
 * - อื่น ๆ = แคชเดิม (SSE ใหม่กว่า)
 */
export function applyActionResult(jobs: readonly Job[] | undefined, job: Job): Job[] {
  const list = jobs ?? []
  const index = list.findIndex((j) => j.id === job.id)
  if (index === -1) return [...list, job]
  const cached = list[index]
  let replacement: Job | null = null
  if (job.cancelling && cached.status === "running" && !cached.cancelling) replacement = { ...cached, cancelling: true }
  else if (job.status === "queued" && (cached.status === "failed" || cached.status === "interrupted")) replacement = job
  else if (job.status === "cancelled" && cached.status !== "cancelled") replacement = job
  if (replacement === null) return list as Job[]
  const next = [...list]
  next[index] = replacement
  return next
}

/** toast ที่ควรเด้งเมื่อสถานะงานเปลี่ยนในแท็บนี้ (เสร็จ / พลาด) · สถานะอื่นไม่เด้ง */
export function jobToast(before: Job | undefined, after: Job): "finished" | "failed" | null {
  if (before?.status === after.status) return null
  if (after.status === "done") return "finished"
  if (after.status === "failed") return "failed"
  return null
}

// ---------- สถานะเปิด/ปิดของชีตคิว (แถบคิวและปุ่มใน toast ใช้ร่วมกัน) ----------

type SheetState = { open: boolean; focusId: string | null }

function createSheetStore() {
  let state: SheetState = { open: false, focusId: null }
  const listeners = new Set<() => void>()
  const set = (next: SheetState) => {
    state = next
    listeners.forEach((listener) => listener())
  }
  return {
    get: () => state,
    /** เปิดชีต · focusId = เลื่อนไปที่แถวของงานนั้น */
    open: (focusId: string | null = null) => set({ open: true, focusId }),
    close: () => {
      resetQueueDrag()
      set({ open: false, focusId: null })
    },
    subscribe(listener: () => void) {
      listeners.add(listener)
      return () => void listeners.delete(listener)
    },
  }
}

export const queueSheet = createSheetStore()

/**
 * กำลังลากเปลี่ยนลำดับงานในชีตอยู่ไหม (sortable-queued.tsx ตั้งค่า) · ชีตใช้ตัดสินว่า Esc หมายถึง "ยกเลิกการลาก"
 * ไม่ใช่ "ปิดชีต" · ลำดับที่ Base UI กับ dnd-kit เห็น Esc ไม่แน่นอน จึงจำตัวเหตุการณ์ Esc ที่กดระหว่างลากไว้ (cancelKey)
 * แล้วเทียบกับเหตุการณ์ที่ Base UI ส่งมา แทนการรอเวลา
 */
export const queueDrag: { active: boolean; cancelKey: Event | null } = { active: false, cancelKey: null }

function rememberCancelKey(event: KeyboardEvent): void {
  if (event.key === "Escape") queueDrag.cancelKey = event
}

export function startQueueDrag(): void {
  queueDrag.active = true
  queueDrag.cancelKey = null
  // capture ที่ window: เห็นก่อนทั้ง Base UI และ dnd-kit
  window.addEventListener("keydown", rememberCancelKey, { capture: true })
}

/**
 * จบการลาก (วาง / ยกเลิก) หรือล้างทันทีเมื่อรายการที่ลากอยู่หายไปกลางคัน (งานเริ่มทำ, กดนอกชีต) หรือชีตปิด
 * จะได้ไม่ค้างว่ายังลากอยู่
 */
export function resetQueueDrag(): void {
  queueDrag.active = false
  window.removeEventListener("keydown", rememberCancelKey, { capture: true })
}

/** Esc นี้เป็นของการลาก (กำลังลากอยู่ หรือเป็นปุ่มเดียวกับที่เพิ่งยกเลิกการลาก) ไม่ใช่คำสั่งปิดชีต */
export function isDragEscape(event: Event | undefined): boolean {
  return queueDrag.active || (event !== undefined && event === queueDrag.cancelKey)
}

export function useQueueSheet(): SheetState {
  return useSyncExternalStore(queueSheet.subscribe, queueSheet.get, queueSheet.get)
}

// ---------- hooks ----------

/**
 * รายการงานและสถานะคิว · SSE คอยแก้แคชให้ จึงไม่โหลดซ้ำเองตอนเปิดชีตหรือย้ายหน้า
 * (คำตอบที่เริ่มโหลดก่อนเหตุการณ์ SSE จะทับสถานะใหม่ด้วยของเก่า) · โหลดใหม่เมื่อ SSE ต่อกลับมาได้ (events.ts)
 */
export function useQueueData() {
  const jobs = useQuery({ ...jobsQuery(), staleTime: Infinity })
  const queue = useQuery({ ...queueQuery(), staleTime: Infinity })
  return { jobs: jobs.data, jobsError: jobs.isError, queue: queue.data }
}

/** เปิดโฟลเดอร์ของไฟล์ · ไม่สำเร็จ = toast (ไม่พบไฟล์ / เปิดไม่ได้) */
export async function revealWithToast(id: string, index: number): Promise<void> {
  try {
    await revealOutput(id, index)
  } catch (error) {
    toast.error(error instanceof ApiError && error.status === 404 ? th.queue.fileMissing : th.queue.revealFailed)
  }
}

function notifyJobChange(before: Job | undefined, after: Job): void {
  const kind = jobToast(before, after)
  const title = jobTitle(after)
  if (kind === "finished") {
    const first = after.outputs?.[0]
    toast.success(fill(th.queue.finished, { title }), {
      id: `job-${after.id}`,
      action: first
        ? { label: th.queue.openFolder, onClick: () => void revealWithToast(after.id, first.index) }
        : undefined,
    })
  } else if (kind === "failed") {
    toast.error(fill(th.queue.failed, { title }), {
      id: `job-${after.id}`,
      description: after.error?.message,
      duration: Infinity,
      action: { label: th.queue.details, onClick: () => queueSheet.open(after.id) },
    })
  }
}

/** ต่อ SSE ครั้งเดียวต่อหน้า (วางไว้ที่ layout) · เด้ง toast เมื่องานเสร็จหรือพลาดระหว่างเปิดแท็บนี้อยู่ */
export function useServerEvents(): void {
  const client = useQueryClient()
  useEffect(
    () => connectEvents(client, { onShutdown: () => toast.dismiss(), onJobChange: notifyJobChange }),
    [client],
  )
}

/** ยกเลิก / ลองใหม่ ของงานหนึ่งงาน · ไม่สำเร็จ = toast แล้วโหลดรายการงานใหม่ */
export function useJobAction(action: "cancel" | "retry", id: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => (action === "cancel" ? cancelJob(id) : retryJob(id)),
    onSuccess: (job) => client.setQueryData<Job[]>(JOBS_KEY, (old) => applyActionResult(old, job)),
    onError: () => {
      toast.error(th.queue.actionFailed)
      void client.invalidateQueries({ queryKey: JOBS_KEY })
    },
  })
}

/** ส่งลำดับคิวใหม่: เรียงในแคชทันที · backend ไม่รับ = ย้อนกลับที่เดิมพร้อม toast */
export function useReorder(): (ids: string[]) => Promise<void> {
  const client = useQueryClient()
  return useCallback(
    async (ids: string[]) => {
      // หยุดการโหลดรายการที่ค้างอยู่ก่อน ไม่งั้นคำตอบเก่าจะทับลำดับใหม่
      await client.cancelQueries({ queryKey: JOBS_KEY })
      const jobs = client.getQueryData<Job[]>(JOBS_KEY)
      if (jobs === undefined) return
      const { jobs: next, snapshot } = applyReorder(jobs, ids)
      if (Object.keys(snapshot).length === 0) return
      client.setQueryData<Job[]>(JOBS_KEY, next)
      try {
        await reorderJobs(ids)
      } catch {
        client.setQueryData<Job[]>(JOBS_KEY, (old) => (old === undefined ? old : rollbackReorder(old, snapshot)))
        toast.error(th.queue.actionFailed)
      }
    },
    [client],
  )
}
