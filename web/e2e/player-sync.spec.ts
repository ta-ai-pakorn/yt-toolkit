/// <reference lib="dom" />
import AxeBuilder from "@axe-core/playwright"
import { expect, test, type Page } from "@playwright/test"

import { fakeYTLog, installFakeYT } from "./fake-yt"

// M3.5 ข้อ 4: ภาพเฟรม ทรานสคริปต์ และแท็บข้อมูลคลิป สั่งตัวเล่นให้เล่นจากเวลานั้น และตามตำแหน่งที่กำลังเล่น
// ไม่ต่อยูทูปจริง: installFakeYT ดักสคริปต์ iframe_api แล้วใช้ YT ปลอม (นับเวลาเอง เร่งได้ด้วย rate)
//
// describe ที่ชื่อลงท้ายด้วย "(ต้องมีตัวเล่นที่หัวคลิป)" ต้องใช้ตัวเล่น (adapter) ที่หัวคลิปของ lane P
// ซึ่งเป็นตัวโหลด iframe_api และส่งเวลาเข้า store · ก่อน lane P merge กลุ่มนี้ไม่ผ่าน (ไม่มีอะไรโหลดตัวเล่น)

// คลิปภาษาไทยที่มีภาพเฟรม (ห่างกัน 4895 ms) และซับอัตโนมัติภาษาไทยในชุดทดสอบ (backend โหมด fake)
const THAI = "88o5Sk8_m1Y"
// คลิปที่มีภาพเฟรม 128 ภาพ ไม่มีซับ
const BBB = "aqz-KE-bpKQ"
const FRAME_STEP_MS = 4895

const frameList = (page: Page) => page.getByRole("list", { name: "รายการภาพเฟรม" })
const frameButton = (page: Page, time: string) => frameList(page).getByRole("button", { name: new RegExp(`^ภาพเฟรมที่ ${time}`) })
const playCorner = (page: Page, time: string) => page.getByRole("button", { name: `เล่นจากตรงนี้ ${time}`, exact: true })
const nowPlaying = (page: Page) => frameList(page).locator("[data-now-playing]")
const lineList = (page: Page) => page.getByRole("list", { name: "บรรทัดในทรานสคริปต์" })
const lineItems = (page: Page) => lineList(page).getByRole("listitem")
const playingLine = (page: Page) => lineList(page).locator('[aria-current="true"]')
const backToPlaying = (page: Page) => page.getByRole("button", { name: "กลับไปบรรทัดที่กำลังเล่น" })
const lightbox = (page: Page) => page.getByRole("dialog")
const tab = (page: Page, name: string) => page.getByRole("tab", { name, exact: true })

const toMs = (timecode: string) => {
  const [h, m, s] = timecode.split(":").map(Number)
  return ((h * 60 + m) * 60 + s) * 1000
}

/** เวลา (ms ตัดเศษวินาที) ของภาพที่มีกรอบ "กำลังเล่น" */
async function nowPlayingMs(page: Page): Promise<number> {
  const alt = (await nowPlaying(page).locator("img").getAttribute("alt")) ?? ""
  return toMs(/\d{2}:\d{2}:\d{2}/.exec(alt)?.[0] ?? "")
}

/** ปรับความเร็วเวลาของตัวเล่นปลอมระหว่างเทสต์ (fake-yt อ่าน rate ทุกครั้งที่ถามเวลา) */
async function setRate(page: Page, rate: number) {
  await page.evaluate((value) => {
    ;(window as unknown as { __fakeYTConfig: { rate?: number } }).__fakeYTConfig.rate = value
  }, rate)
}

/** หยุดตัวเล่นปลอมเหมือนผู้ใช้กดหยุดในตัวเล่นยูทูป (เวลาหยุดนิ่ง สถานะเป็น paused ยังมีตำแหน่ง) */
async function pauseFake(page: Page) {
  await page.evaluate(() => {
    ;(window as unknown as { __fakeYT: { players: { pauseVideo(): void }[] } }).__fakeYT.players[0].pauseVideo()
  })
}

/** มี seek ไปเวลานี้ (วินาที) ในบันทึกของตัวเล่นปลอม */
async function expectSeekTo(page: Page, seconds: number) {
  await expect
    .poll(async () => (await fakeYTLog(page)).seeks.some((s) => Math.abs(s - seconds) < 0.05), { timeout: 10_000 })
    .toBe(true)
}

