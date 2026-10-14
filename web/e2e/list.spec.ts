/// <reference lib="dom" />
import fs from "node:fs"
import path from "node:path"

import { analyzeSettled } from "./axe-settled"
import { expect, test, type Page } from "@playwright/test"

// ความเห็นเจ้าของรอบ 2 (2026-09-30): ลิงก์ในข้อความแชต, กางคลิปในเพลย์ลิสต์, คลิปก่อนหน้า/ถัดไป,
// เลือกข้อความเดิมเมื่อกลับมา และรายการของ W1 ไม่หายเมื่อวางลิงก์ที่ W2 แล้วยกเลิก/ล้มเหลว

const BBB = "aqz-KE-bpKQ"
const ZOO = "jNQXAC9IVRw"
const THIRD = "vid00000003"
const PLAYLIST_ID = "PLfakeplaylist250"
const PLAYLIST_URL = `https://www.youtube.com/playlist?list=${PLAYLIST_ID}`
const MIX_ID = "RDaqz-KE-bpKQ"
const MIX_URL = `https://www.youtube.com/watch?v=${BBB}&list=${MIX_ID}&start_radio=1`
const RESULT_ROWS = 'section[aria-labelledby="results-title"] [role="listitem"]'
const OPENED = "เปิดดูแล้ว"
const PLAYLIST_TITLE: string = JSON.parse(
  fs.readFileSync(path.join(import.meta.dirname, "../../tests/fixtures/playlist", `${PLAYLIST_ID}.json`), "utf8"),
).title
const THREE_LINKS = [`https://youtu.be/${BBB}`, `https://youtu.be/${ZOO}`, PLAYLIST_URL].join("\n")
const LINE_MESSAGE = [
  "สวัสดีครับ ส่งคลิปให้ดูครับ",
  `1. https://youtu.be/${BBB}`,
  `2. https://www.youtube.com/watch?v=${ZOO} ขอบคุณครับ`,
].join("\n")

const PIXEL = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
)

const rows = (page: Page) => page.locator(RESULT_ROWS)
const crumbs = (page: Page) => page.getByRole("navigation", { name: "ตำแหน่งของหน้านี้" })
const sequence = (page: Page) => page.getByRole("navigation", { name: "คลิปในรายการ" })
const heading = (page: Page) => page.getByRole("heading", { level: 1 })

async function analyze(page: Page, text: string) {
  await page.goto("/")
  await page.getByRole("textbox").fill(text)
  await page.getByRole("button", { name: "วิเคราะห์" }).click()
}

async function pasteThree(page: Page) {
  await analyze(page, THREE_LINKS)
  await expect(rows(page)).toHaveCount(3)
  await expect(rows(page).nth(1)).toContainText("Me at the zoo")
}

async function expectThreeIntact(page: Page) {
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole("textbox")).toHaveValue(THREE_LINKS)
  await expect(rows(page)).toHaveCount(3)
  await expect(rows(page).nth(0)).toContainText("Big Buck Bunny")
  await expect(rows(page).nth(1)).toContainText("Me at the zoo")
  await expect(rows(page).nth(2)).toContainText(PLAYLIST_TITLE)
}

async function pasteOnPage(page: Page, text: string) {
  await page.evaluate((value) => navigator.clipboard.writeText(value), text)
  await page.locator("body").click({ position: { x: 5, y: 400 } })
  await page.keyboard.press("Control+V")
}

async function seriousViolations(page: Page) {
  const results = await analyzeSettled(page)
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.map((n) => n.target.join(" ")).slice(0, 5) }))
}

/** คลิปที่สามของลำดับ: backend โหมดข้อมูลปลอมมีแค่สองคลิป จึงตอบแทนจากหน้าเว็บ (ไม่มีภาพเฟรม) */
async function routeThirdClip(page: Page) {
  await page.route(`**/api/videos/${THIRD}*`, (route) =>
    route.fulfill({
      json: {
        videoId: THIRD,
        title: "คลิปทดสอบที่สาม",
        channel: "ช่องทดสอบ",
        durationS: 60,
        thumbnailUrl: "",
        chapters: [],
        video: [],
        audio: [],
        hasStoryboard: false,
        isLive: false,
      },
    }),
  )
  await page.route(`**/api/videos/${THIRD}/storyboard`, (route) =>
    route.fulfill({
      status: 404,
      json: { error: { code: "E_NO_STORYBOARD", message: "คลิปนี้ไม่มีภาพตัวอย่าง", detail: null } },
    }),
  )
}

