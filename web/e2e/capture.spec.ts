/// <reference lib="dom" />
import path from "node:path"

import { analyzeSettled } from "./axe-settled"
import { expect, test, type Page } from "@playwright/test"

import type { Capture } from "../src/lib/types"

import { fakeYTLog, installFakeYT } from "./fake-yt"
import { expectFocusInside } from "./focus"

/**
 * M5 รอบ B2 ถ่ายภาพคมตรงจุด (spec 2): ปุ่มใต้ตัวเล่น ปุ่มบนตัวเล่นลอย เมนูภาพเฟรม แถบ "ภาพที่ถ่ายไว้" ภาพใหญ่ และการลบ
 * โปรเจกต์ chromium: API ถ่ายภาพจำลองด้วย page.route ทั้งหมด (ไม่ถ่ายจริง ไม่ต่อยูทูป) ภาพทุกภาพคือ tests/fixtures/media/cover.jpg
 * หัวคลิปแบบปกติ (ค่าเริ่มต้นของ project) ยกเว้นกลุ่มโรงภาพยนตร์ที่ตั้ง yt-toolkit:theater = "1" เอง
 */

const BBB = "aqz-KE-bpKQ"
const COVER = path.join(import.meta.dirname, "../../tests/fixtures/media/cover.jpg")
const BUTTON = "ถ่ายภาพคมตรงนี้"

const item = (tMs: number): Capture => ({ id: `c_${tMs}`, tMs, width: 1920, height: 1080, url: `/api/cache/${BBB}/captures/c_${tMs}.jpg?v=1` })

