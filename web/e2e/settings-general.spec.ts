import os from "node:os"
import path from "node:path"

import { analyzeSettled } from "./axe-settled"
import { expect, test, type APIRequestContext, type Page } from "@playwright/test"

// W6 แท็บทั่วไป (M4 T17) · ใช้ backend ตัวเดียวกับ spec อื่นใน project chromium
// ค่าตั้งเป็นของส่วนกลาง (spec อื่น เช่น download-tabs อ่านไปสร้างคำขอ) จึงเขียนค่าจริงเฉพาะที่ AC-SET-01 ต้องโหลดหน้าใหม่ดู
// (จำนวนงานพร้อมกัน, โฟลเดอร์ผลลัพธ์) และคืนค่าเดิมใน finally · ที่เหลือใช้ page.route แทน backend
test.describe.configure({ mode: "serial" })

type Stored = Record<string, unknown>

async function readSettings(request: APIRequestContext): Promise<Stored> {
  const response = await request.get("/api/settings")
  expect(response.ok()).toBe(true)
  return (await response.json()) as Stored
}

async function writeSettings(request: APIRequestContext, data: Stored) {
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

/** เขียนค่าจริงชั่วคราว: คืนเฉพาะคีย์ที่แก้กลับเป็นค่าเดิมเมื่อจบ แม้เทสล้ม */
async function withRealSettings(
  request: APIRequestContext,
  keys: string[],
  body: (original: Stored) => Promise<void>
) {
  const original = await readSettings(request)
  try {
    await body(original)
  } finally {
    await writeSettings(request, Object.fromEntries(keys.map((key) => [key, original[key]])))
  }
}

type Stub = { patches: Stored[] }

/** แทน GET/PATCH /api/settings ด้วยค่าในหน้า (เริ่มจากค่าจริงที่อ่านมา) ไม่เขียนอะไรที่ backend · เก็บเนื้อ PATCH ไว้นับ */
async function stubSettings(page: Page, request: APIRequestContext): Promise<Stub> {
  let state = await readSettings(request)
  const stub: Stub = { patches: [] }
  await page.route("**/api/settings", (route) => {
    if (route.request().method() === "PATCH") {
      const body = route.request().postDataJSON() as Stored
      stub.patches.push(body)
      state = { ...state, ...body }
    }
    return route.fulfill({ json: state })
  })
  return stub
}

const saved = (page: Page) => page.locator("[data-sonner-toast]", { hasText: "บันทึกแล้ว" })

async function seriousViolations(page: Page) {
  const results = await analyzeSettled(page)
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.map((n) => n.target.join(" ")).slice(0, 5) }))
}

test("/settings เปิดที่แท็บทั่วไป พร้อมแปดช่อง และส่วนข้อมูลในเครื่อง", async ({ page }) => {
  await page.goto("/settings")
  await expect(page.getByRole("tab", { name: "ทั่วไป" })).toHaveAttribute("aria-selected", "true")
  await expect(page.getByLabel("โฟลเดอร์ผลลัพธ์")).toBeVisible()
  await expect(page.getByRole("button", { name: "เปิดโฟลเดอร์" })).toBeVisible()
  await expect(page.getByRole("combobox", { name: "รูปแบบชื่อไฟล์" })).toBeVisible()
  await expect(page.getByText(/^ตัวอย่าง: .+\.mp4$/)).toBeVisible()
  await expect(page.getByRole("group", { name: "จำนวนงานพร้อมกัน" })).toBeVisible()
  await expect(page.getByRole("combobox", { name: "ภาษาเสียงเริ่มต้น" })).toBeVisible()
  await expect(page.getByRole("combobox", { name: "คุณภาพวิดีโอเริ่มต้น" })).toBeVisible()
  await expect(page.getByRole("combobox", { name: "ความละเอียดภาพที่ถ่าย" })).toBeVisible()
  await expect(page.getByRole("group", { name: "รูปแบบเสียงเริ่มต้น" })).toBeVisible()
  await expect(page.getByRole("switch", { name: "ทำภาพคมอัตโนมัติตอนโหลดวิดีโอ" })).toBeVisible()
  // M6 รอบ A: ส่วน "ข้อมูลในเครื่อง" (ปุ่มล้างมีขนาดหรือไม่มีก็ได้ ขึ้นกับ cache ของ spec อื่นที่รันพร้อมกัน)
  const local = page.getByRole("group", { name: "ข้อมูลในเครื่อง" })
  await expect(local.getByRole("button", { name: /^ล้างข้อมูลชั่วคราว/ })).toBeVisible()
  await expect(local.getByRole("button", { name: "สำรองค่าตั้ง" })).toBeVisible()
  await expect(local.getByRole("button", { name: "นำเข้าค่าตั้ง" })).toBeVisible()
  // ไม่มีปุ่มบันทึก: ทุกช่องบันทึกเมื่อเปลี่ยน
  await expect(page.getByRole("button", { name: /^บันทึก/ })).toHaveCount(0)
})

