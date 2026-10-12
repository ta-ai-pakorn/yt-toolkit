/// <reference lib="dom" />
import { analyzeSettled } from "./axe-settled"
import { expect, test, type Page } from "@playwright/test"

// M6 รอบ B (AC-SET-05): ส่วน "ดูรายละเอียด" และปุ่ม "คัดลอกข้อมูลแจ้งปัญหา" (spec 6.4)
// โปรเจกต์ chromium ห้ามสร้างงานจริง: error ที่ทดสอบมาจาก page.route ทั้งหมด (POST /api/jobs ก็ mock)
// มีแค่ POST /api/diagnostics ที่ไปถึง backend จริงในโหมดข้อมูลปลอม (รายงานจริง)

const BBB = "aqz-KE-bpKQ"
const COPY = "คัดลอกข้อมูลแจ้งปัญหา"
const COPIED = "คัดลอกแล้ว"
const REFUSED = "ยูทูปไม่ยอมส่งไฟล์ของคลิปนี้ตอนนี้ ลองใหม่ภายหลัง"
const UNKNOWN = 'มีบางอย่างผิดพลาด กด "คัดลอกข้อมูลแจ้งปัญหา" แล้วส่งให้ผู้ดูแล'
const DETAIL = "ERROR: [youtube] aqz-KE-bpKQ: HTTP Error 403: Forbidden"
// ทุกรายงานเรียก node / ffmpeg --version ฝั่งเซิร์ฟเวอร์: ตอนรันเต็มชุด 4 workers เครื่องหน่วง ใช้เกิน 5 วินาทีได้
// (เหมือนหน้าตรวจสุขภาพที่รอ 15 วินาที) จึงรอ toast หลังกดคัดลอกนานเท่ากัน
const REPORT = { timeout: 15_000 }

const toast = (page: Page, text: string) => page.locator("[data-sonner-toast]").filter({ hasText: text })
const errorCard = (page: Page) => page.getByRole("alert").filter({ hasText: "เปิดข้อมูลคลิปไม่สำเร็จ" })
// Chromium บน Windows เก็บ text/plain ในคลิปบอร์ดเป็น CRLF (Notepad / LINE อ่านได้ปกติ) เทสเทียบแบบ LF
const clipboardText = async (page: Page) =>
  (await page.evaluate(() => navigator.clipboard.readText())).replace(/\r\n/g, "\n")

test.beforeEach(async ({ context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"])
})

/** ข้อมูลคลิปตอบ error (GET /api/videos/<id> เท่านั้น) */
async function failVideo(page: Page, status: number, code: string, message: string, detail: string | null) {
  await page.route(`**/api/videos/${BBB}`, (route) =>
    route.request().method() === "GET"
      ? route.fulfill({ status, json: { error: { code, message, detail } } })
      : route.fallback(),
  )
}

/** body ของ POST /api/diagnostics ทุกครั้งที่หน้าเว็บส่ง */
function diagnosticsBodies(page: Page): unknown[] {
  const bodies: unknown[] = []
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/api/diagnostics" && request.method() === "POST") {
      bodies.push(request.postDataJSON())
    }
  })
  return bodies
}

/** axe ระดับ serious/critical · include = ตรวจเฉพาะส่วนนั้น (หน้าตรวจสุขภาพ: แถวปุ่มที่รอบนี้เพิ่มปุ่ม ดู Step ของ T12) */
async function seriousViolations(page: Page, include?: string) {
  const results = await analyzeSettled(page, include ? (builder) => builder.include(include) : undefined)
  return results.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)
}

test("หน้าคลิปเปิดไม่ได้: ดูรายละเอียด → รหัส + ข้อความเทคนิค → คัดลอกข้อมูลแจ้งปัญหา ได้รายงานจริงและ toast คัดลอกแล้ว", async ({
  page,
}) => {
  const bodies = diagnosticsBodies(page)
  await failVideo(page, 502, "E_YT_REFUSED", REFUSED, DETAIL)
  await page.goto(`/v/${BBB}`)
  const card = errorCard(page)
  await expect(card).toContainText(REFUSED)
  await expect(card.getByText("รหัส E_YT_REFUSED")).toHaveCount(0) // พับไว้ (รหัสนี้ไม่ใช่ E_UNKNOWN)
  await card.getByRole("button", { name: "ดูรายละเอียด" }).click()
  await expect(card.getByText("รหัส E_YT_REFUSED")).toBeVisible()
  await expect(card.getByText(DETAIL)).toBeVisible()
  await card.getByRole("button", { name: COPY }).click()
  await expect(toast(page, COPIED)).toBeVisible(REPORT)
  const text = await clipboardText(page)
  expect(text.startsWith("## รายงานปัญหา YT Toolkit\n")).toBe(true)
  expect(text).toContain(`- รหัส: E_YT_REFUSED · หน้าจอ: video-header (videoId ${BBB})\n`)
  expect(text).toContain(`- รายละเอียด: ${DETAIL}\n`)
  expect(text).toContain("### log ล่าสุด (50 บรรทัด)\n")
  expect(bodies).toEqual([{ code: "E_YT_REFUSED", detail: DETAIL, context: "video-header", videoId: BBB }])
})

