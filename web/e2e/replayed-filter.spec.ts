/// <reference lib="dom" />
import AxeBuilder from "@axe-core/playwright"
import { expect, test, type Page } from "@playwright/test"

// owner round 5: ภาพเฟรมในช่วงที่คนดูซ้ำบ่อยเด่นขึ้น (กรอบอำพัน + ป้าย "ดูซ้ำบ่อย") · ตัวกรอง "ดูซ้ำบ่อย (n ภาพ)" (?replayed=1)
// · ปุ่มเวลาของช่วงดูซ้ำไม่พาไปแท็บภาพเฟรมถ้าผู้ใช้เปลี่ยนแท็บไปก่อนข้อมูลมาถึง
// mostReplayed จำลองด้วย page.route ข้อมูลส่วนอื่นมาจาก backend โหมด fake

// คลิปภาษาไทยที่มีภาพเฟรม (ห่างกัน 4895 ms)
const THAI = "88o5Sk8_m1Y"
const NEW_KEYS = ["stats", "tags", "categories", "mostReplayed"]
// 20-30 วินาที มีภาพ 24475, 29370 ms · 60-66 วินาที มีภาพ 63635 ms → 3 ภาพ
const SEGMENTS = [
  { startMs: 20_000, endMs: 30_000 },
  { startMs: 60_000, endMs: 66_000 },
]
const IN_SEGMENTS = ["ภาพเฟรมที่ 00:00:24", "ภาพเฟรมที่ 00:00:29", "ภาพเฟรมที่ 00:01:03"]
const FILTER = "ดูซ้ำบ่อย (3 ภาพ)"
const ZIP = "โหลดทั้งหมด (.zip)"

async function withVideo(page: Page, videoId: string, patch: Record<string, unknown> = {}) {
  await page.route(
    (url) => url.pathname === `/api/videos/${videoId}`,
    async (route) => {
      const response = await route.fetch()
      const body = (await response.json()) as Record<string, unknown>
      for (const key of NEW_KEYS) delete body[key]
      await route.fulfill({ response, json: { ...body, ...patch } })
    },
  )
}

const frameList = (page: Page) => page.getByRole("list", { name: "รายการภาพเฟรม" })
const filterButton = (page: Page) => page.getByRole("button", { name: /^ดูซ้ำบ่อย \(\d+ ภาพ\)$/ })
const lightbox = (page: Page) => page.getByRole("dialog")
const tab = (page: Page, name: string) => page.getByRole("tab", { name, exact: true })
const frameAlts = (page: Page) => frameList(page).locator("img").evaluateAll((imgs) => imgs.map((img) => img.getAttribute("alt")))

async function frameCount(page: Page): Promise<number> {
  const response = await page.request.get(`/api/videos/${THAI}/storyboard`)
  return ((await response.json()) as { frames: unknown[] }).frames.length
}

test.describe("แท็บภาพเฟรม: ภาพในช่วงที่คนดูซ้ำบ่อย", () => {
  test("ภาพในช่วงมีกรอบอำพันและป้ายตัวอักษร 'ดูซ้ำบ่อย' ที่เห็นได้ · ภาพอื่นไม่มีทั้งสองอย่าง · ชื่อปุ่มเหมือนเดิม", async ({ page }) => {
    await withVideo(page, THAI, { mostReplayed: SEGMENTS })
    await page.goto(`/v/${THAI}`)
    const total = await frameCount(page)
    await expect(frameList(page).getByRole("listitem")).toHaveCount(total)

    const marked = frameList(page).getByRole("button").filter({ has: page.locator("[data-replayed]") })
    await expect(marked).toHaveCount(3)
    expect(await marked.locator("img").evaluateAll((imgs) => imgs.map((img) => img.getAttribute("alt")))).toEqual(IN_SEGMENTS)
    for (let i = 0; i < 3; i += 1) {
      const button = marked.nth(i)
      const label = button.locator("[data-replayed]")
      await expect(label).toBeVisible()
      // คำที่ตาเห็น (โปรแกรมอ่านหน้าจอได้คำนี้จากข้อความซ่อนครั้งเดียว ไม่ซ้ำสองรอบ)
      const visibleText = label.locator(":scope > span[aria-hidden]")
      await expect(visibleText).toBeVisible()
      await expect(visibleText).toHaveText("ดูซ้ำบ่อย")
      await expect(button.locator("[data-replayed-frame]")).toHaveCount(1)
      await expect(button).toHaveAccessibleName(/^ภาพเฟรมที่ \d{2}:\d{2}:\d{2}\s+ดูซ้ำบ่อย$/)
    }
    // กรอบอำพันอยู่ด้านในภาพ (inset) ไม่ใช่เส้นนอกแบบภาพที่ไฮไลต์ (?at=)
    await expect(marked.first().locator("[data-replayed-frame]")).toHaveCSS("box-shadow", /inset/)

    const others = frameList(page).getByRole("button").filter({ hasNot: page.locator("[data-replayed]") })
    await expect(others).toHaveCount(total - 3)
    await expect(frameList(page).locator("[data-replayed-frame]")).toHaveCount(3)
    await expect(others.first()).toHaveAccessibleName(/^ภาพเฟรมที่ \d{2}:\d{2}:\d{2}$/)
  })
})