/** เวลาแบบที่แถบ/ภาพใหญ่แสดง (คลิปไม่ถึงชั่วโมง): "0:02" · มีเศษ 100 ms = "0:02.5" */
function clock(ms: number): string {
  const seconds = Math.floor(ms / 1000)
  const tenth = Math.floor((ms % 1000) / 100)
  const whole = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`
  return tenth === 0 ? whole : `${whole}.${tenth}`
}

/**
 * hold = กั้นคำตอบของการถ่ายไว้จน promise นี้จบ (ตรวจสถานะ "กำลังถ่าย…" ได้โดยไม่แข่งกับเวลา)
 * maxTMs = ตอบ 422 แบบ backend เมื่อ tMs เกินค่านี้ (ตรวจว่าเว็บไม่ส่งเวลาที่เลยท้ายคลิป)
 */
type MockOptions = { hold?: Promise<void>; error?: { status: number; code: string; message: string }; maxTMs?: number }
type MockState = { list: Capture[]; posts: number[]; deletes: string[]; reveals: number }

/** จำลอง API ถ่ายภาพของคลิป BBB: รายการ ถ่าย (หน่วงได้ / ตอบ error ได้) ลบ เปิดโฟลเดอร์ และไฟล์ภาพ */
async function mockCaptures(page: Page, initial: Capture[] = [], options: MockOptions = {}): Promise<MockState> {
  const state: MockState = { list: [...initial], posts: [], deletes: [], reveals: 0 }
  await page.route(`**/api/videos/${BBB}/captures`, async (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: { captures: state.list } })
    const { tMs } = route.request().postDataJSON() as { tMs: number }
    state.posts.push(tMs)
    if (options.hold) await options.hold
    if (options.maxTMs !== undefined && tMs > options.maxTMs) {
      const message = "ข้อมูลที่ส่งมาไม่ถูกต้อง ลองรีเฟรชหน้าเว็บ"
      return route.fulfill({ status: 422, json: { error: { code: "E_BAD_REQUEST", message, detail: null } } })
    }
    if (options.error) {
      const { status, code, message } = options.error
      return route.fulfill({ status, json: { error: { code, message, detail: null } } })
    }
    const capture = item(tMs)
    state.list = [...state.list.filter((c) => c.id !== capture.id), capture].sort((a, b) => a.tMs - b.tMs)
    return route.fulfill({ status: 201, json: capture })
  })
  await page.route(`**/api/videos/${BBB}/captures/reveal`, (route) => {
    state.reveals += 1
    return route.fulfill({ json: { ok: true } })
  })
  await page.route(`**/api/videos/${BBB}/captures/c_*`, (route) => {
    const id = new URL(route.request().url()).pathname.split("/").pop() ?? ""
    state.deletes.push(id)
    state.list = state.list.filter((c) => c.id !== id)
    return route.fulfill({ status: 204, body: "" })
  })
  await page.route(`**/api/cache/${BBB}/captures/**`, (route) => route.fulfill({ path: COVER, contentType: "image/jpeg" }))
  return state
}

const captureButton = (page: Page) => page.locator('[data-slot="player-controls"]').getByRole("button", { name: BUTTON })
const strip = (page: Page) => page.locator('[data-slot="capture-strip"]')
const stripList = (page: Page) => strip(page).getByRole("list")
const tile = (page: Page, time: string) => stripList(page).getByRole("button", { name: `ภาพเฟรมที่ ${time}`, exact: true })
const toast = (page: Page, text: string | RegExp) => page.locator("[data-sonner-toast]").filter({ hasText: text })
const dock = (page: Page) => page.getByRole("region", { name: "ตัวเล่นคลิป (ลอย)" })
const header = (page: Page) => page.locator('[data-slot="video-header"]')
/** การสลับเลย์เอาต์ (view transition) จบแล้ว: ระหว่างนั้นคลิกไม่ได้ (ดู theater.spec.ts) */
const settled = (page: Page) => expect(page.locator("html[data-theater-switching]")).toHaveCount(0)

/** ข้อมูลคลิปจาก backend โหมด fake แต่สลับกว้าง/สูง: คลิปกลายเป็นแนวตั้ง (แบบเดียวกับ theater.spec.ts) */
async function asPortrait(page: Page) {
  await page.route(
    (url) => url.pathname === `/api/videos/${BBB}`,
    async (route) => {
      const response = await route.fetch()
      const body = (await response.json()) as { video: { width?: number; height: number }[] }
      const video = body.video.map((f) => (f.width ? { ...f, width: f.height, height: f.width } : f))
      await route.fulfill({ response, json: { ...body, video } })
    },
  )
}

async function open(page: Page) {
  await installFakeYT(page, { durationS: 635, rate: 0.001 })
  await page.goto(`/v/${BBB}`)
  await expect(page.getByRole("heading", { level: 1 })).not.toBeEmpty()
}

async function play(page: Page) {
  await page.getByRole("button", { name: "เล่นคลิป", exact: true }).click()
  await expect(page.locator('[data-slot="player-host"] iframe')).toHaveCount(1)
  await expect.poll(async () => (await fakeYTLog(page)).calls).toContain("play")
  await settled(page)
}

async function seriousViolations(page: Page) {
  const results = await analyzeSettled(page)
  return results.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)
}

test("ปุ่มมีหลังเริ่มเล่น · กำลังถ่าย… · toast ดูภาพเปิดภาพที่เพิ่งถ่าย · ภาพเข้าแถบ · เวลาปัดทีละ 100 ms", async ({ page }) => {
  let release!: () => void
  const hold = new Promise<void>((resolve) => (release = resolve))
  const state = await mockCaptures(page, [], { hold })
  await open(page)
  await expect(captureButton(page)).toHaveCount(0)
  await expect(strip(page)).toHaveCount(0)
  await play(page)
  const frame = page.getByRole("img", { name: /^ภาพเฟรมที่ / }).nth(2)
  await frame.click({ button: "right" })
  await page.getByRole("menuitem", { name: "เล่นจากตรงนี้" }).click()

  await captureButton(page).click()
  await expect(page.locator('[data-slot="player-controls"]').getByRole("button", { name: "กำลังถ่าย…" })).toBeDisabled()
  release()
  await expect(toast(page, /^ถ่ายภาพคมแล้ว · /)).toBeVisible()
  expect(state.posts).toHaveLength(1)
  expect(state.posts[0] % 100).toBe(0)
  await expect(captureButton(page)).toBeEnabled()
  await expect(page.getByRole("heading", { name: "ภาพที่ถ่ายไว้ (1)" })).toBeVisible()
  await expect(stripList(page).getByRole("listitem")).toHaveCount(1)

  await toast(page, /^ถ่ายภาพคมแล้ว · /).getByRole("button", { name: "ดูภาพ" }).click()
  await expect(page.getByRole("dialog", { name: `ภาพเฟรมที่ ${clock(state.posts[0])}` })).toBeVisible()
  await expect(page.locator('[data-slot="capture-actions"]').getByRole("button")).toHaveText([
    "คัดลอกภาพ",
    "โหลดภาพนี้",
    "เปิดในยูทูปตรงเวลานี้",
    "เล่นจากตรงนี้",
    "ลบภาพนี้",
  ])
})

