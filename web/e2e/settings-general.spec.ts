import os from "node:os"
import path from "node:path"

import AxeBuilder from "@axe-core/playwright"
import { expect, test, type APIRequestContext, type Page } from "@playwright/test"

// W6 แท็บทั่วไป (M4 T17) · ใช้ backend ตัวเดียวกับ spec อื่นใน project chromium
// spec นี้แก้เฉพาะการตั้งค่า (PATCH /api/settings) ไม่สร้างงาน และคืนค่าเดิมใน afterAll
test.describe.configure({ mode: "serial" })

const KEYS = ["outputDir", "concurrency", "audioLanguage", "videoDefault", "audioDefault"] as const
type Original = Record<(typeof KEYS)[number], unknown>

let original: Original

async function readSettings(request: APIRequestContext): Promise<Original> {
  const response = await request.get("/api/settings")
  expect(response.ok()).toBe(true)
  const all = (await response.json()) as Record<string, unknown>
  return Object.fromEntries(KEYS.map((key) => [key, all[key]])) as Original
}

async function writeSettings(request: APIRequestContext, data: Partial<Original>) {
  const page = await request.get("/")
  const match = /<meta name="yt-token" content="([^"]+)"/.exec(await page.text())
  if (!match) throw new Error("อ่าน token จากหน้าแรกไม่ได้")
  const response = await request.fetch("/api/settings", {
    method: "PATCH",
    headers: { "X-Toolkit-Token": match[1], Origin: new URL(page.url()).origin },
    data,
  })
  expect(response.ok(), `PATCH /api/settings ตอบ ${response.status()}`).toBe(true)
}

test.beforeAll(async ({ request }) => {
  original = await readSettings(request)
})

test.afterAll(async ({ request }) => {
  await writeSettings(request, original)
})

// ทุกเทสเริ่มจากค่าเดิมของเครื่องเทส (ยกเว้นพื้นฐานที่เทสต้องรู้: จำนวนงานพร้อมกัน = 2)
test.beforeEach(async ({ request }) => {
  await writeSettings(request, { ...original, concurrency: 2 })
})

const saved = (page: Page) => page.locator("[data-sonner-toast]", { hasText: "บันทึกแล้ว" })

async function seriousViolations(page: Page) {
  const results = await new AxeBuilder({ page }).analyze()
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.map((n) => n.target.join(" ")).slice(0, 5) }))
}

test("/settings เปิดที่แท็บทั่วไป พร้อมห้าช่อง", async ({ page }) => {
  await page.goto("/settings")
  await expect(page.getByRole("tab", { name: "ทั่วไป" })).toHaveAttribute("aria-selected", "true")
  await expect(page.getByLabel("โฟลเดอร์ผลลัพธ์")).toBeVisible()
  await expect(page.getByRole("button", { name: "เปิดโฟลเดอร์" })).toBeVisible()
  await expect(page.getByRole("group", { name: "จำนวนงานพร้อมกัน" })).toBeVisible()
  await expect(page.getByRole("combobox", { name: "ภาษาเสียงเริ่มต้น" })).toBeVisible()
  await expect(page.getByRole("combobox", { name: "คุณภาพวิดีโอเริ่มต้น" })).toBeVisible()
  await expect(page.getByRole("group", { name: "รูปแบบเสียงเริ่มต้น" })).toBeVisible()
  // ไม่มีปุ่มบันทึก: ทุกช่องบันทึกเมื่อเปลี่ยน
  await expect(page.getByRole("button", { name: /^บันทึก/ })).toHaveCount(0)
})

test("AC-SET-01 E: เปลี่ยนจำนวนงานพร้อมกันเป็น 1 → แจ้งบันทึกแล้ว และโหลดหน้าใหม่ยังเป็น 1", async ({ page }) => {
  await page.goto("/settings/general")
  const group = page.getByRole("group", { name: "จำนวนงานพร้อมกัน" })
  await expect(group.getByRole("button", { name: "2", exact: true })).toHaveAttribute("aria-pressed", "true")
  await group.getByRole("button", { name: "1", exact: true }).click()
  await expect(saved(page)).toBeVisible()
  await expect(group.getByRole("button", { name: "1", exact: true })).toHaveAttribute("aria-pressed", "true")
  await page.reload()
  await expect(
    page.getByRole("group", { name: "จำนวนงานพร้อมกัน" }).getByRole("button", { name: "1", exact: true })
  ).toHaveAttribute("aria-pressed", "true")
})

test("โฟลเดอร์ผลลัพธ์: ที่อยู่เต็ม + Enter → บันทึกแล้ว โหลดหน้าใหม่ยังอยู่", async ({ page }) => {
  const target = path.join(os.tmpdir(), "yt-toolkit-e2e-general-out")
  await page.goto("/settings/general")
  const input = page.getByLabel("โฟลเดอร์ผลลัพธ์")
  await input.fill(target)
  await input.press("Enter")
  await expect(saved(page)).toBeVisible()
  await page.reload()
  await expect(page.getByLabel("โฟลเดอร์ผลลัพธ์")).toHaveValue(target)
})

