/// <reference lib="dom" />
import { expect, test, type Page } from "@playwright/test"

import { analyzeSettled } from "./axe-settled"

/**
 * M5 รอบ C บัญชียูทูปชั่วคราว (spec 1.1-1.3): error ของหน้า W2 → ปุ่ม → dialog → นำเข้า → แถบบนหน้า → ลบออกตอนนี้
 * โปรเจกต์ chromium: /api/cookies* และข้อมูลคลิปตอนติดจำกัดอายุจำลองด้วย page.route ทั้งหมด (ไม่นำเข้าจริง ไม่ต่อยูทูป)
 * ใช้คลิป Big Buck Bunny ของ backend ปลอม: คำขอแรกตอบ E_AGE_RESTRICTED หลังนำเข้าปล่อยผ่านไปที่ backend
 */

const BBB = "aqz-KE-bpKQ"
const AGE_MESSAGE = "คลิปนี้จำกัดอายุ ต้องเข้าสู่ระบบยูทูปถึงจะเปิดได้"
const TRIED_MESSAGE =
  "ลองด้วยบัญชีแล้วยังเปิดไม่ได้ บัญชีนี้อาจไม่มีสิทธิ์ดูคลิปนี้ หรือการเข้าสู่ระบบหมดอายุแล้ว ลองนำเข้าใหม่"
const INVALID = "ไฟล์นี้ใช้ไม่ได้ ตรวจว่าเข้าสู่ระบบยูทูปแล้วก่อนส่งออก แล้วส่งออก cookies.txt ใหม่"
const REMOVED = "ลบบัญชีออกจากแอพแล้ว · กลับไปกดออกจากระบบในหน้าต่างไม่ระบุตัวตน แล้วปิดหน้าต่าง"
const USE = "ใช้บัญชียูทูปชั่วคราว"
const GOOD_FILE = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t2000000000\tSAPISID\te2e-not-a-real-value\n"

type AccountMock = { imports: unknown[]; deletes: number; videoCalls: number; active: boolean }

/** จำลองบัญชีและข้อมูลคลิป: ยังไม่นำเข้า = /videos/BBB ตอบ error (code) · นำเข้าแล้ว = ปล่อยไป backend */
async function mockAccount(page: Page, options: { active?: boolean; code?: string; message?: string } = {}) {
  const state: AccountMock = { imports: [], deletes: 0, videoCalls: 0, active: options.active ?? false }
  // แบบเดียวกับ backend: เวลานำเข้าและเวลาลบมาจากวินาทีเดียวกัน (ตัดเศษมิลลิวินาที) ห่างกัน 2 ชม. พอดี
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
    const body = route.request().postDataJSON() as { text: string; acceptWarning: boolean }
    state.imports.push(body)
    if (!body.text.includes("SAPISID")) {
      return route.fulfill({
        status: 422,
        json: { error: { code: "E_COOKIES_INVALID", message: INVALID, detail: "no YouTube sign-in cookie" } },
      })
    }
    state.active = true
    return route.fulfill({ json: status() })
  })
  await page.route(`**/api/videos/${BBB}`, (route) => {
    state.videoCalls += 1
    if (state.active && !options.code) return route.continue()
    const code = options.code ?? "E_AGE_RESTRICTED"
    const message = options.message ?? AGE_MESSAGE
    return route.fulfill({ status: code === "E_VIDEO_PRIVATE" ? 404 : 409, json: { error: { code, message, detail: null } } })
  })
  return state
}

const errorCard = (page: Page) => page.getByRole("alert").filter({ hasText: "เปิดข้อมูลคลิปไม่สำเร็จ" })
const dialog = (page: Page) => page.getByRole("dialog", { name: USE })
const banner = (page: Page) => page.getByTestId("account-banner")
const toast = (page: Page, text: string) => page.locator("[data-sonner-toast]").filter({ hasText: text })