test("AC-SET-01 E: เปลี่ยนจำนวนงานพร้อมกันเป็น 1 → แจ้งบันทึกแล้ว และโหลดหน้าใหม่ยังเป็น 1", async ({
  page,
  request,
}) => {
  await withRealSettings(request, ["concurrency"], async () => {
    await writeSettings(request, { concurrency: 2 })
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
})

test("โฟลเดอร์ผลลัพธ์: ที่อยู่เต็ม + Enter → บันทึกแล้ว โหลดหน้าใหม่ยังอยู่", async ({ page, request }) => {
  const target = path.join(os.tmpdir(), "yt-toolkit-e2e-general-out")
  await withRealSettings(request, ["outputDir"], async () => {
    await page.goto("/settings/general")
    const input = page.getByLabel("โฟลเดอร์ผลลัพธ์")
    await input.fill(target)
    await input.press("Enter")
    await expect(saved(page)).toBeVisible()
    await page.reload()
    await expect(page.getByLabel("โฟลเดอร์ผลลัพธ์")).toHaveValue(target)
  })
})

test("โฟลเดอร์ผลลัพธ์: ที่อยู่ไม่เต็ม (abc) → ข้อความจากเซิร์ฟเวอร์ใต้ช่อง และโหลดหน้าใหม่ค่าเดิมไม่เปลี่ยน", async ({
  page,
  request,
}) => {
  const { outputDir } = await readSettings(request)
  await page.goto("/settings/general")
  const input = page.getByLabel("โฟลเดอร์ผลลัพธ์")
  await expect(input).toHaveValue(String(outputDir))
  await input.fill("abc")
  await input.press("Enter")
  const message = page.getByText("ใส่ที่อยู่โฟลเดอร์แบบเต็ม", { exact: false })
  await expect(message).toBeVisible()
  await expect(input).toHaveAttribute("aria-invalid", "true")
  await expect(saved(page)).toHaveCount(0)
  await page.reload()
  await expect(page.getByLabel("โฟลเดอร์ผลลัพธ์")).toHaveValue(String(outputDir))
  await expect(message).toHaveCount(0)
})

test("โฟลเดอร์ผลลัพธ์: ออกจากช่องโดยไม่แก้ไม่ส่งอะไร · Esc คืนค่าที่บันทึกไว้", async ({ page, request }) => {
  const stub = await stubSettings(page, request)
  const { outputDir } = await readSettings(request)
  await page.goto("/settings/general")
  const input = page.getByLabel("โฟลเดอร์ผลลัพธ์")
  await input.focus()
  await input.blur()
  await input.fill("abc")
  await input.press("Escape")
  await expect(input).toHaveValue(String(outputDir))
  await input.blur()
  expect(stub.patches).toHaveLength(0)
})

test("M5 นับ PATCH ของช่องโฟลเดอร์: Enter แล้วออกจากช่อง = 1 · ออกจากช่องอย่างเดียว = 1 · แก้อีกแล้วออก = 2", async ({
  page,
  request,
}) => {
  const stub = await stubSettings(page, request)
  const first = path.join(os.tmpdir(), "yt-toolkit-e2e-count-a")
  const second = path.join(os.tmpdir(), "yt-toolkit-e2e-count-b")
  await page.goto("/settings/general")
  const input = page.getByLabel("โฟลเดอร์ผลลัพธ์")

  // Enter ตามด้วยออกจากช่องทันที: ส่งครั้งเดียว
  await input.fill(first)
  await input.press("Enter")
  await input.blur()
  await expect(saved(page)).toBeVisible()
  expect(stub.patches).toEqual([{ outputDir: first }])

  // แก้ค่าแล้วออกจากช่องโดยไม่กด Enter: บันทึกเอง ได้ครั้งที่สอง
  await input.fill(second)
  await input.blur()
  await expect.poll(() => stub.patches.length).toBe(2)
  expect(stub.patches[1]).toEqual({ outputDir: second })

  // ออกจากช่องซ้ำโดยไม่แก้: ไม่ส่งเพิ่ม
  await input.focus()
  await input.blur()
  await page.waitForTimeout(300)
  expect(stub.patches).toHaveLength(2)
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

test("คุณภาพวิดีโอเริ่มต้นและรูปแบบเสียงเริ่มต้น เปลี่ยนแล้วบันทึกและคงอยู่ (ใช้ค่าจำลอง ไม่เขียน backend)", async ({
  page,
  request,
}) => {
  const stub = await stubSettings(page, request)
  await page.goto("/settings/general")
  await page.getByRole("combobox", { name: "คุณภาพวิดีโอเริ่มต้น" }).click()
  await page.getByRole("option", { name: "เปิดได้ทุกที่ 720p" }).click()
  await expect(saved(page)).toBeVisible()
  await page.getByRole("group", { name: "รูปแบบเสียงเริ่มต้น" }).getByRole("button", { name: "wav" }).click()
  await page.getByRole("combobox", { name: "ภาษาเสียงเริ่มต้น" }).click()
  await page.getByRole("option", { name: "ไทย", exact: true }).click()
  await expect.poll(() => stub.patches.length).toBe(3)
  expect(stub.patches).toEqual([{ videoDefault: "compat-720" }, { audioDefault: "wav" }, { audioLanguage: "th" }])
  await page.reload()
  await expect(page.getByRole("combobox", { name: "คุณภาพวิดีโอเริ่มต้น" })).toContainText("เปิดได้ทุกที่ 720p")
  await expect(page.getByRole("combobox", { name: "ภาษาเสียงเริ่มต้น" })).toContainText("ไทย")
  await expect(
    page.getByRole("group", { name: "รูปแบบเสียงเริ่มต้น" }).getByRole("button", { name: "wav" })
  ).toHaveAttribute("aria-pressed", "true")
})

test("ทำภาพคมอัตโนมัติ: เปิดอยู่ตั้งต้น · ปิดแล้วบันทึกและคงอยู่ (ใช้ค่าจำลอง ไม่เขียน backend)", async ({ page, request }) => {
  const stub = await stubSettings(page, request)
  await page.goto("/settings/general")
  const toggle = page.getByRole("switch", { name: "ทำภาพคมอัตโนมัติตอนโหลดวิดีโอ" })
  await expect(toggle).toHaveAttribute("aria-checked", "true")
  await expect(page.getByText("ใช้ไฟล์ที่โหลดมาแล้ว ไม่ต้องโหลดเพิ่ม ใช้เวลาเพิ่มราว 10-40 วินาทีต่อคลิป")).toBeVisible()
  await toggle.click()
  await expect(saved(page)).toBeVisible()
  expect(stub.patches).toEqual([{ autoSharpFrames: false }])
  await page.reload()
  await expect(page.getByRole("switch", { name: "ทำภาพคมอัตโนมัติตอนโหลดวิดีโอ" })).toHaveAttribute("aria-checked", "false")
})

test("โหลดค่าตั้งไม่สำเร็จ → แจ้งพร้อมปุ่มลองใหม่ แล้วแสดงช่องเมื่อโหลดได้", async ({ page }) => {
  let fail = true
  await page.route("**/api/settings", (route) => {
    if (route.request().method() === "GET" && fail) {
      return route.fulfill({
        status: 500,
        json: { error: { code: "E_UNKNOWN", message: 'มีบางอย่างผิดพลาด กด "คัดลอกข้อมูลแจ้งปัญหา" แล้วส่งให้ผู้ดูแล', detail: null } },
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
    // M6 รอบ A: ขนาดข้อมูลชั่วคราวมาทีหลัง ปุ่มล้างจึงจางจาก disabled เป็นปกติ (transition-all ของ Button)
    // ถ้าคำตอบมาหลังรอหน้านิ่งแล้ว axe จะอ่านสีกลางทาง (4.41:1) จึงรอคำตอบก่อน แล้วให้ analyzeSettled รอการจางจบ
    const storage = page.waitForResponse((r) => new URL(r.url()).pathname === "/api/storage")
    await page.goto("/settings/general")
    const { reclaimableBytes } = (await (await storage).json()) as { reclaimableBytes: number }
    // ปุ่มต้องถึงสถานะสุดท้ายก่อน (ไม่มีอะไรให้ล้าง = ยังจางอยู่ตามจริง ขึ้นกับ cache ของ spec อื่น)
    const clear = page.getByRole("group", { name: "ข้อมูลในเครื่อง" }).getByRole("button", { name: /^ล้างข้อมูลชั่วคราว/ })
    await expect(clear).toBeEnabled({ enabled: reclaimableBytes > 0 })
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

test("ความละเอียดภาพที่ถ่าย: ค่าเริ่มต้นสูงสุดที่มี · เลือก 720p แล้วบันทึกและคงอยู่ (ใช้ค่าจำลอง ไม่เขียน backend)", async ({ page, request }) => {
  const stub = await stubSettings(page, request)
  await page.goto("/settings/general")
  const select = page.getByRole("combobox", { name: "ความละเอียดภาพที่ถ่าย" })
  await expect(select).toContainText("สูงสุดที่มี")
  await expect(page.getByText("ภาพยิ่งละเอียด ตัวหนังสือเล็กในคลิปยิ่งอ่านง่าย ใช้เน็ตต่อภาพมากขึ้น (4K ราว 8 MB)")).toBeVisible()
  await select.click()
  await page.getByRole("option", { name: "720p", exact: true }).click()
  await expect(saved(page)).toBeVisible()
  expect(stub.patches).toEqual([{ captureQuality: "720" }])
  await page.reload()
  await expect(page.getByRole("combobox", { name: "ความละเอียดภาพที่ถ่าย" })).toContainText("720p")
})