test.describe("รายการของ W1 ไม่หายเมื่อวางลิงก์ที่ W2 แล้วไม่สำเร็จ", () => {
  test.beforeEach(async ({ context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"])
  })

  test("วางลิงก์ที่ต้องถามที่ W2 แล้วกด Esc → breadcrumb ยังมี 'รายการที่วาง' · ย้อนกลับได้ 3 แถวกับข้อความเดิม", async ({
    page,
  }) => {
    await pasteThree(page)
    await rows(page).nth(0).getByRole("link", { name: /เปิดดู/ }).click()
    await expect(heading(page)).toContainText("Big Buck Bunny")
    await pasteOnPage(page, `https://www.youtube.com/watch?v=${ZOO}&list=${PLAYLIST_ID}`)
    const dialog = page.getByRole("dialog")
    await expect(dialog).toContainText("ลิงก์นี้อยู่ในเพลย์ลิสต์")
    await page.keyboard.press("Escape")
    await expect(dialog).toHaveCount(0)
    await expect(crumbs(page)).toContainText("รายการที่วาง (3 ลิงก์)")
    await page.goBack()
    await expectThreeIntact(page)
  })

  test("วางลิงก์ที่ W2 แล้ว /resolve ล้มเหลว → breadcrumb ยังอยู่ · ย้อนกลับได้ 3 แถวกับข้อความเดิม", async ({ page }) => {
    await pasteThree(page)
    await rows(page).nth(1).getByRole("link", { name: /เปิดดู/ }).click()
    await expect(heading(page)).toContainText("Me at the zoo")
    await page.route("**/api/resolve", (route) => route.abort())
    await pasteOnPage(page, [`https://youtu.be/${BBB}`, PLAYLIST_URL].join("\n"))
    await expect(page.getByText(/วิเคราะห์ลิงก์ไม่สำเร็จ/)).toBeVisible()
    await expect(page).toHaveURL(new RegExp(`/v/${ZOO}$`))
    await expect(crumbs(page)).toContainText("รายการที่วาง (3 ลิงก์)")
    await page.goBack()
    await expectThreeIntact(page)
  })
})

test.describe("D1 ลิงก์ในข้อความที่คัดลอกมาจากแชต", () => {
  test("วางข้อความจาก LINE (ทักทาย เลขข้อ ขอบคุณ) → ได้ 2 แถวคลิป ไม่มีแถวสีแดง และบอกเบา ๆ ว่าข้ามข้อความ", async ({
    page,
  }) => {
    await analyze(page, LINE_MESSAGE)
    await expect(rows(page)).toHaveCount(2)
    await expect(rows(page).nth(0)).toContainText("Big Buck Bunny")
    await expect(rows(page).nth(1)).toContainText("Me at the zoo")
    await expect(page.getByText("ลิงก์นี้ไม่ใช่ลิงก์ยูทูป")).toHaveCount(0)
    const note = page.getByText("ข้ามข้อความที่ไม่ใช่ลิงก์")
    await expect(note).toBeVisible()
    await expect(note).toHaveClass(/text-muted-foreground/)
  })

  test("กด Ctrl+V ข้อความจาก LINE นอกช่องกรอก → วิเคราะห์ทันที ได้ 2 แถว", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"])
    await page.goto("/")
    await pasteOnPage(page, LINE_MESSAGE)
    await expect(rows(page)).toHaveCount(2)
    await expect(page.getByRole("textbox")).toHaveValue(LINE_MESSAGE)
  })

  test("ลิงก์สะอาดล้วน ๆ ไม่มีบรรทัด 'ข้ามข้อความ'", async ({ page }) => {
    await pasteThree(page)
    await expect(page.getByText("ข้ามข้อความที่ไม่ใช่ลิงก์")).toHaveCount(0)
  })

  test("ข้อความที่ไม่มีลิงก์เลย → ข้อความเดิม 'ไม่พบลิงก์ในข้อความที่วาง'", async ({ page }) => {
    await analyze(page, "สวัสดีครับ\nขอบคุณครับ")
    await expect(page.getByText("ไม่พบลิงก์ในข้อความที่วาง")).toBeVisible()
    await expect(rows(page)).toHaveCount(0)
  })
})

