import { colorsOf, contrastRatio, focusRingContrast, textContrast } from "./contrast"
import { expect, test, type Page } from "@playwright/test"

// M6 D1 T1: ขอบโฟกัส (WCAG 2.2 non-text contrast) ต้องต่างจากพื้นหลังอย่างน้อย 3:1 ทั้งธีมสว่างและมืด
// อ่านสีขอบจาก box-shadow ที่คำนวณแล้ว เทียบกับพื้นทึบที่อยู่ข้างหลัง · /api/stats ถูก mock ไม่เขียน backend

const FILLED = {
  since: null,
  clips: 3,
  files: 5,
  totalBytes: 1_400_000_000,
  byKind: [
    { kind: "video", files: 3, bytes: 1_300_000_000 },
    { kind: "audio", files: 2, bytes: 100_000_000 },
  ],
  byMonth: [
    { month: "2026-10", clips: 2, files: 3, bytes: 1_200_000_000 },
    { month: "2026-09", clips: 1, files: 2, bytes: 200_000_000 },
  ],
}

const MIN = 3

async function themed(page: Page, scheme: "light" | "dark", url: string) {
  await page.emulateMedia({ colorScheme: scheme })
  await page.goto(url)
  await expect(page.locator("html")).toHaveClass(scheme === "dark" ? /dark/ : /light/)
}

test("contrastRatio: ดำบนขาว = 21", () => {
  expect(contrastRatio("rgb(0,0,0)", "rgb(255,255,255)")).toBeCloseTo(21, 5)
})

for (const scheme of ["light", "dark"] as const) {
  test.describe(`ขอบโฟกัส ≥ 3:1 (${scheme})`, () => {
    test("W1: ช่องวางลิงก์และปุ่มวาง", async ({ page }) => {
      await themed(page, scheme, "/")
      // วงขอบของช่องวางลิงก์ถูกวาดบนกรอบ InputGroup ไม่ใช่บน textarea เอง
      expect(await focusRingContrast(page, page.getByRole("textbox"), page.locator('[data-slot="input-group"]'))).toBeGreaterThanOrEqual(MIN)
      expect(await focusRingContrast(page, page.getByRole("button", { name: "วาง", exact: true }))).toBeGreaterThanOrEqual(MIN)
    })

    test("ตั้งค่าทั่วไป: ปุ่มเลือก (Select) และตัวเลือกในรายการ", async ({ page }) => {
      await themed(page, scheme, "/settings/general")
      const trigger = page.getByRole("combobox").first()
      await expect(trigger).toBeVisible()
      expect(await focusRingContrast(page, trigger)).toBeGreaterThanOrEqual(MIN)
      await page.keyboard.press("Enter")
      const popup = page.getByRole("listbox")
      await expect(popup).toBeVisible()
      // ตัวเลือกที่โฟกัสด้วยคีย์บอร์ดมีขอบในตัวเลือก (inset) บนพื้นรายการ ไม่ใช่แค่พื้นไฮไลต์
      const option = page.locator('[role="option"][data-highlighted]').first()
      await expect(option).toBeVisible()
      await expect(option).toBeFocused()
      const { ring, bg } = await colorsOf(option)
      expect(contrastRatio(ring, bg)).toBeGreaterThanOrEqual(MIN)
    })

    test("สถิติ: ปุ่มล้างสถิติและปุ่มยกเลิกในกล่องยืนยัน", async ({ page }) => {
      await page.route("**/api/stats", (route) => route.fulfill({ json: FILLED }))
      await themed(page, scheme, "/settings/stats")
      const clear = page.getByRole("tabpanel").getByRole("button", { name: "ล้างสถิติ" })
      await expect(clear).toBeVisible()
      expect(await focusRingContrast(page, clear)).toBeGreaterThanOrEqual(MIN)
      await page.keyboard.press("Enter")
      const dialog = page.getByRole("alertdialog")
      await expect(dialog).toBeVisible()
      expect(await focusRingContrast(page, dialog.getByRole("button", { name: "ยกเลิก" }))).toBeGreaterThanOrEqual(MIN)
    })

    test("ตั้งค่า: แท็บ", async ({ page }) => {
      await page.route("**/api/stats", (route) => route.fulfill({ json: FILLED }))
      await themed(page, scheme, "/settings/stats")
      const tab = page.getByRole("tab", { name: "ขั้นสูง" })
      await expect(tab).toBeVisible()
      expect(await focusRingContrast(page, tab)).toBeGreaterThanOrEqual(MIN)
    })

    test("ประวัติ: ช่องค้นหา (วงขอบอยู่ที่กรอบ InputGroup)", async ({ page }) => {
      await page.route("**/api/history*", (route) =>
        route.fulfill({
          json: {
            items: [{ videoId: "jNQXAC9IVRw", title: "Me at the zoo", channel: "", thumbnailUrl: "", durationS: 19, outputs: [], lastAt: new Date().toISOString() }],
            total: 1,
          },
        }),
      )
      await themed(page, scheme, "/history")
      const input = page.getByRole("textbox")
      await expect(input).toBeVisible()
      expect(await focusRingContrast(page, input, page.locator('[data-slot="input-group"]'))).toBeGreaterThanOrEqual(MIN)
    })

    test("ในการ์ด (แท็บซับ): ปุ่มปรับเอง และปุ่มเลื่อนค่า (slider)", async ({ page }) => {
      await themed(page, scheme, "/v/88o5Sk8_m1Y?tab=subs")
      const custom = page.getByRole("button", { name: "ปรับเอง" })
      await expect(custom).toBeVisible()
      await expect(custom.locator('xpath=ancestor::*[@data-slot="card"]')).toHaveCount(1)
      expect(await focusRingContrast(page, custom)).toBeGreaterThanOrEqual(MIN)
      await page.keyboard.press("Enter")
      const slider = page.getByRole("slider").first()
      await expect(slider).toBeVisible()
      expect(await focusRingContrast(page, slider, page.locator('[data-slot="slider-thumb"]').first())).toBeGreaterThanOrEqual(MIN)
    })

    test("ปุ่มสีแดง (destructive) ในกล่องยืนยันปิดโปรแกรม: วงขอบ ≥ 3:1 และตัวอักษร ≥ 4.5:1", async ({ page }) => {
      await page.route("**/api/shutdown", (route) =>
        route.fulfill({ status: 409, json: { error: { code: "E_JOBS_PENDING", message: "มีงานค้าง", detail: null }, pendingJobs: 4 } }),
      )
      await themed(page, scheme, "/settings/health")
      await page.getByRole("button", { name: "ปิดโปรแกรม" }).focus()
      await page.keyboard.press("Enter")
      const dialog = page.getByRole("alertdialog", { name: "ปิดโปรแกรมตอนนี้?" })
      await expect(dialog).toBeVisible()
      const danger = dialog.getByRole("button", { name: "ปิดเลย" })
      expect(await focusRingContrast(page, danger)).toBeGreaterThanOrEqual(MIN)
      expect(await textContrast(danger)).toBeGreaterThanOrEqual(4.5)
    })
  })
}
