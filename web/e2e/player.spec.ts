/// <reference lib="dom" />
import AxeBuilder from "@axe-core/playwright"
import { expect, test, type Page } from "@playwright/test"

import { fakeYTLog, installFakeYT } from "./fake-yt"

// M3.5 ตัวเล่นคลิปใน W2 (lane P): ช่องตัวเล่นที่หัวคลิป ลอยมุมจอ แถบไทม์ไลน์ ช่วงไฮไลต์ ข้อผิดพลาด และปุ่ม "ดูภาพปก"
// ไม่ต่อยูทูปจริง: installFakeYT ดักสคริปต์ API และ iframe (ต้องเรียกก่อน goto ทุกครั้ง)

// คลิปภาษาไทย 372 วินาที ภาพเฟรมเยอะ หน้าจึงเลื่อนได้ยาว
const THAI = "88o5Sk8_m1Y"
const REPLAYED = [
  { startMs: 20_000, endMs: 30_000 },
  { startMs: 60_000, endMs: 66_000 },
]
const CHAPTERS = [
  { startS: 0, endS: 90, title: "เปิด" },
  { startS: 90, endS: 200, title: "กลาง" },
  { startS: 200, endS: 372, title: "ท้าย" },
]
const NEW_KEYS = ["stats", "tags", "categories", "mostReplayed"]

const PLAY = "เล่นคลิป"
const DOCK = "ตัวเล่นคลิป (ลอย)"
const TIMELINE = "ตำแหน่งในคลิป"
const REEL = "เล่นเฉพาะช่วงที่ดูซ้ำบ่อย"
const REEL_STOP = "หยุดเล่นช่วงไฮไลต์"
const COVER = "ดูภาพปก"

/** ข้อมูลคลิปจาก backend โหมด fake + patch (ลบคีย์ใหม่ก่อน ผลไม่ขึ้นกับ fixture) */
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

const heading = (page: Page) => page.getByRole("heading", { level: 1 })
const playButton = (page: Page) => page.getByRole("button", { name: PLAY, exact: true })
const iframe = (page: Page) => page.locator('[data-slot="player-host"] iframe')
const dock = (page: Page) => page.getByRole("region", { name: DOCK })
const slot = (page: Page) => page.locator('[data-slot="player-slot"]')
const timeline = (page: Page) => page.getByRole("slider", { name: TIMELINE })
/** "ช่วง i จาก n" ที่เห็นบนจอ (แถวไทม์ไลน์ หรือบนตัวเล่นลอย) ไม่รวมข้อความ aria-live ที่ซ่อนไว้ให้โปรแกรมอ่านหน้าจอ */
const reelStatus = (page: Page) => page.locator('[data-slot="reel-status"]')
const reelButton = (page: Page) => page.getByRole("button", { name: REEL, exact: true })
const actionRow = (page: Page) => page.locator('[data-slot="cover-button"]').locator("..")
const frameList = (page: Page) => page.getByRole("list", { name: "รายการภาพเฟรม" })

async function open(page: Page, patch: Record<string, unknown> = {}) {
  await withVideo(page, THAI, patch)
  await page.goto(`/v/${THAI}`)
  await expect(heading(page)).not.toBeEmpty()
}

/** กด ▶ แล้วรอจนตัวเล่นปลอมเล่นอยู่ */
async function play(page: Page) {
  await playButton(page).click()
  await expect(iframe(page)).toHaveCount(1)
  await expect.poll(async () => (await fakeYTLog(page)).calls).toContain("play")
}

/** เลื่อนหน้าลงจนช่องตัวเล่นพ้นจอ */
async function scrollAway(page: Page) {
  // รอภาพเฟรมโหลดจนหน้ายาวพอ
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollHeight - window.innerHeight))
    .toBeGreaterThan(600)
  await page.evaluate(() => window.scrollTo(0, 1200))
}

/** รอให้แอนิเมชันในหน้าจบ (ตัวเล่นลอยเลื่อนขึ้นมา) ก่อนวัดตำแหน่งหรือตรวจสี */
async function settle(page: Page) {
  await expect.poll(() => page.evaluate(() => document.getAnimations().filter((a) => a.playState === "running").length)).toBe(0)
}

