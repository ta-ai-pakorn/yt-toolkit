import { analyzeSettled } from "./axe-settled"
import { expect, test, type APIRequestContext, type Page } from "@playwright/test"

// M6 รอบ A: รูปแบบชื่อไฟล์ + ตัวอย่าง (AC-OUT-10) และ "ข้อมูลในเครื่อง" (AC-SET-07..10) ในแท็บทั่วไป
// project chromium ห้ามเขียน backend ที่ spec อื่นใช้ร่วม: /api/settings (GET/PATCH), /api/storage*, /api/settings/import,
// /api/settings/export และ /api/history ถูก mock ด้วย page.route ทั้งหมด

type Stored = Record<string, unknown>
type Stub = { patches: Stored[]; state: () => Stored }

async function readSettings(request: APIRequestContext): Promise<Stored> {
  const response = await request.get("/api/settings")
  expect(response.ok()).toBe(true)
  return (await response.json()) as Stored
}

/** แทน GET/PATCH /api/settings ด้วยค่าในหน้า (เริ่มจากค่าจริง) ไม่เขียน backend · เก็บเนื้อ PATCH ไว้นับ */
async function stubSettings(page: Page, request: APIRequestContext, start: Stored = {}): Promise<Stub> {
  let state = { ...(await readSettings(request)), ...start }
  const patches: Stored[] = []
  await page.route("**/api/settings", (route) => {
    if (route.request().method() === "PATCH") {
      const body = route.request().postDataJSON() as Stored
      patches.push(body)
      state = { ...state, ...body }
    }
    return route.fulfill({ json: state })
  })
  return { patches, state: () => state }
}

type Clip = { videoId: string; title: string; channel: string }

async function stubHistory(page: Page, items: Clip[]) {
  await page.route("**/api/history?*", (route) =>
    route.fulfill({
      json: {
        items: items.map((c) => ({ ...c, thumbnailUrl: "", durationS: 60, outputs: [], lastAt: new Date().toISOString() })),
        total: items.length,
      },
    })
  )
}

async function stubStorage(page: Page, reclaimableBytes: number, freedBytes = reclaimableBytes) {
  const calls = { clear: 0 }
  await page.route("**/api/storage", (route) =>
    route.fulfill({ json: { cacheBytes: reclaimableBytes, workBytes: 0, reclaimableBytes } })
  )
  await page.route("**/api/storage/clear", (route) => {
    calls.clear += 1
    return route.fulfill({ json: { freedBytes } })
  })
  return calls
}

const example = (page: Page) => page.locator("#general-filename-example")
const toast = (page: Page, text: string) => page.locator("[data-sonner-toast]", { hasText: text })

async function seriousViolations(page: Page) {
  const results = await analyzeSettled(page)
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target.join(" ")).slice(0, 5) }))
}

// ---------- รูปแบบชื่อไฟล์ ----------

test("AC-OUT-10: เปลี่ยนรูปแบบ → ตัวอย่างเปลี่ยนทันที ใช้คลิปที่เปิดล่าสุด และไม่เรียก API อื่นนอกจากบันทึก", async ({
  page,
  request,
}) => {
  const stub = await stubSettings(page, request, { filenameStyle: "title" })
  await stubHistory(page, [{ videoId: "aqz-KE-bpKQ", title: 'ทดสอบ: "A/B" <ภาค 1>?', channel: "ช่อง/ทดสอบ" }])
  await stubStorage(page, 0)
  await page.goto("/settings/general")
  await expect(example(page)).toHaveText("ตัวอย่าง: ทดสอบ AB ภาค 1.mp4")
  const requests: string[] = []
  page.on("request", (r) => {
    if (new URL(r.url()).pathname.startsWith("/api/")) requests.push(`${r.method()} ${new URL(r.url()).pathname}`)
  })
  await page.getByRole("combobox", { name: "รูปแบบชื่อไฟล์" }).click()
  await page.getByRole("option", { name: "ชื่อคลิป - ช่อง" }).click()
  await expect(example(page)).toHaveText("ตัวอย่าง: ทดสอบ AB ภาค 1 - ช่องทดสอบ.mp4")
  await expect(toast(page, "บันทึกแล้ว")).toBeVisible()
  await page.getByRole("combobox", { name: "รูปแบบชื่อไฟล์" }).click()
  await page.getByRole("option", { name: "ชื่อคลิป (คุณภาพ)" }).click()
  await expect(example(page)).toHaveText("ตัวอย่าง: ทดสอบ AB ภาค 1 (1080p).mp4")
  await expect.poll(() => stub.patches.length).toBe(2)
  expect(stub.patches).toEqual([{ filenameStyle: "title-channel" }, { filenameStyle: "title-quality" }])
  expect(requests).toEqual(["PATCH /api/settings", "PATCH /api/settings"])
})