test("ภาพใหญ่ ←/→ · Esc/ยกเลิกปิดแค่กล่องยืนยัน · ลบหลังยืนยันแล้ว toast และโฟกัสภาพถัดไป (ไม่มี = ก่อนหน้า)", async ({ page }) => {
  const state = await mockCaptures(page, [item(1000), item(2000), item(3000)])
  await open(page)
  await expect(page.getByRole("heading", { name: "ภาพที่ถ่ายไว้ (3)" })).toBeVisible()
  await tile(page, "0:02").click()
  const second = page.getByRole("dialog", { name: "ภาพเฟรมที่ 0:02" })
  await expect(second).toBeVisible()
  // ←/→ ฟังที่ตัวภาพใหญ่: กดก่อนโฟกัสย้ายเข้าไป ปุ่มไปที่ภาพในแถบแทน (CI run 38870704595)
  await expectFocusInside(second)
  await page.keyboard.press("ArrowRight")
  const last = page.getByRole("dialog", { name: "ภาพเฟรมที่ 0:03" })
  await expect(last).toBeVisible()
  const remove = last.getByRole("button", { name: "ลบภาพนี้" })
  const confirm = page.getByRole("alertdialog", { name: "ลบภาพนี้ทั้งในแอพและในโฟลเดอร์ไหม" })

  // Esc ในกล่องยืนยัน = ปิดแค่กล่องยืนยัน ภาพใหญ่ยังเปิดอยู่
  await remove.click()
  await expect(confirm).toBeVisible()
  await expectFocusInside(confirm)
  await page.keyboard.press("Escape")
  await expect(confirm).toHaveCount(0)
  await expect(last).toBeVisible()

  // ยกเลิก = ไม่ลบ โฟกัสกลับที่ "ลบภาพนี้"
  await remove.click()
  await confirm.getByRole("button", { name: "ยกเลิก" }).click()
  await expect(confirm).toHaveCount(0)
  await expect(remove).toBeFocused()
  expect(state.deletes).toEqual([])

  // ลบภาพสุดท้าย = โฟกัสภาพก่อนหน้า
  await remove.click()
  await confirm.getByRole("button", { name: "ลบภาพ", exact: true }).click()
  await expect(toast(page, "ลบภาพแล้ว")).toBeVisible()
  expect(state.deletes).toEqual(["c_3000"])
  await expect(page.getByRole("dialog")).toHaveCount(0)
  await expect(page.getByRole("heading", { name: "ภาพที่ถ่ายไว้ (2)" })).toBeVisible()
  await expect(tile(page, "0:02")).toBeFocused()

  // ลบภาพแรก = โฟกัสภาพถัดไป
  await tile(page, "0:01").click()
  const first = page.getByRole("dialog", { name: "ภาพเฟรมที่ 0:01" })
  await first.getByRole("button", { name: "ลบภาพนี้" }).click()
  await confirm.getByRole("button", { name: "ลบภาพ", exact: true }).click()
  await expect(page.getByRole("heading", { name: "ภาพที่ถ่ายไว้ (1)" })).toBeVisible()
  expect(state.deletes).toEqual(["c_3000", "c_1000"])
  await expect(page.getByRole("dialog")).toHaveCount(0)
  await expect(tile(page, "0:02")).toBeFocused()
})