test.describe("ช่องตัวเล่นที่หัวคลิป", () => {
  test("ไม่มีคำขอไปยูทูปก่อนกดเล่น · กด ▶ แล้วโหลดตัวเล่นในกล่องปก (youtube-nocookie, referrerpolicy, title)", async ({ page }) => {
    const { requests } = await installFakeYT(page)
    await open(page)
    const button = playButton(page)
    await expect(button).toBeVisible()
    const coverBox = await slot(page).boundingBox()
    expect((coverBox?.width ?? 0) / (coverBox?.height ?? 1)).toBeCloseTo(16 / 9, 1)
    // รอให้หน้าโหลดภาพเฟรมเสร็จ แล้วตรวจว่ายังไม่มีอะไรไปยูทูป
    await expect(page.getByRole("list", { name: "รายการภาพเฟรม" })).toBeVisible()
    await page.waitForTimeout(300)
    expect(requests).toEqual([])
    await expect(page.locator("iframe")).toHaveCount(0)

    await play(page)
    expect(requests.some((url) => url === "https://www.youtube.com/iframe_api")).toBe(true)
    const frame = iframe(page)
    await expect(frame).toHaveAttribute("referrerpolicy", "strict-origin-when-cross-origin")
    // เล่นต่อได้ทันทีหลังโหลด (ยูทูปต้องได้สิทธิ์ autoplay จาก iframe) และเต็มจอ/ภาพซ้อนภาพได้
    await expect(frame).toHaveAttribute("allow", "autoplay; encrypted-media; picture-in-picture; fullscreen")
    await expect(frame).toHaveAttribute("src", new RegExp(`^https://www\\.youtube-nocookie\\.com/embed/${THAI}\\?`))
    await expect(frame).toHaveAttribute("src", /enablejsapi=1/)
    const title = await heading(page).textContent()
    await expect(frame).toHaveAttribute("title", `ตัวเล่นคลิป: ${title}`)
    // ตัวเล่นอยู่ในกล่องปกเดิม ขนาดเท่าเดิม
    const frameBox = await frame.boundingBox()
    expect(Math.abs((frameBox?.width ?? 0) - (coverBox?.width ?? 0))).toBeLessThan(2)
    expect(Math.abs((frameBox?.y ?? 0) - (coverBox?.y ?? 0))).toBeLessThan(2)
    await expect(playButton(page)).toHaveCount(0)
    expect((await fakeYTLog(page)).players).toBe(1)
  })

  test("เลื่อนจอลง = ลอยมุมขวาล่าง (iframe เดิม ไม่โหลดใหม่) · ช่องเดิมขึ้น 'กำลังเล่นที่มุมจอ' · 'กลับไปที่หัวคลิป' แล้วกลับเข้าช่อง", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    const { requests } = await installFakeYT(page)
    await open(page)
    await play(page)
    await iframe(page).evaluate((el) => el.setAttribute("data-marker", "same"))
    await expect(dock(page)).toHaveCount(0)

    await scrollAway(page)
    await expect(dock(page)).toBeVisible()
    await expect(dock(page)).toHaveCSS("position", "fixed")
    await settle(page)
    const box = await dock(page).boundingBox()
    expect(box?.width ?? 0).toBeGreaterThan(300)
    expect(box?.width ?? 0).toBeLessThan(340)
    expect((box?.x ?? 0) + (box?.width ?? 0)).toBeGreaterThan(1240)
    expect((box?.y ?? 0) + (box?.height ?? 0)).toBeGreaterThan(760)
    await expect(dock(page).locator("iframe")).toHaveAttribute("data-marker", "same")
    const videoBox = await dock(page).locator('[data-slot="player-host"]').boundingBox()
    expect((videoBox?.width ?? 0) / (videoBox?.height ?? 1)).toBeCloseTo(16 / 9, 1)
    // เว้นที่ท้ายหน้า เนื้อหาล่างสุดไม่ถูกบัง
    const padding = await page.evaluate(() => parseFloat(getComputedStyle(document.body).paddingBottom))
    expect(padding).toBeGreaterThanOrEqual(box?.height ?? 0)
    // ชื่อปุ่มขึ้นต้นด้วยคำกริยา (สิ่งที่กดแล้วเกิด) ข้อความที่เห็นเป็นคำอธิบาย
    const placeholderButton = page.locator('[data-slot="player-docked-placeholder"]')
    await expect(placeholderButton).toHaveAccessibleName("กลับไปที่หัวคลิป")
    await expect(placeholderButton).toBeAttached()
    await expect(placeholderButton).toHaveAccessibleDescription("กำลังเล่นที่มุมจอ")
    await expect(placeholderButton).toContainText("กำลังเล่นที่มุมจอ")
    // ไม่มีแถบไทม์ไลน์ตอนลอย
    await expect(timeline(page)).toHaveCount(0)

    await dock(page).getByRole("button", { name: "กลับไปที่หัวคลิป" }).click()
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0)
    await expect(dock(page)).toHaveCount(0)
    await expect(iframe(page)).toHaveAttribute("data-marker", "same")
    await expect(timeline(page)).toBeVisible()
    expect(await page.evaluate(() => parseFloat(getComputedStyle(document.body).paddingBottom))).toBe(0)

    // เห็นช่องไม่ถึงครึ่ง = ลอย และส่วนที่เหลือในจอเป็นปกจาง ๆ "กำลังเล่นที่มุมจอ" กดแล้วเลื่อนกลับขึ้นบน
    const slotBox = (await slot(page).boundingBox())!
    await page.evaluate((y) => window.scrollTo(0, y), slotBox.y + slotBox.height * 0.75)
    await expect(dock(page)).toBeVisible()
    const placeholder = page.locator('[data-slot="player-docked-placeholder"]')
    await expect(placeholder).toBeInViewport()
    await placeholder.click({ position: { x: slotBox.width / 2, y: slotBox.height * 0.9 } })
    await expect(dock(page)).toHaveCount(0)
    const log = await fakeYTLog(page)
    expect(log.players).toBe(1)
    expect(requests.filter((url) => url.includes("/embed/"))).toHaveLength(1)
  })

  test("ยังไม่เคยเล่น: เลื่อนจอลงไม่ลอย", async ({ page }) => {
    await installFakeYT(page)
    await open(page)
    await scrollAway(page)
    await page.waitForTimeout(200)
    await expect(dock(page)).toHaveCount(0)
  })

  test("✕ 'ปิดตัวเล่น' หยุดและเอาตัวเล่นออก กลับเป็นปก + ▶ (โฟกัสที่ ▶)", async ({ page }) => {
    await installFakeYT(page)
    await open(page)
    await play(page)
    await scrollAway(page)
    await dock(page).getByRole("button", { name: "ปิดตัวเล่น" }).click()
    await expect(dock(page)).toHaveCount(0)
    await expect(page.locator("iframe")).toHaveCount(0)
    expect((await fakeYTLog(page)).calls).toContain("destroy")
    await expect(playButton(page)).toBeFocused()
    await expect(timeline(page)).toHaveCount(0)
    // ปิดแล้วเลื่อนจอก็ไม่ลอยอีก
    await page.evaluate(() => window.scrollTo(0, 1300))
    await page.waitForTimeout(200)
    await expect(dock(page)).toHaveCount(0)
  })
})