/** element อยู่ในกรอบที่เห็นของรายการทรานสคริปต์ (กรอบเลื่อนของ ScrollArea) ไม่ใช่แค่ในจอ */
async function inListView(locator: ReturnType<Page["locator"]>): Promise<boolean> {
  return locator.evaluate((element) => {
    const viewport = element.closest('[data-slot="scroll-area-viewport"]')
    if (!viewport) return false
    const box = element.getBoundingClientRect()
    const frame = viewport.getBoundingClientRect()
    return box.bottom > frame.top + 1 && box.top < frame.bottom - 1
  })
}

// จอสูงพอให้หัวคลิปและรายการทรานสคริปต์อยู่ในจอพร้อมกัน: หน้าไม่ต้องเลื่อน ตรวจได้ว่าการเลื่อนตามไม่ดึงทั้งหน้า
const TALL = { width: 1280, height: 1600 }

/** ภาพเฟรมทุกภาพวาดแล้ว (content-visibility ทำให้ภาพไกลจอยังไม่ถูกวาด แต่ปุ่มอยู่ใน DOM ครบ) */
async function openFrames(page: Page, videoId: string) {
  await page.goto(`/v/${videoId}`)
  await expect(frameList(page).getByRole("listitem").first()).toBeVisible()
}

test.describe("M3.5 ภาพเฟรม: ปุ่ม ▶ และเมนู 'เล่นจากตรงนี้'", () => {
  test("ปุ่ม ▶ มุมภาพเห็นเมื่อชี้เมาส์ และเมื่อโฟกัสอยู่ในภาพ · ชื่อ 'เล่นจากตรงนี้ HH:MM:SS' · ไม่อยู่ในลำดับ Tab", async ({ page }) => {
    await installFakeYT(page, { rate: 1 })
    await openFrames(page, BBB)
    const corner = playCorner(page, "00:00:09")
    await expect(corner).toHaveCount(1)
    await expect(corner).toHaveCSS("opacity", "0")
    await frameButton(page, "00:00:09").hover()
    await expect(corner).toHaveCSS("opacity", "1")

    // ย้ายเมาส์ออก แล้วโฟกัสภาพด้วยคีย์บอร์ด: ปุ่ม ▶ ของภาพนั้นโผล่ (ให้เห็นว่ามี) แต่ Tab ข้ามไปภาพถัดไป
    // ผู้ใช้คีย์บอร์ดเล่นจากภาพด้วยเมนู "เล่นจากตรงนี้" (Shift+F10)
    await page.mouse.move(0, 0)
    await frameButton(page, "00:00:04").focus()
    await page.keyboard.press("Tab")
    await page.keyboard.press("Shift+Tab")
    await expect(frameButton(page, "00:00:04")).toBeFocused()
    await expect(playCorner(page, "00:00:04")).toHaveCSS("opacity", "1")
    await expect(playCorner(page, "00:00:04")).toHaveAttribute("tabindex", "-1")
    await page.keyboard.press("Tab")
    await expect(frameButton(page, "00:00:09")).toBeFocused()
  })

  test("คีย์บอร์ด: Shift+F10 ที่ภาพ → 'เล่นจากตรงนี้' → ตัวเล่น seek ไปเวลาของภาพ", async ({ page }) => {
    await installFakeYT(page, { rate: 1 })
    await openFrames(page, THAI)
    await frameButton(page, "00:00:09").focus()
    await page.keyboard.press("Shift+F10")
    await expect(page.getByRole("menu")).toBeVisible()
    await page.getByRole("menuitem", { name: "เล่นจากตรงนี้" }).focus()
    await page.keyboard.press("Enter")
    await expectSeekTo(page, (2 * FRAME_STEP_MS) / 1000)
  })

  test("กด ▶ ไม่เปิดภาพใหญ่และไม่เปลี่ยน URL · คลิกตัวภาพยังเปิดภาพใหญ่เหมือนเดิม", async ({ page }) => {
    await installFakeYT(page, { rate: 1 })
    await openFrames(page, BBB)
    await frameButton(page, "00:00:09").hover()
    await playCorner(page, "00:00:09").click()
    await page.waitForTimeout(300)
    await expect(lightbox(page)).toHaveCount(0)
    await expect(page).toHaveURL(new RegExp(`/v/${BBB}$`))

    await frameButton(page, "00:00:04").click()
    await expect(lightbox(page)).toHaveAttribute("aria-label", "ภาพเฟรมที่ 00:00:04")
  })

  test("คลิกขวามีรายการ 'เล่นจากตรงนี้' ต่อจาก 'เปิดในยูทูปตรงเวลานี้' · เลือกแล้วเมนูปิด ไม่เปิดภาพใหญ่", async ({ page }) => {
    await installFakeYT(page, { rate: 1 })
    await openFrames(page, BBB)
    await frameButton(page, "00:00:09").click({ button: "right" })
    const items = page.getByRole("menu").getByRole("menuitem")
    await expect(items.nth(4)).toHaveText("เปิดในยูทูปตรงเวลานี้")
    await expect(items.nth(5)).toHaveText("เล่นจากตรงนี้")
    await items.nth(5).click()
    await expect(page.getByRole("menu")).toHaveCount(0)
    await expect(lightbox(page)).toHaveCount(0)
  })

  test("ยังไม่เล่น: ไม่มีภาพที่มีกรอบ 'กำลังเล่น' และไม่มีคำขอไปยูทูปเลย", async ({ page }) => {
    const { requests } = await installFakeYT(page, { rate: 1 })
    await openFrames(page, BBB)
    await page.waitForTimeout(500)
    await expect(nowPlaying(page)).toHaveCount(0)
    expect(requests).toEqual([])
  })
})

