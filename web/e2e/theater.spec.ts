/// <reference lib="dom" />
import AxeBuilder from "@axe-core/playwright"
import { expect, test, type Page } from "@playwright/test"

import { fakeYTLog, installFakeYT } from "./fake-yt"

/**
 * M5 รอบ B2 โหมดโรงภาพยนตร์ (spec 1): กด ▶ แล้วขยาย · ปุ่ม/T สลับ · จำค่าข้ามคลิป · คลิปแนวตั้ง · จอแคบ · ลดการเคลื่อนไหว
 * ตัวเล่นปลอม (installFakeYT) ไม่ต่อยูทูปจริง ไม่สร้างงาน · ไฟล์นี้ล้างค่า "0" ที่ project chromium ตั้งไว้ (playwright.config)
 * เพื่อทดสอบค่าเริ่มต้นจริง (ไม่มีค่า = โรงภาพยนตร์)
 */
test.use({ storageState: { cookies: [], origins: [] } })

const BBB = "aqz-KE-bpKQ" // 635 วิ แนวนอน สูงสุด 3840x2160
const THAI = "88o5Sk8_m1Y"

const header = (page: Page) => page.locator('[data-slot="video-header"]')
const slot = (page: Page) => page.locator('[data-slot="player-slot"]')
const iframe = (page: Page) => page.locator('[data-slot="player-host"] iframe')
const toggle = (page: Page) => page.locator('[data-slot="theater-toggle"]')
const heading = (page: Page) => page.getByRole("heading", { level: 1 })
const dock = (page: Page) => page.getByRole("region", { name: "ตัวเล่นคลิป (ลอย)" })
const stored = (page: Page) => page.evaluate(() => window.localStorage.getItem("yt-toolkit:theater"))

/** นับครั้งที่เรียก document.startViewTransition (ต้องติดตั้งก่อน goto) */
async function countTransitions(page: Page) {
  await page.addInitScript(() => {
    const w = window as unknown as { __vt: number }
    w.__vt = 0
    if (typeof document.startViewTransition !== "function") return
    const original = document.startViewTransition.bind(document)
    document.startViewTransition = ((update?: ViewTransitionUpdateCallback) => {
      w.__vt += 1
      return original(update)
    }) as typeof document.startViewTransition
  })
}
const transitions = (page: Page) => page.evaluate(() => (window as unknown as { __vt: number }).__vt)

async function open(page: Page, videoId: string) {
  await installFakeYT(page, { durationS: 635, rate: 0.001 })
  await page.goto(`/v/${videoId}`)
  await expect(heading(page)).not.toBeEmpty()
}

/**
 * รอให้การสลับเลย์เอาต์ (view transition ราว 300 ms) จบ: ระหว่างนั้น <html> รับการคลิกแทนทุกอย่าง (พฤติกรรมของเบราว์เซอร์)
 * ถ้าคลิกตอนนั้น Playwright ลองใหม่โดยบังคับเลื่อนจอ (scrollIntoView end/center/start) จนช่องตัวเล่นพ้นจอครึ่งหนึ่ง
 * ตัวเล่นจึงลอยและแถวปุ่มใต้ตัวเล่นหายไป (gate 2) · คีย์บอร์ดไม่ต้องรอ (ไม่มีการเลื่อนจอ)
 */
const settled = (page: Page) => expect(page.locator("html[data-theater-switching]")).toHaveCount(0)

/** กดปุ่มสลับหลังการสลับครั้งก่อนจบแล้ว */
async function clickToggle(page: Page) {
  await settled(page)
  await toggle(page).click()
}

/** กด ▶ ในช่องตัวเล่น แล้วรอจนตัวเล่นปลอมเล่นอยู่และการขยาย (ถ้ามี) จบแล้ว */
async function play(page: Page) {
  await page.getByRole("button", { name: "เล่นคลิป", exact: true }).click()
  await expect(iframe(page)).toHaveCount(1)
  await expect.poll(async () => (await fakeYTLog(page)).calls).toContain("play")
  await settled(page)
}