test("โฟลเดอร์ผลลัพธ์: ที่อยู่ไม่เต็ม (abc) → ข้อความจากเซิร์ฟเวอร์ใต้ช่อง และโหลดหน้าใหม่ค่าเดิมไม่เปลี่ยน", async ({
  page,
}) => {
  await page.goto("/settings/general")
  const input = page.getByLabel("โฟลเดอร์ผลลัพธ์")
  await expect(input).toHaveValue(String(original.outputDir))
  await input.fill("abc")
  await input.press("Enter")
  const message = page.getByText("ใส่ที่อยู่โฟลเดอร์แบบเต็ม", { exact: false })
  await expect(message).toBeVisible()
  await expect(input).toHaveAttribute("aria-invalid", "true")
  await expect(saved(page)).toHaveCount(0)
  await page.reload()
  await expect(page.getByLabel("โฟลเดอร์ผลลัพธ์")).toHaveValue(String(original.outputDir))
  await expect(message).toHaveCount(0)
})

test("โฟลเดอร์ผลลัพธ์: ออกจากช่องโดยไม่แก้ไม่ส่งอะไร · Esc คืนค่าที่บันทึกไว้", async ({ page }) => {
  let patches = 0
  await page.route("**/api/settings", (route) => {
    if (route.request().method() === "PATCH") patches += 1
    return route.continue()
  })
  await page.goto("/settings/general")
  const input = page.getByLabel("โฟลเดอร์ผลลัพธ์")
  await input.focus()
  await input.blur()
  await input.fill("abc")
  await input.press("Escape")
  await expect(input).toHaveValue(String(original.outputDir))
  await input.blur()
  expect(patches).toBe(0)
})

test("เปิดโฟลเดอร์ → ไม่มีข้อความผิดพลาด (โหมดข้อมูลปลอมไม่เปิดโฟลเดอร์จริง)", async ({ page }) => {
  await page.goto("/settings/general")
  const opened = page.waitForResponse(
    (response) => response.url().endsWith("/api/settings/open-output") && response.request().method() === "POST"
  )
  await page.getByRole("button", { name: "เปิดโฟลเดอร์" }).click()
  expect((await opened).ok()).toBe(true)
  await expect(page.locator('[data-sonner-toast][data-type="error"]')).toHaveCount(0)
})

test("คุณภาพวิดีโอเริ่มต้นและรูปแบบเสียงเริ่มต้น เปลี่ยนแล้วบันทึกและคงอยู่", async ({ page }) => {
  await page.goto("/settings/general")
  await page.getByRole("combobox", { name: "คุณภาพวิดีโอเริ่มต้น" }).click()
  await page.getByRole("option", { name: "เปิดได้ทุกที่ 720p" }).click()
  await expect(saved(page)).toBeVisible()
  await page.getByRole("group", { name: "รูปแบบเสียงเริ่มต้น" }).getByRole("button", { name: "wav" }).click()
  await page.getByRole("combobox", { name: "ภาษาเสียงเริ่มต้น" }).click()
  await page.getByRole("option", { name: "ไทย", exact: true }).click()
  await page.reload()
  await expect(page.getByRole("combobox", { name: "คุณภาพวิดีโอเริ่มต้น" })).toContainText("เปิดได้ทุกที่ 720p")
  await expect(page.getByRole("combobox", { name: "ภาษาเสียงเริ่มต้น" })).toContainText("ไทย")
  await expect(
    page.getByRole("group", { name: "รูปแบบเสียงเริ่มต้น" }).getByRole("button", { name: "wav" })
  ).toHaveAttribute("aria-pressed", "true")
})

test("โหลดค่าตั้งไม่สำเร็จ → แจ้งพร้อมปุ่มลองใหม่ แล้วแสดงช่องเมื่อโหลดได้", async ({ page }) => {
  let fail = true
  await page.route("**/api/settings", (route) => {
    if (route.request().method() === "GET" && fail) {
      return route.fulfill({
        status: 500,
        json: { error: { code: "E_UNKNOWN", message: "มีบางอย่างผิดพลาด ถ่ายภาพหน้าจอนี้ส่งให้ผู้ดูแล", detail: null } },
      })
    }
    return route.continue()
  })
  await page.goto("/settings/general")
  await expect(page.getByText("โหลดค่าตั้งไม่สำเร็จ")).toBeVisible()
  fail = false
  await page.getByRole("button", { name: "ลองใหม่" }).click()
  await expect(page.getByLabel("โฟลเดอร์ผลลัพธ์")).toBeVisible()
})

for (const scheme of ["dark", "light"] as const) {
  test(`axe: แท็บทั่วไปไม่มีปัญหาระดับ serious/critical (${scheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme })
    await page.goto("/settings/general")
    await expect(page.getByLabel("โฟลเดอร์ผลลัพธ์")).toBeVisible()
    await expect(page.locator("html")).toHaveClass(scheme === "dark" ? /dark/ : /light/)
    expect(await seriousViolations(page)).toEqual([])
  })
}

test("หน้าต่างแคบ 640 × 800: ไม่เลื่อนซ้ายขวา", async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 800 })
  await page.goto("/settings/general")
  await expect(page.getByLabel("โฟลเดอร์ผลลัพธ์")).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(640)
})