test.describe("M3.5 ทรานสคริปต์: ปุ่มเวลาหน้าบรรทัด", () => {
  test("ทุกบรรทัดมีปุ่มเวลา 'เล่นจากตรงนี้ HH:MM:SS' · กดแล้วอยู่แท็บเดิม · กดข้อความยังไปภาพเฟรม", async ({ page }) => {
    await installFakeYT(page, { rate: 1 })
    await page.goto(`/v/${THAI}?tab=transcript`)
    const first = lineItems(page).first()
    await expect(first).toBeVisible()
    const time = (await first.locator(".font-mono").textContent())?.trim() ?? ""
    expect(time).toMatch(/^\d{2}:\d{2}:\d{2}$/)
    const play = first.getByRole("button", { name: `เล่นจากตรงนี้ ${time}`, exact: true })
    await play.click()
    await page.waitForTimeout(300)
    await expect(page).toHaveURL(new RegExp(`/v/${THAI}\\?tab=transcript$`))
    await expect(tab(page, "ทรานสคริปต์")).toHaveAttribute("aria-selected", "true")

    await first.locator("button:not([aria-label])").click()
    await expect(page).toHaveURL(new RegExp(`/v/${THAI}\\?at=\\d+$`))
    await expect(tab(page, "ภาพเฟรม")).toHaveAttribute("aria-selected", "true")
  })

  test("ยังไม่เล่น: เลื่อนรายการเองไม่ขึ้นปุ่ม 'กลับไปบรรทัดที่กำลังเล่น'", async ({ page }) => {
    await installFakeYT(page, { rate: 1 })
    await page.goto(`/v/${THAI}?tab=transcript`)
    await expect(lineItems(page).first()).toBeVisible()
    await lineList(page).hover()
    await page.mouse.wheel(0, 400)
    await page.waitForTimeout(300)
    await expect(backToPlaying(page)).toHaveCount(0)
  })
})