test.describe("แถบไทม์ไลน์", () => {
  test("ยังไม่เล่นไม่มีแถบ · เล่นแล้วมีช่วงดูซ้ำบ่อย ขีด chapter · คลิก = seek · คีย์บอร์ด seek ตอนปล่อยปุ่ม", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    await installFakeYT(page, { durationS: 372 })
    await open(page, { mostReplayed: REPLAYED, chapters: CHAPTERS })
    await expect(timeline(page)).toHaveCount(0)
    await play(page)
    const bar = timeline(page)
    await expect(bar).toBeVisible()
    await expect(bar.locator('[data-slot="timeline-replayed"]')).toHaveCount(2)
    // chapter แรกเริ่มที่ 0 ไม่ต้องมีขีด
    await expect(bar.locator('[data-slot="timeline-chapter"]')).toHaveCount(2)
    const barBox = await bar.boundingBox()
    const slotBox = await slot(page).boundingBox()
    expect(Math.abs((barBox?.width ?? 0) - (slotBox?.width ?? 0))).toBeLessThan(2)

    // คลิกกลางแถบ = 186 วินาที
    await bar.click({ position: { x: (barBox?.width ?? 0) / 2, y: (barBox?.height ?? 0) / 2 } })
    await expect.poll(async () => (await fakeYTLog(page)).seeks.at(-1)).toBe(186)
    await expect(bar).toHaveAttribute("aria-valuetext", /^00:03:0[6-9]$/)

    // คีย์บอร์ด: Home → 0 แล้ว ขวา → 5 วินาที
    await page.evaluate(() => {
      // หยุดเวลาไว้ ตัวเลขจะได้ไม่ขยับระหว่างตรวจ
      ;(window as unknown as { __fakeYT: { players: { pauseVideo(): void }[] } }).__fakeYT.players[0].pauseVideo()
    })
    await bar.focus()
    await page.keyboard.press("Home")
    await expect.poll(async () => (await fakeYTLog(page)).seeks.at(-1)).toBe(0)
    await expect(bar).toHaveAttribute("aria-valuetext", "00:00:00")
    const before = (await fakeYTLog(page)).seeks.length
    await page.keyboard.down("ArrowRight")
    await expect(bar).toHaveAttribute("aria-valuetext", "00:00:05")
    expect((await fakeYTLog(page)).seeks.length).toBe(before)
    await page.keyboard.up("ArrowRight")
    await expect.poll(async () => (await fakeYTLog(page)).seeks.at(-1)).toBe(5)
    await page.keyboard.press("End")
    await expect.poll(async () => (await fakeYTLog(page)).seeks.at(-1)).toBe(372)
  })

  test("คลิปไม่มีความยาว = ไม่มีแถบ", async ({ page }) => {
    await installFakeYT(page)
    await open(page, { durationS: 0 })
    await play(page)
    await expect(timeline(page)).toHaveCount(0)
  })
})

test.describe("เล่นเฉพาะช่วงที่ดูซ้ำบ่อย", () => {
  test("ไม่มีช่วงดูซ้ำ = ไม่มีปุ่ม", async ({ page }) => {
    await installFakeYT(page)
    await open(page)
    await expect(page.getByRole("button", { name: REEL })).toHaveCount(0)
  })

  test("ปุ่มอยู่ในแถวปุ่มของหัวคลิป (ข้าง 'ดูภาพปก') ตั้งแต่ก่อนเล่น · ไม่มีแถวใต้ตัวเล่นก่อนเล่น", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    await installFakeYT(page)
    await open(page, { mostReplayed: REPLAYED })
    await expect(actionRow(page).getByRole("button", { name: REEL, exact: true })).toBeVisible()
    const cover = await page.getByRole("button", { name: COVER, exact: true }).boundingBox()
    const reel = await reelButton(page).boundingBox()
    expect(Math.abs((reel?.y ?? 0) - (cover?.y ?? 0))).toBeLessThan(4)
    await expect(page.locator('[data-slot="player-controls"]')).toHaveCount(0)
  })

  test("เล่นทีละช่วงตามลำดับ 'ช่วง 1 จาก 2' → 'ช่วง 2 จาก 2' แล้วหยุดหลังช่วงสุดท้าย", async ({ page }) => {
    await installFakeYT(page, { rate: 20 })
    await open(page, { mostReplayed: REPLAYED })
    const button = reelButton(page)
    await expect(button).toBeVisible()
    await button.click()
    // สถานะกับปุ่มหยุดอยู่ในแถวไทม์ไลน์ใต้ตัวเล่น (มีหลังกดเล่น)
    const controls = page.locator('[data-slot="player-controls"]')
    await expect(controls.locator('[data-slot="reel-status"]')).toHaveText(/ช่วง 1 จาก 2/)
    await expect(controls.getByRole("button", { name: REEL_STOP })).toBeVisible()
    await expect(reelStatus(page)).toHaveText(/ช่วง 2 จาก 2/)
    await expect(reelStatus(page)).toHaveCount(0, { timeout: 5000 })
    await expect(page.getByRole("button", { name: REEL_STOP })).toHaveCount(0)
    const log = await fakeYTLog(page)
    expect(log.seeks.slice(0, 2)).toEqual([20, 60])
    expect(log.calls.at(-1)).toBe("pause")
  })

  test("'หยุดเล่นช่วงไฮไลต์' หยุดคลิป (โฟกัสไปแถบไทม์ไลน์ข้าง ๆ) · seek เองที่แถบไทม์ไลน์ยกเลิกช่วงไฮไลต์", async ({ page }) => {
    await installFakeYT(page, { rate: 1 })
    await open(page, { mostReplayed: REPLAYED })
    await reelButton(page).click()
    await expect(reelStatus(page)).toHaveText(/ช่วง 1 จาก 2/)
    // ประกาศให้โปรแกรมอ่านหน้าจอจาก aria-live ที่อยู่ตลอดข้างปุ่ม
    await expect(actionRow(page).locator('[aria-live="polite"]')).toHaveText("ช่วง 1 จาก 2")
    await page.getByRole("button", { name: REEL_STOP }).click()
    await expect(reelStatus(page)).toHaveCount(0)
    // ปุ่มหยุดหายไป โฟกัสไม่หลุดไป body: ไปที่แถบไทม์ไลน์ในแถวเดียวกัน
    await expect(timeline(page)).toBeFocused()
    expect((await fakeYTLog(page)).calls.at(-1)).toBe("pause")

    await reelButton(page).click()
    await expect(reelStatus(page)).toHaveText(/ช่วง 1 จาก 2/)
    await timeline(page).click({ position: { x: 5, y: 10 } })
    await expect(reelStatus(page)).toHaveCount(0)
    await expect(reelButton(page)).toBeVisible()
  })
})

