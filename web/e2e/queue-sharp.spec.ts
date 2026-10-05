import { expect, test, type Page } from "@playwright/test"

import type { SharpSet } from "../src/lib/types"

import { cancelJobsFor, enqueue, openQueueSheet, waitForJob } from "./queue-helpers"

/**
 * M5 รอบ B กับ backend โหมด fake ตัวจริง (โปรเจกต์ queue): ใช้เฉพาะคลิปปลอม SHARPCLIP01 และ AUTOSHARP01
 * (probe = Big Buck Bunny 635 วิ ภาพเร็ว 128 ภาพ) · โหมด fake ไม่มี ffmpeg ภาพคมทุกภาพเป็นสำเนาของ media/cover.jpg
 */

const SHARP = "SHARPCLIP01"
const AUTO = "AUTOSHARP01"
const VIDEO = { maxQuality: false, splitChapters: false, noAudio: false, audioLanguage: "original" }
const FRAMES = (page: Page) => page.getByRole("list", { name: "รายการภาพเฟรม" }).getByRole("listitem")

test.beforeEach(async ({ request }) => {
  await cancelJobsFor(request, [SHARP, AUTO])
})

test("ภาพคมทุก 60 วินาที: เสร็จได้โฟลเดอร์ 11 ภาพ · หน้า W2 ที่เปิดอยู่สลับเป็นภาพคมเอง · แถวคิวไม่มีปุ่มดาวน์โหลด", async ({
  page,
  request,
}) => {
  await page.goto(`/v/${SHARP}`)
  await expect(FRAMES(page)).toHaveCount(128)
  const [job] = await enqueue(request, [{ videoId: SHARP, kind: "frames_sharp", params: { intervalS: 60 } }])
  const done = await waitForJob(request, (j) => j.id === job.id && j.status === "done", { timeout: 30_000 })
  expect(done.outputs).toHaveLength(1)
  expect(done.outputs![0].files).toBe(11)
  expect(done.outputs![0].name).toMatch(/^คลิปภาพคม - ภาพคม( \(\d+\))?$/)

  // ข่าว SSE ของงานที่เสร็จโหลดชุดภาพคมใหม่ แล้วส่วนภาพเฟรมเปิดภาพคมให้เอง
  const toggle = page.getByRole("group", { name: "ชุดภาพเฟรม" })
  await expect(toggle.getByRole("button", { name: "ภาพคม" })).toHaveAttribute("aria-pressed", "true")
  await expect(FRAMES(page)).toHaveCount(11)

  const row = (await openQueueSheet(page)).locator(`[data-job-id="${job.id}"]`)
  await expect(row).toContainText("คลิปภาพคม · ภาพคม 11 ภาพ")
  await expect(row.getByRole("link", { name: /^ดาวน์โหลด / })).toHaveCount(0)
  await expect(row.getByRole("button", { name: /^เปิดโฟลเดอร์/ })).toBeVisible()
  expect((await request.get(`/api/jobs/${job.id}/outputs/0`)).status()).toBe(404)

  const sharp = (await (await request.get(`/api/videos/${SHARP}/sharp`)).json()) as SharpSet
  expect(sharp.origin).toBe("manual")
  expect(sharp.frames.map((f) => f.tMs)).toEqual(Array.from({ length: 11 }, (_, i) => i * 60_000))
})

test("ภาพรวมเฟรมและ zip จากชุดภาพคม", async ({ request }) => {
  const [sharpJob] = await enqueue(request, [{ videoId: SHARP, kind: "frames_sharp", params: { intervalS: 120 } }])
  await waitForJob(request, (j) => j.id === sharpJob.id && j.status === "done", { timeout: 30_000 })
  const [sheet, zip] = await enqueue(request, [
    { videoId: SHARP, kind: "contact_sheet", params: { source: "sharp", columns: 5 } },
    { videoId: SHARP, kind: "frames_zip", params: { source: "sharp" } },
  ])
  const sheetDone = await waitForJob(request, (j) => j.id === sheet.id && j.status === "done", { timeout: 30_000 })
  const zipDone = await waitForJob(request, (j) => j.id === zip.id && j.status === "done", { timeout: 30_000 })
  expect(sheetDone.outputs![0].name).toMatch(/^คลิปภาพคม - contact sheet( \(\d+\))?\.jpg$/)
  expect(zipDone.outputs![0].name).toMatch(/^คลิปภาพคม - frames( \(\d+\))?\.zip$/)
})

test("ภาพคมอัตโนมัติ: งานวิดีโอ 720p ของ AUTOSHARP01 ได้ไฟล์ mp4 อย่างเดียว และชุดภาพคม 128 ภาพในแอพ", async ({ request }) => {
  const [job] = await enqueue(request, [{ videoId: AUTO, kind: "video", params: VIDEO }])
  const done = await waitForJob(request, (j) => j.id === job.id && j.status === "done", { timeout: 30_000 })
  expect(done.outputs!.map((o) => o.name)).toEqual([expect.stringMatching(/\.mp4$/)])
  expect(done.notes ?? []).toEqual([])
  const sharp = (await (await request.get(`/api/videos/${AUTO}/sharp`)).json()) as SharpSet
  expect(sharp.origin).toBe("auto")
  expect(sharp.frames).toHaveLength(128)
})