test.describe("M3.5 ภาพเฟรมตามการเล่น (ต้องมีตัวเล่นที่หัวคลิป)", () => {
  test("กด ▶ ของภาพ → ตัวเล่น seek ไปเวลาของภาพและเล่น · ภาพนั้นมีกรอบ 'กำลังเล่น' ภาพเดียว · เร่งเวลาแล้วกรอบย้ายตาม", async ({
    page,
  }) => {
    await installFakeYT(page, { rate: 1 })
    await openFrames(page, THAI)
    // ภาพที่ 3 ของคลิป (2 × 4895 ms = 9790 ms = 00:00:09)
    await frameButton(page, "00:00:09").hover()
    await playCorner(page, "00:00:09").click()
    await expectSeekTo(page, (2 * FRAME_STEP_MS) / 1000)
    await expect.poll(async () => (await fakeYTLog(page)).calls.includes("play")).toBe(true)

    await expect(nowPlaying(page)).toHaveCount(1)
    await expect(nowPlaying(page).locator("img")).toHaveAttribute("alt", "ภาพเฟรมที่ 00:00:09")
    // ต่างจากกรอบ ?at= (outline) · ไม่ทำให้ภาพเป็น aria-current
    await expect(nowPlaying(page)).not.toHaveAttribute("data-highlighted", "")
    await expect(nowPlaying(page)).not.toHaveAttribute("aria-current", "true")
    await expect(nowPlaying(page)).toContainText("กำลังเล่น")

    // เร่งเวลา 20 เท่า: ภาพห่างกัน ~4.9 วินาที กรอบย้ายไปภาพถัดไปภายในราว 0.25 วินาที
    const start = await nowPlayingMs(page)
    await setRate(page, 20)
    await expect.poll(() => nowPlayingMs(page), { timeout: 5_000 }).toBeGreaterThan(start + 2 * FRAME_STEP_MS - 1000)
    await expect(nowPlaying(page)).toHaveCount(1)
  })

  test("เมนู 'เล่นจากตรงนี้' → seek ไปเวลาของภาพ", async ({ page }) => {
    await installFakeYT(page, { rate: 1 })
    await openFrames(page, THAI)
    await frameButton(page, "00:00:19").click({ button: "right" })
    await page.getByRole("menuitem", { name: "เล่นจากตรงนี้" }).click()
    await expectSeekTo(page, (4 * FRAME_STEP_MS) / 1000)
    await expect(nowPlaying(page).locator("img")).toHaveAttribute("alt", "ภาพเฟรมที่ 00:00:19")
  })

  test("ระหว่างเล่น DOM ของภาพเฟรมเปลี่ยนเฉพาะภาพเดิมกับภาพใหม่ที่กำลังเล่น", async ({ page }) => {
    await installFakeYT(page, { rate: 20 })
    await openFrames(page, THAI)
    await frameButton(page, "00:00:04").hover()
    await playCorner(page, "00:00:04").click()
    await expect(nowPlaying(page)).toHaveCount(1)
    // จดทุกการเปลี่ยนแปลงใต้รายการภาพเฟรมช่วง 2 วินาที: ทุกครั้งที่เปลี่ยนต้องเป็นภาพเดิม/ภาพใหม่คู่เดียว
    const batches = await frameList(page).evaluate(
      (list) =>
        new Promise<number[]>((resolve) => {
          const sizes: number[] = []
          const observer = new MutationObserver((records) => {
            const tiles = new Set(records.map((record) => (record.target as Element).closest("li")))
            sizes.push(tiles.size)
          })
          observer.observe(list, { subtree: true, attributes: true, childList: true, characterData: true })
          setTimeout(() => {
            observer.disconnect()
            resolve(sizes)
          }, 2000)
        }),
    )
    expect(batches.length).toBeGreaterThan(0)
    for (const size of batches) expect(size).toBeLessThanOrEqual(2)
  })
})

