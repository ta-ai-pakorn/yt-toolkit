/// <reference lib="dom" />
import path from "node:path"

import { analyzeSettled } from "./axe-settled"
import { expect, test, type Page } from "@playwright/test"

import type { Job, SharpSet, Storyboard, VideoFormat, VideoInfo } from "../src/lib/types"

import { mockEnqueue } from "./queue-helpers"

/**
 * M5 รอบ B dialog "ขอภาพคม" (โปรเจกต์ chromium: mockEnqueue ทุกเทสที่กดเริ่ม ไม่มีงานจริง)
 * BBB 635 วิ ภาพเร็ว 128 ภาพ ทุก 4.961 วิ · format 720p ที่เลือก = 298 (150,524,867 ไบต์) · ZOO 19 วิ ไม่มี storyboard สูงสุด 240p
 * dialog ไม่มีเทสคอมโพเนนต์ (Vitest รันใน node) จึงมีสเปกนี้เป็นเทสเดียวที่คลุมทั้งเมาส์ คีย์บอร์ด และ a11y
 */

const BBB = "aqz-KE-bpKQ"
const BBB_TITLE = "Big Buck Bunny 60fps 4K - Official Blender Foundation Short Film"
const ZOO = "jNQXAC9IVRw"
const COVER = path.join(import.meta.dirname, "../../tests/fixtures/media/cover.jpg")

const dialog = (page: Page) => page.getByRole("dialog", { name: "ขอภาพคม" })
const sameRadio = (page: Page) => dialog(page).getByRole("radio", { name: /เวลาเดียวกับภาพเร็ว/ })
const customRadio = (page: Page) => dialog(page).getByRole("radio", { name: "ตั้งเอง ทุก วินาที" })
const customField = (page: Page) => dialog(page).getByRole("textbox", { name: "ตั้งเอง ทุก วินาที" })
const start = (page: Page) => dialog(page).getByRole("button", { name: "เริ่มดึงภาพคม" })

/**
 * กด "เริ่มดึงภาพคม" แล้วรอ POST /api/jobs ออกไปจริง ก่อนตรวจว่ากล่องปิด
 * พังที่นี่ = การกดไม่ถึงคำสั่งเริ่ม · พังที่ toBeHidden = ส่งแล้วแต่กล่องไม่ปิด (แยกสองกรณีออกจากกัน)
 */
async function clickStart(page: Page) {
  const posted = page.waitForRequest((r) => new URL(r.url()).pathname === "/api/jobs" && r.method() === "POST", {
    timeout: 5_000,
  })
  await start(page).click()
  await posted
}

async function openDialog(page: Page, videoId = BBB) {
  await page.goto(`/v/${videoId}`)
  await page.getByRole("button", { name: "ขอภาพคม" }).click()
  await expect(dialog(page)).toBeVisible()
}

async function patchVideo(page: Page, videoId: string, patch: (info: VideoInfo) => VideoInfo) {
  await page.route(`**/api/videos/${videoId}`, async (route) => {
    const response = await route.fetch()
    await route.fulfill({ response, json: patch((await response.json()) as VideoInfo) })
  })
}

async function seriousViolations(page: Page) {
  const results = await analyzeSettled(page)
  return results.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)
}

test("ค่าเริ่มต้น: เวลาเดียวกับภาพเร็ว 128 ภาพ ขนาดและความละเอียด · เริ่ม = ส่ง {} แล้วปิด dialog", async ({ page }) => {
  const queue = await mockEnqueue(page)
  await openDialog(page)
  await expect(sameRadio(page)).toBeChecked()
  await expect(dialog(page)).toContainText("ทุก ~5.0 วินาที · 128 ภาพ")
  await expect(dialog(page)).toContainText("ต้องโหลดวิดีโอชั่วคราวราว 151 MB (ลบทิ้งเมื่อเสร็จ)")
  await expect(dialog(page)).toContainText("ภาพกว้าง 1280 px")
  await expect(dialog(page)).not.toContainText("ภาพคมชุดเดิมในแอพ")
  await clickStart(page)
  await expect(dialog(page)).toBeHidden()
  await expect(page.getByText("เพิ่มเข้าคิวแล้ว", { exact: true })).toBeVisible()
  expect(queue.bodies).toEqual([[{ videoId: BBB, kind: "frames_sharp", params: {}, title: BBB_TITLE }]])
})

