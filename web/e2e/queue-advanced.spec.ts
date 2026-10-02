import { expect, test, type APIRequestContext } from "@playwright/test"

import type { Job, NewJob } from "../src/lib/types"

import { cancelJobsFor, enqueue, openQueueSheet, resumeQueue, waitForJob } from "./queue-helpers"

/**
 * M5 รอบ A กับ backend โหมด fake ตัวจริง (โปรเจกต์ queue): งานจริงของคลิปปลอมใน tests/fixtures/downloads/behaviors.json
 * ตรวจเฉพาะงานของคลิปตัวเอง (ไม่นับยอดรวมของแถบคิว) · โหมด fake ตัดด้วยการคัดลอก: ตรวจชื่อไฟล์ จำนวนไฟล์ และโน้ต
 * ข้อความโน้ต SponsorBlock ตามมติ owner 2026-10-02: "ไม่ได้ตัดโฆษณา" (ไม่ใช่ "ได้คลิปเต็ม" เพราะตั้งช่วงเวลาร่วมด้วยได้)
 */

const CLIPS = ["RANGECLIP01", "CHAPTERS001", "ADSCUTCLIP1", "ADSNODATA01", "ADSOFFLINE1"]

const VIDEO = { maxQuality: false, splitChapters: false, noAudio: false, audioLanguage: "original" }

async function done(request: APIRequestContext, item: NewJob): Promise<Job> {
  const [job] = await enqueue(request, [item])
  return waitForJob(request, (j) => j.id === job.id && j.status === "done", { timeout: 30_000 })
}

// backend ของโปรเจกต์ queue ใช้ร่วมกับ spec อื่น (queue-flow เบรกคิวและรันงานช้า): ปลดเบรกและเคลียร์งานค้างของคลิปเหล่านี้ก่อนทุกเทส
// test.setTimeout(60 วิ) ให้เกินเวลารองาน 30 วิ: ถ้ารองานไม่ทัน จะได้ข้อความ "งานที่เห็นล่าสุด" ของ waitForJob ไม่ใช่แค่ timeout เปล่า
test.beforeEach(async ({ request }) => {
  test.setTimeout(60_000)
  await resumeQueue(request)
  await cancelJobsFor(request, CLIPS)
})

const names = (job: Job) => (job.outputs ?? []).map((output) => output.name)

test("ช่วงเวลา: ชื่อไฟล์มี (01.30-05.00) · แถวคิวต่อท้าย ' · ช่วง 1:30-5:00'", async ({ page, request }) => {
  const job = await done(request, {
    videoId: "RANGECLIP01",
    kind: "video",
    params: { ...VIDEO, range: { startMs: 90_000, endMs: 300_000 } },
  })
  expect(names(job)).toEqual(["คลิปช่วงเวลา (01.30-05.00).mp4"])
  await page.goto("/")
  const sheet = await openQueueSheet(page)
  await expect(sheet.locator(`[data-job-id="${job.id}"]`)).toContainText("คลิปช่วงเวลา · ช่วง 1:30-5:00")
})

test("แยก chapter (เสียง m4a): 3 ไฟล์ตามลำดับ และปุ่มดาวน์โหลดครบทุกไฟล์", async ({ page, request }) => {
  const job = await done(request, {
    videoId: "CHAPTERS001",
    kind: "audio",
    params: { format: "m4a", splitChapters: true, audioLanguage: "original" },
  })
  expect(names(job)).toEqual(["01 - Intro.m4a", "02 - The cool thing.m4a", "03 - End.m4a"])
  await page.goto("/")
  const row = (await openQueueSheet(page)).locator(`[data-job-id="${job.id}"]`)
  await expect(row).toContainText("คลิปมี 3 chapter · แยก chapter")
  await expect(row.getByRole("link", { name: /^ดาวน์โหลด / })).toHaveCount(3)
})

test("แยก chapter (วิดีโอ): ชื่อไฟล์ 01-03", async ({ request }) => {
  const job = await done(request, { videoId: "CHAPTERS001", kind: "video", params: { ...VIDEO, splitChapters: true } })
  expect(names(job)).toEqual(["01 - Intro.mp4", "02 - The cool thing.mp4", "03 - End.mp4"])
})

test("ตัดโฆษณาที่มีข้อมูล: ชื่อมี (ตัดโฆษณา) ไม่มีโน้ต", async ({ request }) => {
  const job = await done(request, { videoId: "ADSCUTCLIP1", kind: "video", params: { ...VIDEO, sponsorblock: ["sponsor"] } })
  expect(names(job)).toEqual(["คลิปมีช่วงโฆษณา (ตัดโฆษณา).mp4"])
  expect(job.notes ?? []).toEqual([])
})

test("ไม่มีข้อมูลจากชุมชน: ได้คลิปเต็ม ชื่อปกติ และโน้ตสีเทาในแถวคิว", async ({ page, request }) => {
  const job = await done(request, { videoId: "ADSNODATA01", kind: "video", params: { ...VIDEO, sponsorblock: ["sponsor"] } })
  expect(names(job)).toEqual(["คลิปไม่มีข้อมูลโฆษณา.mp4"])
  expect(job.notes).toEqual([{ code: "SPONSORBLOCK_EMPTY", message: "ไม่มีข้อมูลจากชุมชน ไม่ได้ตัดโฆษณา" }])
  await page.goto("/")
  const row = (await openQueueSheet(page)).locator(`[data-job-id="${job.id}"]`)
  await expect(row).toContainText("ไม่มีข้อมูลจากชุมชน ไม่ได้ตัดโฆษณา")
  await expect(row).toContainText("คลิปไม่มีข้อมูลโฆษณา · ตัดโฆษณา")
})

test("ติดต่อ SponsorBlock ไม่ได้: งานสำเร็จ ได้คลิปเต็ม พร้อมโน้ต", async ({ request }) => {
  const job = await done(request, {
    videoId: "ADSOFFLINE1",
    kind: "audio",
    params: { format: "m4a", splitChapters: false, audioLanguage: "original", sponsorblock: ["sponsor"] },
  })
  expect(names(job)).toEqual(["คลิปที่ติดต่อ SponsorBlock ไม่ได้.m4a"])
  expect(job.notes).toEqual([{ code: "SPONSORBLOCK_UNREACHABLE", message: "ติดต่อ SponsorBlock ไม่ได้ ไม่ได้ตัดโฆษณา" }])
})