test.describe("แท็บภาพเฟรม: ตัวกรอง 'ดูซ้ำบ่อย'", () => {
  test("เปิด/ปิดด้วยปุ่ม aria-pressed · URL ?replayed=1 แบบแทนที่ประวัติ · เวลาของภาพยังถูกต้อง · โหลดหน้าใหม่ยังกรองอยู่", async ({
    page,
  }) => {
    await withVideo(page, THAI, { mostReplayed: SEGMENTS })
    await page.goto(`/v/${THAI}`)
    const total = await frameCount(page)
    const button = filterButton(page)
    await expect(button).toHaveText(FILTER)
    await expect(button).toHaveAttribute("aria-pressed", "false")
    await expect(frameList(page).getByRole("listitem")).toHaveCount(total)
    const historyLength = await page.evaluate(() => history.length)

    await button.click()
    await expect(button).toHaveAttribute("aria-pressed", "true")
    await expect(page).toHaveURL(new RegExp(`/v/${THAI}\\?replayed=1$`))
    await expect(frameList(page).getByRole("listitem")).toHaveCount(3)
    expect(await frameAlts(page)).toEqual(IN_SEGMENTS)
    // ภาพที่เหลือทุกภาพมีป้าย
    await expect(frameList(page).locator("[data-replayed]")).toHaveCount(3)
    expect(await page.evaluate(() => history.length)).toBe(historyLength)

    await page.reload()
    await expect(filterButton(page)).toHaveAttribute("aria-pressed", "true")
    await expect(frameList(page).getByRole("listitem")).toHaveCount(3)

    await filterButton(page).click()
    await expect(filterButton(page)).toHaveAttribute("aria-pressed", "false")
    await expect(page).toHaveURL(new RegExp(`/v/${THAI}$`))
    await expect(frameList(page).getByRole("listitem")).toHaveCount(total)
  })

  test("คีย์บอร์ด: Space เปิดตัวกรอง · เมนูคลิกขวาของภาพที่กรองแล้วคัดลอกเวลาของภาพนั้นถูกต้อง", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"])
    await withVideo(page, THAI, { mostReplayed: SEGMENTS })
    await page.goto(`/v/${THAI}`)
    await filterButton(page).focus()
    await page.keyboard.press("Space")
    await expect(filterButton(page)).toHaveAttribute("aria-pressed", "true")
    // ภาพที่สองของชุดที่กรองแล้ว = 00:00:29
    const second = frameList(page).getByRole("button").nth(1)
    await second.focus()
    await page.keyboard.press("Shift+F10")
    await expect(page.getByRole("menuitem", { name: "คัดลอกภาพ" })).toBeFocused()
    await page.getByRole("menuitem", { name: "คัดลอกเวลา" }).click()
    await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe("00:00:29")
  })

  test("ภาพใหญ่ (lightbox) ←/→ เลื่อนเฉพาะภาพที่กรองแล้ว · ปิดแล้วโฟกัสกลับภาพที่ดูล่าสุด", async ({ page }) => {
    await withVideo(page, THAI, { mostReplayed: SEGMENTS })
    await page.goto(`/v/${THAI}?replayed=1`)
    await expect(frameList(page).getByRole("listitem")).toHaveCount(3)
    await frameList(page).getByRole("button").first().click()
    await expect(lightbox(page)).toHaveAttribute("aria-label", "ภาพเฟรมที่ 00:00:24")
    await page.keyboard.press("ArrowRight")
    await expect(lightbox(page)).toHaveAttribute("aria-label", "ภาพเฟรมที่ 00:00:29")
    // ข้ามภาพ 00:00:34 ... 00:00:58 ที่ถูกกรองออก
    await page.keyboard.press("ArrowRight")
    await expect(lightbox(page)).toHaveAttribute("aria-label", "ภาพเฟรมที่ 00:01:03")
    // ภาพสุดท้ายของชุดที่กรอง: กดต่อไม่ไปไหน
    await page.keyboard.press("ArrowRight")
    await expect(lightbox(page)).toHaveAttribute("aria-label", "ภาพเฟรมที่ 00:01:03")
    await page.keyboard.press("ArrowLeft")
    await expect(lightbox(page)).toHaveAttribute("aria-label", "ภาพเฟรมที่ 00:00:29")
    await page.keyboard.press("Escape")
    await expect(lightbox(page)).toHaveCount(0)
    await expect(frameList(page).getByRole("button", { name: /^ภาพเฟรมที่ 00:00:29/ })).toBeFocused()
  })

  test("'โหลดทั้งหมด (.zip)' ไม่ขึ้นกับตัวกรอง: ชื่อปุ่มเดิม คำขอเดิม (ไม่มีพารามิเตอร์) ได้ไฟล์ .zip", async ({ page }) => {
    await withVideo(page, THAI, { mostReplayed: SEGMENTS })
    await page.goto(`/v/${THAI}?replayed=1`)
    await expect(filterButton(page)).toHaveAttribute("aria-pressed", "true")
    const zipButton = page.getByRole("button", { name: ZIP, exact: true })
    await expect(zipButton).toHaveText(ZIP)
    const request = page.waitForRequest((r) => new URL(r.url()).pathname === `/api/videos/${THAI}/storyboard/frames.zip`)
    const download = page.waitForEvent("download")
    await zipButton.click()
    expect(new URL((await request).url()).search).toBe("")
    expect((await download).suggestedFilename()).toMatch(/\.zip$/)
  })

  test("?replayed=1 แต่คลิปไม่มีช่วงดูซ้ำ: ไม่สนใจ เห็นทุกภาพ และไม่มีปุ่มกรอง", async ({ page }) => {
    await withVideo(page, THAI)
    await page.goto(`/v/${THAI}?replayed=1`)
    const total = await frameCount(page)
    await expect(frameList(page).getByRole("listitem")).toHaveCount(total)
    await expect(filterButton(page)).toHaveCount(0)
    await expect(page.getByRole("button", { name: ZIP, exact: true })).toBeVisible()
  })

  test("เวลาใน URL (?at=) ชี้ภาพที่ถูกกรองออก: ปิดตัวกรองให้เห็นและไฮไลต์ภาพนั้น", async ({ page }) => {
    await withVideo(page, THAI, { mostReplayed: SEGMENTS })
    await page.goto(`/v/${THAI}?at=9790&replayed=1`)
    const highlighted = frameList(page).locator("[data-highlighted]")
    await expect(highlighted).toHaveCount(1)
    await expect(highlighted.locator("img")).toHaveAttribute("alt", "ภาพเฟรมที่ 00:00:09")
    await expect(filterButton(page)).toHaveAttribute("aria-pressed", "false")
    await expect(page).toHaveURL(new RegExp(`/v/${THAI}\\?at=9790$`))
  })

  test("ไปภาพของ chapter (?at= นอกช่วง) แล้วกดเปิดตัวกรอง: เปิดติด (ล้างเวลา) เห็นเฉพาะภาพที่มีป้าย (fix round 1)", async ({ page }) => {
    // chapter เริ่ม 10 วินาที (?at=10000) → ภาพที่ใกล้ที่สุด 9790 ms (00:00:09) อยู่นอกช่วงดูซ้ำ
    await withVideo(page, THAI, { mostReplayed: SEGMENTS, chapters: [{ startS: 10, endS: 50, title: "ตอนแรก" }] })
    await page.goto(`/v/${THAI}?tab=info`)
    await page.getByRole("button", { name: "ไปภาพเฟรมช่วง 00:00:10" }).click()
    await expect(page).toHaveURL(new RegExp(`/v/${THAI}\\?at=10000$`))
    await expect(frameList(page).locator("[data-highlighted] img")).toHaveAttribute("alt", "ภาพเฟรมที่ 00:00:09")

    await filterButton(page).click()
    await expect(filterButton(page)).toHaveAttribute("aria-pressed", "true")
    await expect(page).toHaveURL(new RegExp(`/v/${THAI}\\?replayed=1$`))
    await expect(frameList(page).getByRole("listitem")).toHaveCount(3)
    expect(await frameAlts(page)).toEqual(IN_SEGMENTS)
    // ไม่ปิดตัวเองตามมาทีหลัง
    await page.waitForTimeout(300)
    await expect(filterButton(page)).toHaveAttribute("aria-pressed", "true")
    await expect(frameList(page).locator("[data-replayed]")).toHaveCount(3)

    // กรองอยู่แล้วไป chapter อีกครั้ง (เวลาใหม่ชี้ภาพที่ถูกกรองออก): ตัวกรองปิดให้เห็นภาพนั้น
    await tab(page, "ข้อมูลคลิป").click()
    await page.getByRole("button", { name: "ไปภาพเฟรมช่วง 00:00:10" }).click()
    await expect(frameList(page).locator("[data-highlighted] img")).toHaveAttribute("alt", "ภาพเฟรมที่ 00:00:09")
    await expect(filterButton(page)).toHaveAttribute("aria-pressed", "false")
    await expect(page).toHaveURL(new RegExp(`/v/${THAI}\\?at=10000$`))
  })

  test("จอ 360 px: ปุ่มตัวกรองและปุ่มโหลดทั้งสองสูงอย่างน้อย 44 px และหน้าไม่ล้นจอ (fix round 1)", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 800 })
    await withVideo(page, THAI, { mostReplayed: SEGMENTS })
    await page.goto(`/v/${THAI}`)
    for (const button of [filterButton(page), page.getByRole("button", { name: "โหลดภาพรวมเฟรม" }), page.getByRole("button", { name: ZIP, exact: true })]) {
      await expect(button).toBeVisible()
      expect((await button.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(44)
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360)
  })

  for (const scheme of ["dark", "light"] as const) {
    test(`เปิดตัวกรองแล้วไม่มีปัญหาระดับ serious/critical (${scheme})`, async ({ page }) => {
      await withVideo(page, THAI, { mostReplayed: SEGMENTS })
      await page.emulateMedia({ colorScheme: scheme })
      await page.goto(`/v/${THAI}?replayed=1`)
      await expect(page.locator("html")).toHaveClass(scheme === "dark" ? /dark/ : /light/)
      await expect(frameList(page).getByRole("listitem")).toHaveCount(3)
      await expect(frameList(page).locator("[data-replayed]").first()).toBeVisible()
      const results = await new AxeBuilder({ page }).analyze()
      const serious = results.violations
        .filter((v) => v.impact === "serious" || v.impact === "critical")
        .map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target.join(" ")).slice(0, 5) }))
      expect(serious).toEqual([])
    })
  }
})