test.describe("ข้อผิดพลาดของตัวเล่น", () => {
  test("error 150 (เจ้าของไม่ให้ฝัง): ข้อความในช่อง + ลิงก์ 'เปิดในยูทูป' ตรงเวลา · ไม่มีตัวเล่นค้าง", async ({ page }) => {
    await installFakeYT(page, { errorCode: 150 })
    await open(page)
    await playButton(page).click()
    const alert = slot(page).getByRole("alert")
    await expect(alert).toContainText("เจ้าของคลิปไม่อนุญาตให้เล่นนอกยูทูป")
    await expect(alert).toBeFocused()
    const link = alert.getByRole("link", { name: /^เปิดในยูทูป/ })
    await expect(link).toHaveAttribute("href", `https://www.youtube.com/watch?v=${THAI}&t=0s`)
    await expect(link).toHaveAttribute("target", "_blank")
    await expect(page.locator("iframe")).toHaveCount(0)
    // เลื่อนจอลงไม่ลอย
    await scrollAway(page)
    await page.waitForTimeout(200)
    await expect(dock(page)).toHaveCount(0)
  })

  test("error อื่น (153): 'เล่นคลิปนี้ในแอพไม่ได้'", async ({ page }) => {
    await installFakeYT(page, { errorCode: 153 })
    await open(page)
    await playButton(page).click()
    await expect(slot(page).getByRole("alert")).toContainText("เล่นคลิปนี้ในแอพไม่ได้")
  })

  test("โหลดสคริปต์ยูทูปไม่ได้ (ออฟไลน์): ข้อความ + 'ลองอีกครั้ง' · ต่อเน็ตได้แล้วกดลองใหม่ = เล่นได้", async ({ page }) => {
    const fake = await installFakeYT(page, { failScript: true })
    await open(page)
    await playButton(page).click()
    const alert = slot(page).getByRole("alert")
    await expect(alert).toContainText("ต้องต่ออินเทอร์เน็ตก่อนถึงจะเล่นคลิปได้")
    const retry = alert.getByRole("button", { name: "ลองอีกครั้ง" })
    // ยังออฟไลน์: กดแล้วผิดพลาดเหมือนเดิม
    await retry.click()
    await expect(slot(page).getByRole("alert")).toContainText("ต้องต่ออินเทอร์เน็ต")
    fake.setFailScript(false)
    await slot(page).getByRole("button", { name: "ลองอีกครั้ง" }).click()
    await expect(iframe(page)).toHaveCount(1)
    await expect.poll(async () => (await fakeYTLog(page)).calls).toContain("play")
    await expect(slot(page).getByRole("alert")).toHaveCount(0)
  })
})

test.describe("ปุ่ม 'ดูภาพปก'", () => {
  async function checkCover(page: Page) {
    const button = page.getByRole("button", { name: COVER, exact: true })
    await expect(button).toHaveAttribute("aria-haspopup", "dialog")
    await button.click()
    const dialog = page.getByRole("dialog", { name: "ภาพปกของคลิป" })
    await expect(dialog).toBeVisible()
    await expect(dialog.locator("img")).toHaveAttribute("src", /ytimg|\.jpg|\.webp/)
    await page.keyboard.press("Escape")
    await expect(dialog).toHaveCount(0)
    await expect(button).toBeFocused()
  }

  test("อยู่ในแถวปุ่มข้าง 'เปิดในยูทูป' · เปิดได้ก่อนเล่น ระหว่างเล่น (ไม่หยุดคลิป) และหลังลอยกลับมา", async ({ page }) => {
    await installFakeYT(page)
    await open(page)
    const youtube = await page.getByRole("link", { name: /^เปิดในยูทูป/ }).boundingBox()
    const cover = await page.getByRole("button", { name: COVER, exact: true }).boundingBox()
    expect(Math.abs((youtube?.y ?? 0) - (cover?.y ?? 0))).toBeLessThan(4)
    await checkCover(page)

    await play(page)
    await checkCover(page)
    const log = await fakeYTLog(page)
    expect(log.calls).not.toContain("pause")
    expect(log.states.at(-1)).toBe(1)

    await page.evaluate(() => window.scrollTo(0, 1200))
    await expect(dock(page)).toBeVisible()
    await page.evaluate(() => window.scrollTo(0, 0))
    await expect(dock(page)).toHaveCount(0)
    await checkCover(page)
  })

  test("ตอนผิดพลาดก็เปิดได้ · กดปก (ช่องตัวเล่น) = เล่น ไม่ใช่เปิดภาพใหญ่", async ({ page }) => {
    await installFakeYT(page, { errorCode: 150 })
    await open(page)
    await playButton(page).click()
    await expect(slot(page).getByRole("alert")).toBeVisible()
    await expect(page.getByRole("dialog")).toHaveCount(0)
    await checkCover(page)
  })
})

