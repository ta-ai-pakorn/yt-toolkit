import { analyzeSettled } from "./axe-settled"
import { expect, test } from "@playwright/test"

test("AC-SET-02: ไม่มี ffmpeg → แสดงใช้ไม่ได้พร้อมปุ่มโหลดใหม่", async ({ page }) => {
  await page.goto("/settings/health")
  const row = page.getByTestId("tool-ffmpeg")
  await expect(row).toContainText("ใช้ไม่ได้", { timeout: 15_000 })
  await expect(row.getByRole("button", { name: "โหลด ffmpeg ใหม่" })).toBeVisible()
})

test("ตัวช่วยของ yt-dlp เป็น deno", async ({ page }) => {
  await page.goto("/settings/health")
  await expect(page.getByTestId("tool-jsRuntime")).toContainText("deno", { timeout: 15_000 })
})

test("โหมดข้อมูลปลอม (E2E รัน serve + YT_TOOLKIT_FAKE=1) → หน้าตรวจสุขภาพบอกไว้", async ({ page }) => {
  await page.goto("/settings/health")
  const banner = page.getByTestId("fake-mode")
  await expect(banner).toContainText("โหมดข้อมูลปลอม", { timeout: 15_000 })
  await expect(banner).toHaveAttribute("role", "status")
})

test("ไม่ใช่โหมดข้อมูลปลอม → ไม่มีแถบบอก", async ({ page }) => {
  await page.route("**/api/health", async (route) => {
    const response = await route.fetch()
    const body = await response.json()
    delete body.mode
    await route.fulfill({ response, json: body })
  })
  await page.goto("/settings/health")
  await expect(page.getByTestId("tool-ffmpeg")).toBeVisible({ timeout: 15_000 })
  await expect(page.getByTestId("fake-mode")).toHaveCount(0)
})

test("owner round 3: แถว 'ทำงานแบบเบราว์เซอร์ (curl_cffi)' พร้อมใช้ บอกเวอร์ชัน ไม่มีข้อมูลคุกกี้", async ({ page }) => {
  await page.goto("/settings/health")
  const row = page.getByTestId("tool-impersonation")
  await expect(row).toContainText("ทำงานแบบเบราว์เซอร์ (curl_cffi)", { timeout: 15_000 })
  await expect(row).toContainText("พร้อม")
  await expect(row).toContainText(/\d+\.\d+/)
  await expect(page.getByText(/cookie|คุกกี้|VISITOR/i)).toHaveCount(0)
})

test("backend รุ่นก่อนที่ไม่มีแถว impersonation → หน้าตรวจสุขภาพยังแสดงแถวอื่นครบ", async ({ page }) => {
  await page.route("**/api/health", async (route) => {
    const response = await route.fetch()
    const body = await response.json()
    delete body.tools.impersonation
    await route.fulfill({ response, json: body })
  })
  await page.goto("/settings/health")
  await expect(page.getByTestId("tool-network")).toBeVisible({ timeout: 15_000 })
  await expect(page.getByTestId("tool-impersonation")).toHaveCount(0)
})

test("แท็บเกี่ยวกับแสดงเวอร์ชัน", async ({ page }) => {
  await page.goto("/settings/about")
  await expect(page.getByText(/\d+\.\d+\.\d+/)).toBeVisible()
})

const INSTALL = "**/api/tools/ffmpeg/install"

test("ติดตั้ง ffmpeg แล้ว backend ตอบสถานะไม่ผ่าน → แจ้งข้อความผิดพลาด ไม่ใช่สำเร็จ", async ({ page }) => {
  await page.route(INSTALL, (route) =>
    route.fulfill({
      json: { status: "error", name: "ffmpeg", version: null, message: "ตรวจไฟล์ที่โหลดมาไม่ผ่าน", path: null },
    }),
  )
  await page.goto("/settings/health")
  await page.getByRole("button", { name: "โหลด ffmpeg ใหม่" }).click()
  await expect(page.getByText("ตรวจไฟล์ที่โหลดมาไม่ผ่าน")).toBeVisible()
  await expect(page.getByText("ติดตั้ง ffmpeg แล้ว")).toHaveCount(0)
})

test("ติดตั้ง ffmpeg แล้ว backend ตอบสถานะพร้อม → แจ้งติดตั้งแล้ว", async ({ page }) => {
  await page.route(INSTALL, (route) =>
    route.fulfill({ json: { status: "ok", name: "ffmpeg", version: "7.0", message: null, path: null } }),
  )
  await page.goto("/settings/health")
  await page.getByRole("button", { name: "โหลด ffmpeg ใหม่" }).click()
  await expect(page.getByText("ติดตั้ง ffmpeg แล้ว")).toBeVisible()
})

