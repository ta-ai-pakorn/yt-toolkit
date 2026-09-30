/// <reference lib="dom" />
import fs from "node:fs"
import path from "node:path"

import AxeBuilder from "@axe-core/playwright"
import { expect, test, type Page } from "@playwright/test"

// คลิปภาษาไทยที่มีภาพเฟรม (storyboard จริง) และซับอัตโนมัติภาษาไทย (th-orig) ในชุดทดสอบ
const THAI = "88o5Sk8_m1Y"
const THAI_URL = `https://www.youtube.com/watch?v=${THAI}`
const BBB = "aqz-KE-bpKQ"
// คลิปที่มีแต่ซับอัตโนมัติ yue (ไม่ใช่ -orig) กับซับแปล: ไม่มีแทร็กเริ่มต้น ผู้ใช้ต้องเลือกเอง
const NO_ORIG = "NOORIGSUB01"

const FRAME_LIST = "รายการภาพเฟรม"
const LINES = "บรรทัดในทรานสคริปต์"
const SEARCH = "ค้นหาคำในทรานสคริปต์"
const NO_SUBS = "คลิปนี้ไม่มีซับ"
const PICK_HINT = "คลิปนี้ไม่มีซับจากเจ้าของคลิปหรือซับภาษาต้นฉบับ เลือกแทร็กที่ต้องการจากรายการ"
const M2_MENU = ["คัดลอกภาพ", "โหลดภาพนี้", "คัดลอกเวลา", "คัดลอกลิงก์ช่วงนี้"]
const MENU_WITH_SUBS = [...M2_MENU, "ดูซับช่วงนี้"]
// ภาพเฟรมของคลิปนี้ห่างกัน 4895 ms: ภาพที่ใกล้ 10 วินาทีที่สุดคือ 9790 ms (00:00:09)
const FRAME_NEAR_10S = "00:00:09"
const FRAME_NEAR_10S_MS = 9790
const HALF_INTERVAL_MS = Math.ceil(4895 / 2)

type Json3 = { events: { tStartMs: number; dDurationMs?: number; aAppend?: number; segs?: { utf8: string; tOffsetMs?: number }[] }[] }
type Token = { t: string; s: number; e: number }

/**
 * token ของซับไทยในชุดทดสอบ (แปลงจาก json3 จริง): หนึ่งคำ = หนึ่ง token เวลาจบ = เวลาเริ่มของคำถัดไป
 * ใช้จำลอง API /tokens (ส่วนของ backend ทำคนละงาน) หน้าเว็บจึงทดสอบได้โดยไม่ขึ้นกับตัวแยกซับ
 */
function thaiTokens(): Token[] {
  const file = path.join(import.meta.dirname, "../../tests/fixtures/subs", THAI, "th-orig.json3")
  const data = JSON.parse(fs.readFileSync(file, "utf8")) as Json3
  const words: Token[] = []
  for (const event of data.events) {
    if (!event.segs || event.aAppend) continue
    const end = event.tStartMs + (event.dDurationMs ?? 0)
    event.segs.forEach((seg, index) => {
      if (seg.utf8.trim() === "") return
      const next = event.segs?.[index + 1]
      words.push({
        t: seg.utf8,
        s: event.tStartMs + (seg.tOffsetMs ?? 0),
        e: next ? event.tStartMs + (next.tOffsetMs ?? 0) : end,
      })
    })
  }
  return words.map((word, index) => {
    const next = words[index + 1]
    const e = next ? Math.min(word.e, next.s) : word.e
    return { ...word, e: Math.max(e, word.s + 1) }
  })
}

const THAI_TRACKS = {
  tracks: [
    { id: "a.th-orig", lang: "th", name: "Thai (Original)", group: "original" },
    { id: "t.en", lang: "en", name: "English", group: "translated" },
  ],
  defaultTrackId: "a.th-orig",
}

const NO_ORIG_TRACKS = {
  tracks: [
    { id: "a.yue", lang: "yue", name: "Cantonese", group: "original" },
    { id: "t.en", lang: "en", name: "English", group: "translated" },
    { id: "t.th", lang: "th", name: "Thai", group: "translated" },
  ],
}