test("ใช้คีย์บอร์ดล้วน: Tab จากตัวเลือกเวลาเดียวกับภาพเร็วผ่านช่องตัวเลข ไปถึงปุ่มเริ่ม ยังเป็นโหมดเดิมและส่ง {}", async ({ page }) => {
  const queue = await mockEnqueue(page)
  await openDialog(page)
  await sameRadio(page).focus()
  await expect(sameRadio(page)).toBeFocused()
  await page.keyboard.press("Tab")
  await expect(customField(page)).toBeFocused()
  // แค่ Tab ผ่านช่องตัวเลขไม่เปลี่ยนโหมด (เปลี่ยนเมื่อพิมพ์หรือเอาเมาส์กดเท่านั้น)
  await expect(sameRadio(page)).toBeChecked()
  await page.keyboard.press("Tab")
  await expect(dialog(page).getByRole("button", { name: "ยกเลิก" })).toBeFocused()
  await page.keyboard.press("Tab")
  await expect(start(page)).toBeFocused()
  await expect(sameRadio(page)).toBeChecked()
  await page.keyboard.press("Enter")
  await expect(dialog(page)).toBeHidden()
  expect(queue.bodies).toEqual([[{ videoId: BBB, kind: "frames_sharp", params: {}, title: BBB_TITLE }]])
})

test("ลูกศรซ้าย/ขวาที่ขอบช่องตัวเลข: โฟกัสอยู่ในช่อง ไม่กระโดดไปเลือกตัวเลือกอื่น", async ({ page }) => {
  await mockEnqueue(page)
  await openDialog(page)
  await customField(page).fill("12")
  await expect(customRadio(page)).toBeChecked()
  await customField(page).focus()
  await page.keyboard.press("Home")
  await page.keyboard.press("ArrowLeft")
  await expect(customField(page)).toBeFocused()
  await page.keyboard.press("End")
  await page.keyboard.press("ArrowRight")
  await expect(customField(page)).toBeFocused()
  await expect(customField(page)).toHaveValue("12")
  await expect(customRadio(page)).toBeChecked()
  await expect(sameRadio(page)).not.toBeChecked()
})

test("ตั้งเอง ทุก 7 วินาที: 91 ภาพ ส่ง intervalS 7", async ({ page }) => {
  const queue = await mockEnqueue(page)
  await openDialog(page)
  // ค่าเริ่มต้นของ BBB ก็คือ 7 อยู่แล้ว: fill("7") ไม่เกิด change จึงไม่เปลี่ยนโหมด ผู้ใช้จริงต้องคลิกช่อง (กดเมาส์ลง = โหมดตั้งเอง) แล้วพิมพ์
  await customField(page).click()
  await expect(customRadio(page)).toBeChecked()
  await customField(page).fill("7")
  await expect(customRadio(page)).toBeChecked()
  await expect(dialog(page)).toContainText("· 91 ภาพ")
  await clickStart(page)
  await expect(dialog(page)).toBeHidden()
  expect(queue.bodies[0][0].params).toEqual({ intervalS: 7 })
})

test("AC-FRAME-04: ทุก 2 วินาทีเกิน 200 ภาพ บอกช่วงใหม่แบบสด ในพื้นที่ role=status และส่ง intervalS 4", async ({ page }) => {
  const queue = await mockEnqueue(page)
  await openDialog(page)
  // ยังไม่เกิน 200 ภาพ: พื้นที่ role=status มีอยู่ใน DOM แล้วแต่ว่าง (โปรแกรมอ่านหน้าจอจะอ่านเมื่อข้อความเปลี่ยน)
  await expect(dialog(page).locator('[role="status"]')).toHaveCount(1)
  await expect(dialog(page).locator('[role="status"]')).toHaveText("")
  await customField(page).fill("2")
  await expect(dialog(page).getByRole("status")).toHaveText("ทุก 2 วินาทีจะได้ 318 ภาพ เกินที่ดึงได้ 200 ภาพ จะใช้ทุก 4 วินาทีแทน")
  await expect(dialog(page)).not.toContainText("· 318 ภาพ")
  await clickStart(page)
  await expect(dialog(page)).toBeHidden()
  expect(queue.bodies[0][0].params).toEqual({ intervalS: 4 })
})

test("เวลาเดียวกับภาพเร็วที่เกิน 200 ภาพ: ประโยคช่วงใหม่ (ทศนิยมหนึ่งตำแหน่ง) และส่ง intervalS 4", async ({ page }) => {
  const queue = await mockEnqueue(page)
  // ภาพเร็วจำลองทุก 3 วินาที = 212 ภาพ (BBB ยาว 635 วินาที → ช่วงใหม่ ceil(635/200) = 4)
  const storyboard: Storyboard = {
    intervalMs: 3000,
    frames: Array.from({ length: 212 }, (_, index) => ({
      index,
      tMs: index * 3000,
      url: `/api/cache/${BBB}/storyboard/f_${String(index).padStart(4, "0")}.jpg?v=1`,
    })),
  }
  await page.route(`**/api/videos/${BBB}/storyboard`, (route) => route.fulfill({ json: storyboard }))
  await page.route(`**/api/cache/${BBB}/storyboard/**`, (route) => route.fulfill({ path: COVER, contentType: "image/jpeg" }))
  await openDialog(page)
  await expect(sameRadio(page)).toBeChecked()
  await expect(dialog(page).getByRole("status")).toHaveText("ทุก 3.0 วินาทีจะได้ 212 ภาพ เกินที่ดึงได้ 200 ภาพ จะใช้ทุก 4 วินาทีแทน")
  await expect(dialog(page)).not.toContainText("ทุก ~3.0 วินาที · 212 ภาพ")
  await clickStart(page)
  await expect(dialog(page)).toBeHidden()
  expect(queue.bodies[0][0].params).toEqual({ intervalS: 4 })
})