async function chooseFile(page: Page, text: string, name = "cookies.txt") {
  await dialog(page).getByLabel("cookies.txt").setInputFiles({ name, mimeType: "text/plain", buffer: Buffer.from(text) })
}

async function seriousViolations(page: Page) {
  const results = await analyzeSettled(page)
  return results.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)
}

test("error จำกัดอายุ: ข้อความใหม่ + ปุ่ม · dialog มีคำเตือน คลิปส่วนตัว และ 6 ขั้นตอน · ยกเลิก/Esc ไม่ส่งอะไร", async ({ page }) => {
  const state = await mockAccount(page)
  await page.goto(`/v/${BBB}`)
  await expect(errorCard(page)).toContainText(AGE_MESSAGE)
  await expect(errorCard(page).getByRole("button", { name: "ลองใหม่" })).toHaveCount(0)
  await errorCard(page).getByRole("button", { name: USE }).click()
  const box = dialog(page)
  await expect(box).toBeVisible()
  await expect(box.getByRole("alert")).toContainText("ใช้บัญชีสำรองเท่านั้น")
  await expect(box).toContainText("คลิปส่วนตัว: ให้เจ้าของช่องแชร์คลิปให้อีเมลของบัญชีสำรองใน YouTube Studio ก่อน")
  await expect(box.getByRole("listitem")).toHaveText([
    "เปิดหน้าต่างไม่ระบุตัวตน (Ctrl+Shift+N)",
    "เข้าสู่ระบบยูทูปด้วยบัญชีสำรอง",
    "เปิด youtube.com/robots.txt ในแท็บเดิม",
    "ส่งออกไฟล์ cookies.txt ด้วยส่วนขยาย (ต้องอนุญาตให้ทำงานในหน้าต่างไม่ระบุตัวตน)",
    "เปิดหน้าต่างนั้นค้างไว้ ไม่ต้องเปิดยูทูปในหน้าต่างนั้น",
    "เลือกไฟล์ด้านล่าง",
  ])
  await expect(box.getByRole("button", { name: "นำเข้าแล้วลองใหม่" })).toBeDisabled()
  await expect(box.getByText(/คุกกี้/)).toHaveCount(0) // C5: UI ไม่พูดคำว่าคุกกี้
  await chooseFile(page, GOOD_FILE)
  await box.getByRole("button", { name: "ยกเลิก" }).click()
  await expect(box).toHaveCount(0)
  await errorCard(page).getByRole("button", { name: USE }).click()
  await chooseFile(page, GOOD_FILE)
  await page.keyboard.press("Escape")
  await expect(dialog(page)).toHaveCount(0)
  expect(state.imports).toEqual([])
  await expect(banner(page)).toHaveCount(0)
})

test("ไฟล์ใช้ไม่ได้ = ข้อความใต้ช่อง dialog ยังเปิด", async ({ page }) => {
  const state = await mockAccount(page)
  await page.goto(`/v/${BBB}`)
  await errorCard(page).getByRole("button", { name: USE }).click()
  await expect(dialog(page)).not.toContainText(INVALID)
  await chooseFile(page, "not a cookie file\n")
  await dialog(page).getByRole("button", { name: "นำเข้าแล้วลองใหม่" }).click()
  await expect(dialog(page)).toContainText(INVALID)
  await expect(dialog(page).getByLabel("cookies.txt")).toHaveAttribute("aria-invalid", "true")
  await expect(dialog(page)).toBeVisible()
  expect(state.imports).toEqual([{ text: "not a cookie file\n", acceptWarning: true }])
})