test("ติดตั้ง ffmpeg ซ้ำตอนกำลังโหลดอยู่ (สถานะเตือน) → แจ้งข้อมูล ไม่ใช่ error และหายเอง", async ({ page }) => {
  await page.route(INSTALL, (route) =>
    route.fulfill({
      json: { status: "warn", name: "ffmpeg", version: null, message: "กำลังโหลดอยู่แล้ว รอสักครู่", path: null },
    }),
  )
  await page.goto("/settings/health")
  await page.getByRole("button", { name: "โหลด ffmpeg ใหม่" }).click()
  const toast = page.locator("[data-sonner-toast]", { hasText: "กำลังโหลดอยู่แล้ว รอสักครู่" })
  await expect(toast).toBeVisible()
  await expect(toast).toHaveAttribute("data-type", "info")
  await expect(page.getByText("ติดตั้ง ffmpeg แล้ว")).toHaveCount(0)
  // ไม่ค้างถาวร: sonner ปิดเองหลังราว 4 วินาที
  await expect(toast).toHaveCount(0, { timeout: 10_000 })
})

test("ปิดโปรแกรม: ปุ่มหมุนระหว่างรอ แล้วขึ้นหน้าปิดแล้ว และไม่เหลือแจ้งเตือนค้าง", async ({ page }) => {
  await page.route("**/api/tools/ffmpeg/install", (route) =>
    route.fulfill({ json: { status: "error", name: "ffmpeg", version: null, message: "แจ้งเตือนเก่า", path: null } }),
  )
  await page.route("**/api/shutdown", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 500))
    await route.fulfill({ json: { ok: true } })
  })
  await page.goto("/settings/health")
  await page.getByRole("button", { name: "โหลด ffmpeg ใหม่" }).click()
  await expect(page.getByText("แจ้งเตือนเก่า")).toBeVisible()
  await page.getByRole("button", { name: "ปิดโปรแกรม" }).click()
  await expect(page.getByRole("button", { name: "ปิดโปรแกรม" }).getByRole("status", { name: "กำลังโหลด" })).toBeVisible()
  await expect(page.getByText("ปิดโปรแกรมแล้ว")).toBeVisible()
  await expect(page.getByText("แจ้งเตือนเก่า")).toHaveCount(0)
})

test("M5 รอบ C: แถว บัญชียูทูป บอกสถานะอย่างเดียว · ไม่ได้ใช้บัญชี", async ({ page }) => {
  await page.goto("/settings/health")
  const row = page.getByTestId("tool-account")
  await expect(row).toContainText("บัญชียูทูป", { timeout: 15_000 })
  await expect(row).toContainText("ไม่ได้ใช้บัญชี")
  await expect(row).toContainText("พร้อม")
})

test("M5 รอบ C: ใช้บัญชีอยู่ = ใช้บัญชีชั่วคราวอยู่ (นำเข้าเมื่อ HH:MM) · backend รุ่นก่อนไม่มีแถวนี้", async ({ page }) => {
  let withRow = true
  await page.route("**/api/health", async (route) => {
    const response = await route.fetch()
    const body = await response.json()
    if (withRow) body.account = { status: "ok", active: true, importedAt: "2026-10-06T02:05:00Z" }
    else delete body.account
    await route.fulfill({ response, json: body })
  })
  await page.goto("/settings/health")
  await expect(page.getByTestId("tool-account")).toContainText(/ใช้บัญชีชั่วคราวอยู่ \(นำเข้าเมื่อ \d{2}:\d{2}\)/, {
    timeout: 15_000,
  })
  withRow = false
  await page.reload()
  await expect(page.getByTestId("tool-network")).toBeVisible({ timeout: 15_000 })
  await expect(page.getByTestId("tool-account")).toHaveCount(0)
})

// M6 D1 T1 (spec 1.3): สีของแถวเตือน (warn) และใช้ไม่ได้ (error) ต้องผ่าน axe ทั้งสองธีม · ตอบ /api/health จริงแล้วแก้สองแถวให้เป็นสถานะนั้น
for (const scheme of ["light", "dark"] as const) {
  test(`axe: หน้าตรวจสุขภาพที่มีแถวเตือนและใช้ไม่ได้ ไม่มีปัญหาระดับ serious/critical (${scheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme })
    await page.route("**/api/health", async (route) => {
      const response = await route.fetch()
      const body = await response.json()
      body.tools.ffmpeg = { ...body.tools.ffmpeg, status: "error", version: null, message: "หาโปรแกรมไม่เจอ" }
      body.disk = { ...body.disk, status: "warn", message: "พื้นที่เหลือน้อย" }
      await route.fulfill({ response, json: body })
    })
    await page.goto("/settings/health")
    await expect(page.getByTestId("tool-ffmpeg")).toContainText("ใช้ไม่ได้", { timeout: 15_000 })
    await expect(page.getByTestId("tool-disk")).toContainText("เตือน")
    await expect(page.locator("html")).toHaveClass(scheme === "dark" ? /dark/ : /light/)
    const results = await analyzeSettled(page)
    const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical")
    expect(serious.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target.join(" ")).slice(0, 5) }))).toEqual([])
  })
}
