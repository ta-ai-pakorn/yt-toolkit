/// <reference lib="dom" />
import fs from "node:fs"
import path from "node:path"

import { expect, test, type Page } from "@playwright/test"

import { fakeYTLog, installFakeYT } from "./fake-yt"
import { resumeQueue } from "./queue-helpers"

/**
 * M5 รอบ B2 ถ่ายภาพคมตรงจุดกับ backend โหมดปลอมจริง (project queue รันทีละ spec --workers=1):
 * FakeExtractor ตัดชิ้นจาก tests/fixtures/capture/piece.mp4 · FakeMediaTools คัดลอก cover.jpg · ไม่ต่อยูทูป
 * ใช้คลิปปลอม CAPTURE0001 (ถ่ายได้) และ CAPTUREBOT1 (ยูทูปขอตรวจสอบ) เท่านั้น
 * project นี้ไม่มีค่า yt-toolkit:theater ตั้งไว้: กด ▶ แล้วได้โหมดโรงภาพยนตร์ (ค่าเริ่มต้นจริง)
 */

const CLIP = "CAPTURE0001"
const BOT = "CAPTUREBOT1"
const TITLE = "คลิปถ่ายภาพคม"

const captureButton = (page: Page) => page.locator('[data-slot="player-controls"]').getByRole("button", { name: "ถ่ายภาพคมตรงนี้" })
const toast = (page: Page, text: string | RegExp) => page.locator("[data-sonner-toast]").filter({ hasText: text })

async function openAndPlay(page: Page, videoId: string) {
  await installFakeYT(page, { durationS: 635, rate: 0.001 })
  await page.goto(`/v/${videoId}`)
  await page.getByRole("button", { name: "เล่นคลิป", exact: true }).click()
  await expect.poll(async () => (await fakeYTLog(page)).calls).toContain("play")
  await expect(page.locator('[data-slot="video-header"]')).toHaveAttribute("data-layout", "theater-wide")
}

test("ถ่ายจริงกับ backend ปลอม: แถบ ไฟล์ในโฟลเดอร์ของคลิป เวลาเดิมได้ภาพเดิม และลบทั้งสองที่", async ({ page, request }) => {
  await openAndPlay(page, CLIP)
  await captureButton(page).click()
  await expect(toast(page, "ถ่ายภาพคมแล้ว · 0:00")).toBeVisible()
  await expect(page.getByRole("heading", { name: "ภาพที่ถ่ายไว้ (1)" })).toBeVisible()

  const listed = (await (await request.get(`/api/videos/${CLIP}/captures`)).json()) as { captures: { id: string; url: string }[] }
  expect(listed.captures.map((c) => c.id)).toEqual(["c_0"])
  const image = await request.get(listed.captures[0].url)
  expect(image.ok()).toBe(true)
  expect(image.headers()["content-type"]).toBe("image/jpeg")
  const { outputDir } = (await (await request.get("/api/settings")).json()) as { outputDir: string }
  const folder = path.join(outputDir, `${TITLE} [${CLIP}]`, "ภาพที่ถ่าย")
  expect(fs.readdirSync(folder)).toEqual(["frame_00-00-00.jpg"])

  // เวลาเดิม: backend ตอบ 200 พร้อมภาพเดิม ไม่สร้างไฟล์ใหม่
  const again = page.waitForResponse((r) => r.url().endsWith(`/api/videos/${CLIP}/captures`) && r.request().method() === "POST")
  await captureButton(page).click()
  expect((await again).status()).toBe(200)
  await expect(page.getByRole("heading", { name: "ภาพที่ถ่ายไว้ (1)" })).toBeVisible()
  expect(fs.readdirSync(folder)).toEqual(["frame_00-00-00.jpg"])

  await page.locator('[data-slot="capture-strip"]').getByRole("list").getByRole("button").first().click()
  await page.getByRole("dialog").getByRole("button", { name: "ลบภาพนี้" }).click()
  await page.getByRole("alertdialog").getByRole("button", { name: "ลบภาพ", exact: true }).click()
  await expect(toast(page, "ลบภาพแล้ว")).toBeVisible()
  await expect(page.locator('[data-slot="capture-strip"]')).toHaveCount(0)
  expect(fs.readdirSync(folder)).toEqual([])
  expect(((await (await request.get(`/api/videos/${CLIP}/captures`)).json()) as { captures: unknown[] }).captures).toEqual([])
})

test("ยูทูปขอตรวจสอบระหว่างถ่าย: toast และคิวพัก ปุ่มถ่ายภาพปิดพร้อมเหตุผล", async ({ page, request }) => {
  try {
    await openAndPlay(page, BOT)
    await captureButton(page).click()
    await expect(toast(page, "ยูทูปขอให้ยืนยันว่าไม่ใช่บอท พักคิวไว้ 10 นาทีก่อนนะ")).toBeVisible()
    await expect
      .poll(async () => ((await (await request.get("/api/queue")).json()) as { pausedUntil: string | null }).pausedUntil)
      .not.toBeNull()
    await expect(captureButton(page)).toBeDisabled()
    await expect(page.locator('[data-slot="capture-strip"]')).toHaveCount(0)
  } finally {
    await resumeQueue(request) // spec ถัดไปของ project queue ต้องได้คิวที่ไม่พัก
  }
})
