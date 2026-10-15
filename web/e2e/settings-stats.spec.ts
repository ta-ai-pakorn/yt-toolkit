import { analyzeSettled } from "./axe-settled"
import { expect, test, type Page } from "@playwright/test"

// M6 รอบ C: แท็บสถิติของฉัน (AC-STAT-02 ฝั่งเบราว์เซอร์, AC-STAT-04, การล้าง) · /api/stats* ถูก mock ทั้งหมด ไม่เขียน backend

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
const EMPTY = { since: null, clips: 0, files: 0, totalBytes: 0, byKind: [], byMonth: [] }
const SINCE = "2026-10-15T05:00:00+00:00"

async function stubStats(page: Page, first: object, opts: { failReset?: boolean } = {}) {
  const calls = { get: 0, reset: 0 }
  let current = first
  await page.route("**/api/stats", (route) => {
    calls.get += 1
    return route.fulfill({ json: current })
  })
  await page.route("**/api/stats/reset", async (route) => {
    calls.reset += 1
    if (opts.failReset) return route.fulfill({ status: 500, json: { error: { code: "E_UNKNOWN", message: "พัง" } } })
    await new Promise((r) => setTimeout(r, 300)) // ช้าพอให้กดซ้ำได้ถ้าปุ่มไม่ล็อก
    current = { ...EMPTY, since: SINCE }
    return route.fulfill({ json: { since: SINCE } })
  })
  return calls
}

const toast = (page: Page, text: string) => page.locator("[data-sonner-toast]", { hasText: text })

async function seriousViolations(page: Page) {
  const results = await analyzeSettled(page)
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target.join(" ")).slice(0, 5) }))
}

test("แท็บสถิติอยู่ระหว่างขั้นสูงกับตรวจสุขภาพระบบ และเปิดที่ /settings/stats", async ({ page }) => {
  await stubStats(page, FILLED)
  await page.goto("/settings/stats")
  await expect(page.getByRole("tab")).toHaveText(["ทั่วไป", "ขั้นสูง", "สถิติของฉัน", "ตรวจสุขภาพระบบ", "เกี่ยวกับ"])
  await expect(page.getByRole("tab", { name: "สถิติของฉัน" })).toHaveAttribute("aria-selected", "true")
})

test("AC-STAT-02: เปิดแท็บแล้วทุกคำขอไปที่เครื่องนี้เท่านั้น", async ({ page, baseURL }) => {
  const origins = new Set<string>()
  page.on("request", (request) => origins.add(new URL(request.url()).origin))
  await stubStats(page, FILLED)
  await page.goto("/settings/stats")
  await expect(page.getByText("คำนวณในเครื่องนี้เท่านั้น ไม่ส่งไปที่ไหน")).toBeVisible()
  await page.waitForLoadState("networkidle")
  expect([...origins]).toEqual([new URL(baseURL!).origin])
  expect(new URL(baseURL!).hostname).toBe("127.0.0.1")
})

test("ตัวเลข 4 ช่องและตารางรายเดือน", async ({ page }) => {
  await stubStats(page, FILLED)
  await page.goto("/settings/stats")
  const tiles = page.getByTestId("stats-tiles")
  await expect(tiles).toContainText("คลิป")
  await expect(tiles).toContainText("3")
  await expect(tiles).toContainText("1.4 GB")
  await expect(tiles).toContainText("วิดีโอ")
  await expect(tiles).toContainText("3 ไฟล์")
  const rows = page.getByRole("table").getByRole("row")
  await expect(rows.nth(0)).toHaveText(/เดือน.*คลิป.*ไฟล์.*ขนาด/)
  await expect(rows.nth(1)).toContainText("ตุลาคม 2569")
  await expect(rows.nth(2)).toContainText("กันยายน 2569")
  await expect(rows.nth(2)).toContainText("200 MB")
})

test("นับได้แต่ไม่มีเดือนในหน้าต่าง 12 เดือน = มีตัวเลข ไม่มีตาราง", async ({ page }) => {
  await stubStats(page, { ...FILLED, byMonth: [] })
  await page.goto("/settings/stats")
  await expect(page.getByTestId("stats-tiles")).toContainText("1.4 GB")
  await expect(page.getByRole("table")).toHaveCount(0)
})