test("ยังไม่เคยเปิดคลิป: ตัวอย่างใช้ชื่อคลิปภาษาไทยตัวอย่าง", async ({ page, request }) => {
  await stubSettings(page, request, { filenameStyle: "title-channel" })
  await stubHistory(page, [])
  await stubStorage(page, 0)
  await page.goto("/settings/general")
  await expect(example(page)).toHaveText("ตัวอย่าง: สอนทำกับข้าวง่าย ๆ ใน 10 นาที - ครัวบ้านเรา.mp4")
})

// ---------- ล้างข้อมูลชั่วคราว ----------

test("AC-SET-07: ปุ่มบอกขนาด → กล่องยืนยัน → ยกเลิกไม่ส่งอะไร → ล้างเลย → toast ได้พื้นที่คืน", async ({ page, request }) => {
  await stubSettings(page, request)
  await stubHistory(page, [])
  const calls = await stubStorage(page, 1_200_000_000)
  await page.goto("/settings/general")
  await expect(page.getByRole("group", { name: "ข้อมูลในเครื่อง" })).toBeVisible()
  const clear = page.getByRole("button", { name: "ล้างข้อมูลชั่วคราว (1.2 GB)" })
  await clear.click()
  const dialog = page.getByRole("alertdialog")
  await expect(dialog.getByRole("heading", { name: "ล้างข้อมูลชั่วคราว 1.2 GB?" })).toBeVisible()
  await expect(dialog).toContainText("ไฟล์ที่โหลดไว้ ประวัติ และค่าตั้งยังอยู่ครบ แต่เปิดคลิปเก่าต้องดึงภาพใหม่")
  await dialog.getByRole("button", { name: "ยกเลิก" }).click()
  await expect(dialog).toHaveCount(0)
  expect(calls.clear).toBe(0)
  await clear.click()
  await page.getByRole("alertdialog").getByRole("button", { name: "ล้างเลย" }).click()
  await expect(toast(page, "ล้างแล้ว ได้พื้นที่คืน 1.2 GB")).toBeVisible()
  await expect(page.getByRole("alertdialog")).toHaveCount(0)
  expect(calls.clear).toBe(1)
})

test("ไม่มีอะไรให้ล้าง หรือโหลดขนาดไม่ได้ = ปุ่มกดไม่ได้ ไม่มี error", async ({ page, request }) => {
  await stubSettings(page, request)
  await stubHistory(page, [])
  await page.route("**/api/storage", (route) => route.fulfill({ status: 500, json: { error: { code: "E_UNKNOWN", message: "x" } } }))
  await page.goto("/settings/general")
  await expect(page.getByRole("button", { name: "ล้างข้อมูลชั่วคราว", exact: true })).toBeDisabled()
  await expect(page.locator("[data-sonner-toast]")).toHaveCount(0)
})

test("ล้างไม่สำเร็จ → กล่องยืนยันปิด และ toast error พร้อมปุ่มคัดลอกข้อมูลแจ้งปัญหา", async ({ page, request }) => {
  await stubSettings(page, request)
  await stubHistory(page, [])
  await page.route("**/api/storage", (route) => route.fulfill({ json: { cacheBytes: 5e6, workBytes: 0, reclaimableBytes: 5e6 } }))
  await page.route("**/api/storage/clear", (route) =>
    route.fulfill({ status: 500, json: { error: { code: "E_UNKNOWN", message: "มีบางอย่างผิดพลาด", detail: "OSError" } } })
  )
  await page.goto("/settings/general")
  await page.getByRole("button", { name: "ล้างข้อมูลชั่วคราว (5.0 MB)" }).click()
  await page.getByRole("alertdialog").getByRole("button", { name: "ล้างเลย" }).click()
  await expect(toast(page, "มีบางอย่างผิดพลาด").getByRole("button", { name: "คัดลอกข้อมูลแจ้งปัญหา" })).toBeVisible()
  await expect(page.getByRole("alertdialog")).toHaveCount(0)
})