/** ข้อมูลคลิปจาก backend โหมด fake แต่สลับกว้าง/สูง: คลิปกลายเป็นแนวตั้ง */
async function asPortrait(page: Page, videoId: string) {
  await page.route(
    (url) => url.pathname === `/api/videos/${videoId}`,
    async (route) => {
      const response = await route.fetch()
      const body = (await response.json()) as { video: { width?: number; height: number }[] }
      const video = body.video.map((f) => (f.width ? { ...f, width: f.height, height: f.width } : f))
      await route.fulfill({ response, json: { ...body, video } })
    },
  )
}

async function seriousViolations(page: Page) {
  const results = await new AxeBuilder({ page }).analyze()
  return results.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)
}

test("▶ ขยายเต็มความกว้างโดยไม่โหลดตัวเล่นใหม่ · ปุ่มและปุ่ม T สลับ · จำค่าไว้", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 })
  await countTransitions(page)
  await open(page, BBB)
  await expect(header(page)).toHaveAttribute("data-layout", "compact")
  await expect(toggle(page)).toHaveCount(0)
  expect((await slot(page).boundingBox())?.width ?? 0).toBeLessThan(300)

  await play(page)
  await expect(header(page)).toHaveAttribute("data-layout", "theater-wide")
  await expect.poll(async () => (await slot(page).boundingBox())?.width ?? 0).toBeGreaterThan(900)
  const slotBox = (await slot(page).boundingBox())!
  expect((await heading(page).boundingBox())!.y).toBeGreaterThan(slotBox.y + slotBox.height)
  await expect(toggle(page)).toHaveText("ย่อตัวเล่น (T)")
  await expect(toggle(page)).toHaveAttribute("aria-pressed", "true")
  expect(await transitions(page)).toBeGreaterThan(0)
  await toggle(page).hover()
  await expect(page.getByText("โหมดโรงภาพยนตร์", { exact: true })).toBeVisible()

  await iframe(page).evaluate((node) => node.setAttribute("data-marker", "same"))
  await heading(page).click()
  await page.keyboard.press("t")
  await expect(header(page)).toHaveAttribute("data-layout", "compact")
  await expect(toggle(page)).toHaveText("ขยายตัวเล่น (T)")
  await expect(toggle(page)).toHaveAttribute("aria-pressed", "false")
  expect(await stored(page)).toBe("0")
  await clickToggle(page)
  await expect(header(page)).toHaveAttribute("data-layout", "theater-wide")
  expect(await stored(page)).toBe("1")
  // สลับไปมาแล้วยังเป็น iframe ตัวเดิม (ไม่ถูกสร้างใหม่ ไม่โหลดใหม่)
  await expect(iframe(page)).toHaveAttribute("data-marker", "same")
  expect((await fakeYTLog(page)).players).toBe(1)
})

test("ค่าที่จำไว้ใช้กับทุกคลิป · เปิดคลิปอื่นเริ่มแบบปกติจนกว่าจะกด ▶", async ({ page }) => {
  await open(page, BBB)
  await play(page)
  await clickToggle(page)
  await expect(header(page)).toHaveAttribute("data-layout", "compact")

  await open(page, THAI)
  await expect(header(page)).toHaveAttribute("data-layout", "compact")
  await play(page)
  await expect(header(page)).toHaveAttribute("data-layout", "compact")
  await clickToggle(page)
  await expect(header(page)).toHaveAttribute("data-layout", "theater-wide")

  await open(page, BBB)
  await expect(header(page)).toHaveAttribute("data-layout", "compact")
  await play(page)
  await expect(header(page)).toHaveAttribute("data-layout", "theater-wide")
})