test("AC-STAT-04: ไม่มีงานที่เสร็จ = ยังไม่มีสถิติ ไม่มีปุ่มล้าง", async ({ page }) => {
  await stubStats(page, EMPTY)
  await page.goto("/settings/stats")
  await expect(page.getByText("ยังไม่มีสถิติ")).toBeVisible()
  await expect(page.getByRole("table")).toHaveCount(0)
  await expect(page.getByRole("button", { name: "ล้างสถิติ" })).toHaveCount(0)
  await expect(page.getByText(/^นับตั้งแต่/)).toHaveCount(0)
})

test("ล้างสถิติ: ยกเลิกแล้วตัวเลขยังอยู่ · ยืนยันแล้ว POST ครั้งเดียว ขึ้น toast และนับตั้งแต่", async ({ page }) => {
  const calls = await stubStats(page, FILLED)
  await page.goto("/settings/stats")
  await page.getByRole("button", { name: "ล้างสถิติ" }).click()
  const dialog = page.getByRole("alertdialog")
  await expect(dialog).toContainText("เริ่มนับสถิติใหม่?")
  await expect(dialog).toContainText("ประวัติและไฟล์ที่โหลดไว้ยังอยู่ครบ")
  await dialog.getByRole("button", { name: "ยกเลิก" }).click()
  await expect(page.getByTestId("stats-tiles")).toBeVisible()
  expect(calls.reset).toBe(0)

  await expect(page.getByRole("alertdialog")).toHaveCount(0)
  await page.getByRole("tabpanel").getByRole("button", { name: "ล้างสถิติ" }).click()
  const confirm = page.getByRole("alertdialog").getByRole("button", { name: "ล้างสถิติ" })
  // กดสองครั้งติดกันก่อน React วาดใหม่ (isPending/disabled ยังเป็นค่าเก่า) = ต้องยิง POST ครั้งเดียว
  await confirm.evaluate((el: HTMLElement) => {
    el.click()
    el.click()
  })
  await expect(toast(page, "ล้างสถิติแล้ว")).toBeVisible()
  expect(calls.reset).toBe(1)
  await expect(page.getByText("ยังไม่มีสถิติ")).toBeVisible()
  await expect(page.getByText("นับตั้งแต่ 15 ตุลาคม 2569")).toBeVisible()
})

test("ล้างสถิติไม่สำเร็จ = toast error มีปุ่มคัดลอก ตัวเลขเดิมยังอยู่", async ({ page }) => {
  await stubStats(page, FILLED, { failReset: true })
  await page.goto("/settings/stats")
  await page.getByRole("button", { name: "ล้างสถิติ" }).click()
  await page.getByRole("alertdialog").getByRole("button", { name: "ล้างสถิติ" }).click()
  await expect(page.locator("[data-sonner-toast]").getByRole("button", { name: "คัดลอกข้อมูลแจ้งปัญหา" })).toBeVisible()
  await expect(page.getByTestId("stats-tiles")).toContainText("1.4 GB")
})

test("โหลดสถิติไม่สำเร็จ = ส่วนรายละเอียด error มีปุ่มคัดลอก", async ({ page }) => {
  await page.route("**/api/stats", (route) =>
    route.fulfill({ status: 500, json: { error: { code: "E_UNKNOWN", message: "พัง" } } })
  )
  await page.goto("/settings/stats")
  await expect(page.getByTestId("error-details")).toBeVisible()
  await expect(page.getByRole("button", { name: "คัดลอกข้อมูลแจ้งปัญหา" })).toBeVisible()
})

for (const scheme of ["dark", "light"] as const) {
  test(`axe: แท็บสถิติไม่มีปัญหาระดับ serious/critical (${scheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme })
    await stubStats(page, { ...FILLED, since: SINCE })
    await page.goto("/settings/stats")
    await expect(page.getByRole("table")).toBeVisible()
    expect(await seriousViolations(page)).toEqual([])
  })
}

test("จอ 640 × 800: แท็บสถิติไม่ล้นแนวนอน", async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 800 })
  await stubStats(page, { ...FILLED, since: SINCE })
  await page.goto("/settings/stats")
  await expect(page.getByRole("table")).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(640)
})
