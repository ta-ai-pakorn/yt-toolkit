import { analyzeSettled } from "./axe-settled"
import { expect, test, type Page } from "@playwright/test"

// M6 รอบ A ปุ่ม "วาง" ใน W1 (spec 1, AC-IN-08 / AC-IN-09) · project chromium: ไม่สร้างงาน /api/resolve ถูก mock
// navigator.clipboard.readText ถูกแทนด้วย addInitScript (คลิปบอร์ดของเครื่องใช้ร่วมกันทุก worker ที่รันขนานกัน
// จึงไม่ใช้คลิปบอร์ดจริงเป็นข้อมูลของเทส) · การขอสิทธิ์ของเบราว์เซอร์จริงตรวจด้วยมือใน docs/acceptance.md AC-IN-08/09

const BBB_URL = "https://www.youtube.com/watch?v=aqz-KE-bpKQ"
const HINT = "เบราว์เซอร์ไม่อนุญาตให้อ่านคลิปบอร์ด คลิกในช่องแล้วกด Ctrl+V แทน"

type ClipboardMode = { mode: "text"; text: string } | { mode: "denied" } | { mode: "missing" }

/** แทน readText ก่อนหน้าโหลด และนับจำนวนครั้งที่ถูกเรียกไว้ที่ window.__readTextCalls */
async function stubClipboard(page: Page, setup: ClipboardMode) {
  await page.addInitScript((conf: ClipboardMode) => {
    const counter = { calls: 0 }
    Object.defineProperty(window, "__readTextCalls", { get: () => counter.calls })
    if (conf.mode === "missing") {
      Object.defineProperty(Navigator.prototype, "clipboard", { get: () => undefined, configurable: true })
      return
    }
    const readText = () => {
      counter.calls += 1
      return conf.mode === "denied"
        ? Promise.reject(new DOMException("Read permission denied.", "NotAllowedError"))
        : Promise.resolve(conf.text)
    }
    Object.defineProperty(navigator.clipboard, "readText", { value: readText, configurable: true })
  }, setup)
}

const readTextCalls = (page: Page) => page.evaluate(() => (window as unknown as { __readTextCalls: number }).__readTextCalls)

async function countResolves(page: Page): Promise<{ calls: number }> {
  const seen = { calls: 0 }
  await page.route("**/api/resolve", (route) => {
    seen.calls += 1
    return route.fulfill({ json: { resolveId: "r1", items: [], skippedText: true } })
  })
  return seen
}

const pasteButton = (page: Page) => page.getByRole("button", { name: "วาง", exact: true })

test("AC-IN-08: ลิงก์ในคลิปบอร์ด → กดวาง แทนข้อความในช่องแล้ววิเคราะห์ทันที · ไม่อ่านคลิปบอร์ดก่อนกด", async ({ page }) => {
  await stubClipboard(page, { mode: "text", text: BBB_URL })
  const resolves = await countResolves(page)
  await page.goto("/")
  await page.getByRole("textbox").fill("ข้อความเก่าในช่อง")
  expect(await readTextCalls(page)).toBe(0)
  await pasteButton(page).click()
  await expect(page.getByRole("textbox")).toHaveValue(BBB_URL)
  await expect.poll(() => resolves.calls).toBe(1)
  expect(await readTextCalls(page)).toBe(1)
})

test("AC-IN-08: ข้อความอื่น → เติมลงช่องอย่างเดียว ไม่วิเคราะห์", async ({ page }) => {
  await stubClipboard(page, { mode: "text", text: "สูตรแกงเขียวหวาน" })
  const resolves = await countResolves(page)
  await page.goto("/")
  await pasteButton(page).click()
  await expect(page.getByRole("textbox")).toHaveValue("สูตรแกงเขียวหวาน")
  await expect(page.getByRole("textbox")).toBeFocused()
  expect(resolves.calls).toBe(0)
})

test("คลิปบอร์ดว่าง → ช่องเดิมไม่เปลี่ยน โฟกัสช่อง ไม่มีคำแนะนำ", async ({ page }) => {
  await stubClipboard(page, { mode: "text", text: "  " })
  await page.goto("/")
  await page.getByRole("textbox").fill("เดิม")
  await pasteButton(page).click()
  await expect(page.getByRole("textbox")).toBeFocused()
  await expect(page.getByRole("textbox")).toHaveValue("เดิม")
  await expect(page.getByText(HINT)).toHaveCount(0)
})

for (const mode of ["denied", "missing"] as const) {
  test(`AC-IN-09: เบราว์เซอร์ไม่ให้อ่านคลิปบอร์ด (${mode}) → คำแนะนำใต้ช่อง โฟกัสช่อง ไม่มี error สีแดง ไม่มี toast`, async ({
    page,
  }) => {
    await stubClipboard(page, { mode })
    await page.goto("/")
    await pasteButton(page).click()
    const hint = page.getByText(HINT)
    await expect(hint).toBeVisible()
    await expect(hint).toHaveAttribute("role", "status")
    await expect(page.getByRole("textbox")).toBeFocused()
    await expect(page.getByRole("textbox")).toHaveAttribute("aria-describedby", "paste-hint")
    await expect(page.getByRole("alert")).toHaveCount(0)
    await expect(page.locator("[data-sonner-toast]")).toHaveCount(0)
    // พิมพ์ในช่อง = คำแนะนำหายไป
    await page.getByRole("textbox").fill("x")
    await expect(hint).toHaveCount(0)
  })
}

test("ระหว่างวิเคราะห์ ปุ่มวางกดไม่ได้ (โฟกัสยังอยู่) และไม่อ่านคลิปบอร์ด", async ({ page }) => {
  await stubClipboard(page, { mode: "text", text: BBB_URL })
  let release: () => void = () => undefined
  await page.route("**/api/resolve", async (route) => {
    await new Promise<void>((resolve) => (release = resolve))
    await route.fulfill({ json: { resolveId: "r1", items: [], skippedText: true } })
  })
  await page.goto("/")
  await page.getByRole("textbox").fill(BBB_URL)
  await page.getByRole("button", { name: "วิเคราะห์" }).click()
  await expect(pasteButton(page)).toHaveAttribute("aria-disabled", "true")
  await pasteButton(page).click({ force: true })
  expect(await readTextCalls(page)).toBe(0)
  release()
})

test("หน้าต่างแคบ 640 px: ปุ่มวางกับปุ่มวิเคราะห์อยู่แถวเดียวกัน คำแนะนำไม่ทำให้เลื่อนซ้ายขวา · axe ผ่าน", async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 800 })
  await stubClipboard(page, { mode: "denied" })
  await page.goto("/")
  await pasteButton(page).click()
  await expect(page.getByText(HINT)).toBeVisible()
  const paste = await pasteButton(page).boundingBox()
  const analyze = await page.getByRole("button", { name: "วิเคราะห์" }).boundingBox()
  expect(paste && analyze && Math.abs(paste.y - analyze.y) < 2).toBe(true)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(640)
  const results = await analyzeSettled(page)
  expect(results.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual([])
})
