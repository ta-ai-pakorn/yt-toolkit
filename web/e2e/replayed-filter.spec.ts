/// <reference lib="dom" />
import { analyzeSettled } from "./axe-settled"
import { expect, test, type Page } from "@playwright/test"

import { expectFocusInside } from "./focus"
import { mockEnqueue } from "./queue-helpers"

// owner round 5: ภาพเฟรมในช่วงที่คนดูซ้ำบ่อยเด่นขึ้น (กรอบอำพัน + ป้าย "ดูซ้ำบ่อย") · ตัวกรอง "ดูซ้ำบ่อย (n ภาพ)" (?replayed=1)
// · ปุ่มเวลาของช่วงดูซ้ำเล่นคลิปที่หัวคลิป (M3.5) ไม่รอ storyboard และไม่พาไปแท็บภาพเฟรมแล้ว
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
// ปุ่มของตัวภาพ (เปิดภาพใหญ่) ไม่รวมปุ่ม ▶ "เล่นจากตรงนี้" ที่มุมภาพ (M3.5)
const frameButtons = (page: Page) => frameList(page).getByRole("button", { name: /^ภาพเฟรมที่/ })
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

    const marked = frameButtons(page).filter({ has: page.locator("[data-replayed]") })
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

    const others = frameButtons(page).filter({ hasNot: page.locator("[data-replayed]") })
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
    const second = frameButtons(page).nth(1)
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
    await frameButtons(page).first().click()
    await expect(lightbox(page)).toHaveAttribute("aria-label", "ภาพเฟรมที่ 00:00:24")
    // ←/→ ฟังที่ตัวภาพใหญ่: รอโฟกัสย้ายเข้าไปก่อน
    await expectFocusInside(lightbox(page))
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

  test("'โหลดทั้งหมด (.zip)' ไม่ขึ้นกับตัวกรอง: ชื่อปุ่มเดิม ส่งงานเข้าคิว frames_zip โดยไม่มีพารามิเตอร์กรอง (M4)", async ({
    page,
  }) => {
    const queue = await mockEnqueue(page)
    await withVideo(page, THAI, { mostReplayed: SEGMENTS })
    await page.goto(`/v/${THAI}?replayed=1`)
    await expect(filterButton(page)).toHaveAttribute("aria-pressed", "true")
    const zipButton = page.getByRole("button", { name: ZIP, exact: true })
    await expect(zipButton).toHaveText(ZIP)
    let downloads = 0
    page.on("download", () => (downloads += 1))
    await zipButton.click()
    await expect.poll(() => queue.bodies.length).toBe(1)
    // ตัวกรองไม่มีผล: มีแค่ source (ไม่มีช่วงเวลา ไม่มีรายการภาพ) และไม่มีไฟล์โหลดผ่านเบราว์เซอร์
    expect(queue.bodies[0]).toEqual([{ videoId: THAI, kind: "frames_zip", params: { source: "fast" } }])
    await expect(page.getByText("เพิ่มเข้าคิวแล้ว").first()).toBeVisible()
    expect(downloads).toBe(0)
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

  test("ภาพของเวลาใน URL (?at= นอกช่วง) แล้วกดเปิดตัวกรอง: เปิดติด (ล้างเวลา) เห็นเฉพาะภาพที่มีป้าย (fix round 1)", async ({ page }) => {
    // ?at=10000 → ภาพที่ใกล้ที่สุด 9790 ms (00:00:09) อยู่นอกช่วงดูซ้ำ
    // (M3.5: ปุ่มเวลาของ chapter เล่นคลิปแทนการพามาที่นี่ จึงเปิดด้วยเวลาใน URL ตรง ๆ)
    await withVideo(page, THAI, { mostReplayed: SEGMENTS })
    await page.goto(`/v/${THAI}?at=10000`)
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

    // กรองอยู่แล้วมาจากบรรทัดทรานสคริปต์ต้นคลิป (เวลาใหม่ชี้ภาพที่ถูกกรองออก): ตัวกรองปิดให้เห็นภาพนั้น
    await tab(page, "ทรานสคริปต์").click()
    const firstLine = page.getByRole("list", { name: "บรรทัดในทรานสคริปต์" }).getByRole("listitem").first()
    await firstLine.locator("button:not([aria-label])").click()
    await expect(page).toHaveURL(new RegExp(`/v/${THAI}\\?at=\\d+$`))
    await expect(frameList(page).locator("[data-highlighted]")).toHaveCount(1)
    await expect(frameList(page).locator("[data-highlighted] [data-replayed]")).toHaveCount(0)
    await expect(filterButton(page)).toHaveAttribute("aria-pressed", "false")
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
      const results = await analyzeSettled(page)
      const serious = results.violations
        .filter((v) => v.impact === "serious" || v.impact === "critical")
        .map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target.join(" ")).slice(0, 5) }))
      expect(serious).toEqual([])
    })
  }
})

test.describe("แท็บข้อมูลคลิป: ปุ่มเวลาของช่วงดูซ้ำ (M3.5)", () => {
  test("กดเวลาแล้วอยู่แท็บเดิม ไม่ขอ storyboard ไม่มีสถานะรอ · เปลี่ยนแท็บต่อก็ไม่ถูกพาไปแท็บภาพเฟรมทีหลัง", async ({ page }) => {
    await withVideo(page, THAI, { mostReplayed: SEGMENTS })
    const storyboardCalls: string[] = []
    page.on("request", (request) => {
      if (new URL(request.url()).pathname === `/api/videos/${THAI}/storyboard`) storyboardCalls.push(request.url())
    })
    await page.goto(`/v/${THAI}?tab=info`)
    const time = page.getByRole("button", { name: "เล่นจาก 00:01:00" })
    await time.click()
    await expect(time).not.toHaveAttribute("aria-busy", "true")
    await expect(tab(page, "ข้อมูลคลิป")).toHaveAttribute("aria-selected", "true")

    await tab(page, "ซับ").click()
    await page.waitForTimeout(500)
    await expect(tab(page, "ซับ")).toHaveAttribute("aria-selected", "true")
    await expect(page).toHaveURL(new RegExp(`/v/${THAI}\\?tab=subs$`))
    expect(storyboardCalls).toHaveLength(0)
  })
})
