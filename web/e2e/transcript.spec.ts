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
// เมนูของภาพเฟรมที่ไม่ขึ้นกับซับ: 4 รายการของ M2 + "เปิดในยูทูปตรงเวลานี้" (owner round 4) + "เล่นจากตรงนี้" (M3.5)
// + "ถ่ายภาพคมตรงนี้" (M5 รอบ B2) + "ตั้งเป็นจุดเริ่ม"/"ตั้งเป็นจุดจบ" (M5 รอบ A)
const M2_MENU = [
  "คัดลอกภาพ",
  "โหลดภาพนี้",
  "คัดลอกเวลา",
  "คัดลอกลิงก์ช่วงนี้",
  "เปิดในยูทูปตรงเวลานี้",
  "เล่นจากตรงนี้",
  "ถ่ายภาพคมตรงนี้",
  "ตั้งเป็นจุดเริ่ม",
  "ตั้งเป็นจุดจบ",
]
const MENU_WITH_SUBS = [...M2_MENU, "ดูซับช่วงนี้"]
// ภาพเฟรมของคลิปนี้ห่างกัน 4895 ms: ภาพที่ใกล้ 10 วินาทีที่สุดคือ 9790 ms (00:00:09)
const FRAME_NEAR_10S = "00:00:09"
const FRAME_NEAR_10S_MS = 9790

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
// ปุ่มข้อความของบรรทัด (ไปภาพเฟรม) ไม่รวมปุ่มเวลา "เล่นจากตรงนี้ …" หน้าบรรทัด (M3.5)
const lineText = (item: ReturnType<typeof lineItems>) => item.locator("button:not([aria-label])")
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
  // มาด้วยการคลิกเมาส์ (ไม่ใช่วงโฟกัสจากคีย์บอร์ด): ต้องเห็นกรอบไฮไลต์ = outline ทึบ 2px เว้นช่อง 1px สี --accent-text
  await expect(highlighted).toHaveCSS("outline-style", "solid")
  await expect(highlighted).toHaveCSS("outline-width", "2px")
  await expect(highlighted).toHaveCSS("outline-offset", "1px")
  const colors = await highlighted.evaluate((element) => ({
    outline: getComputedStyle(element).outlineColor,
    accent: getComputedStyle(document.documentElement).getPropertyValue("--accent-text").trim(),
  }))
  expect(colors.outline).toBe(hexToRgb(colors.accent))
  const timeOf = (alt: string | null) => toMs(/\d{2}:\d{2}:\d{2}/.exec(alt ?? "")?.[0] ?? "")
  const chosen = timeOf(await highlighted.locator("img").getAttribute("alt"))
  const all = (await frameList(page).locator("img").evaluateAll((imgs) => imgs.map((img) => img.getAttribute("alt")))).map(
    timeOf,
  )
  // เป็นภาพที่ใกล้ at ที่สุดในทุกภาพ (เวลาหลังภาพสุดท้าย = ภาพสุดท้าย) · timecode ตัดเศษวินาทีทิ้ง จึงเผื่อ 1 วินาที
  const best = Math.min(...all.map((t) => Math.abs(t - at)))
  expect(Math.abs(chosen - at)).toBeLessThanOrEqual(best + 1000)
}

/** "#9a6200" → "rgb(154, 98, 0)" (รูปแบบที่ getComputedStyle คืนมา) */
function hexToRgb(hex: string): string {
  const n = Number.parseInt(hex.replace("#", ""), 16)
  return `rgb(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255})`
}

function atFromUrl(page: Page): number {
  return Number(new URL(page.url()).searchParams.get("at"))
}