test.describe("จอแคบ 360 px", () => {
  test("ตัวเล่นในช่องปกเล็ก แถบไทม์ไลน์เต็มแถวใต้ชื่อคลิป · ปุ่มช่วงไฮไลต์ในแถวปุ่ม สูง 44 px · ลอย = แถบเต็มความกว้างล่างจอ วิดีโอราว 40% · ไม่มีเลื่อนแนวนอน", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 360, height: 740 })
    await installFakeYT(page)
    await open(page, { mostReplayed: REPLAYED, chapters: CHAPTERS })
    await play(page)
    const bar = await timeline(page).boundingBox()
    expect(bar?.width ?? 0).toBeGreaterThan(300)
    expect(bar?.height ?? 0).toBeGreaterThanOrEqual(44)
    // แถบไทม์ไลน์อยู่ใต้ชื่อคลิป ทั้งที่ตาเห็นและใน DOM
    const title = await heading(page).boundingBox()
    expect(bar?.y ?? 0).toBeGreaterThan((title?.y ?? 0) + (title?.height ?? 0) - 1)
    const reel = await reelButton(page).boundingBox()
    expect(reel?.height ?? 0).toBeGreaterThanOrEqual(44)
    for (const control of [page.getByRole("button", { name: COVER, exact: true }), page.getByRole("button", { name: "บันทึกเป็นโน้ต (.md)" })]) {
      expect((await control.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(44)
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360)

    await scrollAway(page)
    await expect(dock(page)).toBeVisible()
    await settle(page)
    const box = await dock(page).boundingBox()
    expect(box?.x ?? 1).toBe(0)
    expect(box?.width ?? 0).toBe(360)
    expect(Math.round((box?.y ?? 0) + (box?.height ?? 0))).toBe(740)
    const video = await dock(page).locator('[data-slot="player-host"]').boundingBox()
    expect((video?.width ?? 0) / 360).toBeGreaterThan(0.35)
    expect((video?.width ?? 0) / 360).toBeLessThan(0.45)
    for (const name of ["ปิดตัวเล่น", "กลับไปที่หัวคลิป"]) {
      const button = await dock(page).getByRole("button", { name }).boundingBox()
      expect(button?.height ?? 0).toBeGreaterThanOrEqual(44)
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360)
  })
})

test.describe("สั่งเล่นตอนหัวคลิปพ้นจอ", () => {
  test("เลื่อนลงในแท็บภาพเฟรมแล้วกด ▶ ของภาพ → ตัวเล่นลอยมุมขวาล่างทันที (ตั้งแต่กำลังโหลด) · หน้าไม่เด้งขึ้น · seek ตรงเวลาของภาพ", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    await installFakeYT(page, { rate: 1 })
    // หน่วงสคริปต์ยูทูปไว้ จะได้เห็นว่าลอยตั้งแต่ยังโหลดไม่เสร็จ (ลงทะเบียนทีหลัง = ทำงานก่อน route ของ installFakeYT)
    let release = () => {}
    const gate = new Promise<void>((resolve) => (release = resolve))
    await page.route("https://www.youtube.com/iframe_api", async (route) => {
      await gate
      await route.fallback()
    })
    await open(page)
    await scrollAway(page)
    // ภาพเฟรมแถวล่าง ๆ (คลิปนี้มี 76 ภาพ) อยู่ในจอตอนเลื่อนลงแล้ว ช่องตัวเล่นที่หัวคลิปพ้นจอ
    const target = frameList(page).getByRole("listitem").nth(60)
    await target.scrollIntoViewIfNeeded()
    await expect(slot(page)).not.toBeInViewport()
    const imageButton = target.getByRole("button", { name: /^ภาพเฟรมที่ / })
    const time = /\d{2}:\d{2}:\d{2}/.exec((await imageButton.getAttribute("aria-label")) ?? (await target.locator("img").getAttribute("alt")) ?? "")?.[0] ?? ""
    expect(time).not.toBe("")
    const afterScroll = await page.evaluate(() => window.scrollY)
    await imageButton.hover()
    await target.getByRole("button", { name: `เล่นจากตรงนี้ ${time}`, exact: true }).click()

    // ยังโหลดสคริปต์ไม่เสร็จ แต่ตัวเล่นลอยมุมจอแล้ว (มีวงหมุน "กำลังโหลดตัวเล่น")
    await expect(dock(page)).toBeVisible()
    await expect(dock(page)).toHaveCSS("position", "fixed")
    await expect(dock(page).getByLabel("กำลังโหลดตัวเล่น")).toBeVisible()
    // รอแอนิเมชันตอนลอยขึ้นมาจบ (วงหมุนยังหมุนอยู่ จึงดูเฉพาะของกล่องตัวเล่นลอย)
    await expect.poll(() => dock(page).evaluate((el) => el.getAnimations().filter((a) => a.playState === "running").length)).toBe(0)
    const box = await dock(page).boundingBox()
    expect((box?.x ?? 0) + (box?.width ?? 0)).toBeGreaterThan(1240)
    expect((box?.y ?? 0) + (box?.height ?? 0)).toBeGreaterThan(760)
    // หน้าไม่ถูกดึงกลับขึ้นไปที่หัวคลิป
    expect(await page.evaluate(() => window.scrollY)).toBe(afterScroll)

    release()
    await expect(dock(page).locator("iframe")).toHaveCount(1)
    const [h, m, sec] = time.split(":").map(Number)
    const seconds = (h * 60 + m) * 60 + sec
    // เวลาของภาพมีเศษ ms (ช่วงห่างของภาพ 4895 ms) seek ต้องตกในวินาทีนั้น
    await expect
      .poll(async () => (await fakeYTLog(page)).seeks.some((value) => value >= seconds && value < seconds + 1))
      .toBe(true)
    await expect.poll(async () => (await fakeYTLog(page)).calls).toContain("play")
    await expect(dock(page)).toBeVisible()
    expect((await fakeYTLog(page)).players).toBe(1)
  })
})

