import { focusRingContrast } from "./contrast"
import { expect, test, type Locator, type Page } from "@playwright/test"

import type { Job } from "../src/lib/types"

import { mockEnqueue } from "./queue-helpers"

// M6 D1 T2 (spec 1.2): เดินทั้งแอพด้วยคีย์บอร์ดอย่างเดียว W1 → W2 → W5 → W4 → W6 → W7
// หลัง page.goto("/") ใช้แต่ page.keyboard (ไม่มี click() ไม่มี focus()) · project chromium: POST /api/jobs ถูก mock
// ไม่มีงานจริงเกิดขึ้น · /api/stats ถูก mock เป็นข้อมูลมีตัวเลข · ทุกขั้นตรวจว่าโฟกัสอยู่ที่ปุ่มที่ตั้งใจ และเห็นวงโฟกัส
// แถบแท็บของแอพ (Base UI) เปิดแท็บแบบกดเลือกเอง: ลูกศรย้ายโฟกัส · Enter เปิดแท็บที่โฟกัส (aria-selected ตามมา)

const BBB = "aqz-KE-bpKQ"
const BBB_URL = `https://www.youtube.com/watch?v=${BBB}`
const FILLED = {
  since: null,
  clips: 3,
  files: 5,
  totalBytes: 1_400_000_000,
  byKind: [{ kind: "video", files: 5, bytes: 1_400_000_000 }],
  byMonth: [{ month: "2026-10", clips: 3, files: 5, bytes: 1_400_000_000 }],
}
const MIN_RING = 3

/** กด Tab (หรือ Shift+Tab) จนโฟกัสถึงเป้าหมาย · เกินจำนวนครั้ง = ล้มพร้อมบอกว่าโฟกัสค้างที่ไหน (ไม่วนไม่รู้จบ) */
async function tabTo(page: Page, target: Locator, opts: { max?: number; back?: boolean } = {}) {
  const max = opts.max ?? 40
  const key = opts.back ? "Shift+Tab" : "Tab"
  for (let i = 0; i < max; i++) {
    if (await target.evaluate((el) => el === document.activeElement)) return
    await page.keyboard.press(key)
  }
  if (await target.evaluate((el) => el === document.activeElement)) return
  const at = await page.evaluate(() => {
    const el = document.activeElement
    return el ? `${el.tagName.toLowerCase()} "${(el.getAttribute("aria-label") ?? el.textContent ?? "").trim().slice(0, 40)}"` : "ไม่มี"
  })
  throw new Error(`${target} not reachable by ${key} within ${max} presses (โฟกัสค้างที่ ${at})`)
}

/** โฟกัสอยู่ที่เป้าหมาย และมีวงโฟกัสให้เห็นอยู่หนึ่งจุด */
async function expectFocused(page: Page, target: Locator) {
  await expect(target).toBeFocused()
  await expect(page.locator(":focus-visible")).toHaveCount(1)
}

