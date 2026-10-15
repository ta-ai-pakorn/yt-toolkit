import path from "node:path"

import { expect, test, type Page } from "@playwright/test"

import { cancelJobsFor, enqueue, gotoReady, openQueueSheet, waitForJob } from "../e2e/queue-helpers"

// รูปในคู่มือพนักงาน (README) ใช้ข้อมูลปลอมล้วน (backend โหมด YT_TOOLKIT_FAKE=1 ของ playwright.shots.config.ts)
// รันด้วย `npm run build && npm run shots` ไฟล์ไปอยู่ที่ docs/images/ ลำดับเทสต้องเรียงตามเลขรูป
const BBB = "aqz-KE-bpKQ"
const THAI = "88o5Sk8_m1Y"
const ZOO = "jNQXAC9IVRw"
const ZOO_TITLE = "Me at the zoo"
const SLOW = "SLOWDOWNLD1"
const SLOW_TITLE = "คลิปโหลดช้า 1"
const IMAGES = path.join(import.meta.dirname, "../../docs/images")
// ที่อยู่โฟลเดอร์ที่โชว์ในรูป: ค่าสมมติ ไม่ใช่ที่อยู่จริงของเครื่องที่ถ่าย (ข้อกำหนด C4)
const NEUTRAL_OUTPUT_DIR = "C:\\Users\\พนักงาน\\Downloads\\YT-Toolkit"

test.describe.configure({ mode: "serial" })

const shot = (page: Page, name: string, opts: { fullPage?: boolean; clip?: { x: number; y: number; width: number; height: number } } = {}) =>
  page.screenshot({ path: path.join(IMAGES, `${name}.png`), ...opts })

/** รอให้ฟอนต์โหลดครบและแอนิเมชันที่จบได้จบก่อนถ่าย */
async function settle(page: Page) {
  await page.evaluate(() => document.fonts.ready)
  await page.evaluate(() =>
    Promise.all(
      document
        .getAnimations()
        .filter((a) => a.effect?.getComputedTiming().endTime !== Infinity)
        .map((a) => a.finished.catch(() => undefined)),
    ),
  )
}

test.beforeEach(async ({ page }) => {
  // รูปไม่ให้เห็นที่อยู่จริงของเครื่อง: แทนค่า outputDir ที่หน้าเว็บอ่านเป็นที่อยู่สมมติ (เฉพาะที่แสดง ไม่แตะ backend)
  await page.route("**/api/settings", async (route) => {
    if (route.request().method() !== "GET") return route.fallback()
    const response = await route.fetch()
    await route.fulfill({ response, json: { ...((await response.json()) as object), outputDir: NEUTRAL_OUTPUT_DIR } })
  })
})

test("01-home", async ({ page }) => {
  await page.goto("/")
  const heading = page.getByRole("heading", { name: "วางลิงก์ยูทูป แล้วเลือกสิ่งที่อยากได้" })
  await expect(heading).toBeVisible()
  await page.getByRole("textbox").fill(`https://www.youtube.com/watch?v=${BBB}`)
  await settle(page)
  await shot(page, "01-home")
})

test("02-clip-frames", async ({ page }) => {
  await page.goto(`/v/${BBB}?tab=frames`)
  await expect(page.getByRole("tab", { name: "ภาพเฟรม", exact: true })).toHaveAttribute("aria-selected", "true")
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible()
  // รอจนภาพเฟรมทุกภาพโหลดเสร็จ (ไม่ถ่ายตอนยังเป็นกรอบเทา)
  const frames = page.getByRole("list", { name: "รายการภาพเฟรม" }).locator("img")
  await expect(frames.first()).toBeVisible()
  await expect
    // ภาพที่อยู่นอกจอโหลดแบบ lazy จึงเช็กเฉพาะภาพที่อยู่ในหน้าจอ
    .poll(() =>
      frames.evaluateAll((imgs) => {
        const shown = (imgs as HTMLImageElement[]).filter((img) => img.getBoundingClientRect().top < window.innerHeight)
        return shown.length > 0 && shown.every((img) => img.complete && img.naturalWidth > 0)
      }),
    )
    .toBe(true)
  await settle(page)
  // ตัดเหลือหัวคลิป แท็บ และแถวภาพแรก (ภาพถ่ายหลายแถวทำให้ไฟล์ใหญ่เกิน 300 KB)
  await shot(page, "02-clip-frames", { clip: { x: 160, y: 60, width: 960, height: 520 } })
})

test("03-clip-subtitles", async ({ page }) => {
  await page.goto(`/v/${THAI}?tab=subs`)
  await expect(page.getByRole("tab", { name: "ซับ", exact: true })).toHaveAttribute("aria-selected", "true")
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible()
  await settle(page)
  await shot(page, "03-clip-subtitles", { fullPage: true })
})

test("04-download", async ({ page }) => {
  await page.goto(`/v/${BBB}?tab=video`)
  await expect(page.getByRole("button", { name: "โหลด mp4", exact: true })).toBeVisible()
  await settle(page)
  await shot(page, "04-download", { fullPage: true })
})

test("05-queue", async ({ page, request }) => {
  // งานแรกให้จบเพื่อขึ้นประวัติ งานที่สองโหลดช้า ให้คิวมีงานที่กำลังทำอยู่ตอนถ่าย
  const [done] = await enqueue(request, [
    { videoId: ZOO, kind: "audio", params: { format: "m4a", splitChapters: false, audioLanguage: "original" }, title: ZOO_TITLE },
  ])
  await waitForJob(request, (job) => job.id === done.id && job.status === "done", { timeout: 60_000 })
  await enqueue(request, [
    {
      videoId: SLOW,
      kind: "video",
      params: { maxQuality: false, splitChapters: false, noAudio: false, audioLanguage: "original" },
      title: SLOW_TITLE,
    },
  ])
  await waitForJob(request, (job) => job.videoId === SLOW && job.status === "running", { timeout: 30_000 })
  await gotoReady(page, `/v/${BBB}?tab=video`)
  const sheet = await openQueueSheet(page)
  await expect(sheet.getByText(SLOW_TITLE)).toBeVisible()
  await settle(page)
  await shot(page, "05-queue")
  // ยกเลิกงานที่ค้างอยู่ ให้รูปถัดไปไม่มีแถบคิวกวนสายตา
  await cancelJobsFor(request, [SLOW])
})

test("06-history", async ({ page }) => {
  await page.goto("/history")
  await expect(page.getByRole("link", { name: ZOO_TITLE })).toBeVisible()
  // รอปกคลิปทุกภาพโหลดเสร็จ (ไม่ถ่ายตอนยังเป็นกรอบเทา)
  const covers = page.locator("tbody img")
  await expect(covers).toHaveCount(3)
  await expect
    .poll(() => covers.evaluateAll((imgs) => (imgs as HTMLImageElement[]).every((img) => img.complete && img.naturalWidth > 0)))
    .toBe(true)
  await settle(page)
  await shot(page, "06-history")
})

test("07-settings", async ({ page }) => {
  await page.goto("/settings/general")
  await expect(page.getByText(NEUTRAL_OUTPUT_DIR)).toBeVisible().catch(() => undefined)
  await expect(page.getByRole("tab", { name: "ทั่วไป", exact: true })).toHaveAttribute("aria-selected", "true")
  await settle(page)
  await shot(page, "07-settings")
})