test.describe("D2 กางรายชื่อคลิปในแถวเพลย์ลิสต์/มิกซ์", () => {
  test("กาง 'ดูคลิปในเพลย์ลิสต์' → 50 คลิป + แสดงเพิ่ม · เปิดคลิปแล้วย้อนกลับยังกางอยู่ พร้อมป้าย 'เปิดดูแล้ว'", async ({
    page,
  }) => {
    await page.route("https://i.ytimg.com/**", (route) => route.fulfill({ contentType: "image/png", body: PIXEL }))
    await pasteThree(page)
    const row = rows(page).nth(2)
    const toggle = row.getByRole("button", { name: "ดูคลิปในเพลย์ลิสต์" })
    await expect(toggle).toHaveAttribute("aria-expanded", "false")
    const panelId = await toggle.getAttribute("aria-controls")
    await toggle.click()
    const hide = row.getByRole("button", { name: "ซ่อนรายชื่อคลิป" })
    await expect(hide).toHaveAttribute("aria-expanded", "true")
    const list = row.getByRole("list", { name: `คลิปใน ${PLAYLIST_TITLE}` })
    await expect(page.locator(`[id="${panelId}"]`)).toBeVisible()
    await expect(list.getByRole("link")).toHaveCount(50)
    // แถวในรายการผลยังนับเท่าเดิม (รายชื่อคลิปไม่ใช่แถวผล)
    await expect(rows(page)).toHaveCount(3)
    const first = list.getByRole("link").first()
    await expect(first).toContainText("1:01")
    await expect(first.locator("img")).toHaveAttribute("loading", "lazy")
    await expect(first.locator("img")).toHaveAttribute("src", "https://i.ytimg.com/vi/fake0000001/mqdefault.jpg")
    await row.getByRole("button", { name: "แสดงเพิ่ม" }).click()
    await expect(list.getByRole("link")).toHaveCount(100)
    await expect(row).toContainText("แสดง 100 จาก 200 คลิป")

    const second = list.getByRole("link").nth(1)
    await expect(second).toHaveAttribute("href", "/v/fake0000002")
    await second.click()
    await expect(page).toHaveURL(/\/v\/fake0000002$/)
    await expect(crumbs(page)).toContainText("รายการที่วาง (3 ลิงก์)")
    await page.goBack()
    await expect(hide).toHaveAttribute("aria-expanded", "true")
    await expect(list.getByRole("link")).toHaveCount(100)
    await expect(list.getByRole("link").nth(1)).toContainText(OPENED)
    await expect(list.getByRole("link").nth(0)).not.toContainText(OPENED)
    // โหลดหน้าใหม่ก็ยังกางอยู่
    await page.reload()
    await expect(list.getByRole("link")).toHaveCount(100)
    // พับเก็บ
    await hide.click()
    await expect(row.getByRole("button", { name: "ดูคลิปในเพลย์ลิสต์" })).toHaveAttribute("aria-expanded", "false")
    await expect(list).toHaveCount(0)
  })

  test("แถวมิกซ์ก็กางได้ (25 คลิปแรก ไม่มีแสดงเพิ่ม) · เปิดคลิปแล้วย้อนกลับยังกางอยู่ พร้อมป้าย 'เปิดดูแล้ว'", async ({
    page,
  }) => {
    await page.route("https://i.ytimg.com/**", (route) => route.fulfill({ contentType: "image/png", body: PIXEL }))
    await analyze(page, [MIX_URL, `https://youtu.be/${ZOO}`].join("\n"))
    await rows(page).first().getByRole("button", { name: "ทั้งมิกซ์ (25 คลิปแรก)" }).click()
    const row = rows(page).first()
    await expect(row).toContainText("มิกซ์ - Big Buck Bunny")
    await row.getByRole("button", { name: "ดูคลิปในเพลย์ลิสต์" }).click()
    const list = row.getByRole("list", { name: "คลิปใน มิกซ์ - Big Buck Bunny" })
    await expect(list.getByRole("link")).toHaveCount(25)
    await expect(row.getByRole("button", { name: "แสดงเพิ่ม" })).toHaveCount(0)
    await list.getByRole("link").nth(1).click()
    await expect(heading(page)).toContainText("Me at the zoo")
    await page.goBack()
    await expect(row.getByRole("button", { name: "ซ่อนรายชื่อคลิป" })).toHaveAttribute("aria-expanded", "true")
    await expect(list.getByRole("link").nth(1)).toContainText(OPENED)
  })

  for (const scheme of ["dark", "light"] as const) {
    test(`axe: หน้าแรกตอนกางรายชื่อคลิปไม่มีปัญหาระดับ serious/critical (${scheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme })
      await page.route("https://i.ytimg.com/**", (route) => route.fulfill({ contentType: "image/png", body: PIXEL }))
      await analyze(page, LINE_MESSAGE + "\n" + PLAYLIST_URL)
      await rows(page).nth(2).getByRole("button", { name: "ดูคลิปในเพลย์ลิสต์" }).click()
      await expect(rows(page).nth(2).getByRole("list").getByRole("link")).toHaveCount(50)
      await expect(page.locator("html")).toHaveClass(scheme === "dark" ? /dark/ : /light/)
      expect(await seriousViolations(page)).toEqual([])
    })
  }
})

test.describe("D3 คลิปก่อนหน้า/ถัดไปที่ W2", () => {
  const LIST = [`https://youtu.be/${BBB}`, "https://vimeo.com/123", PLAYLIST_URL, `https://youtu.be/${ZOO}`, THIRD]

  async function openFirst(page: Page) {
    await routeThirdClip(page)
    await analyze(page, LIST.join("\n"))
    await expect(rows(page)).toHaveCount(5)
    await rows(page).nth(0).getByRole("link", { name: /เปิดดู/ }).click()
    await expect(heading(page)).toContainText("Big Buck Bunny")
  }

  test("เปิด #1 → ถัดไป #2 → ถัดไป #3 (ถัดไปจาง) → ก่อนหน้า #2 · ข้ามแถวลิงก์ผิดและแถวเพลย์ลิสต์ · ย้อนกลับเห็นเปิดแล้วครบสาม", async ({
    page,
  }) => {
    await openFirst(page)
    const nav = sequence(page)
    await expect(nav).toContainText("1 จาก 3")
    await expect(nav.getByText("คลิปที่ 1 จาก 3")).toHaveClass(/sr-only/)
    await expect(nav.getByRole("button", { name: "ก่อนหน้า" })).toHaveAttribute("aria-disabled", "true")

    await nav.getByRole("button", { name: "ถัดไป" }).click()
    await expect(page).toHaveURL(new RegExp(`/v/${ZOO}$`))
    await expect(heading(page)).toContainText("Me at the zoo")
    await expect(heading(page)).toBeFocused()
    await expect(nav).toContainText("2 จาก 3")
    await expect(crumbs(page)).toContainText("รายการที่วาง (5 ลิงก์)")

    await nav.getByRole("button", { name: "ถัดไป" }).click()
    await expect(page).toHaveURL(new RegExp(`/v/${THIRD}$`))
    await expect(heading(page)).toContainText("คลิปทดสอบที่สาม")
    await expect(nav).toContainText("3 จาก 3")
    const next = nav.getByRole("button", { name: "ถัดไป" })
    await expect(next).toHaveAttribute("aria-disabled", "true")
    await next.click({ force: true })
    await expect(page).toHaveURL(new RegExp(`/v/${THIRD}$`))

    await nav.getByRole("button", { name: "ก่อนหน้า" }).click()
    await expect(page).toHaveURL(new RegExp(`/v/${ZOO}$`))
    await expect(nav).toContainText("2 จาก 3")

    // ไปคลิปอื่นแทนที่ประวัติ: ย้อนกลับครั้งเดียวถึงหน้ารายการ
    await page.goBack()
    await expect(page).toHaveURL(/\/$/)
    await expect(rows(page)).toHaveCount(5)
    for (const index of [0, 3, 4]) await expect(rows(page).nth(index)).toContainText(OPENED)
  })

  test("ไปคลิปถัดไปแล้วเลื่อนขึ้นบนสุด", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 500 })
    await openFirst(page)
    await expect(page.getByRole("list", { name: "รายการภาพเฟรม" }).getByRole("listitem")).toHaveCount(128)
    await page.evaluate(() => window.scrollTo(0, 400))
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(100)
    await sequence(page).getByRole("button", { name: "ถัดไป" }).evaluate((button: HTMLElement) => button.click())
    await expect(heading(page)).toContainText("Me at the zoo")
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0)
  })

  test("ปุ่มก่อนหน้า/ถัดไปสูงอย่างน้อย 44 px · อยู่แถวเดียวกับ breadcrumb บนจอกว้าง และลงบรรทัดใหม่บนจอแคบ", async ({ page }) => {
    await openFirst(page)
    const next = sequence(page).getByRole("button", { name: "ถัดไป" })
    expect((await next.boundingBox())!.height).toBeGreaterThanOrEqual(44)
    const crumbBox = (await crumbs(page).boundingBox())!
    const navBox = (await sequence(page).boundingBox())!
    expect(navBox.x).toBeGreaterThan(crumbBox.x + crumbBox.width - 1)
    expect(Math.abs(navBox.y + navBox.height / 2 - (crumbBox.y + crumbBox.height / 2))).toBeLessThan(12)

    await page.setViewportSize({ width: 360, height: 740 })
    const narrowCrumb = (await crumbs(page).boundingBox())!
    const narrowNav = (await sequence(page).boundingBox())!
    expect(narrowNav.y).toBeGreaterThanOrEqual(narrowCrumb.y + narrowCrumb.height - 1)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360)
  })

  test("เปิดคลิปจากรายชื่อที่กางใต้แถวเพลย์ลิสต์ → ลำดับเป็นคลิปในเพลย์ลิสต์นั้น", async ({ page }) => {
    await page.route("https://i.ytimg.com/**", (route) => route.fulfill({ contentType: "image/png", body: PIXEL }))
    await analyze(page, [MIX_URL, `https://youtu.be/${ZOO}`].join("\n"))
    await rows(page).first().getByRole("button", { name: "ทั้งมิกซ์ (25 คลิปแรก)" }).click()
    await rows(page).first().getByRole("button", { name: "ดูคลิปในเพลย์ลิสต์" }).click()
    await rows(page).first().getByRole("list").getByRole("link").first().click()
    await expect(heading(page)).toContainText("Big Buck Bunny")
    await expect(sequence(page)).toContainText("1 จาก 25")
    await sequence(page).getByRole("button", { name: "ถัดไป" }).click()
    await expect(heading(page)).toContainText("Me at the zoo")
    await expect(sequence(page)).toContainText("2 จาก 25")
  })

  test("เปิดคลิปตรง ๆ ด้วย URL → ไม่มีปุ่มก่อนหน้า/ถัดไป", async ({ page }) => {
    await pasteThree(page)
    await page.goto(`/v/${BBB}`)
    await expect(heading(page)).toContainText("Big Buck Bunny")
    await expect(sequence(page)).toHaveCount(0)
    await expect(page.getByRole("button", { name: "ถัดไป" })).toHaveCount(0)
  })

  for (const scheme of ["dark", "light"] as const) {
    test(`axe: W2 ที่มีปุ่มก่อนหน้า/ถัดไปไม่มีปัญหาระดับ serious/critical (${scheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme })
      await openFirst(page)
      await expect(sequence(page)).toBeVisible()
      await expect(page.getByRole("list", { name: "รายการภาพเฟรม" }).getByRole("listitem")).toHaveCount(128)
      await expect(page.locator("html")).toHaveClass(scheme === "dark" ? /dark/ : /light/)
      expect(await seriousViolations(page)).toEqual([])
    })
  }
})

test.describe("D5 กลับมาหน้าแรกแล้วแตะช่อง = เลือกข้อความเดิมทั้งหมด", () => {
  test.beforeEach(async ({ context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"])
  })

  const selection = (page: Page) =>
    page.getByRole("textbox").evaluate((box: HTMLTextAreaElement) => [box.selectionStart, box.selectionEnd, box.value.length])

  test("ย้อนกลับมา คลิกช่อง → เลือกทั้งหมด · วางลิงก์ใหม่ → แทนที่ข้อความและรายการเดิม", async ({ page }) => {
    await pasteThree(page)
    await rows(page).nth(0).getByRole("link", { name: /เปิดดู/ }).click()
    await expect(heading(page)).toContainText("Big Buck Bunny")
    await page.goBack()
    await expectThreeIntact(page)
    await page.getByRole("textbox").click()
    const [start, end, length] = await selection(page)
    expect([start, end]).toEqual([0, length])

    const fresh = [`https://youtu.be/${ZOO}`, PLAYLIST_URL].join("\n")
    await page.evaluate((value) => navigator.clipboard.writeText(value), fresh)
    await page.keyboard.press("Control+V")
    await expect(page.getByRole("textbox")).toHaveValue(fresh)
    await expect(rows(page)).toHaveCount(2)
    await expect(rows(page).nth(0)).toContainText("Me at the zoo")
    await expect(rows(page).nth(1)).toContainText(PLAYLIST_TITLE)
  })

  test("โหลดหน้าใหม่แล้วกด Tab เข้าช่อง ก็เลือกทั้งหมด · แตะครั้งต่อไปทำงานปกติ (วางแล้วไม่วิเคราะห์เอง)", async ({ page }) => {
    await pasteThree(page)
    await page.reload()
    await expectThreeIntact(page)
    // M6 รอบ A: ปุ่ม "วาง" อยู่ระหว่างช่องกับปุ่มวิเคราะห์ จึงเริ่มถอยจากปุ่มวาง
    await page.getByRole("button", { name: "วาง", exact: true }).focus()
    await page.keyboard.press("Shift+Tab")
    await expect(page.getByRole("textbox")).toBeFocused()
    const [start, end, length] = await selection(page)
    expect([start, end]).toEqual([0, length])

    // ครั้งที่สอง: คลิกแล้วเคอร์เซอร์อยู่ตรงที่คลิก วางแล้วต่อท้ายตามปกติ ไม่วิเคราะห์เอง
    let resolves = 0
    page.on("request", (request) => {
      if (request.url().endsWith("/api/resolve")) resolves += 1
    })
    await page.getByRole("button", { name: "วิเคราะห์" }).focus()
    await page.getByRole("textbox").click()
    const [again, againEnd] = await selection(page)
    expect(again).toBe(againEnd)
    await page.keyboard.press("Control+End")
    await page.evaluate(() => navigator.clipboard.writeText("\nhttps://youtu.be/aqz-KE-bpKQ"))
    await page.keyboard.press("Control+V")
    await expect(page.getByRole("textbox")).toHaveValue(`${THREE_LINKS}\nhttps://youtu.be/${BBB}`)
    await page.waitForTimeout(300)
    expect(resolves).toBe(0)
  })

  test("ช่องว่าง (ยังไม่เคยวาง) คลิกแล้ววางลิงก์ → ลงช่องตามปกติ ไม่วิเคราะห์เอง", async ({ page }) => {
    await page.goto("/")
    await page.getByRole("textbox").click()
    await page.evaluate((value) => navigator.clipboard.writeText(value), `https://youtu.be/${BBB}`)
    await page.keyboard.press("Control+V")
    await expect(page.getByRole("textbox")).toHaveValue(`https://youtu.be/${BBB}`)
    await expect(page).toHaveURL(/\/$/)
  })
})