test.describe("M3.5 ทรานสคริปต์ตามการเล่น (ต้องมีตัวเล่นที่หัวคลิป)", () => {
  test("กดเวลาของบรรทัด → seek ไปต้นบรรทัด · บรรทัดนั้นได้ aria-current และแถบพื้น · เร่งเวลาแล้วบรรทัดย้ายและเลื่อนตามในกรอบ", async ({
    page,
  }) => {
    await page.setViewportSize(TALL)
    await installFakeYT(page, { rate: 1 })
    await page.goto(`/v/${THAI}?tab=transcript`)
    const third = lineItems(page).nth(2)
    await expect(third).toBeVisible()
    const time = (await third.locator(".font-mono").textContent())?.trim() ?? ""
    await third.getByRole("button", { name: `เล่นจากตรงนี้ ${time}`, exact: true }).click()
    await expect.poll(async () => (await fakeYTLog(page)).seeks.length).toBeGreaterThan(0)
    const seek = (await fakeYTLog(page)).seeks.at(-1) ?? -1
    expect(Math.floor(seek)).toBe(toMs(time) / 1000)

    await expect(playingLine(page)).toHaveCount(1)
    await expect(lineItems(page).nth(2)).toHaveAttribute("data-playing", "")
    await expect(playingLine(page)).toHaveText(await third.locator("button:not([aria-label])").textContent() ?? "")

    // เร่งเวลา: บรรทัดที่กำลังเล่นเลื่อนลึกลงไปในรายการ และกรอบรายการเลื่อนตามให้เห็นเสมอ (ไม่ขึ้นปุ่มกลับไป)
    await setRate(page, 20)
    await expect
      .poll(() => lineItems(page).evaluateAll((items) => items.findIndex((item) => item.hasAttribute("data-playing"))), {
        timeout: 15_000,
      })
      .toBeGreaterThan(20)
    await expect.poll(() => inListView(playingLine(page))).toBe(true)
    await expect(backToPlaying(page)).toHaveCount(0)
    // การเลื่อนตามเลื่อนเฉพาะกรอบรายการ ไม่ดึงทั้งหน้า
    expect(await page.evaluate(() => window.scrollY)).toBeLessThan(5)
  })

  test("เลื่อนรายการเอง (ล้อเมาส์) → หยุดเลื่อนตาม ขึ้นปุ่ม 'กลับไปบรรทัดที่กำลังเล่น' · กดแล้วบรรทัดที่กำลังเล่นกลับมาในกรอบและได้โฟกัส", async ({
    page,
  }) => {
    await page.setViewportSize(TALL)
    await installFakeYT(page, { rate: 1 })
    await page.goto(`/v/${THAI}?tab=transcript`)
    const first = lineItems(page).first()
    await expect(first).toBeVisible()
    await first.locator(".font-mono").click()
    await expect(playingLine(page)).toHaveCount(1)
    await setRate(page, 20)

    // เลื่อนกลับขึ้นบนสุดเองด้วยล้อเมาส์ ระหว่างที่บรรทัดเดินหน้าไปเรื่อย ๆ
    await lineList(page).hover()
    await page.mouse.wheel(0, -2000)
    await expect(backToPlaying(page)).toBeVisible()
    await expect.poll(() => inListView(lineItems(page).first())).toBe(true)
    // ไม่ถูกดึงกลับ: รอให้บรรทัดที่กำลังเล่นหลุดกรอบไปแล้วก็ยังไม่เลื่อนตาม
    await expect.poll(() => inListView(playingLine(page)), { timeout: 15_000 }).toBe(false)
    await page.waitForTimeout(500)
    expect(await inListView(lineItems(page).first())).toBe(true)

    // หยุดคลิปไว้ก่อนกด (ยังมีตำแหน่ง ปุ่มยังอยู่): ที่ 20 เท่า บรรทัดที่กำลังเล่นเปลี่ยนทุกไม่กี่ร้อย ms
    // โฟกัสไปอยู่ที่บรรทัดที่เล่นอยู่ตอนกด และไม่วิ่งตามบรรทัดต่อ ๆ ไป (ย้ายโฟกัสเองระหว่างเล่นจะรบกวนผู้ใช้)
    // ถ้าไม่หยุด aria-current ย้ายไปบรรทัดถัดไปก่อนตรวจ เทสต์จะเทียบกับเป้าที่ขยับอยู่
    await pauseFake(page)
    await expect(backToPlaying(page)).toBeVisible()
    const playingText = await playingLine(page).textContent()
    await backToPlaying(page).click()
    await expect(backToPlaying(page)).toHaveCount(0)
    await expect.poll(() => inListView(playingLine(page))).toBe(true)
    await expect(playingLine(page)).toBeFocused()
    await expect(playingLine(page)).toHaveText(playingText ?? "")
  })

  test("กด 'กลับไปบรรทัดที่กำลังเล่น' ระหว่างเล่นอยู่: โฟกัสบรรทัดที่เล่นตอนกด แล้วเลื่อนตามต่อโดยโฟกัสไม่ตาม", async ({ page }) => {
    await page.setViewportSize(TALL)
    await installFakeYT(page, { rate: 1 })
    await page.goto(`/v/${THAI}?tab=transcript`)
    await expect(lineItems(page).first()).toBeVisible()
    await lineItems(page).first().locator(".font-mono").click()
    await expect(playingLine(page)).toHaveCount(1)
    await lineList(page).hover()
    await page.mouse.wheel(0, 600)
    await expect(backToPlaying(page)).toBeVisible()
    await backToPlaying(page).click()
    await expect(backToPlaying(page)).toHaveCount(0)
    // โฟกัสอยู่บนปุ่มข้อความของบรรทัดในรายการ (ไม่หลุดไป body ทั้งที่ปุ่มหายไป)
    expect(await page.evaluate(() => document.activeElement?.closest('[aria-label="บรรทัดในทรานสคริปต์"]') !== null)).toBe(true)
    await setRate(page, 20)
    await expect.poll(() => inListView(playingLine(page))).toBe(true)
  })

  test("คีย์บอร์ด: ลูกศรลงในรายการ = เลื่อนเอง (หยุดเลื่อนตาม) · กดเวลาของบรรทัดอื่น = กลับมาเลื่อนตาม", async ({ page }) => {
    await installFakeYT(page, { rate: 1 })
    await page.goto(`/v/${THAI}?tab=transcript`)
    const first = lineItems(page).first()
    await expect(first).toBeVisible()
    await first.locator(".font-mono").click()
    await expect(playingLine(page)).toHaveCount(1)
    await page.keyboard.press("ArrowDown")
    await expect(backToPlaying(page)).toBeVisible()
    await lineItems(page).nth(1).locator(".font-mono").click()
    await expect(backToPlaying(page)).toHaveCount(0)
  })
})