test("แถบมีจุดหยุด Tab เดียว · ลูกศร/Home/End เลื่อน · Enter เปิดภาพใหญ่ · Esc กลับมาที่ภาพเดิม", async ({ page }) => {
  await mockCaptures(page, [item(1000), item(2500), item(3000)])
  await open(page)
  await expect(stripList(page).locator('button[tabindex="0"]')).toHaveCount(1)
  await tile(page, "0:01").focus()
  await page.keyboard.press("ArrowRight")
  await expect(tile(page, "0:02.5")).toBeFocused()
  await page.keyboard.press("End")
  await expect(tile(page, "0:03")).toBeFocused()
  await page.keyboard.press("Home")
  await expect(tile(page, "0:01")).toBeFocused()
  await expect(stripList(page).locator('button[tabindex="0"]')).toHaveCount(1)
  await page.keyboard.press("Enter")
  await expect(page.getByRole("dialog", { name: "ภาพเฟรมที่ 0:01" })).toBeVisible()
  await page.keyboard.press("Escape")
  await expect(tile(page, "0:01")).toBeFocused()
})

test("ย่อหน้าต่างข้าม 640 px ตอนเปิดภาพใหญ่: แถบไม่ถูกสร้างใหม่ ภาพใหญ่ยังเปิดอยู่ ปิดแล้วโฟกัสกลับที่ภาพเดิม", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 })
  await mockCaptures(page, [item(1000), item(2000)])
  await open(page)
  const section = await strip(page).elementHandle()
  await tile(page, "0:02").click()
  const dialog = page.getByRole("dialog", { name: "ภาพเฟรมที่ 0:02" })
  await expect(dialog).toBeVisible()

  await page.setViewportSize({ width: 600, height: 900 })
  // จอแคบ: แถบย้ายไปอยู่ใต้ชื่อคลิป (คอลัมน์ข้อมูล) แต่เป็น element เดิม · หน้าไม่ล้นแนวนอน
  await expect(page.locator('[data-slot="video-info"] [data-slot="capture-strip"]')).toHaveCount(1)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
  expect(await section?.evaluate((node) => node.isConnected)).toBe(true)
  await expect(dialog).toBeVisible()

  await page.setViewportSize({ width: 1280, height: 900 })
  await expect(page.locator('[data-slot="video-info"] [data-slot="capture-strip"]')).toHaveCount(0)
  expect(await section?.evaluate((node) => node.isConnected)).toBe(true)
  await expect(dialog).toBeVisible()
  await page.keyboard.press("Escape")
  await expect(dialog).toHaveCount(0)
  await expect(tile(page, "0:02")).toBeFocused()
})

test("เมนูคลิกขวาของภาพเฟรม 'ถ่ายภาพคมตรงนี้' ใช้เวลาของภาพ", async ({ page }) => {
  const state = await mockCaptures(page)
  await open(page)
  const storyboard = (await (await page.request.get(`/api/videos/${BBB}/storyboard`)).json()) as { frames: { tMs: number }[] }
  await page.getByRole("img", { name: /^ภาพเฟรมที่ / }).nth(2).click({ button: "right" })
  await page.getByRole("menuitem", { name: BUTTON }).click()
  await expect.poll(() => state.posts).toEqual([Math.round(storyboard.frames[2].tMs / 100) * 100])
  await expect(page.getByRole("heading", { name: "ภาพที่ถ่ายไว้ (1)" })).toBeVisible()
})

test("ตัวเล่นลอยมีปุ่มไอคอน 'ถ่ายภาพคมตรงนี้' · ถ่ายแล้วหน้าไม่เลื่อน", async ({ page }) => {
  // มีภาพอยู่แล้วหนึ่งภาพ: ภาพใหม่เข้าแถวเดิมของแถบ หัวคลิปไม่สูงขึ้น (ตำแหน่งเลื่อนเทียบกันได้ตรง ๆ)
  const state = await mockCaptures(page, [item(5000)])
  await open(page)
  await play(page)
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollHeight - window.innerHeight)).toBeGreaterThan(1200)
  await page.evaluate(() => window.scrollTo(0, 1200))
  await expect(dock(page)).toBeVisible()
  // ตัวเล่นลอยแล้วแถวใต้ตัวเล่นหายไป เบราว์เซอร์ปรับตำแหน่งเลื่อนตาม (scroll anchoring) จึงจำตำแหน่งหลังลอยแล้ว
  const scrolled = await page.evaluate(() => window.scrollY)
  await dock(page).getByRole("button", { name: BUTTON }).click()
  await expect.poll(() => state.posts.length).toBe(1)
  await expect(page.getByRole("heading", { name: "ภาพที่ถ่ายไว้ (2)" })).toBeAttached()
  await expect(toast(page, /^ถ่ายภาพคมแล้ว · /)).toBeVisible()
  expect(await page.evaluate(() => window.scrollY)).toBe(scrolled)
  await expect(dock(page)).toBeVisible()
})

