import { randomUUID } from "node:crypto"

import {
  expect,
  type APIRequestContext,
  type Locator,
  type Page,
  type Request,
  type Response,
} from "@playwright/test"

import type { Job, JobStatus, NewJob } from "../src/lib/types"

/**
 * ตัวช่วย e2e ของคิวงาน (M4 สัญญา C14)
 *
 * - งานจริงสร้างได้เฉพาะใน spec ชื่อ queue-*.spec.ts (project "queue" มี backend ของตัวเอง)
 * - spec ในโปรเจกต์ chromium ที่กดปุ่มส่งเข้าคิวต้องเรียก mockEnqueue(page) ก่อนเสมอ
 * - คำขอที่เปลี่ยนข้อมูล (POST/PUT) ต้องมี X-Toolkit-Token และ Origin ของ backend: อ่าน token จาก
 *   <meta name="yt-token"> ของหน้าเว็บ (token(page)) หรือจากหน้าแรกที่ backend ส่งมา (เมื่อมีแค่ request)
 */

type Auth = { token: string; origin: string }

const TOKEN_META = /<meta name="yt-token" content="([^"]+)"/
const authCache = new WeakMap<APIRequestContext, Auth>()

/** token ของ backend จากหน้าเว็บที่เปิดอยู่ */
export async function token(page: Page): Promise<string> {
  const value = await page
    .locator('meta[name="yt-token"]')
    .getAttribute("content")
  if (!value)
    throw new Error(
      'ไม่พบ <meta name="yt-token"> ในหน้าเว็บ (เปิดหน้าของแอพก่อน)'
    )
  return value
}

/** token และ origin ของ backend จากหน้าแรก (ใช้ได้ทั้ง request ของเทสและ page.request) */
async function auth(request: APIRequestContext): Promise<Auth> {
  const cached = authCache.get(request)
  if (cached) return cached
  const response = await request.get("/")
  const match = TOKEN_META.exec(await response.text())
  if (!response.ok() || !match)
    throw new Error(`อ่าน token จากหน้าแรกไม่ได้ (HTTP ${response.status()})`)
  const value = { token: match[1], origin: new URL(response.url()).origin }
  authCache.set(request, value)
  return value
}

async function mutate(
  request: APIRequestContext,
  method: "POST" | "PUT",
  path: string,
  data?: unknown
) {
  const { token: value, origin } = await auth(request)
  return request.fetch(path, {
    method,
    headers: { "X-Toolkit-Token": value, Origin: origin },
    ...(data === undefined ? {} : { data }),
  })
}

/** รายการงาน: ไม่ส่ง status = รายการค่าเริ่มต้นแบบเดียวกับแถบคิว · ส่ง status = เฉพาะสถานะนั้น (สูงสุด 200) */
export async function listJobs(
  request: APIRequestContext,
  status?: JobStatus
): Promise<Job[]> {
  const response = await request.get(
    status ? `/api/jobs?status=${status}&limit=200` : "/api/jobs"
  )
  expect(response.ok(), `GET /api/jobs ตอบ ${response.status()}`).toBe(true)
  return ((await response.json()) as { jobs: Job[] }).jobs
}

/**
 * รอจนมีงานที่ตรงเงื่อนไขในรายการค่าเริ่มต้น (ถามทุก 250 ms) หมดเวลา = โยน error พร้อมสถานะงานล่าสุด
 * รายการค่าเริ่มต้นไม่มีงานที่ยกเลิกแล้ว (C4) จึงรอ status "cancelled" ด้วยตัวนี้ไม่ได้:
 * ใช้ listJobs(request, "cancelled") แทน (เช่นใน expect.poll)
 */
export async function waitForJob(
  request: APIRequestContext,
  match: (job: Job) => boolean,
  opts: { timeout?: number } = {}
): Promise<Job> {
  const deadline = Date.now() + (opts.timeout ?? 20_000)
  for (;;) {
    const last = await listJobs(request)
    const found = last.find(match)
    if (found) return found
    if (Date.now() > deadline) {
      const seen =
        last.map((j) => `${j.videoId}:${j.kind}:${j.status}`).join(", ") ||
        "ไม่มีงาน"
      throw new Error(`รองานไม่สำเร็จภายในเวลา งานที่เห็นล่าสุด: ${seen}`)
    }
    await new Promise((resolve) => setTimeout(resolve, 250))
  }
}

/** ยกเลิกงานที่ยังไม่จบของคลิปเหล่านี้ (ยกเลิกงานที่รอคิวก่อน งานจะได้ไม่เริ่มแทนที่งานที่ถูกยกเลิก) */
export async function cancelJobsFor(
  request: APIRequestContext,
  videoIds: string[]
): Promise<void> {
  const wanted = new Set(videoIds)
  for (const status of ["queued", "running"] as const) {
    for (const job of await listJobs(request, status)) {
      if (!wanted.has(job.videoId)) continue
      const response = await mutate(
        request,
        "POST",
        `/api/jobs/${job.id}/cancel`
      )
      // 409 = งานจบไปแล้วระหว่างนั้น ไม่ถือว่าพัง
      if (!response.ok() && response.status() !== 409) {
        throw new Error(
          `ยกเลิกงาน ${job.id} ไม่ได้ (HTTP ${response.status()})`
        )
      }
    }
  }
}