test.describe("M3 ทรานสคริปต์: ค้นหา (FR-SUB-8)", () => {
  test("พิมพ์ 'กรุงเทพ' → 'พบ N บรรทัด' และทุกบรรทัดที่เห็นมีคำนี้ถูกเน้นด้วย mark", async ({ page }) => {
    await mockThai(page)
    await page.goto(`/v/${THAI}?tab=transcript`)
    await expect(page.getByText("จากแทร็ก ไทย (อัตโนมัติ)", { exact: false })).toBeVisible()
    // ป้ายแทร็กขึ้นก่อนรายการบรรทัดวาดเสร็จได้ (เครื่องช้า): รอให้มีบรรทัดก่อนนับ ไม่นับทันที
    await expect.poll(() => lineItems(page).count()).toBeGreaterThan(3)

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
    // คำค้นใช้ useDeferredValue: รอให้รายการกรองเสร็จ (บรรทัดแรกมีคำที่ไฮไลต์) ก่อนอ่านเวลา
    await expect(lineItems(page).first().locator("mark").first()).toBeVisible()
    const first = lineItems(page).first()
    const time = (await first.locator(".font-mono").textContent()) ?? ""
    await lineText(first).click()

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
    await lineText(lineItems(page).last()).click()
    await expect(page).toHaveURL(/\?at=\d+$/)
    await expectHighlightedFrameNear(page, atFromUrl(page))
  })
})

test.describe("M3 ทรานสคริปต์: บรรทัดของเวลา at ระหว่างค้นหา", () => {
  // เวลากลางคลิป: บรรทัดนี้อยู่ลึกในรายการ (ต้องเลื่อนกรอบถึงจะเห็น) และไม่มีคำว่า กรุงเทพ
  const DEEP_AT = 200_000

  test("ค้นไม่เจอแล้วลบตัวอักษรจนเจออีกครั้ง → โฟกัสยังอยู่ที่ช่องค้นหา ไม่ถูกดึงไปที่บรรทัด", async ({ page }) => {
    await mockThai(page)
    await page.goto(`/v/${THAI}?tab=transcript&at=${DEEP_AT}`)
    await expect(currentLine(page)).toBeFocused()
    await searchBox(page).click()
    await page.keyboard.type("กรุงเทพz")
    await expect(page.getByText("ไม่พบคำนี้ในทรานสคริปต์")).toBeVisible()
    await page.keyboard.press("Backspace")
    await expect(page.getByText(/^พบ \d+ บรรทัด$/)).toBeVisible()
    await expect(searchBox(page)).toBeFocused()
    // รอให้เฟรมถัดไปผ่าน (ถ้าจะแย่งโฟกัสก็เกิดตอนนั้น) แล้วตรวจอีกครั้ง
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))))
    await expect(searchBox(page)).toBeFocused()
    await expect(searchBox(page)).toHaveValue("กรุงเทพ")
  })

  test("ล้างคำค้น → บรรทัดของเวลา at กลับมาอยู่กลางกรอบรายการ โดยโฟกัสยังอยู่ที่ช่องค้นหา (M5)", async ({ page }) => {
    await mockThai(page)
    await page.goto(`/v/${THAI}?tab=transcript&at=${DEEP_AT}`)
    await expect(currentLine(page)).toBeFocused()
    await expect(currentLine(page)).toBeInViewport()

    await searchBox(page).fill("กรุงเทพ")
    await expect(page.getByText(/^พบ \d+ บรรทัด$/)).toBeVisible()
    // บรรทัดของ at ไม่มีคำนี้ จึงถูกซ่อนระหว่างค้นหา (และรายการที่สั้นลงเลื่อนกลับไปบนสุด)
    await expect(currentLine(page)).toHaveCount(0)

    await page.getByRole("button", { name: "ล้างคำค้น" }).click()
    await expect(currentLine(page)).toHaveCount(1)
    await expect(currentLine(page)).toBeInViewport()
    await expect(searchBox(page)).toBeFocused()
    const offCenter = await currentLine(page).evaluate((line) => {
      const viewport = line.closest('[data-slot="scroll-area-viewport"]')
      if (!viewport) return Infinity
      const box = line.getBoundingClientRect()
      const frame = viewport.getBoundingClientRect()
      return Math.abs(box.top + box.height / 2 - (frame.top + frame.height / 2))
    })
    expect(offCenter).toBeLessThan(40)
  })
})