/** จำลองรายการแทร็กซับ (และ token ของทุกแทร็ก) ตามสัญญา C4 */
async function mockSubtitles(page: Page, videoId: string, tracks: object, tokens: Token[] = []) {
  await page.route(`**/api/videos/${videoId}/subtitles`, (route) => route.fulfill({ json: tracks }))
  await page.route(`**/api/videos/${videoId}/subtitles/*/tokens`, (route) =>
    route.fulfill({ json: { hasWordTiming: true, tokens } }),
  )
}

const mockThai = (page: Page) => mockSubtitles(page, THAI, THAI_TRACKS, thaiTokens())

const tab = (page: Page, name: string) => page.getByRole("tab", { name, exact: true })
const searchBox = (page: Page) => page.getByRole("textbox", { name: SEARCH })
const lineItems = (page: Page) => page.getByRole("list", { name: LINES }).getByRole("listitem")
const frameList = (page: Page) => page.getByRole("list", { name: FRAME_LIST })
const frameButton = (page: Page, time: string) => page.getByRole("button", { name: `ภาพเฟรมที่ ${time}` })
const currentLine = (page: Page) => page.getByRole("list", { name: LINES }).locator('[aria-current="true"]')

const toMs = (timecode: string) => {
  const [h, m, s] = timecode.split(":").map(Number)
  return ((h * 60 + m) * 60 + s) * 1000
}

/** ภาพที่ไฮไลต์อยู่ต้องมีภาพเดียว ได้โฟกัส เห็นอยู่ในจอ และเป็นภาพที่ใกล้เวลา at ที่สุด (ภาพห่างกัน ~4.9 วินาที) */
async function expectHighlightedFrameNear(page: Page, at: number) {
  const highlighted = frameList(page).locator("[data-highlighted]")
  await expect(highlighted).toHaveCount(1)
  await expect(highlighted).toBeFocused()
  await expect(highlighted).toBeInViewport()
  await expect(highlighted).toHaveAttribute("aria-current", "true")
  // กรอบไฮไลต์ (outline) หรือวงโฟกัส (box-shadow) อย่างใดอย่างหนึ่งต้องเห็นอยู่ ขึ้นกับว่าเบราว์เซอร์ถือว่าโฟกัสจากคีย์บอร์ดไหม
  const marked = await highlighted.evaluate((element) => {
    const style = getComputedStyle(element)
    return style.outlineStyle !== "none" || style.boxShadow !== "none"
  })
  expect(marked).toBe(true)
  const alt = (await highlighted.locator("img").getAttribute("alt")) ?? ""
  const time = /\d{2}:\d{2}:\d{2}/.exec(alt)?.[0] ?? ""
  // ห่างจาก at ไม่เกินครึ่งช่วงห่างของภาพ · timecode ตัดเศษวินาทีทิ้ง จึงเผื่อเพิ่มอีก 1 วินาที
  expect(Math.abs(toMs(time) - at)).toBeLessThanOrEqual(HALF_INTERVAL_MS + 1000)
}

function atFromUrl(page: Page): number {
  return Number(new URL(page.url()).searchParams.get("at"))
}

test.describe("M3 ทรานสคริปต์: ค้นหา (FR-SUB-8)", () => {
  test("พิมพ์ 'กรุงเทพ' → 'พบ N บรรทัด' และทุกบรรทัดที่เห็นมีคำนี้ถูกเน้นด้วย mark", async ({ page }) => {
    await mockThai(page)
    await page.goto(`/v/${THAI}?tab=transcript`)
    await expect(page.getByText("จากแทร็ก ไทย (อัตโนมัติ)", { exact: false })).toBeVisible()
    const total = await lineItems(page).count()
    expect(total).toBeGreaterThan(3)

    await searchBox(page).fill("กรุงเทพ")
    await expect(page.getByText(/^พบ \d+ บรรทัด$/)).toBeVisible()
    const n = Number(/\d+/.exec((await page.getByText(/^พบ \d+ บรรทัด$/).textContent()) ?? "")?.[0])
    expect(n).toBeGreaterThanOrEqual(1)
    await expect(lineItems(page)).toHaveCount(n)
    for (const item of await lineItems(page).all()) {
      await expect(item.locator("mark").first()).toHaveText("กรุงเทพ")
    }
  })

  test("ไม่พบคำ → 'ไม่พบคำนี้ในทรานสคริปต์' · กดล้างคำค้นแล้วกลับมาครบทุกบรรทัด โฟกัสอยู่ที่ช่องค้นหา", async ({ page }) => {
    await mockThai(page)
    await page.goto(`/v/${THAI}?tab=transcript`)
    await expect(lineItems(page).first()).toBeVisible()
    const total = await lineItems(page).count()
    await expect(page.getByRole("button", { name: "ล้างคำค้น" })).toHaveCount(0)

    await searchBox(page).fill("เชียงใหม่ไม่มีแน่นอน")
    await expect(page.getByText("ไม่พบคำนี้ในทรานสคริปต์")).toBeVisible()
    await expect(lineItems(page)).toHaveCount(0)

    await page.getByRole("button", { name: "ล้างคำค้น" }).click()
    await expect(searchBox(page)).toHaveValue("")
    await expect(searchBox(page)).toBeFocused()
    await expect(lineItems(page)).toHaveCount(total)
    await expect(page.getByText("ไม่พบคำนี้ในทรานสคริปต์")).toHaveCount(0)
  })
})

