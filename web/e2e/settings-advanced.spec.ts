/// <reference lib="dom" />
import { expect, test, type Page } from "@playwright/test"

import { analyzeSettled } from "./axe-settled"

/**
 * M5 รอบ C แท็บ ตั้งค่า > ขั้นสูง (/settings/advanced, spec 1.1) และแถว "บัญชียูทูป" ในหน้าตรวจสุขภาพ (spec 1.4)
 * โปรเจกต์ chromium: /api/cookies* จำลองด้วย page.route (ไม่นำเข้าจริง)
 */

const INTRO =
  "ใช้เมื่อต้องโหลดคลิปจำกัดอายุ คลิปส่วนตัว หรือคลิปเฉพาะสมาชิก แอพเก็บการเข้าสู่ระบบไว้ชั่วคราวและลบเองเมื่อโหลดเสร็จ"
const USE = "ใช้บัญชียูทูปชั่วคราว"
const GOOD_FILE = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t2000000000\tLOGIN_INFO\te2e-not-a-real-value\n"

async function mockAccount(page: Page) {
  const state = { active: false, imports: 0, deletes: 0 }
  const status = () => {
    if (!state.active) return { active: false, used: false }
    const at = Math.floor(Date.now() / 1000) * 1000
    return { active: true, importedAt: new Date(at).toISOString(), expiresAt: new Date(at + 7_200_000).toISOString(), used: false }
  }
  await page.route("**/api/cookies", (route) => {
    if (route.request().method() === "DELETE") {
      state.deletes += 1
      state.active = false
    }
    return route.fulfill({ json: status() })
  })
  await page.route("**/api/cookies/import", (route) => {
    state.imports += 1
    state.active = true
    return route.fulfill({ json: status() })
  })
  return state
}

const panelStatus = (page: Page) => page.getByTestId("account-status")

test("แท็บขั้นสูง: คำอธิบาย สถานะ ปุ่ม · dialog ปุ่มนำเข้าเป็น นำเข้า · นำเข้าแล้วมีเวลาที่จะลบและปุ่มลบออกตอนนี้", async ({ page }) => {
  const state = await mockAccount(page)
  await page.goto("/settings")
  await page.getByRole("tab", { name: "ขั้นสูง" }).click()
  await expect(page).toHaveURL(/\/settings\/advanced$/)
  await expect(page.getByText(INTRO)).toBeVisible()
  await expect(panelStatus(page)).toHaveText("ไม่ได้ใช้บัญชี")
  await expect(panelStatus(page).getByRole("button", { name: "ลบออกตอนนี้" })).toHaveCount(0)
  await expect(page.getByRole("switch")).toHaveCount(0) // ไม่มี Switch หรือตัวเลือกแหล่งแบบ PRD เดิม
  await page.getByRole("button", { name: USE }).click()
  const dialog = page.getByRole("dialog", { name: USE })
  await expect(dialog.getByRole("button", { name: "นำเข้าแล้วลองใหม่" })).toHaveCount(0)
  await dialog.getByLabel("cookies.txt").setInputFiles({ name: "cookies.txt", mimeType: "text/plain", buffer: Buffer.from(GOOD_FILE) })
  await dialog.getByRole("button", { name: "นำเข้า", exact: true }).click()
  await expect(dialog).toHaveCount(0)
  await expect(panelStatus(page)).toContainText(/ใช้บัญชีชั่วคราวอยู่ ลบอัตโนมัติภายใน 2 ชม\./)
  await panelStatus(page).getByRole("button", { name: "ลบออกตอนนี้" }).click()
  await expect(panelStatus(page)).toHaveText("ไม่ได้ใช้บัญชี")
  await expect(page.locator("[data-sonner-toast]").filter({ hasText: "ลบบัญชีออกจากแอพแล้ว" })).toBeVisible()
  expect([state.imports, state.deletes]).toEqual([1, 1])
})

for (const scheme of ["dark", "light"] as const) {
  test(`axe ${scheme}: แท็บขั้นสูงไม่มีปัญหาระดับ serious/critical`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme })
    await mockAccount(page)
    await page.goto("/settings/advanced")
    await expect(page.getByText(INTRO)).toBeVisible()
    await expect(page.locator("html")).toHaveClass(scheme === "dark" ? /dark/ : /light/)
    const results = await analyzeSettled(page)
    expect(results.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)).toEqual([])
  })
}

test("หน้าต่างแคบ 640 px: แท็บขั้นสูงไม่เลื่อนซ้ายขวา", async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 800 })
  await mockAccount(page)
  await page.goto("/settings/advanced")
  await expect(page.getByText(INTRO)).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(640)
})