test("คีย์บอร์ดอย่างเดียว: วางลิงก์ → หน้าคลิป → โหลด → คิว → ประวัติ → ตั้งค่า → ล้างสถิติ → ช่องเลือก", async ({ page }) => {
  test.setTimeout(90_000)
  const { bodies } = await mockEnqueue(page)
  // งานปลอมที่ POST ตอบกลับ ส่งต่อให้ GET /api/jobs ด้วย แถบคิวจึงไม่หายถ้าแอพโหลดรายการงานใหม่
  let posted: Job[] = []
  page.on("response", async (response) => {
    const url = new URL(response.url())
    if (url.pathname === "/api/jobs" && response.request().method() === "POST") {
      posted = ((await response.json()) as { jobs: Job[] }).jobs
    }
  })
  await page.route("**/api/jobs", async (route) => {
    if (route.request().method() !== "GET" || posted.length === 0) return route.fallback()
    return route.fulfill({ json: { jobs: posted } })
  })
  await page.route("**/api/stats", (route) => route.fulfill({ json: FILLED }))

  await page.goto("/")

  // 1. W1: Tab ถึงช่องวางลิงก์ พิมพ์ลิงก์ แล้ว Ctrl+Enter วิเคราะห์ (คลิปเดียว = ไปหน้าคลิปเลย)
  const box = page.getByRole("textbox", { name: "ลิงก์ยูทูป" })
  await tabTo(page, box)
  await expectFocused(page, box)
  await page.keyboard.insertText(BBB_URL)
  await expect(box).toHaveValue(BBB_URL)
  await page.keyboard.press("Control+Enter")
  await expect(page).toHaveURL(new RegExp(`/v/${BBB}$`))
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Big Buck Bunny")

  // 2. W2: Tab ถึงแท็บที่เปิดอยู่ (ภาพเฟรม) · ลูกศรขวา/ซ้ายย้ายโฟกัส · Enter เปิดแท็บ = aria-selected ตามมา
  const tabs = page.getByRole("tablist", { name: "เครื่องมือของคลิปนี้" })
  const tab = (name: string) => tabs.getByRole("tab", { name, exact: true })
  await tabTo(page, tab("ภาพเฟรม"))
  await expectFocused(page, tab("ภาพเฟรม"))
  expect(await focusRingContrast(page, tab("ภาพเฟรม"))).toBeGreaterThanOrEqual(MIN_RING)
  await page.keyboard.press("ArrowRight")
  await page.keyboard.press("ArrowRight")
  await expectFocused(page, tab("เสียง"))
  await page.keyboard.press("Enter")
  await expect(tab("เสียง")).toHaveAttribute("aria-selected", "true")
  await expect(page).toHaveURL(new RegExp(`/v/${BBB}\\?tab=audio$`))
  await page.keyboard.press("ArrowLeft")
  await expectFocused(page, tab("วิดีโอ"))
  await page.keyboard.press("Enter")
  await expect(tab("วิดีโอ")).toHaveAttribute("aria-selected", "true")
  await expect(tab("เสียง")).toHaveAttribute("aria-selected", "false")
  await expect(page).toHaveURL(new RegExp(`/v/${BBB}\\?tab=video$`))

  // 3. แท็บวิดีโอ: Tab ถึงปุ่ม "โหลด mp4" แล้ว Enter = ส่งเข้าคิวหนึ่งครั้ง (POST ถูก mock)
  const download = page.getByRole("button", { name: "โหลด mp4", exact: true })
  await expect(download).toBeVisible()
  await tabTo(page, download)
  await expectFocused(page, download)
  await page.keyboard.press("Enter")
  await expect(page.getByText("เพิ่มเข้าคิวแล้ว", { exact: true })).toBeVisible()
  await expect.poll(() => bodies.length).toBe(1)
  expect(bodies[0]).toMatchObject([{ videoId: BBB, kind: "video" }])

  // 4. W5: Tab ต่อไปถึงแถบคิวด้านล่าง · Enter เปิดชีตคิว (aria-expanded) · Escape ปิด โฟกัสกลับที่แถบ
  const toggle = page.getByRole("region", { name: "คิวงาน" }).getByRole("button", { name: "เปิดคิวงาน" })
  await expect(toggle).toBeVisible()
  await tabTo(page, toggle)
  await expectFocused(page, toggle)
  await page.keyboard.press("Enter")
  const sheet = page.getByRole("dialog", { name: "คิวงาน" })
  await expect(sheet).toBeVisible()
  await expect(page.getByRole("region", { name: "คิวงาน", includeHidden: true }).locator("button[aria-expanded]")).toHaveAttribute(
    "aria-expanded",
    "true",
  )
  await expect(sheet.locator(":focus")).toHaveCount(1)
  await page.keyboard.press("Escape")
  await expect(sheet).toBeHidden()
  await expect(toggle).toHaveAttribute("aria-expanded", "false")
  await expectFocused(page, toggle)

  // 5. W4: Shift+Tab ย้อนขึ้นจากแถบคิวผ่านหน้าคลิปทั้งหน้า ถึงเมนู "ประวัติ" บนหัว แล้ว Enter
  //    (Tab ไปข้างหน้าจากแถบคิวเข้า toast "เพิ่มเข้าคิวแล้ว" ของ sonner แล้วออกนอกหน้า · sonner คืนโฟกัสให้แถบคิวตอนโฟกัสออกจาก toast
  //    ใน Playwright ที่ไม่มีแถบที่อยู่ของเบราว์เซอร์ Tab จึงวน แถบคิว → toast → แถบคิว ดูรายงาน T2)
  const nav = page.getByRole("navigation", { name: "เมนูหลัก" })
  const history = nav.getByRole("link", { name: "ประวัติ" })
  await tabTo(page, history, { back: true, max: 80 })
  await expectFocused(page, history)
  await page.keyboard.press("Enter")
  await expect(page).toHaveURL(/\/history$/)
  await expect(history).toHaveAttribute("aria-current", "page")

  // 6. W6: Tab ถึง "ตั้งค่า" แล้ว Enter · ลูกศรย้ายแท็บตั้งค่า + Enter = URL /settings/<แท็บ>
  const settings = nav.getByRole("link", { name: "ตั้งค่า" })
  await tabTo(page, settings)
  await expectFocused(page, settings)
  await page.keyboard.press("Enter")
  // /settings เด้งต่อไป /settings/general ทันที (router.tsx) จึงรอที่ปลายทาง ไม่ใช่ URL ชั่วคราว
  await expect(page).toHaveURL(/\/settings\/general$/)
  const settingsTab = (name: string) => page.getByRole("tab", { name, exact: true })
  await tabTo(page, settingsTab("ทั่วไป"))
  await expectFocused(page, settingsTab("ทั่วไป"))
  await page.keyboard.press("ArrowRight")
  await expectFocused(page, settingsTab("ขั้นสูง"))
  await page.keyboard.press("Enter")
  await expect(page).toHaveURL(/\/settings\/advanced$/)
  await expect(settingsTab("ขั้นสูง")).toHaveAttribute("aria-selected", "true")
  await page.keyboard.press("ArrowRight")
  await expectFocused(page, settingsTab("สถิติของฉัน"))
  await page.keyboard.press("Enter")
  await expect(page).toHaveURL(/\/settings\/stats$/)
  await expect(settingsTab("สถิติของฉัน")).toHaveAttribute("aria-selected", "true")

  // 7. W7: Tab ถึง "ล้างสถิติ" · Enter เปิดกล่องยืนยัน โฟกัสอยู่ในกล่อง · Escape ปิด โฟกัสกลับที่ปุ่ม
  await expect(page.getByTestId("stats-tiles")).toContainText("1.4 GB")
  const reset = page.getByRole("tabpanel").getByRole("button", { name: "ล้างสถิติ" })
  await tabTo(page, reset)
  await expectFocused(page, reset)
  expect(await focusRingContrast(page, reset)).toBeGreaterThanOrEqual(MIN_RING)
  await page.keyboard.press("Enter")
  const confirm = page.getByRole("alertdialog")
  await expect(confirm).toBeVisible()
  await expect(confirm).toContainText("เริ่มนับสถิติใหม่?")
  await expect(confirm.locator(":focus")).toHaveCount(1)
  await page.keyboard.press("Escape")
  await expect(confirm).toHaveCount(0)
  await expectFocused(page, reset)

  // 8. แท็บทั่วไป: Shift+Tab กลับแถบแท็บ ลูกศรซ้ายสองครั้ง + Enter · Tab ถึงช่องเลือก
  //    Enter เปิดรายการ ลูกศรลงย้ายตัวเลือก Escape ปิด = โฟกัสกลับที่ช่อง ค่าเดิมไม่เปลี่ยน
  await tabTo(page, settingsTab("สถิติของฉัน"), { back: true })
  await page.keyboard.press("ArrowLeft")
  await page.keyboard.press("ArrowLeft")
  await expectFocused(page, settingsTab("ทั่วไป"))
  await page.keyboard.press("Enter")
  await expect(page).toHaveURL(/\/settings\/general$/)
  const select = page.getByRole("combobox", { name: "คุณภาพวิดีโอเริ่มต้น" })
  await expect(select).toBeVisible()
  const before = await select.textContent()
  await tabTo(page, select)
  await expectFocused(page, select)
  expect(await focusRingContrast(page, select)).toBeGreaterThanOrEqual(MIN_RING)
  await page.keyboard.press("Enter")
  const listbox = page.getByRole("listbox")
  await expect(listbox).toBeVisible()
  await page.keyboard.press("ArrowDown")
  await page.keyboard.press("Escape")
  await expect(listbox).toBeHidden()
  await expectFocused(page, select)
  await expect(select).toHaveText(before ?? "")
})