test("error จาก backend: toast ข้อความไทย ไม่มีภาพในแถบ ปุ่มกลับมากดได้", async ({ page }) => {
  const message = 'คลิปนี้ถ่ายภาพคมเฉพาะจุดไม่ได้ ใช้ "ขอภาพคม" ทั้งคลิปแทนได้'
  await mockCaptures(page, [], { error: { status: 422, code: "E_CAPTURE_UNSUPPORTED", message } })
  await open(page)
  await play(page)
  await captureButton(page).click()
  await expect(toast(page, message)).toBeVisible()
  await expect(strip(page)).toHaveCount(0)
  await expect(captureButton(page)).toBeEnabled()
})

test("คิวพักเพราะยูทูปขอตรวจสอบ: ปุ่มกดไม่ได้แต่โฟกัสได้ พร้อมเวลาที่ลองใหม่", async ({ page }) => {
  const state = await mockCaptures(page)
  const until = new Date(Date.now() + 10 * 60_000).toISOString()
  let paused = true
  await page.route("**/api/queue", (route) =>
    route.fulfill({ json: { pausedUntil: paused ? until : null, reason: paused ? "E_BOT_CHECK" : null, concurrency: 2 } }),
  )
  await open(page)
  await play(page)
  await expect(captureButton(page)).toBeDisabled()
  await captureButton(page).focus()
  await expect(captureButton(page)).toBeFocused()
  await captureButton(page).hover()
  await expect(page.getByText(/^พักการโหลดอยู่เพราะยูทูปขอตรวจสอบ ลองใหม่หลัง \d{2}:\d{2}$/)).toBeVisible()
  await captureButton(page).click({ force: true })

  // ด่านกั้น: เลิกพักแล้วถ่ายจากเมนูภาพเฟรม (เปิดเมนู = โหลดสถานะคิวใหม่) แล้วรอให้คำขอนั้นถึง
  // คำขอที่ได้ต้องมีแค่ของเมนู: คลิกตอนคิวพักไม่ได้ส่งอะไรเลย (คำขอนั้นจะมาก่อนของเมนูถ้ามี)
  paused = false
  const storyboard = (await (await page.request.get(`/api/videos/${BBB}/storyboard`)).json()) as { frames: { tMs: number }[] }
  await page.getByRole("img", { name: /^ภาพเฟรมที่ / }).nth(2).click({ button: "right" })
  await page.getByRole("menuitem", { name: BUTTON }).click()
  await expect(page.getByRole("heading", { name: "ภาพที่ถ่ายไว้ (1)" })).toBeVisible()
  expect(state.posts).toEqual([Math.round(storyboard.frames[2].tMs / 100) * 100])
})

test("ดูจนจบคลิปแล้วกดถ่าย: ส่งเวลาไม่เกิน 100 ms ก่อนจบ ไม่ได้ 422", async ({ page }) => {
  const durationS = 635
  const state = await mockCaptures(page, [], { maxTMs: durationS * 1000 - 100 })
  await open(page)
  await play(page)
  await page.locator('[data-slot="player-controls"] [role="slider"]').focus()
  await page.keyboard.press("End") // เล่นจากท้ายคลิป: ตัวเล่นปลอมจบทันที (ENDED) เวลาของตัวเล่น = ความยาวคลิป
  await expect.poll(async () => (await fakeYTLog(page)).states).toContain(0)
  await captureButton(page).click()
  await expect(toast(page, /^ถ่ายภาพคมแล้ว · /)).toBeVisible()
  expect(state.posts).toHaveLength(1)
  expect(state.posts[0]).toBeLessThanOrEqual(durationS * 1000 - 100)
  await expect(page.getByRole("heading", { name: "ภาพที่ถ่ายไว้ (1)" })).toBeVisible()
})