test("E_UNKNOWN: ส่วนรายละเอียดกางไว้แล้ว เห็นปุ่มคัดลอกโดยไม่ต้องกด", async ({ page }) => {
  await failVideo(page, 500, "E_UNKNOWN", UNKNOWN, "RuntimeError: boom")
  await page.goto(`/v/${BBB}`)
  const card = errorCard(page)
  await expect(card).toContainText(UNKNOWN)
  await expect(card.getByText("รหัส E_UNKNOWN")).toBeVisible()
  await expect(card.getByRole("button", { name: COPY })).toBeVisible()
})

test("toast ของ error: ค้างเกิน 6 วินาที มีปุ่มคัดลอกในตัว กดแล้วคัดลอกได้และ toast ยังอยู่", async ({ page }) => {
  await page.route("**/api/jobs", (route) =>
    route.request().method() === "POST"
      ? route.fulfill({ status: 500, json: { error: { code: "E_UNKNOWN", message: UNKNOWN, detail: "boom" } } })
      : route.fallback(),
  )
  await page.goto(`/v/${BBB}`)
  await page.getByRole("button", { name: "โหลดภาพรวมเฟรม" }).click()
  const failed = toast(page, UNKNOWN)
  await expect(failed).toBeVisible()
  await page.waitForTimeout(6_000) // เกิน 4 วินาทีของ sonner
  await expect(failed).toBeVisible()
  await failed.getByRole("button", { name: COPY }).click()
  await expect(toast(page, COPIED)).toBeVisible(REPORT)
  await expect(failed).toBeVisible()
  expect(await clipboardText(page)).toContain("- รหัส: E_UNKNOWN · หน้าจอ: enqueue\n")
})

test("หน้าตรวจสุขภาพ: ปุ่มอยู่ถัดจาก ตรวจอีกครั้ง รายงานไม่มีหัวข้อ error", async ({ page }) => {
  const bodies = diagnosticsBodies(page)
  await page.goto("/settings/health")
  await expect(page.getByTestId("tool-ffmpeg")).toBeVisible({ timeout: 15_000 })
  const recheck = page.getByRole("button", { name: "ตรวจอีกครั้ง" })
  await expect(recheck.locator("xpath=following-sibling::button[1]")).toHaveText(COPY)
  await page.getByRole("button", { name: COPY }).click()
  await expect(toast(page, COPIED)).toBeVisible(REPORT)
  const text = await clipboardText(page)
  expect(text).toContain("- บัญชียูทูป: ไม่ได้ใช้บัญชี\n")
  expect(text).not.toContain("### error")
  expect(bodies).toEqual([{ context: "health" }])
})

test("หน้าพัง (โหลดไฟล์โค้ดไม่ได้): ปุ่มคัดลอกใช้ได้และ toast คัดลอกแล้วขึ้น", async ({ page }) => {
  await page.route("**/assets/video-*.js", (route) => route.abort())
  await page.goto(`/v/${BBB}`)
  await expect(page.getByText("โปรแกรมเพิ่งอัปเดต โหลดหน้านี้ใหม่อีกครั้ง")).toBeVisible()
  await page.getByRole("button", { name: COPY }).click()
  await expect(toast(page, COPIED)).toBeVisible(REPORT)
  expect(await clipboardText(page)).toContain("- รหัส: E_UNKNOWN · หน้าจอ: chunk\n")
})

test("คลิปบอร์ดไม่ยอม = คัดลอกไม่สำเร็จ ลองอีกครั้ง · ต่อโปรแกรมไม่ได้ = ข้อความเชื่อมต่อโปรแกรมไม่ได้", async ({ page }) => {
  await page.addInitScript(() => {
    const blocked = () => Promise.reject(new DOMException("blocked", "NotAllowedError"))
    Clipboard.prototype.write = blocked
    Clipboard.prototype.writeText = blocked
  })
  await page.goto("/settings/health")
  await expect(page.getByTestId("tool-ffmpeg")).toBeVisible({ timeout: 15_000 })
  await page.getByRole("button", { name: COPY }).click()
  await expect(toast(page, "คัดลอกไม่สำเร็จ ลองอีกครั้ง")).toBeVisible(REPORT)
  await page.route("**/api/diagnostics", (route) => route.abort())
  await page.getByRole("button", { name: COPY }).click()
  await expect(toast(page, "เชื่อมต่อโปรแกรมไม่ได้ ถ้าปิดโปรแกรมไปแล้ว เปิดใหม่ด้วย start.bat")).toBeVisible()
})