test.describe("แท็บข้อมูลคลิป: ปุ่มเวลาของช่วงดูซ้ำระหว่างรอข้อมูล", () => {
  test("กดเวลาแล้วเปลี่ยนแท็บก่อน storyboard มาถึง: อยู่แท็บใหม่ ไม่ถูกพาไปแท็บภาพเฟรม · ระหว่างรอปุ่มขึ้น aria-busy", async ({
    page,
  }) => {
    await withVideo(page, THAI, { mostReplayed: SEGMENTS })
    let release: () => void = () => {}
    const gate = new Promise<void>((resolve) => (release = resolve))
    let delayed = false
    await page.route(
      (url) => url.pathname === `/api/videos/${THAI}/storyboard`,
      async (route) => {
        if (!delayed) {
          delayed = true
          await gate
        }
        await route.continue()
      },
    )
    await page.goto(`/v/${THAI}?tab=info`)
    const time = page.getByRole("button", { name: "ไปภาพเฟรมช่วง 00:01:00" })
    await time.click()
    await expect(time).toHaveAttribute("aria-busy", "true")
    await expect(tab(page, "ข้อมูลคลิป")).toHaveAttribute("aria-selected", "true")

    await tab(page, "ซับ").click()
    await expect(tab(page, "ซับ")).toHaveAttribute("aria-selected", "true")
    const response = page.waitForResponse((r) => new URL(r.url()).pathname === `/api/videos/${THAI}/storyboard`)
    release()
    await response
    await page.waitForTimeout(500)
    await expect(tab(page, "ซับ")).toHaveAttribute("aria-selected", "true")
    await expect(page).toHaveURL(new RegExp(`/v/${THAI}\\?tab=subs$`))

    // กลับมาแท็บข้อมูลคลิป ปุ่มไม่ค้างสถานะรอ และกดแล้วไปภาพเฟรมได้ตามปกติ (storyboard อยู่ใน cache แล้ว)
    await tab(page, "ข้อมูลคลิป").click()
    await expect(time).not.toHaveAttribute("aria-busy", "true")
    await time.click()
    await expect(page).toHaveURL(new RegExp(`/v/${THAI}\\?at=63635$`))
  })
})