test.describe("M3 ทรานสคริปต์ → ภาพเฟรม", () => {
  test("กดบรรทัดแรกที่ค้นเจอ → แท็บภาพเฟรม ?at=<ms> · ภาพที่ใกล้ที่สุดมีกรอบ อยู่ในจอ และได้โฟกัส · ย้อนกลับครั้งเดียวถึง W1", async ({
    page,
  }) => {
    await mockThai(page)
    await page.goto("/")
    await page.getByRole("textbox").fill(THAI_URL)
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    await expect(page).toHaveURL(new RegExp(`/v/${THAI}$`))
    await tab(page, "ทรานสคริปต์").click()
    await searchBox(page).fill("กรุงเทพ")
    const first = lineItems(page).first().getByRole("button")
    const time = (await first.locator(".font-mono").textContent()) ?? ""
    await first.click()

    // แท็บภาพเฟรมเป็นค่าเริ่มต้น จึงไม่ขึ้น tab= ใน URL เหลือแค่ at
    await expect(page).toHaveURL(new RegExp(`/v/${THAI}\\?at=\\d+$`))
    await expect(tab(page, "ภาพเฟรม")).toHaveAttribute("aria-selected", "true")
    const at = atFromUrl(page)
    expect(Math.floor(at / 1000)).toBe(toMs(time) / 1000)
    await expectHighlightedFrameNear(page, at)

    await page.goBack()
    await expect(page).toHaveURL(/\/$/)
  })

  test("กดบรรทัดสุดท้าย → ภาพท้ายคลิปที่อยู่ไกลจอ (ยังไม่ถูกวาด) ถูกเลื่อนมาให้เห็นและได้โฟกัส", async ({ page }) => {
    await mockThai(page)
    await page.goto(`/v/${THAI}?tab=transcript`)
    await expect(lineItems(page).first()).toBeVisible()
    await lineItems(page).last().getByRole("button").click()
    await expect(page).toHaveURL(/\?at=\d+$/)
    await expectHighlightedFrameNear(page, atFromUrl(page))
  })
})

test.describe("M3 ภาพเฟรม → ทรานสคริปต์ (Q6 = ก)", () => {
  test(`คลิกขวาภาพ ${FRAME_NEAR_10S} → เมนูมี 5 รายการ สุดท้ายคือ 'ดูซับช่วงนี้' → บรรทัดของเวลานั้นถูกไฮไลต์และเห็นในจอ`, async ({
    page,
  }) => {
    await mockThai(page)
    await page.goto(`/v/${THAI}`)
    await frameButton(page, FRAME_NEAR_10S).click({ button: "right" })
    const menu = page.getByRole("menu")
    await expect(menu.getByRole("menuitem")).toHaveText(MENU_WITH_SUBS)
    await menu.getByRole("menuitem", { name: "ดูซับช่วงนี้" }).click()

    await expect(page).toHaveURL(new RegExp(`\\?tab=transcript&at=${FRAME_NEAR_10S_MS}$`))
    await expect(tab(page, "ทรานสคริปต์")).toHaveAttribute("aria-selected", "true")
    await expect(currentLine(page)).toHaveCount(1)
    await expect(currentLine(page)).toBeInViewport()
    await expect(currentLine(page)).toBeFocused()
    await expectCurrentLineCovers(page, FRAME_NEAR_10S_MS)
  })

  test("คีย์บอร์ด: Shift+F10 ที่ภาพ → เลือก 'ดูซับช่วงนี้' ด้วยลูกศร + Enter ได้เหมือนกัน", async ({ page }) => {
    await mockThai(page)
    await page.goto(`/v/${THAI}`)
    await frameButton(page, FRAME_NEAR_10S).focus()
    await page.keyboard.press("Shift+F10")
    await expect(page.getByRole("menu").getByRole("menuitem")).toHaveText(MENU_WITH_SUBS)
    await expect(page.getByRole("menuitem", { name: "คัดลอกภาพ" })).toBeFocused()
    for (let i = 0; i < 4; i++) await page.keyboard.press("ArrowDown")
    await expect(page.getByRole("menuitem", { name: "ดูซับช่วงนี้" })).toBeFocused()
    await page.keyboard.press("Enter")

    await expect(page).toHaveURL(new RegExp(`\\?tab=transcript&at=${FRAME_NEAR_10S_MS}$`))
    await expect(currentLine(page)).toBeInViewport()
    await expect(currentLine(page)).toBeFocused()
    await expectCurrentLineCovers(page, FRAME_NEAR_10S_MS)
  })
})