// ---------- สำรอง / นำเข้าค่าตั้ง ----------

test("AC-SET-09: สำรองค่าตั้ง → ดาวน์โหลดไฟล์ชื่อตามวันที่", async ({ page, request }) => {
  await stubSettings(page, request)
  await stubHistory(page, [])
  await stubStorage(page, 0)
  await page.route("**/api/settings/export", (route) =>
    route.fulfill({
      body: '{"app": "yt-toolkit", "schema": 1, "settings": {}}\n',
      headers: {
        "Content-Type": "application/json",
        "Content-Disposition": "attachment; filename=\"yt-toolkit-settings-2026-10-14.json\"; filename*=UTF-8''yt-toolkit-settings-2026-10-14.json",
      },
    })
  )
  await page.goto("/settings/general")
  const download = page.waitForEvent("download")
  await page.getByRole("button", { name: "สำรองค่าตั้ง" }).click()
  expect((await download).suggestedFilename()).toBe("yt-toolkit-settings-2026-10-14.json")
  await expect(page.locator("[data-sonner-toast]")).toHaveCount(0)
})

const IMPORT_FILE = (settings: Stored) => ({
  name: "yt-toolkit-settings-2026-10-14.json",
  mimeType: "application/json",
  buffer: Buffer.from(JSON.stringify({ app: "yt-toolkit", schema: 1, settings })),
})

test("AC-SET-09: นำเข้าไฟล์ถูกต้อง → นำเข้าค่าตั้งแล้ว และค่าใหม่ขึ้นบนจอทันที", async ({ page, request }) => {
  const stub = await stubSettings(page, request, { concurrency: 2 })
  await stubHistory(page, [])
  await stubStorage(page, 0)
  const bodies: string[] = []
  await page.route("**/api/settings/import", (route) => {
    bodies.push(route.request().postData() ?? "")
    return route.fulfill({ json: { settings: { ...stub.state(), concurrency: 3 }, warnings: [] } })
  })
  await page.goto("/settings/general")
  await page.locator('input[type="file"]').setInputFiles(IMPORT_FILE({ concurrency: 3 }))
  await expect(toast(page, "นำเข้าค่าตั้งแล้ว")).toBeVisible()
  await expect(
    page.getByRole("group", { name: "จำนวนงานพร้อมกัน" }).getByRole("button", { name: "3", exact: true })
  ).toHaveAttribute("aria-pressed", "true")
  expect(JSON.parse(bodies[0])).toEqual({ app: "yt-toolkit", schema: 1, settings: { concurrency: 3 } })
})

test("AC-SET-09: โฟลเดอร์ในไฟล์ใช้บนเครื่องนี้ไม่ได้ → คำเตือนค้างจนกดปิด", async ({ page, request }) => {
  const stub = await stubSettings(page, request)
  await stubHistory(page, [])
  await stubStorage(page, 0)
  await page.route("**/api/settings/import", (route) =>
    route.fulfill({ json: { settings: stub.state(), warnings: ["outputDir"] } })
  )
  await page.goto("/settings/general")
  await page.locator('input[type="file"]').setInputFiles(IMPORT_FILE({ outputDir: "Q:\\YT" }))
  const warning = toast(page, "นำเข้าค่าตั้งแล้ว แต่ใช้โฟลเดอร์ผลลัพธ์ในไฟล์บนเครื่องนี้ไม่ได้ จึงใช้โฟลเดอร์เดิมต่อ")
  await expect(warning).toBeVisible()
  await page.waitForTimeout(4500) // toast ปกติหายใน 4 วินาที
  await expect(warning).toBeVisible()
  await warning.getByRole("button", { name: "ปิด" }).click()
  await expect(warning).toHaveCount(0)
})

