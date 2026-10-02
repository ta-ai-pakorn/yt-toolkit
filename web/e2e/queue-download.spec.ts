/// <reference lib="dom" />
import fs from "node:fs"
import path from "node:path"

import { expect, test, type Page } from "@playwright/test"

import type { Job } from "../src/lib/types"

import { cancelJobsFor, openQueueSheet, waitForJob } from "./queue-helpers"

/**
 * M4 T15 (โปรเจกต์ queue: งานจริงบน backend โหมด fake): กดปุ่มโหลดในแท็บวิดีโอ/เสียงของ W2 แล้วงานทำจนเสร็จ
 * spec นี้ใช้เฉพาะคลิป BBB และ 8lpOfyoxcvU (C14) ไม่ชนกับ spec คิวอื่น
 */

const BBB = "aqz-KE-bpKQ"
const DUB = "8lpOfyoxcvU"
const FIXTURES = path.join(import.meta.dirname, "../../tests/fixtures")

/** ชื่อคลิปในชุดทดสอบ (ชื่อ BBB ไม่มีอักขระต้องห้ามของชื่อไฟล์ จึงเป็นชื่อไฟล์ตรงตัว) */
function fixtureTitle(videoId: string): string {
  const file = path.join(FIXTURES, "probe", `${videoId}.json`)
  return (JSON.parse(fs.readFileSync(file, "utf8")) as { title: string }).title
}

/** กดปุ่มส่งเข้าคิวแล้วคืนงานที่ backend สร้าง (อ่านจากคำตอบของ POST /api/jobs) */
async function submitAndGetJob(page: Page, button: string): Promise<Job> {
  const posted = page.waitForResponse(
    (response) => new URL(response.url()).pathname === "/api/jobs" && response.request().method() === "POST",
  )
  await page.getByRole("button", { name: button, exact: true }).click()
  const response = await posted
  expect(response.ok(), `POST /api/jobs ตอบ ${response.status()}`).toBe(true)
  const { jobs } = (await response.json()) as { jobs: Job[] }
  expect(jobs).toHaveLength(1)
  return jobs[0]
}

test.beforeEach(async ({ request }) => {
  await cancelJobsFor(request, [BBB, DUB])
})

test("วิดีโอ BBB ค่าเริ่มต้น → งานเสร็จ ได้ไฟล์ '<ชื่อคลิป>.mp4' · ปุ่ม 'ดาวน์โหลด' ได้ไฟล์ video/mp4 ขนาดเท่าไฟล์ในชุดทดสอบ", async ({
  page,
  request,
}) => {
  await page.goto(`/v/${BBB}?tab=video`)
  const created = await submitAndGetJob(page, "โหลด mp4")
  expect(created).toMatchObject({ videoId: BBB, kind: "video" })
  await expect(page.getByText("เพิ่มเข้าคิวแล้ว", { exact: true })).toBeVisible()

  const done = await waitForJob(request, (job) => job.id === created.id && job.status === "done", { timeout: 30_000 })
  // ชื่อไฟล์ = ชื่อคลิป แต่ถูกตัดให้สั้นลงได้ตามความยาว path ที่เหลือของโฟลเดอร์ผลลัพธ์ (C10) จึงเทียบแค่ส่วนต้น
  expect(done.outputs).toHaveLength(1)
  const name = done.outputs![0].name
  expect(name).toMatch(/\.mp4$/)
  expect(fixtureTitle(BBB).startsWith(name.slice(0, -".mp4".length))).toBe(true)

  // แถวงานที่เสร็จในชีตคิวมีปุ่มดาวน์โหลดของไฟล์นี้
  const sheet = await openQueueSheet(page)
  const download = sheet.getByLabel(`ดาวน์โหลด ${name}`)
  await expect(download).toBeVisible()

  const expectedSize = fs.statSync(path.join(FIXTURES, "media", "video.mp4")).size
  const response = await request.get(`/api/jobs/${done.id}/outputs/0`)
  expect(response.ok()).toBe(true)
  expect(response.headers()["content-type"]).toMatch(/^video\/mp4/)
  expect((await response.body()).length).toBe(expectedSize)

  const [file] = await Promise.all([page.waitForEvent("download"), download.click()])
  expect(fs.statSync(await file.path()).size).toBe(expectedSize)
})

test("เสียง m4a ของคลิปพากย์ เลือกภาษาอังกฤษ → ส่ง audioLanguage en-US และงานเสร็จได้ไฟล์ .m4a", async ({ page, request }) => {
  await page.goto(`/v/${DUB}?tab=audio`)
  await expect(page.getByRole("button", { name: "m4a (แนะนำ)" })).toHaveAttribute("aria-pressed", "true")
  const language = page.getByRole("combobox", { name: "ภาษาเสียง", exact: true })
  await language.click()
  await page.getByRole("option", { name: "อังกฤษ (สหรัฐอเมริกา)" }).click()
  await expect(language.locator('[data-slot="select-value"]')).toHaveText("อังกฤษ (สหรัฐอเมริกา)")

  const created = await submitAndGetJob(page, "โหลด m4a")
  expect(created).toMatchObject({ videoId: DUB, kind: "audio", params: { format: "m4a", audioLanguage: "en-US" } })

  const done = await waitForJob(request, (job) => job.id === created.id && job.status === "done", { timeout: 30_000 })
  expect(done.outputs).toHaveLength(1)
  expect(done.outputs?.[0].name).toMatch(/\.m4a$/)
})