test.describe("toast กับตัวเล่นลอย", () => {
  /** สองกล่องทับกันไหม (เว้นขอบให้ 1 px) */
  const overlaps = (a: { x: number; y: number; width: number; height: number }, b: typeof a) =>
    a.x < b.x + b.width - 1 && b.x < a.x + a.width - 1 && a.y < b.y + b.height - 1 && b.y < a.y + a.height - 1

  async function toastWhileDocked(page: Page) {
    await installFakeYT(page, { rate: 1 })
    await open(page)
    await play(page)
    await scrollAway(page)
    await expect(dock(page)).toBeVisible()
    await settle(page)
    // toast จากเมนูภาพเฟรม "คัดลอกเวลา" (คัดลอกได้หรือไม่ได้ก็ขึ้น toast)
    // ภาพแถวล่าง ๆ: เลื่อนมาให้เห็นแล้วหัวคลิปยังพ้นจอ (ตัวเล่นยังลอย)
    const image = frameList(page).getByRole("button", { name: /^ภาพเฟรมที่ / }).nth(60)
    await image.scrollIntoViewIfNeeded()
    await expect(dock(page)).toBeVisible()
    await image.click({ button: "right" })
    await page.getByRole("menuitem", { name: "คัดลอกเวลา" }).click()
    const toast = page.locator("[data-sonner-toast]").first()
    await expect(toast).toBeVisible()
    await settle(page)
    return toast
  }

  for (const size of [
    { width: 1280, height: 800 },
    { width: 360, height: 740 },
  ]) {
    test(`จอ ${size.width} px: toast ขึ้นเหนือตัวเล่นลอย ไม่ทับกัน`, async ({ page }) => {
      await page.setViewportSize(size)
      const toast = await toastWhileDocked(page)
      const toastBox = (await toast.boundingBox())!
      const dockBox = (await dock(page).boundingBox())!
      expect(overlaps(toastBox, dockBox)).toBe(false)
      expect(toastBox.y + toastBox.height).toBeLessThanOrEqual(dockBox.y)
      expect(toastBox.y + toastBox.height).toBeLessThanOrEqual(size.height)
    })
  }

  test("แถบคิวของ M4 (--dock-bottom-offset) ดันทั้งตัวเล่นลอยและ toast ขึ้น ยังไม่ทับกัน", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    await page.addInitScript(() => {
      document.addEventListener("DOMContentLoaded", () => document.documentElement.style.setProperty("--dock-bottom-offset", "64px"))
    })
    const toast = await toastWhileDocked(page)
    const toastBox = (await toast.boundingBox())!
    const dockBox = (await dock(page).boundingBox())!
    // ตัวเล่นลอยสูงจากขอบล่าง 1rem + 64 px
    expect(Math.round(800 - (dockBox.y + dockBox.height))).toBe(16 + 64)
    expect(toastBox.y + toastBox.height).toBeLessThanOrEqual(dockBox.y)
  })

  test("ไม่ได้ลอย: toast อยู่ตำแหน่งเดิมของ sonner (ห่างขอบล่าง 24 px)", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    await installFakeYT(page)
    await open(page)
    const image = frameList(page).getByRole("button", { name: /^ภาพเฟรมที่ / }).first()
    await image.click({ button: "right" })
    await page.getByRole("menuitem", { name: "คัดลอกเวลา" }).click()
    const toast = page.locator("[data-sonner-toast]").first()
    await expect(toast).toBeVisible()
    await settle(page)
    const box = (await toast.boundingBox())!
    expect(Math.round(800 - (box.y + box.height))).toBe(24)
  })
})

test.describe("จอแคบ: ลำดับ DOM ตรงกับที่ตาเห็น", () => {
  test("หลังกดเล่น Tab จากชื่อคลิปไปแถบไทม์ไลน์ (แถบอยู่ใต้ชื่อ ทั้งในจอและใน DOM)", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 740 })
    await installFakeYT(page, { durationS: 372 })
    await open(page, { mostReplayed: REPLAYED })
    await play(page)
    await expect(timeline(page)).toBeVisible()
    const order = await page.evaluate(() => {
      const title = document.querySelector("h1")!
      const slider = document.querySelector('[role="slider"]')!
      return Boolean(title.compareDocumentPosition(slider) & Node.DOCUMENT_POSITION_FOLLOWING)
    })
    expect(order).toBe(true)
    await heading(page).focus()
    await page.keyboard.press("Tab")
    await expect(timeline(page)).toBeFocused()
  })

  test("จอกว้าง: แถบไทม์ไลน์อยู่ใต้ตัวเล่นในคอลัมน์ซ้าย กว้างเท่าตัวเล่น", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    await installFakeYT(page, { durationS: 372 })
    await open(page)
    await play(page)
    const bar = (await timeline(page).boundingBox())!
    const box = (await slot(page).boundingBox())!
    expect(Math.abs(bar.x - box.x)).toBeLessThan(2)
    expect(bar.y).toBeGreaterThan(box.y + box.height - 1)
    expect(bar.y - (box.y + box.height)).toBeLessThan(24)
  })
})

test.describe("แถบไทม์ไลน์: แตะกับปัดบนจอสัมผัส", () => {
  test.use({ hasTouch: true })

  test("จอ 360 px: ปัดขึ้นลงที่เริ่มบนแถบ = เลื่อนหน้า ไม่กระโดด · แตะ = กระโดด", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 740 })
    await installFakeYT(page, { durationS: 372 })
    await open(page, { mostReplayed: REPLAYED, chapters: CHAPTERS })
    await play(page)
    const bar = timeline(page)
    await expect(bar).toBeVisible()
    await expect(bar).toHaveCSS("touch-action", "pan-y")
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollHeight - window.innerHeight))
      .toBeGreaterThan(600)
    const before = (await fakeYTLog(page)).seeks.length
    const box = (await bar.boundingBox())!
    // ปัดนิ้วขึ้น (เลื่อนหน้าลง) โดยเริ่มที่กลางแถบ ผ่าน input pipeline จริงของเบราว์เซอร์ (touch-action มีผล)
    const cdp = await page.context().newCDPSession(page)
    const x = Math.round(box.x + box.width / 2)
    const y = Math.round(box.y + box.height / 2)
    await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x, y }] })
    for (let step = 1; step <= 10; step++) {
      await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x, y: y - step * 30 }] })
    }
    await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] })
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(100)
    expect((await fakeYTLog(page)).seeks.length).toBe(before)

    // กลับขึ้นบน แล้วแตะกลางแถบ = กระโดดไปกลางคลิป (186 วินาที)
    await page.evaluate(() => window.scrollTo(0, 0))
    await expect(bar).toBeVisible()
    const again = (await bar.boundingBox())!
    await page.touchscreen.tap(again.x + again.width / 2, again.y + again.height / 2)
    await expect.poll(async () => (await fakeYTLog(page)).seeks.length).toBeGreaterThan(before)
    const seek = (await fakeYTLog(page)).seeks.at(-1) ?? 0
    expect(Math.abs(seek - 186)).toBeLessThanOrEqual(3)
  })
})