test("ช่องตั้งเองผิด: ข้อความใต้ช่อง ปุ่มเริ่มกดไม่ได้ · กลับไปเลือกเวลาเดียวกับภาพเร็วแล้วกดได้", async ({ page }) => {
  await mockEnqueue(page)
  await openDialog(page)
  for (const bad of ["0", "1.5", "abc", "3601"]) {
    await customField(page).fill(bad)
    await expect(dialog(page).getByText("ใส่เลขวินาทีเต็ม 1-3600")).toBeVisible()
    await expect(customField(page)).toHaveAttribute("aria-invalid", "true")
    await expect(start(page)).toBeDisabled()
  }
  await sameRadio(page).click()
  await expect(dialog(page).getByText("ใส่เลขวินาทีเต็ม 1-3600")).toHaveCount(0)
  await expect(start(page)).toBeEnabled()
})

test("ยกเลิก ปิด dialog โดยไม่ส่งงาน", async ({ page }) => {
  const queue = await mockEnqueue(page)
  await openDialog(page)
  await dialog(page).getByRole("button", { name: "ยกเลิก" }).click()
  await expect(dialog(page)).toBeHidden()
  expect(queue.bodies).toEqual([])
})

test("มีชุดภาพคมแล้ว: เตือนว่าจะถูกแทน", async ({ page }) => {
  const set: SharpSet = { origin: "auto", intervalMs: null, frames: [{ index: 0, tMs: 0, url: `/api/cache/${BBB}/sharp/f_0000.jpg?v=1` }] }
  await page.route(`**/api/videos/${BBB}/sharp`, (route) => route.fulfill({ json: set }))
  await page.route(`**/api/cache/${BBB}/sharp/**`, (route) => route.fulfill({ path: COVER, contentType: "image/jpeg" }))
  await openDialog(page)
  await expect(dialog(page)).toContainText("ภาพคมชุดเดิมในแอพจะถูกแทนด้วยชุดใหม่ (ไฟล์ในโฟลเดอร์ไม่หาย)")
})

test("คลิปไม่มี storyboard: ไม่มีตัวเลือกเวลาเดียวกับภาพเร็ว ช่องตั้งเองเริ่มที่ 1 (19 ภาพ) และบอกว่าภาพเล็กกว่าปกติ", async ({ page }) => {
  const queue = await mockEnqueue(page)
  await openDialog(page, ZOO)
  await expect(sameRadio(page)).toHaveCount(0)
  await expect(customField(page)).toHaveValue("1")
  await expect(dialog(page)).toContainText("· 19 ภาพ")
  await expect(dialog(page)).toContainText("คลิปนี้มีภาพสูงสุด 240p ภาพจะเล็กกว่าปกติ")
  await clickStart(page)
  await expect(dialog(page)).toBeHidden()
  expect(queue.bodies[0][0].params).toEqual({ intervalS: 1 })
})

test("คลิปแนวตั้ง (Shorts): ภาพสูง 1280 px และขนาดจาก format 720×1280", async ({ page }) => {
  const portrait: VideoFormat[] = [
    { formatId: "137", width: 1080, height: 1920, fps: 30, vcodec: "avc1.640028", compat: true, sizeBytes: 40_000_000 },
    { formatId: "136", width: 720, height: 1280, fps: 30, vcodec: "avc1.4d401f", compat: true, sizeBytes: 9_000_000 },
  ]
  await patchVideo(page, BBB, (info) => ({ ...info, video: portrait }))
  await openDialog(page)
  await expect(dialog(page)).toContainText("ภาพสูง 1280 px")
  await expect(dialog(page)).toContainText("ต้องโหลดวิดีโอชั่วคราวราว 9.0 MB (ลบทิ้งเมื่อเสร็จ)")
})

test("คลิปสด: ปุ่มปิด (ยังโฟกัสได้) พร้อม tooltip", async ({ page }) => {
  await patchVideo(page, BBB, (info) => ({ ...info, isLive: true }))
  await page.goto(`/v/${BBB}`)
  const button = page.getByRole("button", { name: "ขอภาพคม" })
  await expect(button).toBeDisabled()
  await button.hover()
  await expect(page.locator('[data-slot="tooltip-content"]')).toHaveText("คลิปสดยังขอภาพคมไม่ได้")
})