/** ปลดเบรกฉุกเฉินของคิว (ไม่ได้หยุดพักอยู่ก็ตอบ ok) */
export async function resumeQueue(request: APIRequestContext): Promise<void> {
  const response = await mutate(request, "POST", "/api/queue/resume")
  expect(response.ok(), `POST /api/queue/resume ตอบ ${response.status()}`).toBe(
    true
  )
}

/** ส่งงานเข้าคิวผ่าน API (ใช้เฉพาะใน queue-*.spec.ts) */
export async function enqueue(
  request: APIRequestContext,
  items: NewJob[]
): Promise<Job[]> {
  const response = await mutate(request, "POST", "/api/jobs", { items })
  expect(
    response.ok(),
    `POST /api/jobs ตอบ ${response.status()}: ${await response.text()}`
  ).toBe(true)
  return ((await response.json()) as { jobs: Job[] }).jobs
}

/** กดแถบคิวด้านล่างแล้วคืนชีต "คิวงาน" ที่เปิดขึ้นมา */
export async function openQueueSheet(page: Page): Promise<Locator> {
  const bar = page.getByRole("region", { name: "คิวงาน" })
  await bar.locator("button[aria-expanded]").first().click()
  const sheet = page.getByRole("dialog", { name: "คิวงาน" })
  await expect(sheet).toBeVisible()
  // รอแอนิเมชันเปิด (จางเข้า 200ms) จบก่อน: axe วัดสีตัวอักษรระหว่างโปร่งแสงแล้วได้ค่าต่ำเกินจริง
  // (ข้ามแอนิเมชันวนไม่รู้จบ เช่นแถบความคืบหน้าที่ยังไม่รู้ %)
  await sheet.evaluate((el) =>
    Promise.all(
      el
        .getAnimations({ subtree: true })
        .filter((a) => a.effect?.getComputedTiming().endTime !== Infinity)
        .map((a) => a.finished.catch(() => undefined)),
    ),
  )
  return sheet
}

/**
 * สำหรับโปรเจกต์ chromium: ดัก POST /api/jobs แล้วตอบเป็นงานปลอมสถานะ queued (ไม่มีงานจริงเกิดขึ้น)
 * และเก็บ items ของแต่ละคำขอไว้ใน bodies · GET /api/jobs ผ่านไปที่ backend ตามปกติ
 */
export async function mockEnqueue(page: Page): Promise<{ bodies: NewJob[][] }> {
  const bodies: NewJob[][] = []
  let position = 0
  await page.route("**/api/jobs", async (route) => {
    if (route.request().method() !== "POST") return route.fallback()
    const { items } = route.request().postDataJSON() as { items: NewJob[] }
    bodies.push(items)
    const createdAt = new Date().toISOString()
    const jobs: Job[] = items.map((item) => ({
      id: randomUUID(),
      videoId: item.videoId,
      title: item.title ?? "",
      kind: item.kind,
      params: item.params,
      status: "queued",
      position: ++position,
      createdAt,
    }))
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ jobs }),
    })
  })
  return { bodies }
}

/**
 * เปิดหน้าแล้วรอจน SSE ต่อติด และรายการงานที่โหลดใหม่ตอน SSE ต่อติดครั้งแรก (events.ts) เสร็จแล้ว ก่อนส่งงานเข้าคิว
 * ไม่งั้นคำตอบของการโหลดใหม่นั้น (คำนวณก่อนส่งงาน) อาจทับงานที่เพิ่งเข้าคิวในแคช
 * รอจน /api/events ตอบแล้ว มี GET /api/jobs อย่างน้อยสองครั้ง (โหลดแรก + โหลดใหม่ตอนต่อติด) และไม่มีคำขอค้าง
 * (เหตุการณ์ "response" ของ /api/events อาจมาถึงหลังหน้าเว็บส่งคำขอโหลดใหม่ไปแล้ว จึงไม่นับตามลำดับเวลา)
 */
export async function gotoReady(page: Page, path = "/") {
  const isJobsGet = (request: Request) =>
    new URL(request.url()).pathname === "/api/jobs" && request.method() === "GET"
  let eventsOpen = false
  let inFlight = 0
  let finished = 0
  const onResponse = (response: Response) => {
    if (new URL(response.url()).pathname === "/api/events") eventsOpen = true
  }
  const onRequest = (request: Request) => {
    if (isJobsGet(request)) inFlight += 1
  }
  const onDone = (request: Request) => {
    if (!isJobsGet(request)) return
    inFlight -= 1
    finished += 1
  }
  page.on("response", onResponse)
  page.on("request", onRequest)
  page.on("requestfinished", onDone)
  page.on("requestfailed", onDone)
  try {
    await page.goto(path)
    await expect.poll(() => eventsOpen && finished >= 2 && inFlight === 0).toBe(true)
    // ให้ react-query ใส่คำตอบลงแคชก่อน (หลังโหลดเนื้อหาครบแล้วยังมีขั้นอ่าน JSON)
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => resolve(null))))
  } finally {
    page.off("response", onResponse)
    page.off("request", onRequest)
    page.off("requestfinished", onDone)
    page.off("requestfailed", onDone)
  }
}