for (const scheme of ["light", "dark"] as const) {
  test(`axe ${scheme}: ส่วนรายละเอียดที่กางในกล่อง error · หน้าตรวจสุขภาพ · toast ที่มีปุ่มคัดลอก`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme })
    await failVideo(page, 502, "E_YT_REFUSED", REFUSED, DETAIL)
    await page.goto(`/v/${BBB}`)
    await expect(page.locator("html")).toHaveClass(scheme === "dark" ? /dark/ : /light/)
    await errorCard(page).getByRole("button", { name: "ดูรายละเอียด" }).click()
    await expect(errorCard(page).getByText(DETAIL)).toBeVisible()
    expect(await seriousViolations(page)).toEqual([])

    await page.goto("/settings/health")
    await expect(page.getByRole("button", { name: COPY })).toBeVisible({ timeout: 15_000 })
    // ทั้งหน้ามีปัญหาเดิมที่ไม่เกี่ยวกับรอบนี้ (แถว ffmpeg ที่ใช้ไม่ได้ในโหมดข้อมูลปลอม) จึงตรวจแถวปุ่มที่เพิ่มปุ่ม
    expect(await seriousViolations(page, '[data-testid="health-actions"]')).toEqual([])

    await page.route("**/api/shutdown", (route) =>
      route.fulfill({ status: 500, json: { error: { code: "E_UNKNOWN", message: UNKNOWN, detail: null } } }),
    )
    await page.getByRole("button", { name: "ปิดโปรแกรม" }).click()
    await expect(toast(page, UNKNOWN).getByRole("button", { name: COPY })).toBeVisible()
    expect(await seriousViolations(page, "[data-sonner-toaster]")).toEqual([])
  })
}

test("หน้าต่างกว้าง 640 px: ข้อความเทคนิคยาวไม่มีช่องว่างไม่ทำให้เลื่อนซ้ายขวา", async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 800 })
  await failVideo(page, 502, "E_YT_REFUSED", REFUSED, "x".repeat(300))
  await page.goto(`/v/${BBB}`)
  await errorCard(page).getByRole("button", { name: "ดูรายละเอียด" }).click()
  await expect(errorCard(page).getByText("รหัส E_YT_REFUSED")).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(640)
})

test("กดปุ่มคัดลอกสองครั้งติด: ส่งคำขอรายงานครั้งเดียว และ toast คัดลอกแล้ว ขึ้นอันเดียว", async ({ page }) => {
  const bodies = diagnosticsBodies(page)
  await page.goto("/settings/health")
  await expect(page.getByTestId("tool-ffmpeg")).toBeVisible({ timeout: 15_000 })
  await page.getByRole("button", { name: COPY }).dblclick()
  await expect(toast(page, COPIED)).toBeVisible(REPORT)
  await expect(toast(page, COPIED)).toHaveCount(1)
  expect(bodies).toEqual([{ context: "health" }])
})

test("ระหว่างรอรายงาน: โฟกัสคีย์บอร์ดอยู่ที่ปุ่มคัดลอก ปุ่มมี aria-busy แล้วหายเมื่อเสร็จ", async ({ page }) => {
  let release: () => void = () => {}
  const released = new Promise<void>((resolve) => {
    release = resolve
  })
  let seen = 0
  // หน่วงคำขอรายงานไว้จนกว่าเทสจะปล่อย แล้วส่งต่อไปถึง backend จริง (route.fallback)
  await page.route("**/api/diagnostics", async (route) => {
    seen += 1
    await released
    await route.fallback()
  })
  await page.goto("/settings/health")
  await expect(page.getByTestId("tool-ffmpeg")).toBeVisible({ timeout: 15_000 })
  const copy = page.getByRole("button", { name: COPY })
  await copy.focus()
  await page.keyboard.press("Enter")
  await expect.poll(() => seen).toBe(1)
  await expect(copy).toHaveAttribute("aria-busy", "true")
  await expect(copy).toBeFocused()
  release()
  await expect(toast(page, COPIED)).toBeVisible(REPORT)
  await expect(copy).not.toHaveAttribute("aria-busy")
  await expect(copy).toBeFocused()
})

test("หน้าตรวจสุขภาพที่ 640 px: ปุ่มเรียง ตรวจอีกครั้ง → คัดลอกข้อมูลแจ้งปัญหา → ปิดโปรแกรม ไม่เลื่อนซ้ายขวา", async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 800 })
  await page.goto("/settings/health")
  await expect(page.getByTestId("tool-ffmpeg")).toBeVisible({ timeout: 15_000 })
  await expect(page.getByTestId("health-actions").getByRole("button")).toHaveText(["ตรวจอีกครั้ง", COPY, "ปิดโปรแกรม"])
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(640)
})
