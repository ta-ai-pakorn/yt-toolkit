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
    await expect(page.getByRole("button", { name: "กำลังเล่นที่มุมจอ" })).toBeAttached()
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
    const placeholder = page.getByRole("button", { name: "กำลังเล่นที่มุมจอ" })
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

  test("เล่นทีละช่วงตามลำดับ 'ช่วง 1 จาก 2' → 'ช่วง 2 จาก 2' แล้วหยุดหลังช่วงสุดท้าย", async ({ page }) => {
    await installFakeYT(page, { rate: 20 })
    await open(page, { mostReplayed: REPLAYED })
    const button = page.getByRole("button", { name: REEL })
    await expect(button).toBeVisible()
    await button.click()
    await expect(page.getByText("ช่วง 1 จาก 2")).toBeVisible()
    const stop = page.getByRole("button", { name: REEL_STOP })
    await expect(stop).toBeVisible()
    await expect(page.getByText("ช่วง 2 จาก 2")).toBeVisible()
    await expect(page.getByRole("button", { name: REEL })).toBeVisible({ timeout: 5000 })
    await expect(page.getByText(/^ช่วง \d จาก 2$/)).toHaveCount(0)
    const log = await fakeYTLog(page)
    expect(log.seeks.slice(0, 2)).toEqual([20, 60])
    expect(log.calls.at(-1)).toBe("pause")
  })

  test("'หยุดเล่นช่วงไฮไลต์' หยุดคลิป · seek เองที่แถบไทม์ไลน์ยกเลิกช่วงไฮไลต์", async ({ page }) => {
    await installFakeYT(page, { rate: 1 })
    await open(page, { mostReplayed: REPLAYED })
    await page.getByRole("button", { name: REEL }).click()
    await expect(page.getByText("ช่วง 1 จาก 2")).toBeVisible()
    await page.getByRole("button", { name: REEL_STOP }).click()
    await expect(page.getByText("ช่วง 1 จาก 2")).toHaveCount(0)
    // ปุ่มเดียวกัน โฟกัสไม่หลุด
    await expect(page.getByRole("button", { name: REEL })).toBeFocused()
    expect((await fakeYTLog(page)).calls.at(-1)).toBe("pause")

    await page.getByRole("button", { name: REEL }).click()
    await expect(page.getByText("ช่วง 1 จาก 2")).toBeVisible()
    await timeline(page).click({ position: { x: 5, y: 10 } })
    await expect(page.getByText("ช่วง 1 จาก 2")).toHaveCount(0)
    await expect(page.getByRole("button", { name: REEL })).toBeVisible()
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
  test("ตัวเล่นในช่องปกเล็ก แถบไทม์ไลน์และปุ่มช่วงไฮไลต์เต็มแถว · ลอย = แถบเต็มความกว้างล่างจอ วิดีโอราว 40% · ไม่มีเลื่อนแนวนอน", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 360, height: 740 })
    await installFakeYT(page)
    await open(page, { mostReplayed: REPLAYED, chapters: CHAPTERS })
    await play(page)
    const bar = await timeline(page).boundingBox()
    expect(bar?.width ?? 0).toBeGreaterThan(300)
    expect(bar?.height ?? 0).toBeGreaterThanOrEqual(44)
    const reel = await page.getByRole("button", { name: REEL }).boundingBox()
    expect(reel?.height ?? 0).toBeGreaterThanOrEqual(44)
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
    await page.getByRole("button", { name: REEL }).click()
    await expect(page.getByText("ช่วง 1 จาก 2")).toBeVisible()
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