/** บรรทัดที่ไฮไลต์ = บรรทัดสุดท้ายที่เริ่มก่อนหรือตรงเวลา at (บรรทัดถัดไปเริ่มหลัง at) */
async function expectCurrentLineCovers(page: Page, at: number) {
  const times = await lineItems(page).locator(".font-mono").allTextContents()
  const index = await lineItems(page).evaluateAll((items) =>
    items.findIndex((item) => item.querySelector('[aria-current="true"]') !== null),
  )
  expect(index).toBeGreaterThanOrEqual(0)
  expect(toMs(times[index])).toBeLessThanOrEqual(at)
  if (index + 1 < times.length) expect(toMs(times[index + 1]) + 999).toBeGreaterThanOrEqual(at)
}

test.describe("M3 ทรานสคริปต์: คลิปที่ไม่มีซับ / ไม่มีแทร็กที่ใช้อยู่", () => {
  test("คลิปไม่มีซับ: เมนูภาพเฟรมยังมี 4 รายการเหมือน M2 · แท็บทรานสคริปต์บอก 'คลิปนี้ไม่มีซับ'", async ({ page }) => {
    await mockSubtitles(page, BBB, { tracks: [] })
    await page.goto(`/v/${BBB}`)
    await frameButton(page, "00:00:04").click({ button: "right" })
    await expect(page.getByRole("menu").getByRole("menuitem")).toHaveText(M2_MENU)
    await page.keyboard.press("Escape")

    await page.goto(`/v/${BBB}?tab=transcript`)
    await expect(page.getByText(NO_SUBS)).toBeVisible()
  })

  test("ไม่มีแทร็กที่ใช้อยู่: บอกให้เลือกแทร็ก และปุ่มพาไปแท็บซับ", async ({ page }) => {
    await mockSubtitles(page, NO_ORIG, NO_ORIG_TRACKS)
    await page.goto(`/v/${NO_ORIG}?tab=transcript`)
    await expect(page.getByText(PICK_HINT)).toBeVisible()
    await page.getByRole("button", { name: "ไปเลือกแทร็กที่แท็บซับ" }).click()
    await expect(page).toHaveURL(new RegExp(`/v/${NO_ORIG}\\?tab=subs$`))
    await expect(tab(page, "ซับ")).toHaveAttribute("aria-selected", "true")
  })
})

test.describe("M3 ทรานสคริปต์ การเข้าถึง (axe)", () => {
  for (const scheme of ["dark", "light"] as const) {
    test(`แท็บทรานสคริปต์ระหว่างค้นหาไม่มีปัญหาระดับ serious/critical (${scheme})`, async ({ page }) => {
      await mockThai(page)
      await page.emulateMedia({ colorScheme: scheme })
      await page.goto(`/v/${THAI}?tab=transcript&at=${FRAME_NEAR_10S_MS}`)
      await searchBox(page).fill("กรุงเทพ")
      await expect(lineItems(page).first().locator("mark")).toBeVisible()
      await expect(page.locator("html")).toHaveClass(scheme === "dark" ? /dark/ : /light/)
      expect(await seriousViolations(page)).toEqual([])
    })
  }
})

async function seriousViolations(page: Page) {
  const results = await new AxeBuilder({ page }).analyze()
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.map((n) => n.target.join(" ")).slice(0, 5) }))
}