test.describe("M3 ภาพเฟรม → ทรานสคริปต์ (Q6 = ก)", () => {
  test(`คลิกขวาภาพ ${FRAME_NEAR_10S} → เมนูมี 9 รายการ สุดท้ายคือ 'ดูซับช่วงนี้' → บรรทัดของเวลานั้นถูกไฮไลต์และเห็นในจอ`, async ({
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
    for (let i = 0; i < MENU_WITH_SUBS.indexOf("ดูซับช่วงนี้"); i++) await page.keyboard.press("ArrowDown")
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
  test("คลิปไม่มีซับ: เมนูภาพเฟรมไม่มี 'ดูซับช่วงนี้' (8 รายการ) · แท็บทรานสคริปต์บอก 'คลิปนี้ไม่มีซับ'", async ({ page }) => {
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

test.describe("M3 ทรานสคริปต์: แทร็กที่อ่านไม่ได้", () => {
  test("แทร็กที่อ่านแล้วไม่มีข้อความ (E_NO_SUBTITLES) → 'คลิปนี้ไม่มีซับ' แบบเดียวกับแท็บซับ ไม่มีกล่อง error และปุ่มลองใหม่", async ({
    page,
  }) => {
    await page.route(`**/api/videos/${THAI}/subtitles/*/tokens`, (route) =>
      route.fulfill({ status: 404, json: { error: { code: "E_NO_SUBTITLES", message: NO_SUBS, detail: null } } }),
    )
    await page.goto(`/v/${THAI}?tab=transcript`)
    await expect(page.getByText(NO_SUBS)).toBeVisible()
    await expect(page.getByText("โหลดซับไม่สำเร็จ")).toHaveCount(0)
    await expect(page.getByRole("button", { name: "ลองใหม่" })).toHaveCount(0)
  })

  test("ซับแปลที่ยูทูปไม่ให้โหลด → ข้อความตรง ๆ + 'ใช้ซับภาษาต้นฉบับ' → ทรานสคริปต์ภาษาไทยในแท็บเดิม", async ({ page }) => {
    const blocked = "ยูทูปยังไม่ให้โหลดซับแปลอัตโนมัติในตอนนี้ เลือกซับภาษาต้นฉบับแทน"
    await page.route(`**/api/videos/${THAI}/subtitles/t.en/tokens`, (route) =>
      route.fulfill({ status: 503, json: { error: { code: "E_TRANSLATION_BLOCKED", message: blocked, detail: null } } }),
    )
    await page.goto(`/v/${THAI}?tab=transcript&track=t.en`)
    await expect(page.getByText(blocked)).toBeVisible()
    await expect(page.getByRole("button", { name: "ลองใหม่" })).toHaveCount(0)
    await page.getByRole("button", { name: "ใช้ซับภาษาต้นฉบับ" }).click()
    await expect(page).toHaveURL(/[?&]track=a\.th-orig(&|$)/)
    await expect(tab(page, "ทรานสคริปต์")).toHaveAttribute("aria-selected", "true")
    await expect(lineItems(page).first()).toContainText("สวัสดี")
    await expect(page.getByText(blocked)).toHaveCount(0)
    // ปุ่มหายไปแล้ว: โฟกัสอยู่ที่แผงของแท็บทรานสคริปต์ (ไม่หลุดไป body) Tab ถัดไปถึงช่องค้นหา
    await expect(page.getByRole("tabpanel", { name: "ทรานสคริปต์" })).toBeFocused()
    expect(await page.evaluate(() => document.activeElement === document.body)).toBe(false)
    await page.keyboard.press("Tab")
    await expect(searchBox(page)).toBeFocused()
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