test.describe("รอบแก้หลังรีวิว (2026-09-30)", () => {
  test("กด 'แสดงเพิ่ม' → โฟกัสไปคลิปแรกที่เพิ่งแสดง · ครั้งสุดท้าย (ปุ่มหายไป) โฟกัสก็ไม่หลุดไป body", async ({ page }) => {
    await page.route("https://i.ytimg.com/**", (route) => route.fulfill({ contentType: "image/png", body: PIXEL }))
    await pasteThree(page)
    const row = rows(page).nth(2)
    await row.getByRole("button", { name: "ดูคลิปในเพลย์ลิสต์" }).click()
    const links = row.getByRole("list").getByRole("link")
    await expect(links).toHaveCount(50)
    await row.getByRole("button", { name: "แสดงเพิ่ม" }).click()
    await expect(links).toHaveCount(100)
    await expect(links.nth(50)).toBeFocused()
    await row.getByRole("button", { name: "แสดงเพิ่ม" }).click()
    await row.getByRole("button", { name: "แสดงเพิ่ม" }).click()
    await expect(links).toHaveCount(200)
    await expect(row.getByRole("button", { name: "แสดงเพิ่ม" })).toHaveCount(0)
    await expect(links.nth(150)).toBeFocused()
    await expect(links.nth(150)).toHaveAttribute("href", "/v/fake0000151")
  })

  test("กดถัดไปแล้วคลิปนั้นเปิดไม่ได้ (ไม่มีชื่อคลิป) → โฟกัสไปที่กล่อง error ไม่หลุดไป body", async ({ page }) => {
    await analyze(page, [`https://youtu.be/${BBB}`, "https://youtu.be/missing0001"].join("\n"))
    await expect(rows(page)).toHaveCount(2)
    await rows(page).nth(0).getByRole("link", { name: /เปิดดู/ }).click()
    await expect(heading(page)).toContainText("Big Buck Bunny")
    await sequence(page).getByRole("button", { name: "ถัดไป" }).click()
    await expect(page).toHaveURL(/\/v\/missing0001$/)
    const error = page.getByRole("alert").filter({ hasText: "เปิดข้อมูลคลิปไม่สำเร็จ" })
    await expect(error).toBeVisible()
    await expect(error).toBeFocused()
    expect(await page.evaluate(() => document.activeElement === document.body)).toBe(false)
    await expect(sequence(page)).toContainText("2 จาก 2")
  })

  test("ภาพใหญ่โหลดไม่ได้ → ไม่ค้างเป็นพื้นมืดเปล่า เห็นกรอบภาพ และ Esc ปิดได้", async ({ page }) => {
    await page.route("**/api/cache/**", (route) => route.fulfill({ status: 404, body: "" }))
    await page.goto(`/v/${BBB}`)
    const button = page.getByRole("button", { name: "ภาพเฟรมที่ 00:00:04" })
    await button.click()
    const image = page.getByRole("dialog").locator("img")
    await expect(image).toHaveCSS("visibility", "visible")
    const box = (await image.boundingBox())!
    expect(box.width).toBeGreaterThan(100)
    expect(box.height).toBeGreaterThan(50)
    await page.keyboard.press("Escape")
    await expect(page.getByRole("dialog")).toHaveCount(0)
    await expect(button).toBeFocused()
  })

  test("กลับมาแล้วกด Tab เข้าช่อง (เลือกทั้งหมด) แล้วคลิกในช่อง → เคอร์เซอร์อยู่ตรงที่คลิกตามปกติ", async ({ page }) => {
    await pasteThree(page)
    await page.reload()
    await expectThreeIntact(page)
    // M6 รอบ A: ปุ่ม "วาง" อยู่ระหว่างช่องกับปุ่มวิเคราะห์ จึงเริ่มถอยจากปุ่มวาง
    await page.getByRole("button", { name: "วาง", exact: true }).focus()
    await page.keyboard.press("Shift+Tab")
    const box = page.getByRole("textbox")
    await expect(box).toBeFocused()
    const all = await box.evaluate((el: HTMLTextAreaElement) => [el.selectionStart, el.selectionEnd, el.value.length])
    expect([all[0], all[1]]).toEqual([0, all[2]])
    await box.click({ position: { x: 40, y: 12 } })
    const [start, end] = await box.evaluate((el: HTMLTextAreaElement) => [el.selectionStart, el.selectionEnd])
    expect(start).toBe(end)
  })

  test("จอ 360 px: หัวข้อ 'ภาพเฟรม' อยู่บรรทัดเดียว ปุ่มโหลดอยู่บรรทัดของตัวเอง ไม่ล้นจอ", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 780 })
    await page.goto(`/v/${BBB}`)
    const title = page.getByRole("heading", { name: "ภาพเฟรม" })
    await expect(title).toBeVisible()
    const titleBox = (await title.boundingBox())!
    const lineHeight = await title.evaluate((el) => parseFloat(getComputedStyle(el).lineHeight))
    expect(titleBox.height).toBeLessThan(lineHeight * 1.5)
    const sheet = (await page.getByRole("button", { name: "โหลดภาพรวมเฟรม" }).boundingBox())!
    const zip = (await page.getByRole("button", { name: "โหลดทั้งหมด (.zip)" }).boundingBox())!
    expect(sheet.y).toBeGreaterThanOrEqual(titleBox.y + titleBox.height - 1)
    expect(zip.x + zip.width).toBeLessThanOrEqual(360)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360)
  })
})

