/// <reference lib="dom" />
import path from "node:path"

import { analyzeSettled } from "./axe-settled"
import { expect, test, type Page } from "@playwright/test"

import type { SharpSet } from "../src/lib/types"

import { mockEnqueue } from "./queue-helpers"

/**
 * M5 รอบ B ส่วนภาพเฟรมเมื่อมีชุดภาพคม (โปรเจกต์ chromium: ชุดภาพคมจำลองด้วย page.route ไม่มีงานจริง)
 * ภาพของชุดจำลองคือ tests/fixtures/media/cover.jpg ทุกภาพ เวลาของภาพทุก 60 วินาที (ต่างจากภาพเร็วที่ทุก ~5 วินาที)
 */

const BBB = "aqz-KE-bpKQ"
const ZOO = "jNQXAC9IVRw"
const COVER = path.join(import.meta.dirname, "../../tests/fixtures/media/cover.jpg")
const FRAME_LIST = "รายการภาพเฟรม"
const FAST_COUNT = 128
const MINUTES = Array.from({ length: 11 }, (_, i) => i * 60_000)

function sharpSet(videoId: string, times: number[]): SharpSet {
  return {
    origin: "manual",
    intervalMs: 60_000,
    frames: times.map((tMs, index) => ({
      index,
      tMs,
      url: `/api/cache/${videoId}/sharp/f_${String(index).padStart(4, "0")}.jpg?v=1`,
    })),
  }
}

async function mockSharp(page: Page, videoId: string, times: number[]) {
  await page.route(`**/api/videos/${videoId}/sharp`, (route) => route.fulfill({ json: sharpSet(videoId, times) }))
  await page.route(`**/api/cache/${videoId}/sharp/**`, (route) => route.fulfill({ path: COVER, contentType: "image/jpeg" }))
}

const items = (page: Page) => page.getByRole("list", { name: FRAME_LIST }).getByRole("listitem")
const toggle = (page: Page) => page.getByRole("group", { name: "ชุดภาพเฟรม" })

async function seriousViolations(page: Page) {
  const results = await analyzeSettled(page)
  return results.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)
}

test("ยังไม่มีชุดภาพคม: ไม่มีปุ่มสลับ แสดงภาพเร็วครบ", async ({ page }) => {
  await page.goto(`/v/${BBB}`)
  await expect(items(page)).toHaveCount(FAST_COUNT)
  await expect(toggle(page)).toHaveCount(0)
})

test("มีชุดภาพคม: เปิดมาที่ภาพคม · สลับไปภาพเร็วและกลับได้", async ({ page }) => {
  await mockSharp(page, BBB, MINUTES)
  await page.goto(`/v/${BBB}`)
  await expect(items(page)).toHaveCount(11)
  await expect(toggle(page).getByRole("button", { name: "ภาพคม" })).toHaveAttribute("aria-pressed", "true")
  await toggle(page).getByRole("button", { name: "ภาพเร็ว" }).click()
  await expect(items(page)).toHaveCount(FAST_COUNT)
  await toggle(page).getByRole("button", { name: "ภาพคม" }).click()
  await expect(items(page)).toHaveCount(11)
  await expect(page.getByRole("button", { name: "ภาพเฟรมที่ 00:10:00" })).toBeVisible()
})

test("เมนูคลิกขวาของภาพคมครบทุกรายการ และ 'คัดลอกเวลา' ใช้เวลาของภาพคม", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"])
  await mockSharp(page, BBB, MINUTES)
  await page.goto(`/v/${BBB}`)
  await page.getByRole("button", { name: "ภาพเฟรมที่ 00:01:00" }).click({ button: "right" })
  const menu = page.getByRole("menu")
  await expect(menu.getByRole("menuitem")).toHaveText([
    "คัดลอกภาพ", "โหลดภาพนี้", "คัดลอกเวลา", "คัดลอกลิงก์ช่วงนี้", "เปิดในยูทูปตรงเวลานี้", "เล่นจากตรงนี้",
    "ถ่ายภาพคมตรงนี้", "ตั้งเป็นจุดเริ่ม", "ตั้งเป็นจุดจบ",
  ])
  await menu.getByRole("menuitem", { name: "คัดลอกเวลา" }).click()
  // เขียนคลิปบอร์ดเป็นงาน async: อ่านหลัง toast ยืนยันว่าคัดลอกเสร็จแล้ว
  await expect(page.getByText("คัดลอกแล้ว")).toBeVisible()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe("00:01:00")
})

test("?at= ไฮไลต์ภาพคมที่ใกล้เวลานั้นที่สุด", async ({ page }) => {
  await mockSharp(page, BBB, MINUTES)
  await page.goto(`/v/${BBB}?at=125000`)
  await expect(page.getByRole("button", { name: "ภาพเฟรมที่ 00:02:00" })).toHaveAttribute("aria-current", "true")
})

test("ปุ่มโหลดทั้งชุดส่ง source ตามชุดที่เห็นอยู่", async ({ page }) => {
  const queue = await mockEnqueue(page)
  await mockSharp(page, BBB, MINUTES)
  await page.goto(`/v/${BBB}`)
  await expect(items(page)).toHaveCount(11)
  await page.getByRole("button", { name: "โหลดภาพรวมเฟรม" }).click()
  await expect.poll(() => queue.bodies.length).toBe(1)
  await toggle(page).getByRole("button", { name: "ภาพเร็ว" }).click()
  await page.getByRole("button", { name: "โหลดทั้งหมด (.zip)" }).click()
  await expect.poll(() => queue.bodies.length).toBe(2)
  expect(queue.bodies.map((sent) => [sent[0].kind, sent[0].params])).toEqual([
    ["contact_sheet", { source: "sharp", columns: 5 }],
    ["frames_zip", { source: "fast" }],
  ])
})

test("คลิปไม่มี storyboard แต่มีภาพคม: แสดงภาพคม ไม่มีปุ่มสลับ", async ({ page }) => {
  await mockSharp(page, ZOO, [0, 5000, 10_000, 15_000])
  await page.goto(`/v/${ZOO}`)
  await expect(items(page)).toHaveCount(4)
  await expect(toggle(page)).toHaveCount(0)
  await expect(page.getByText("คลิปนี้ไม่มีภาพตัวอย่างแบบเร็ว", { exact: false })).toHaveCount(0)
})

for (const scheme of ["dark", "light"] as const) {
  test(`axe: ส่วนภาพเฟรมที่มีปุ่มสลับไม่มีปัญหาระดับ serious/critical (${scheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme })
    await mockSharp(page, BBB, MINUTES)
    await page.goto(`/v/${BBB}`)
    await expect(toggle(page)).toBeVisible()
    expect(await seriousViolations(page)).toEqual([])
  })
}

test("หน้าต่างแคบ 640 px: ปุ่มสลับกับปุ่มโหลดไม่ล้นแนวนอน", async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 800 })
  await mockSharp(page, BBB, MINUTES)
  await page.goto(`/v/${BBB}`)
  await expect(toggle(page)).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(640)
})