test.describe("แถบไทม์ไลน์กับโปรแกรมอ่านหน้าจอ", () => {
  test("โฟกัสอยู่ที่แถบ: aria-valuetext หยุดนิ่งระหว่างเล่น (หัวอ่านที่ตาเห็นยังเดิน) · อัปเดตเมื่อหยุดคลิป และเมื่อโฟกัสใหม่", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    await installFakeYT(page, { rate: 20, durationS: 372 })
    await open(page)
    await play(page)
    const bar = timeline(page)
    await expect(bar).toBeVisible()
    await bar.focus()
    const first = (await bar.getAttribute("aria-valuetext")) ?? ""
    const playhead = bar.locator('[data-slot="timeline-playhead"]')
    const left = await playhead.evaluate((el) => (el as HTMLElement).style.left)
    await page.waitForTimeout(800)
    expect(await bar.getAttribute("aria-valuetext")).toBe(first)
    expect(await playhead.evaluate((el) => (el as HTMLElement).style.left)).not.toBe(left)

    // หยุดคลิป (ปุ่มของยูทูป) = อัปเดตเป็นเวลาที่หยุด
    await page.evaluate(() => {
      ;(window as unknown as { __fakeYT: { players: { pauseVideo(): void }[] } }).__fakeYT.players[0].pauseVideo()
    })
    await expect(bar).not.toHaveAttribute("aria-valuetext", first)
    const paused = (await bar.getAttribute("aria-valuetext")) ?? ""

    // เล่นต่อ: นิ่งที่ค่าเดิมจนกว่าจะโฟกัสใหม่
    await page.evaluate(() => {
      ;(window as unknown as { __fakeYT: { players: { playVideo(): void }[] } }).__fakeYT.players[0].playVideo()
    })
    await page.waitForTimeout(600)
    expect(await bar.getAttribute("aria-valuetext")).toBe(paused)
    await heading(page).focus()
    await bar.focus()
    await expect(bar).not.toHaveAttribute("aria-valuetext", paused)
  })
})

test.describe("โฟกัสไม่หลุดเมื่อปุ่มของตัวเล่นหายไปเอง", () => {
  test("โฟกัสที่แถบไทม์ไลน์แล้วเลื่อนจอจนตัวเล่นลอย → 'กลับไปที่หัวคลิป' บนตัวเล่นลอย · เลื่อนกลับ → แถบไทม์ไลน์", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    await installFakeYT(page)
    await open(page)
    await play(page)
    await timeline(page).focus()
    await scrollAway(page)
    await expect(dock(page)).toBeVisible()
    await expect(dock(page).getByRole("button", { name: "กลับไปที่หัวคลิป" })).toBeFocused()
    const scrolled = await page.evaluate(() => window.scrollY)
    expect(scrolled).toBeGreaterThan(600)

    await page.evaluate(() => window.scrollTo(0, 0))
    await expect(dock(page)).toHaveCount(0)
    await expect(timeline(page)).toBeFocused()
    expect(await page.evaluate(() => window.scrollY)).toBe(0)
  })

  test("โฟกัสที่ปุ่มหยุดช่วงไฮไลต์บนตัวเล่นลอยแล้วเลื่อนกลับขึ้น → แถบไทม์ไลน์", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    await installFakeYT(page, { rate: 1 })
    await open(page, { mostReplayed: REPLAYED })
    await reelButton(page).click()
    await expect(reelStatus(page)).toHaveText(/ช่วง 1 จาก 2/)
    await scrollAway(page)
    await expect(dock(page)).toBeVisible()
    await dock(page).getByRole("button", { name: REEL_STOP }).focus()
    await page.evaluate(() => window.scrollTo(0, 0))
    await expect(dock(page)).toHaveCount(0)
    await expect(timeline(page)).toBeFocused()
  })
})

test.describe("ข้อความผิดพลาดกับโฟกัส", () => {
  test("ผิดพลาดครั้งแรกตอนผู้ใช้กด ▶ ของภาพเฟรม: ไม่แย่งโฟกัสจากภาพเฟรม · กดเล่นจากภาพอีกครั้ง = โฟกัสข้อความผิดพลาด", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    await installFakeYT(page, { errorCode: 150 })
    await open(page)
    const tile = frameList(page).getByRole("listitem").nth(2)
    await tile.hover()
    const corner = tile.getByRole("button", { name: /^เล่นจากตรงนี้ / })
    await corner.click()
    const alert = slot(page).getByRole("alert")
    await expect(alert).toBeVisible()
    await page.waitForTimeout(200)
    await expect(corner).toBeFocused()

    await corner.click()
    await expect(alert).toBeFocused()
  })
})