test("ไฟล์เกิน 1 MB ไม่ถูกส่ง (dialog ใหม่ ยังไม่มีข้อความ error ค้างจากขั้นก่อนหน้า)", async ({ page }) => {
  const state = await mockAccount(page)
  await page.goto(`/v/${BBB}`)
  await errorCard(page).getByRole("button", { name: USE }).click()
  await expect(dialog(page)).not.toContainText(INVALID)
  await expect(dialog(page).getByLabel("cookies.txt")).not.toHaveAttribute("aria-invalid", "true")
  await chooseFile(page, "#".repeat(1_048_577), "big.txt")
  await expect(dialog(page)).toContainText(INVALID)
  await expect(dialog(page).getByLabel("cookies.txt")).toHaveAttribute("aria-invalid", "true")
  await expect(dialog(page).getByRole("button", { name: "นำเข้าแล้วลองใหม่" })).toBeDisabled()
  expect(state.imports).toEqual([])
})

test("นำเข้าไฟล์ที่ใช้ได้: dialog ปิด แถบบนหน้าขึ้น โหลดข้อมูลคลิปใหม่เอง · ลบออกตอนนี้ = toast ค้างไว้ แถบหาย", async ({ page }) => {
  const state = await mockAccount(page)
  await page.goto(`/v/${BBB}`)
  await errorCard(page).getByRole("button", { name: USE }).click()
  await chooseFile(page, GOOD_FILE)
  const calls = state.videoCalls
  await dialog(page).getByRole("button", { name: "นำเข้าแล้วลองใหม่" }).click()
  await expect(dialog(page)).toHaveCount(0)
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Big Buck Bunny")
  expect(state.videoCalls).toBeGreaterThan(calls)
  expect(state.imports).toEqual([{ text: GOOD_FILE, acceptWarning: true }])
  await expect(banner(page)).toContainText(/กำลังใช้บัญชียูทูปชั่วคราว · ลบอัตโนมัติภายใน 2 ชม\./)
  await page.goto("/history") // แถบอยู่ทุกหน้า
  await expect(banner(page)).toBeVisible()
  await banner(page).getByRole("button", { name: "ลบออกตอนนี้" }).click()
  await expect(toast(page, REMOVED)).toBeVisible()
  await expect(banner(page)).toHaveCount(0)
  expect(state.deletes).toBe(1)
  await page.waitForTimeout(5_000) // toast ไม่หายเอง
  await expect(toast(page, REMOVED)).toBeVisible()
})

test("ถือบัญชีอยู่แล้วแต่ยังเปิดไม่ได้: ข้อความ ลองด้วยบัญชีแล้ว… ไม่มีปุ่ม", async ({ page }) => {
  await mockAccount(page, { active: true, code: "E_VIDEO_PRIVATE", message: TRIED_MESSAGE })
  await page.goto(`/v/${BBB}`)
  await expect(errorCard(page)).toContainText(TRIED_MESSAGE)
  await expect(errorCard(page).getByRole("button", { name: USE })).toHaveCount(0)
  await expect(banner(page)).toBeVisible()
})

for (const scheme of ["light", "dark"] as const) {
  test(`axe ${scheme}: dialog และแถบบนหน้า ไม่มีปัญหาระดับ serious/critical`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme })
    await mockAccount(page)
    await page.goto(`/v/${BBB}`)
    await expect(page.locator("html")).toHaveClass(scheme === "dark" ? /dark/ : /light/)
    await errorCard(page).getByRole("button", { name: USE }).click()
    await expect(dialog(page)).toBeVisible()
    expect(await seriousViolations(page)).toEqual([])
    await chooseFile(page, GOOD_FILE)
    await dialog(page).getByRole("button", { name: "นำเข้าแล้วลองใหม่" }).click()
    await expect(banner(page)).toBeVisible()
    expect(await seriousViolations(page)).toEqual([])
  })
}

test("หน้าต่างแคบ 640 px: dialog และแถบบนหน้าไม่เลื่อนซ้ายขวา", async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 720 })
  await mockAccount(page)
  await page.goto(`/v/${BBB}`)
  await errorCard(page).getByRole("button", { name: USE }).click()
  await expect(dialog(page)).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(640)
  await chooseFile(page, GOOD_FILE)
  await dialog(page).getByRole("button", { name: "นำเข้าแล้วลองใหม่" }).click()
  await expect(banner(page)).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(640)
})