test.describe("M3.5 แท็บข้อมูลคลิป: ปุ่มเวลาเล่นคลิป (ต้องมีตัวเล่นที่หัวคลิป)", () => {
  test("เวลาของ chapter และช่วงที่คนดูซ้ำบ่อย → ตัวเล่น seek ไปเวลานั้น อยู่แท็บเดิม", async ({ page }) => {
    await installFakeYT(page, { rate: 1 })
    await page.route(
      (url) => url.pathname === `/api/videos/${THAI}`,
      async (route) => {
        const response = await route.fetch()
        const body = (await response.json()) as Record<string, unknown>
        await route.fulfill({
          response,
          json: {
            ...body,
            chapters: [
              { startS: 0, endS: 30, title: "เปิดเรื่อง" },
              { startS: 30, endS: 90, title: "ตอนสอง" },
            ],
            mostReplayed: [{ startMs: 60_000, endMs: 66_000 }],
          },
        })
      },
    )
    await page.goto(`/v/${THAI}?tab=info`)
    await page.getByRole("button", { name: "เล่นจาก 00:00:30" }).click()
    await expectSeekTo(page, 30)
    await page.getByRole("button", { name: "เล่นจาก 00:01:00" }).click()
    await expectSeekTo(page, 60)
    await expect(page).toHaveURL(new RegExp(`/v/${THAI}\\?tab=info$`))
    await expect(tab(page, "ข้อมูลคลิป")).toHaveAttribute("aria-selected", "true")
  })
})

test.describe("M3.5 การเข้าถึงระหว่างเล่น (ต้องมีตัวเล่นที่หัวคลิป)", () => {
  async function seriousViolations(page: Page) {
    // ตัวเล่น (iframe) ตรวจในเทสต์ของตัวเล่นเอง ที่นี่ตรวจภาพเฟรม/ทรานสคริปต์ระหว่างเล่น
    const results = await new AxeBuilder({ page }).exclude("iframe").analyze()
    return results.violations
      .filter((v) => v.impact === "serious" || v.impact === "critical")
      .map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target.join(" ")).slice(0, 5) }))
  }

  for (const scheme of ["dark", "light"] as const) {
    test(`ภาพเฟรมที่มีกรอบ 'กำลังเล่น' และบรรทัดที่กำลังเล่นไม่มีปัญหาระดับ serious/critical (${scheme})`, async ({ page }) => {
      // เวลาแทบไม่เดิน: กรอบและแถบพื้นอยู่นิ่งระหว่างตรวจ
      await installFakeYT(page, { rate: 0.0001 })
      await page.emulateMedia({ colorScheme: scheme })
      await openFrames(page, THAI)
      await frameButton(page, "00:00:09").hover()
      await playCorner(page, "00:00:09").click()
      await expect(nowPlaying(page)).toHaveCount(1)
      expect(await seriousViolations(page)).toEqual([])

      await tab(page, "ทรานสคริปต์").click()
      await lineItems(page).nth(2).locator(".font-mono").click()
      await expect(lineItems(page).nth(2)).toHaveAttribute("data-playing", "")
      expect(await seriousViolations(page)).toEqual([])
    })
  }
})