test("คลิปสด: ปุ่มกดไม่ได้พร้อมเหตุผล", async ({ page }) => {
  await mockCaptures(page)
  await page.route(
    (url) => url.pathname === `/api/videos/${BBB}`,
    async (route) => {
      const response = await route.fetch()
      await route.fulfill({ response, json: { ...(await response.json()), isLive: true } })
    },
  )
  await open(page)
  await play(page)
  await expect(captureButton(page)).toBeDisabled()
  await captureButton(page).hover()
  await expect(page.getByText("คลิปสดถ่ายภาพคมไม่ได้", { exact: true })).toBeVisible()
})

test("'เปิดโฟลเดอร์' ขอให้ backend เปิดโฟลเดอร์ ภาพที่ถ่าย", async ({ page }) => {
  const state = await mockCaptures(page, [item(1000)])
  await open(page)
  await strip(page).getByRole("button", { name: "เปิดโฟลเดอร์" }).click()
  await expect.poll(() => state.reveals).toBe(1)
})

test.describe("โหมดโรงภาพยนตร์แนวนอน", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem("yt-toolkit:theater", "1"))
  })

  test("แถบเป็นแถวเดียวเลื่อนได้ หน้าไม่ล้นแนวนอน · สลับเลย์เอาต์แล้วแถบเป็น element เดิม", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 })
    await mockCaptures(page, Array.from({ length: 14 }, (_, i) => item((i + 1) * 1000)))
    await open(page)
    await play(page)
    await expect(header(page)).toHaveAttribute("data-layout", "theater-wide")
    const list = stripList(page)
    const tops = await list.getByRole("listitem").evaluateAll((items) => items.map((li) => Math.round(li.getBoundingClientRect().top)))
    expect(new Set(tops).size).toBe(1)
    expect(await list.evaluate((ul) => ul.scrollWidth > ul.clientWidth)).toBe(true)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)

    const section = await strip(page).elementHandle()
    await page.locator('[data-slot="theater-toggle"]').click()
    await expect(header(page)).toHaveAttribute("data-layout", "compact")
    await settled(page)
    expect(await section?.evaluate((node) => node.isConnected)).toBe(true)
  })

  test("จอเตี้ย 1366×650: ตัวเล่นแคบลงคง 16:9 อยู่กลาง แถวใต้ตัวเล่นเห็นครบโดยไม่ต้องเลื่อน", async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 650 })
    await mockCaptures(page)
    await open(page)
    await play(page)
    await expect(header(page)).toHaveAttribute("data-layout", "theater-wide")
    expect(await page.evaluate(() => window.scrollY)).toBe(0)
    await expect(captureButton(page)).toBeInViewport({ ratio: 1 })
    await expect(page.locator('[data-slot="theater-toggle"]')).toBeInViewport({ ratio: 1 })
    await expect(page.locator('[data-slot="player-controls"] [role="slider"]')).toBeInViewport({ ratio: 1 })
    const slot = await page.locator('[data-slot="player-slot"]').boundingBox()
    const column = await header(page).boundingBox()
    expect(slot && column).toBeTruthy()
    if (!slot || !column) return
    expect(slot.width).toBeLessThan(column.width - 1)
    expect(Math.abs(slot.width / slot.height - 16 / 9)).toBeLessThan(0.02)
    expect(Math.abs(slot.x - column.x - (column.width - slot.width) / 2)).toBeLessThan(1.5)
  })

  test("คลิปแนวตั้ง: โฟกัสปุ่ม 'ถ่ายภาพคมตรงนี้' แล้วกด T แถวใต้ตัวเล่นย้ายคอลัมน์ โฟกัสยังอยู่ที่ปุ่มนี้", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 })
    await mockCaptures(page)
    await asPortrait(page)
    await open(page)
    await play(page)
    await expect(header(page)).toHaveAttribute("data-layout", "theater-tall")
    await expect(page.locator('[data-slot="video-info"]').locator('[data-slot="player-controls"]')).toHaveCount(1)
    await captureButton(page).focus()
    await expect(captureButton(page)).toBeFocused()
    await page.keyboard.press("t")
    await expect(header(page)).toHaveAttribute("data-layout", "compact")
    await expect(page.locator('[data-slot="video-info"]').locator('[data-slot="player-controls"]')).toHaveCount(0)
    await expect(captureButton(page)).toBeFocused()
  })

  test("คลิปแนวตั้ง: โฟกัสภาพในแถบแล้วกด T แถบย้ายคอลัมน์ (element เดิม) โฟกัสยังอยู่ที่ภาพเดิม", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 })
    await mockCaptures(page, [item(1000), item(2000), item(3000)])
    await asPortrait(page)
    await open(page)
    await play(page)
    await expect(header(page)).toHaveAttribute("data-layout", "theater-tall")
    await expect(page.locator('[data-slot="video-info"] [data-slot="capture-strip"]')).toHaveCount(1)
    const section = await strip(page).elementHandle()
    await tile(page, "0:02").focus()
    await expect(tile(page, "0:02")).toBeFocused()
    await page.keyboard.press("t")
    await expect(header(page)).toHaveAttribute("data-layout", "compact")
    await expect(page.locator('[data-slot="video-info"] [data-slot="capture-strip"]')).toHaveCount(0)
    expect(await section?.evaluate((node) => node.isConnected)).toBe(true)
    await expect(tile(page, "0:02")).toBeFocused()
  })

  test("จอสูง 1280×1000: ตัวเล่นเต็มความกว้างของเนื้อหา", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 1000 })
    await mockCaptures(page)
    await open(page)
    await play(page)
    await expect(header(page)).toHaveAttribute("data-layout", "theater-wide")
    const slot = await page.locator('[data-slot="player-slot"]').boundingBox()
    const column = await header(page).boundingBox()
    expect(slot && column).toBeTruthy()
    if (!slot || !column) return
    expect(Math.abs(slot.width - column.width)).toBeLessThan(1)
  })
})