test("ปุ่ม T ไม่ทำงานตอนพิมพ์ในช่อง มีกล่องเปิดอยู่ หรือกด Alt · Shift+T ใช้ได้", async ({ page }) => {
  await installFakeYT(page, { durationS: 635, rate: 0.001 })
  await page.goto(`/v/${BBB}?tab=video`)
  await play(page)
  await expect(header(page)).toHaveAttribute("data-layout", "theater-wide")

  await page.getByRole("button", { name: "ตัวเลือกขั้นสูง", exact: true }).click()
  await page.getByRole("tabpanel").getByRole("textbox", { name: "เริ่ม", exact: true }).click()
  await page.keyboard.press("t")
  await expect(header(page)).toHaveAttribute("data-layout", "theater-wide")

  await heading(page).click()
  await page.keyboard.press("Alt+t")
  await expect(header(page)).toHaveAttribute("data-layout", "theater-wide")

  await page.getByRole("button", { name: "ดูภาพปก", exact: true }).click()
  await expect(page.getByRole("dialog")).toBeVisible()
  await page.keyboard.press("t")
  await expect(header(page)).toHaveAttribute("data-layout", "theater-wide")
  await page.keyboard.press("Escape")
  await expect(page.getByRole("dialog")).toHaveCount(0)

  await page.keyboard.press("Shift+KeyT")
  await expect(header(page)).toHaveAttribute("data-layout", "compact")
})

test("ปุ่ม T บนแป้นภาษาไทย (ได้ตัว ะ แต่ตำแหน่งปุ่มเป็น KeyT) ก็สลับได้", async ({ page }) => {
  await open(page, BBB)
  await play(page)
  await expect(header(page)).toHaveAttribute("data-layout", "theater-wide")
  await heading(page).click()
  // เลย์เอาต์ภาษาไทย: key เป็นตัวอักษรไทย แต่ code ยังเป็นตำแหน่งปุ่ม T
  await heading(page).dispatchEvent("keydown", { key: "ะ", code: "KeyT", bubbles: true, cancelable: true })
  await expect(header(page)).toHaveAttribute("data-layout", "compact")
  expect(await stored(page)).toBe("0")
})

test("คลิปแนวตั้ง: ตัวเล่นสูง 80% ของจอทางซ้าย ข้อมูลและแถวใต้ตัวเล่นอยู่ทางขวา", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 })
  await asPortrait(page, BBB)
  await open(page, BBB)
  await play(page)
  await expect(header(page)).toHaveAttribute("data-layout", "theater-tall")
  await expect.poll(async () => Math.round((await slot(page).boundingBox())?.height ?? 0)).toBe(720)
  const box = (await slot(page).boundingBox())!
  expect(box.width / box.height).toBeCloseTo(9 / 16, 2)
  const title = (await heading(page).boundingBox())!
  expect(title.x).toBeGreaterThan(box.x + box.width - 1)
  expect(title.y).toBeLessThan(box.y + box.height)
  const bar = (await page.getByRole("slider", { name: "ตำแหน่งในคลิป" }).boundingBox())!
  expect(bar.x).toBeGreaterThan(box.x + box.width - 1)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)

  // แถวใต้ตัวเล่นย้ายคอลัมน์ทุกครั้งที่สลับ: โฟกัสต้องอยู่ที่ปุ่มสลับต่อ (ไม่หลุดไป "ดูภาพปก" จน Enter ครั้งที่สองเปิดภาพปก)
  await toggle(page).focus()
  await page.keyboard.press("Enter")
  await expect(header(page)).toHaveAttribute("data-layout", "compact")
  await expect(toggle(page)).toBeFocused()
  await page.keyboard.press("Enter")
  await expect(header(page)).toHaveAttribute("data-layout", "theater-tall")
  await expect(toggle(page)).toBeFocused()
  await expect(page.getByRole("dialog")).toHaveCount(0)
})

