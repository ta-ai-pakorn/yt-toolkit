/// <reference lib="dom" />
import fs from "node:fs"
import path from "node:path"

import { expect, test, type APIRequestContext, type Page } from "@playwright/test"

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

/** ลบภาพที่ถ่ายไว้ผ่าน API (ใช้ใน finally: ไม่มีภาพ = 404 ก็ถือว่าสะอาดแล้ว) token อ่านจากหน้าแรกของ backend ไม่พึ่งหน้าเว็บที่เปิดอยู่ */
async function deleteCapture(request: APIRequestContext, videoId: string, captureId: string) {
  const home = await request.get("/")
  const match = /<meta name="yt-token" content="([^"]+)"/.exec(await home.text())
  if (!home.ok() || !match) throw new Error(`อ่าน token จากหน้าแรกไม่ได้ (HTTP ${home.status()})`)
  const response = await request.delete(`/api/videos/${videoId}/captures/${captureId}`, {
    headers: { "X-Toolkit-Token": match[1], Origin: new URL(home.url()).origin },
  })
  expect([200, 204, 404], `DELETE capture ตอบ ${response.status()}`).toContain(response.status())
}

async function openAndPlay(page: Page, videoId: string) {
  await installFakeYT(page, { durationS: 635, rate: 0.001 })
  await page.goto(`/v/${videoId}`)
  await page.getByRole("button", { name: "เล่นคลิป", exact: true }).click()
  await expect.poll(async () => (await fakeYTLog(page)).calls).toContain("play")
  await expect(page.locator('[data-slot="video-header"]')).toHaveAttribute("data-layout", "theater-wide")
}

test("ถ่ายจริงกับ backend ปลอม: แถบ ไฟล์ในโฟลเดอร์ของคลิป เวลาเดิมได้ภาพเดิม และลบทั้งสองที่", async ({ page, request }) => {
  try {
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

    // เวลาเดิม: ตัวเล่นปลอม rate 0.001 เดินแทบไม่ขยับ + ปัดเป็นหน่วย 100 ms จึงได้ tMs เดิม (c_0) backend ตอบ 200 พร้อมภาพเดิม ไม่สร้างไฟล์ใหม่
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
  } finally {
    await deleteCapture(request, CLIP, "c_0") // ล้มกลางทางแล้วไม่ทิ้งภาพไว้ให้รอบถัดไป
  }
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
    // เหตุผลที่ปุ่มปิดมาถึงปุ่มจริง (span sr-only ที่ aria-describedby ชี้)
    await expect(page.getByText(/^พักการโหลดอยู่เพราะยูทูปขอตรวจสอบ ลองใหม่หลัง \d{2}:\d{2}$/)).toBeAttached()
    await expect(page.locator('[data-slot="capture-strip"]')).toHaveCount(0)
    // E_BOT_CHECK ไม่เขียนอะไรเลย
    expect(((await (await request.get(`/api/videos/${BOT}/captures`)).json()) as { captures: unknown[] }).captures).toEqual([])
  } finally {
    await resumeQueue(request) // spec ถัดไปของ project queue ต้องได้คิวที่ไม่พัก
  }
})