test("AC-SET-10: ไฟล์ที่ไม่ใช่ไฟล์ค่าตั้ง → ข้อความจาก backend พร้อมปุ่มคัดลอกข้อมูลแจ้งปัญหา", async ({ page, request }) => {
  await stubSettings(page, request)
  await stubHistory(page, [])
  await stubStorage(page, 0)
  const message = 'ไฟล์นี้ไม่ใช่ไฟล์ค่าตั้งของ YT Toolkit หรือไฟล์เสียหาย ลองเลือกไฟล์ที่ได้จากปุ่ม "สำรองค่าตั้ง"'
  await page.route("**/api/settings/import", (route) =>
    route.fulfill({ status: 422, json: { error: { code: "E_SETTINGS_INVALID", message, detail: "app invalid" } } })
  )
  await page.goto("/settings/general")
  await page.locator('input[type="file"]').setInputFiles({ name: "other.json", mimeType: "application/json", buffer: Buffer.from("{}") })
  await expect(toast(page, message).getByRole("button", { name: "คัดลอกข้อมูลแจ้งปัญหา" })).toBeVisible()
})

test("ไฟล์ใหญ่กว่า 1 MB → ไม่ส่งไป backend และแจ้งข้อความเดียวกัน", async ({ page, request }) => {
  await stubSettings(page, request)
  await stubHistory(page, [])
  await stubStorage(page, 0)
  let imports = 0
  await page.route("**/api/settings/import", (route) => {
    imports += 1
    return route.abort()
  })
  await page.goto("/settings/general")
  await page.locator('input[type="file"]').setInputFiles({
    name: "big.json",
    mimeType: "application/json",
    buffer: Buffer.alloc(2 * 1024 * 1024, 0x20),
  })
  const message = 'ไฟล์นี้ไม่ใช่ไฟล์ค่าตั้งของ YT Toolkit หรือไฟล์เสียหาย ลองเลือกไฟล์ที่ได้จากปุ่ม "สำรองค่าตั้ง"'
  await expect(toast(page, message).getByRole("button", { name: "คัดลอกข้อมูลแจ้งปัญหา" })).toBeVisible()
  expect(imports).toBe(0)
})

// ---------- หน้าต่างแคบ และ axe ----------

test("หน้าต่างแคบ 640 px: ตัวอย่างชื่อยาว 300 ตัวและแถวปุ่มไม่ทำให้เลื่อนซ้ายขวา · กล่องยืนยันอ่านได้ครบ", async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 640, height: 800 })
  await stubSettings(page, request, { filenameStyle: "title-channel" })
  await stubHistory(page, [{ videoId: "aqz-KE-bpKQ", title: "ก".repeat(300), channel: "ช".repeat(120) }])
  await stubStorage(page, 1_200_000_000)
  await page.goto("/settings/general")
  await expect(example(page)).toContainText("ตัวอย่าง: กกกก")
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(640)
  await page.getByRole("button", { name: "ล้างข้อมูลชั่วคราว (1.2 GB)" }).click()
  const dialog = page.getByRole("alertdialog")
  await expect(dialog.getByRole("button", { name: "ล้างเลย" })).toBeInViewport()
  const box = await dialog.boundingBox()
  expect(box && box.x >= 0 && box.x + box.width <= 640).toBe(true)
})

for (const scheme of ["dark", "light"] as const) {
  test(`axe: ส่วนข้อมูลในเครื่อง ช่องรูปแบบชื่อไฟล์ และกล่องยืนยัน (${scheme})`, async ({ page, request }) => {
    await page.emulateMedia({ colorScheme: scheme })
    await stubSettings(page, request)
    await stubHistory(page, [])
    await stubStorage(page, 1_200_000_000)
    await page.goto("/settings/general")
    await expect(page.getByRole("button", { name: "ล้างข้อมูลชั่วคราว (1.2 GB)" })).toBeEnabled()
    await expect(page.locator("html")).toHaveClass(scheme === "dark" ? /dark/ : /light/)
    expect(await seriousViolations(page)).toEqual([])
    await page.getByRole("button", { name: "ล้างข้อมูลชั่วคราว (1.2 GB)" }).click()
    await expect(page.getByRole("alertdialog")).toBeVisible()
    expect(await seriousViolations(page)).toEqual([])
  })
}