test("ปิดตัวเล่นลอยตอนขยายอยู่: เลย์เอาต์คงเดิม ยังย่อกลับได้ด้วยปุ่มและปุ่ม T", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await open(page, BBB)
  await play(page)
  await expect(header(page)).toHaveAttribute("data-layout", "theater-wide")
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollHeight - window.innerHeight)).toBeGreaterThan(1500)
  await page.evaluate(() => window.scrollTo(0, 2000))
  await dock(page).getByRole("button", { name: "ปิดตัวเล่น", exact: true }).click()
  await expect(iframe(page)).toHaveCount(0)
  await page.evaluate(() => window.scrollTo(0, 0))

  await expect(header(page)).toHaveAttribute("data-layout", "theater-wide")
  await expect(toggle(page)).toHaveText("ย่อตัวเล่น (T)")
  await heading(page).click()
  await page.keyboard.press("t")
  await expect(header(page)).toHaveAttribute("data-layout", "compact")
  expect(await stored(page)).toBe("0")
  // ย่อแล้วไม่มีปุ่มจนกว่าจะกด ▶ อีกครั้ง (เหมือนก่อนเล่น) และ T ไม่ทำงาน
  await expect(toggle(page)).toHaveCount(0)
  await page.keyboard.press("t")
  await expect(header(page)).toHaveAttribute("data-layout", "compact")

  // กด ▶ อีกครั้ง (ค่าที่จำไว้ = แบบปกติ) แล้วขยายด้วยปุ่ม · ปิดอีกรอบแล้วย่อด้วยคีย์บอร์ด: โฟกัสไปที่ ▶ ไม่หลุดไป body
  await play(page)
  await clickToggle(page)
  await expect(header(page)).toHaveAttribute("data-layout", "theater-wide")
  await page.evaluate(() => window.scrollTo(0, 2000))
  await dock(page).getByRole("button", { name: "ปิดตัวเล่น", exact: true }).click()
  await expect(iframe(page)).toHaveCount(0)
  await page.evaluate(() => window.scrollTo(0, 0))
  await toggle(page).focus()
  await page.keyboard.press("Enter")
  await expect(header(page)).toHaveAttribute("data-layout", "compact")
  await expect(page.getByRole("button", { name: "เล่นคลิป", exact: true })).toBeFocused()
})

test("จอแคบ 600 px: แบบปกติเสมอ ไม่มีปุ่ม และปุ่ม T ไม่ทำงาน", async ({ page }) => {
  await page.setViewportSize({ width: 600, height: 800 })
  await open(page, BBB)
  await play(page)
  await expect(header(page)).toHaveAttribute("data-layout", "compact")
  await expect(toggle(page)).toHaveCount(0)
  await heading(page).click()
  await page.keyboard.press("t")
  await expect(header(page)).toHaveAttribute("data-layout", "compact")
  expect(await stored(page)).toBeNull()
})

test("ลดการเคลื่อนไหว: เลย์เอาต์เหมือนกันแต่ไม่มี view transition", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" })
  await countTransitions(page)
  await open(page, BBB)
  await play(page)
  await expect(header(page)).toHaveAttribute("data-layout", "theater-wide")
  await clickToggle(page)
  await expect(header(page)).toHaveAttribute("data-layout", "compact")
  expect(await transitions(page)).toBe(0)
})

test("ตัวเล่นลอยในโหมดโรงภาพยนตร์ · T สลับได้ระหว่างลอยโดยไม่มีแอนิเมชัน", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await countTransitions(page)
  await open(page, BBB)
  await play(page)
  await expect(header(page)).toHaveAttribute("data-layout", "theater-wide")
  const before = await transitions(page)
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollHeight - window.innerHeight)).toBeGreaterThan(1500)
  await page.evaluate(() => window.scrollTo(0, 2000))
  await expect(dock(page)).toBeVisible()
  await page.keyboard.press("t")
  await expect(header(page)).toHaveAttribute("data-layout", "compact")
  expect(await transitions(page)).toBe(before)
  expect((await fakeYTLog(page)).players).toBe(1)
})

for (const scheme of ["light", "dark"] as const) {
  for (const portrait of [false, true]) {
    const layout = portrait ? "theater-tall" : "theater-wide"
    test(`axe ไม่มีปัญหาร้ายแรงในโหมดโรงภาพยนตร์ ${layout} (${scheme}) · 640 px ไม่ล้นแนวนอน`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme })
      await page.setViewportSize({ width: 640, height: 800 })
      if (portrait) await asPortrait(page, BBB)
      await open(page, BBB)
      await play(page)
      await expect(header(page)).toHaveAttribute("data-layout", layout)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
      expect(await seriousViolations(page)).toEqual([])
    })
  }
}
