import {
  useMutation,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query"
import { useNavigate } from "react-router"
import { toast } from "sonner"

// M6 รอบ B: lib → components ครั้งแรก (toast ต้องมี JSX ของปุ่มคัดลอก) · lib/report.ts ยังไม่มี React
import { showErrorToast } from "@/components/error-report/error-toast"
import { fill } from "@/i18n/th"

import { api, ApiError } from "./api"
import { reportRequest } from "./report"
import type { Job, JobPatch, NewJob, QueueState } from "./types"

/** ทางลัดสำหรับเทส: ส่ง fetch/token ปลอมต่อให้ api() (ผู้ใช้จริงไม่ต้องส่ง) */
type ApiDeps = Parameters<typeof api>[2]

export const JOBS_KEY = ["jobs"] as const
export const QUEUE_KEY = ["queue"] as const

/** รายการงานแบบค่าเริ่มต้นของ GET /jobs (กำลังทำ รอคิว พลาดล่าสุด เสร็จล่าสุด) */
export function jobsQuery(deps?: ApiDeps): {
  queryKey: typeof JOBS_KEY
  queryFn: () => Promise<Job[]>
} {
  return {
    queryKey: JOBS_KEY,
    queryFn: () =>
      api<{ jobs: Job[] }>("/jobs", {}, deps).then((body) => body.jobs),
  }
}

/** สถานะคิว: หยุดพักอยู่ถึงเมื่อไร (เบรกฉุกเฉิน) และทำพร้อมกันได้กี่งาน */
export function queueQuery(deps?: ApiDeps): {
  queryKey: typeof QUEUE_KEY
  queryFn: () => Promise<QueueState>
} {
  return {
    queryKey: QUEUE_KEY,
    queryFn: () => api<QueueState>("/queue", {}, deps),
  }
}

const post = (body?: unknown): RequestInit =>
  body === undefined
    ? { method: "POST" }
    : { method: "POST", body: JSON.stringify(body) }

const jobPath = (id: string) => `/jobs/${encodeURIComponent(id)}`

export async function enqueueJobs(
  items: NewJob[],
  deps?: ApiDeps
): Promise<Job[]> {
  const body = await api<{ jobs: Job[] }>("/jobs", post({ items }), deps)
  return body.jobs
}

export function cancelJob(id: string, deps?: ApiDeps): Promise<Job> {
  return api<Job>(`${jobPath(id)}/cancel`, post(), deps)
}

export function retryJob(id: string, deps?: ApiDeps): Promise<Job> {
  return api<Job>(`${jobPath(id)}/retry`, post(), deps)
}

/** ลำดับใหม่ของงานที่รอคิว (งานที่ไม่ได้รอคิวแล้ว backend ข้ามไปเอง) */
export async function reorderJobs(
  ids: string[],
  deps?: ApiDeps
): Promise<void> {
  await api(
    "/jobs/order",
    { method: "PUT", body: JSON.stringify({ ids }) },
    deps
  )
}

/** "ลองต่อเลย": ปลดเบรกฉุกเฉินก่อนครบเวลา */
export async function resumeQueue(deps?: ApiDeps): Promise<void> {
  await api("/queue/resume", post(), deps)
}

/** เปิดโฟลเดอร์ที่มีไฟล์ของงานนี้ (บนเครื่องผู้ใช้) */
export async function revealOutput(
  id: string,
  index: number,
  deps?: ApiDeps
): Promise<void> {
  await api(`${jobPath(id)}/outputs/${index}/reveal`, post(), deps)
}

/** ลิงก์ดาวน์โหลดไฟล์ของงานผ่านเบราว์เซอร์ */
export const outputUrl = (id: string, index: number) =>
  `/api/jobs/${encodeURIComponent(id)}/outputs/${index}`

/** ใส่งานลงรายการ: มีรหัสนี้อยู่แล้วแทนที่ตำแหน่งเดิม ไม่มีก็ต่อท้าย (คืนรายการใหม่เสมอ) */
export function upsertJob(jobs: readonly Job[], job: Job): Job[] {
  const index = jobs.findIndex((j) => j.id === job.id)
  if (index === -1) return [...jobs, job]
  const next = [...jobs]
  next[index] = job
  return next
}

/**
 * รวมส่วนที่เปลี่ยน (SSE job.updated) เข้ากับงานเดิม: ค่า null = ลบคีย์นั้น, ไม่มีคีย์ = คงค่าเดิม
 * รหัสที่ไม่มีในรายการ = คืนรายการเดิมทั้งก้อน (react-query จึงไม่ render ใหม่)
 */
export function mergeJobPatch(jobs: readonly Job[], patch: JobPatch): Job[] {
  const index = jobs.findIndex((j) => j.id === patch.id)
  if (index === -1) return jobs as Job[]
  const merged: Record<string, unknown> = { ...jobs[index] }
  for (const [key, value] of Object.entries(patch)) {
    if (key === "id" || value === undefined) continue
    if (value === null) delete merged[key]
    else merged[key] = value
  }
  const next = [...jobs]
  next[index] = merged as Job
  return next
}

export type SheetGroups = {
  running: Job[]
  queued: Job[]
  failed: Job[]
  done: Job[]
}

/** แสดงงานที่เสร็จแล้วในชีตคิวได้ไม่เกินเท่านี้ (ที่เหลือดูในหน้าประวัติ) */
const SHEET_DONE_LIMIT = 20

const byTimeAsc = (key: "startedAt" | "finishedAt") => (a: Job, b: Job) =>
  (a[key] ?? "").localeCompare(b[key] ?? "")
const byTimeDesc = (key: "startedAt" | "finishedAt") => (a: Job, b: Job) =>
  (b[key] ?? "").localeCompare(a[key] ?? "")

/**
 * จัดกลุ่มงานในชีตคิว: กำลังทำ (เริ่มก่อนอยู่บน) · รอคิว (ตามลำดับคิว) · พลาด (รวมงานที่ค้างตอนปิดโปรแกรม ล่าสุดอยู่บน)
 * · เสร็จ (ล่าสุดอยู่บน ไม่เกิน 20) · งานที่ยกเลิกไม่แสดง
 */
export function groupForSheet(jobs: readonly Job[]): SheetGroups {
  const of = (...statuses: Job["status"][]) =>
    jobs.filter((j) => statuses.includes(j.status))
  return {
    running: of("running").sort(byTimeAsc("startedAt")),
    queued: of("queued").sort((a, b) => a.position - b.position),
    failed: of("failed", "interrupted").sort(byTimeDesc("finishedAt")),
    done: of("done").sort(byTimeDesc("finishedAt")).slice(0, SHEET_DONE_LIMIT),
  }
}

export type BarSummary = {
  visible: boolean
  current: Job | null
  running: number
  queued: number
  done: number
  failed: number
}

/**
 * ข้อมูลแถบคิวด้านล่าง: แสดงเมื่อมีงานที่ไม่ได้ยกเลิกอย่างน้อยหนึ่งงาน · current = งานที่เพิ่งเริ่มล่าสุดในงานที่กำลังทำ
 * · failed นับรวมงานที่ค้างตอนปิดโปรแกรม (interrupted) เหมือนกลุ่มในชีต
 */
export function barSummary(jobs: readonly Job[]): BarSummary {
  const count = (...statuses: Job["status"][]) =>
    jobs.filter((j) => statuses.includes(j.status)).length
  const running = jobs.filter((j) => j.status === "running")
  const current = running.reduce<Job | null>(
    (latest, job) =>
      latest === null || (job.startedAt ?? "") > (latest.startedAt ?? "")
        ? job
        : latest,
    null
  )
  return {
    visible: jobs.some((j) => j.status !== "cancelled"),
    current,
    running: running.length,
    queued: count("queued"),
    done: count("done"),
    failed: count("failed", "interrupted"),
  }
}

/** ข้อความแจ้งผลการส่งเข้าคิว (หน้าเว็บส่ง th.queue.{added, addedMany, addFailed, goHealth} มา) */
export type EnqueueMessages = {
  added: string
  addedMany: string
  failed: string
  goHealth: string
}

/** ที่อยู่หน้าตรวจสุขภาพ (ติดตั้ง ffmpeg) สำหรับปุ่มใน toast เมื่อเครื่องยังไม่มี ffmpeg */
export const HEALTH_PATH = "/settings/health"

/** id ของ toast "ส่งเข้าคิวไม่สำเร็จ" (M6 รอบ B): พลาดซ้ำแทนที่ toast เดิม ไม่ซ้อนกัน */
export const ENQUEUE_TOAST_ID = "enqueue-error"

type EnqueueEnv = { navigate: (path: string) => void; deps?: ApiDeps }

/**
 * ส่งงานเข้าคิวแล้วแจ้งผลด้วย toast: สำเร็จ = ใส่งานลงแคชรายการงานทันที (แถบคิวขึ้นโดยไม่ต้องรอ SSE) คืน true
 * · 409 E_FFMPEG_MISSING = toast พร้อมปุ่มไปหน้าตรวจสุขภาพ · error อื่น = toast ข้อความจาก backend (ไม่มี = ข้อความกลาง)
 */
export async function submitEnqueue(
  client: QueryClient,
  items: NewJob[],
  messages: EnqueueMessages,
  env: EnqueueEnv
): Promise<boolean> {
  try {
    const jobs = await enqueueJobs(items, env.deps)
    // ใส่เฉพาะงานที่แคชยังไม่มี: SSE อาจมาถึงก่อนคำตอบนี้ (เช่นงานเริ่มทำไปแล้ว) ห้ามย้อนกลับเป็น queued
    client.setQueryData<Job[]>(JOBS_KEY, (old) =>
      jobs.reduce(
        (list, job) =>
          list.some((known) => known.id === job.id) ? list : [...list, job],
        old ?? []
      )
    )
    toast.success(
      jobs.length === 1
        ? messages.added
        : fill(messages.addedMany, { n: jobs.length })
    )
    return true
  } catch (error) {
    const request = reportRequest(error, { context: "enqueue" })
    if (
      error instanceof ApiError &&
      error.status === 409 &&
      error.code === "E_FFMPEG_MISSING"
    ) {
      showErrorToast(error.message, {
        id: ENQUEUE_TOAST_ID,
        request,
        action: {
          label: messages.goHealth,
          onClick: () => env.navigate(HEALTH_PATH),
        },
      })
    } else {
      showErrorToast(
        error instanceof Error && error.message
          ? error.message
          : messages.failed,
        { id: ENQUEUE_TOAST_ID, request }
      )
    }
    return false
  }
}

/** hook ของปุ่มส่งเข้าคิว: enqueue คืน true เมื่อเข้าคิวสำเร็จ · pending = กำลังส่ง (ใช้ปิดปุ่มกันกดซ้ำ) */
export function useEnqueue(messages: EnqueueMessages): {
  enqueue: (items: NewJob[]) => Promise<boolean>
  pending: boolean
} {
  const client = useQueryClient()
  const navigate = useNavigate()
  const mutation = useMutation({
    mutationFn: (items: NewJob[]) =>
      submitEnqueue(client, items, messages, {
        navigate: (path) => void navigate(path),
      }),
  })
  return { enqueue: mutation.mutateAsync, pending: mutation.isPending }
}