test("มีงานภาพคมของคลิปนี้ในคิว: ปุ่มเป็น 'กำลังดึงภาพคม…' และกดไม่ได้", async ({ page }) => {
  const queued: Job = {
    id: "01900000-0000-7000-8000-0000000000e2",
    videoId: BBB,
    title: BBB_TITLE,
    kind: "frames_sharp",
    params: {},
    status: "queued",
    position: 1,
    createdAt: "2026-10-05T03:00:00Z",
  }
  await page.route("**/api/jobs", (route) =>
    route.request().method() === "GET" ? route.fulfill({ json: { jobs: [queued] } }) : route.fallback()
  )
  await page.goto(`/v/${BBB}`)
  const busy = page.getByRole("button", { name: "กำลังดึงภาพคม…" })
  await expect(busy).toBeVisible()
  await expect(busy).toBeDisabled()
})

test("งานภาพคมขึ้นคิวขณะ dialog เปิด: dialog ปิดเอง และไม่เด้งกลับมาเองเมื่องานจบ", async ({ page }) => {
  const sharpJob: Job = {
    id: "01900000-0000-7000-8000-0000000000e3",
    videoId: BBB,
    title: BBB_TITLE,
    kind: "frames_sharp",
    params: {},
    status: "queued",
    position: 1,
    createdAt: "2026-10-05T03:00:00Z",
  }
  // รายการงานที่ backend ปลอมตอบ (แก้ได้กลางเทส) · ไม่มีงานจริงเลย
  let jobs: Job[] = []
  await page.route("**/api/jobs", (route) =>
    route.request().method() === "GET" ? route.fulfill({ json: { jobs } }) : route.fallback()
  )
  // SSE ปลอมที่จบทันทีและให้ต่อใหม่ทุก 300 ms: ทุกครั้งที่ต่อติดหน้าเว็บโหลดรายการงานใหม่ (events.ts onOpen)
  // นี่คือทางที่แอพใช้จริงเมื่อ SSE หลุดแล้วต่อใหม่ จึงใช้ขับให้รายการงานเปลี่ยนโดยไม่ต้องมีงานจริง
  await page.route("**/api/events", (route) =>
    route.fulfill({
      status: 200,
      headers: { "Content-Type": "text/event-stream; charset=utf-8", "Cache-Control": "no-cache" },
      body: "retry: 300\n\n",
    })
  )
  await openDialog(page)
  jobs = [sharpJob]
  await expect(dialog(page)).toBeHidden()
  const busy = page.getByRole("button", { name: "กำลังดึงภาพคม…" })
  await expect(busy).toBeDisabled()
  jobs = []
  const idle = page.getByRole("button", { name: "ขอภาพคม", exact: true })
  await expect(idle).toBeEnabled()
  // รอให้การโหลดใหม่รอบถัดไปผ่านไปแล้วหลายรอบ: dialog ต้องยังปิดอยู่ (ไม่เด้งขึ้นมาเองตอนงานจบ)
  await page.waitForTimeout(1000)
  await expect(dialog(page)).toBeHidden()
  await expect(idle).toBeEnabled()
})

for (const scheme of ["dark", "light"] as const) {
  test(`axe: dialog ขอภาพคมไม่มีปัญหาระดับ serious/critical (${scheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme })
    await openDialog(page)
    // ยืนยันว่าธีมถูกใช้จริงก่อนตรวจสี (ไม่งั้น axe อาจตรวจธีมผิดแล้วผ่านเฉย ๆ)
    await expect(page.locator("html")).toHaveClass(scheme === "dark" ? /dark/ : /light/)
    await customField(page).fill("2")
    await expect(dialog(page).getByRole("status")).toContainText("เกินที่ดึงได้ 200 ภาพ")
    expect(await seriousViolations(page)).toEqual([])
  })
}

test("หน้าต่างแคบ 640 px: ปุ่มและ dialog ไม่ล้นแนวนอน", async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 800 })
  await page.goto(`/v/${BBB}`)
  const button = page.getByRole("button", { name: "ขอภาพคม" })
  await expect(button).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(640)
  await button.click()
  await expect(dialog(page)).toBeVisible()
  await customField(page).fill("2")
  await expect(dialog(page).getByRole("status")).toContainText("เกินที่ดึงได้ 200 ภาพ")
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(640)
  const box = await dialog(page).boundingBox()
  expect(box).not.toBeNull()
  expect(box!.x).toBeGreaterThanOrEqual(0)
  expect(box!.x + box!.width).toBeLessThanOrEqual(640)
})