for (const scheme of ["light", "dark"] as const) {
  test(`axe ไม่มีปัญหาร้ายแรง (${scheme}) แถบ + ภาพใหญ่ · 640 px ไม่ล้นแนวนอน`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme })
    await page.setViewportSize({ width: 640, height: 800 })
    await mockCaptures(page, [item(1000), item(125_400)])
    await open(page)
    await play(page)
    await expect(captureButton(page)).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
    expect(await seriousViolations(page)).toEqual([])
    await tile(page, "2:05.4").click()
    const lightbox = page.locator('[data-slot="lightbox"]')
    await expect(lightbox).toBeVisible()
    // ตรวจหลังภาพโหลดและแอนิเมชันเปิดจบ (ระหว่างจางเข้า สีปุ่มยังโปร่ง axe จะวัดความต่างสีผิด)
    await expect.poll(() => lightbox.locator("img").evaluate((el) => (el as HTMLImageElement).complete)).toBe(true)
    await lightbox.evaluate((el) => Promise.all(el.getAnimations({ subtree: true }).map((a) => a.finished)))
    expect(await seriousViolations(page)).toEqual([])
    // "ลบภาพนี้" พื้นทึบเท่าพื้นหน้าเว็บทั้งตอนปกติและตอนชี้เมาส์ (axe ไม่ตรวจตอนชี้เมาส์) ตัวหนังสือแดงจึงไม่จมพื้นดำ
    const remove = lightbox.getByRole("button", { name: "ลบภาพนี้" })
    const pageBackground = await page.evaluate(() => getComputedStyle(document.body).backgroundColor)
    await expect(remove).toHaveCSS("background-color", pageBackground)
    await remove.hover()
    await expect(remove).toHaveCSS("background-color", pageBackground)
  })
}