test.describe("ตัวเล่นยูทูปแบบที่เจอจริง (fake-yt)", () => {
  test("เวลาเก่าค้างหลัง seek นาน 1.5 วินาที (เน็ตช้า): หัวอ่านไม่เด้งกลับตำแหน่งเก่า แล้วเดินต่อจากจุดใหม่", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    await installFakeYT(page, { rate: 1, durationS: 372, staleAfterSeekMs: 1500 })
    await open(page)
    await play(page)
    const bar = timeline(page)
    await expect(bar).toBeVisible()
    const box = (await bar.boundingBox())!
    // จด left ของหัวอ่านทุก 50 ms ช่วง 2.5 วินาที ระหว่างนั้นคลิกกลางแถบ (186 วินาที = 50%)
    const samples = page.evaluate(
      () =>
        new Promise<number[]>((resolve) => {
          const out: number[] = []
          const read = () => {
            const el = document.querySelector<HTMLElement>('[data-slot="timeline-playhead"]')
            if (el) out.push(parseFloat(el.style.left))
          }
          const id = setInterval(read, 50)
          setTimeout(() => {
            clearInterval(id)
            resolve(out)
          }, 2500)
        }),
    )
    await page.waitForTimeout(100)
    await bar.click({ position: { x: box.width / 2, y: box.height / 2 } })
    const values = await samples
    const jumped = values.findIndex((value) => value >= 49)
    expect(jumped).toBeGreaterThanOrEqual(0)
    expect(Math.min(...values.slice(jumped))).toBeGreaterThanOrEqual(49)
    // พ้นช่วงค้างแล้วเดินต่อจากจุดใหม่ (ไม่ติดค้างที่จุดที่ seek)
    await expect
      .poll(() => bar.locator('[data-slot="timeline-playhead"]').evaluate((el) => parseFloat((el as HTMLElement).style.left)))
      .toBeGreaterThan(50.2)
  })

  test("เบราว์เซอร์ไม่ให้เล่นเอง: พร้อมแล้วหยุดอยู่ที่เวลาที่ขอ ไม่มี error ไม่ค้างกำลังโหลด · กดเล่นในตัวเล่นยูทูปแล้วเดินต่อ", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    await installFakeYT(page, { rate: 1, durationS: 372, autoplayBlocked: true })
    await open(page)
    const tile = frameList(page).getByRole("listitem").nth(2)
    await tile.hover()
    await tile.getByRole("button", { name: "เล่นจากตรงนี้ 00:00:09", exact: true }).click()
    await expect.poll(async () => (await fakeYTLog(page)).calls).toContain("play-blocked")
    await expect(iframe(page)).toHaveCount(1)
    await expect(slot(page).getByRole("alert")).toHaveCount(0)
    await expect(page.getByLabel("กำลังโหลดตัวเล่น")).toHaveCount(0)
    // หยุดอยู่ที่เวลาที่ขอ: ภาพเฟรมนั้นมีกรอบ "กำลังเล่น" แถบไทม์ไลน์อยู่ที่เวลานั้น และไม่เดิน
    await expect(frameList(page).locator("[data-now-playing] img")).toHaveAttribute("alt", "ภาพเฟรมที่ 00:00:09")
    await expect(timeline(page)).toHaveAttribute("aria-valuetext", "00:00:09")
    await page.waitForTimeout(1200)
    await expect(timeline(page)).toHaveAttribute("aria-valuetext", "00:00:09")

    // ผู้ใช้กดปุ่มเล่นของยูทูปเอง
    await page.evaluate(() => {
      ;(window as unknown as { __fakeYT: { players: { playVideo(): void }[] } }).__fakeYT.players[0].playVideo()
    })
    await expect(timeline(page)).not.toHaveAttribute("aria-valuetext", "00:00:09", { timeout: 5000 })
  })

  test("เล่นถึงท้ายคลิประหว่างเล่นช่วงไฮไลต์ (ENDED): ช่วงไฮไลต์จบ กรอบภาพเฟรมและบรรทัดที่กำลังเล่นหายไป ไม่มี error", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    // คลิปยาว 30 วินาที (ตัวเล่นปลอม) ช่วงไฮไลต์ 20-40 วินาที: ถึงท้ายคลิปก่อนท้ายช่วง
    await installFakeYT(page, { rate: 5, durationS: 30 })
    await open(page, { mostReplayed: [{ startMs: 20_000, endMs: 40_000 }] })
    await reelButton(page).click()
    await expect(reelStatus(page)).toHaveText(/ช่วง 1 จาก 1/)
    await expect(frameList(page).locator("[data-now-playing]")).toHaveCount(1)
    await expect.poll(async () => (await fakeYTLog(page)).states, { timeout: 10_000 }).toContain(0)
    await expect(reelStatus(page)).toHaveCount(0)
    await expect(frameList(page).locator("[data-now-playing]")).toHaveCount(0)
    await expect(slot(page).getByRole("alert")).toHaveCount(0)
    await expect(iframe(page)).toHaveCount(1)
    await page.getByRole("tab", { name: "ทรานสคริปต์", exact: true }).click()
    const lines = page.getByRole("list", { name: "บรรทัดในทรานสคริปต์" })
    await expect(lines.getByRole("listitem").first()).toBeVisible()
    await expect(lines.locator("[data-playing]")).toHaveCount(0)
    await expect(page.getByRole("button", { name: "กลับไปบรรทัดที่กำลังเล่น" })).toHaveCount(0)
  })
})

test.describe("axe ทุกสถานะของตัวเล่น", () => {
  const axe = async (page: Page) => {
    await settle(page)
    const results = await new AxeBuilder({ page }).analyze()
    expect(results.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([])
  }

  test("ก่อนเล่น · เล่นในหัวคลิป · ลอย · ช่วงไฮไลต์", async ({ page }) => {
    await installFakeYT(page, { rate: 1 })
    await open(page, { mostReplayed: REPLAYED, chapters: CHAPTERS })
    await axe(page)
    await play(page)
    await expect(timeline(page)).toBeVisible()
    await axe(page)
    await reelButton(page).click()
    await expect(reelStatus(page)).toHaveText(/ช่วง 1 จาก 2/)
    await axe(page)
    await scrollAway(page)
    await expect(dock(page)).toBeVisible()
    await axe(page)
  })

  test("ผิดพลาด (150)", async ({ page }) => {
    await installFakeYT(page, { errorCode: 150 })
    await open(page)
    await playButton(page).click()
    await expect(slot(page).getByRole("alert")).toBeVisible()
    await axe(page)
  })

  test("ออฟไลน์", async ({ page }) => {
    await installFakeYT(page, { failScript: true })
    await open(page)
    await playButton(page).click()
    await expect(slot(page).getByRole("alert")).toBeVisible()
    await axe(page)
  })
})