// M4 งาน 19 (Q7): ทางเข้าหน้า W3 สองทาง · spec นี้ไม่สร้างงาน (อยู่ในโปรเจกต์ chromium) แค่กดไปหน้าเลือกคลิป
test.describe("W3 ทางเข้าหน้าเลือกคลิป (Q7)", () => {
  const OPEN_BATCH = "เลือกคลิปที่จะโหลด"
  const batchLink = (scope: Page | ReturnType<typeof rows>) => scope.getByRole("link", { name: OPEN_BATCH, exact: true })

  test("ผลมีคลิป 2 แถวขึ้นไป → หัวรายการมีปุ่ม 'เลือกคลิปที่จะโหลด' กดแล้วไป /batch?src=…", async ({ page }) => {
    await pasteThree(page)
    // ปุ่มหัวรายการอยู่ก่อนปุ่มของแถวเพลย์ลิสต์ในหน้า
    const header = batchLink(page).first()
    await expect(header).toBeVisible()
    await header.click()
    await expect(page).toHaveURL(/\/batch\?src=[^&]+$/)
    await expect(heading(page)).toHaveText("หลายลิงก์")
    await expect(crumbs(page)).toContainText("รายการที่วาง (3 ลิงก์)")
    // แถวเพลย์ลิสต์ไม่เข้าตาราง: มีบรรทัดบอกทางไปเลือกที่หน้าแรก
    await expect(page.getByText("เพลย์ลิสต์ในรายการนี้เลือกคลิปได้จากปุ่มในแถวของเพลย์ลิสต์ที่หน้าแรก")).toBeVisible()
  })

  test("แถวเพลย์ลิสต์มีปุ่มของตัวเอง → /batch?src=…&playlist=<id> แสดงชื่อเพลย์ลิสต์ · แถวคลิปไม่มีปุ่มนี้", async ({ page }) => {
    await pasteThree(page)
    await expect(batchLink(rows(page).nth(0))).toHaveCount(0)
    await expect(batchLink(rows(page).nth(1))).toHaveCount(0)
    const own = batchLink(rows(page).nth(2))
    await expect(own).toBeVisible()
    await own.click()
    await expect(page).toHaveURL(new RegExp(`/batch\\?src=[^&]+&playlist=${PLAYLIST_ID}$`))
    await expect(heading(page)).toHaveText(PLAYLIST_TITLE)
  })

  test("ลิงก์คลิปเดียวกันสองแบบ (คลิปล้วน + คลิปในเพลย์ลิสต์) = คลิปเดียว → ไม่มีปุ่มที่หัวรายการ", async ({ page }) => {
    await analyze(page, [`https://youtu.be/${BBB}`, `https://www.youtube.com/watch?v=${BBB}&list=${PLAYLIST_ID}`].join("\n"))
    await expect(rows(page)).toHaveCount(2)
    await expect(batchLink(page)).toHaveCount(0)
  })

  test("คลิปแถวเดียว (อีกแถวเป็นลิงก์เสีย) → ไม่มีปุ่มที่หัวรายการ · เพลย์ลิสต์อย่างเดียว = มีแค่ปุ่มของแถว", async ({
    page,
  }) => {
    await analyze(page, [`https://youtu.be/${BBB}`, "https://vimeo.com/123"].join("\n"))
    await expect(rows(page)).toHaveCount(2)
    await expect(batchLink(page)).toHaveCount(0)

    await analyze(page, PLAYLIST_URL)
    await expect(rows(page)).toHaveCount(1)
    await expect(rows(page).first()).toContainText(PLAYLIST_TITLE)
    await expect(batchLink(page)).toHaveCount(1)
    await expect(batchLink(rows(page).first())).toBeVisible()
  })
})
