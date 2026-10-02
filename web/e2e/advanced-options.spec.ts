/// <reference lib="dom" />
import AxeBuilder from "@axe-core/playwright"
import { expect, test, type Page } from "@playwright/test"

import type { AudioJobParams, Settings, SubtitleJobParams, VideoJobParams } from "../src/lib/types"

import { mockEnqueue } from "./queue-helpers"

/**
 * M5 รอบ A: "ตัวเลือกขั้นสูง" ในแท็บวิดีโอ เสียง ซับ (โปรเจกต์ chromium: ทุกเทสที่กดโหลดดัก POST /api/jobs ด้วย mockEnqueue
 * และทุกเทสที่ติ๊กหมวด SponsorBlock ดัก PATCH /api/settings ไม่มีงานจริงและไม่แก้การตั้งค่าจริง)
 */

const THAI = "88o5Sk8_m1Y" // 372 วิ มีซับ a.th-orig ไม่มี chapter
const BBB = "aqz-KE-bpKQ" // 635 วิ ไม่มีซับ ไม่มี chapter
const ZOO = "jNQXAC9IVRw" // 19 วิ 3 chapter มีซับเจ้าของคลิป

const ADVANCED = "ตัวเลือกขั้นสูง"
const ACTIVE = "ใช้ตัวเลือกขั้นสูงอยู่"
const CHAPTERS = "แยกไฟล์ตาม chapter"
const ADS = "ตัดโฆษณา (SponsorBlock)"

const tab = (page: Page, name: string) => page.getByRole("tab", { name, exact: true })
const panel = (page: Page) => page.getByRole("tabpanel")
const button = (page: Page, name: string) => page.getByRole("button", { name, exact: true })
// ช่องเวลา (role textbox) · ใช้ getByRole ไม่ใช่ getByLabel เพราะกลุ่มของช่องก็มีชื่อ "เริ่ม"/"จบ" (role group)
const field = (page: Page, name: "เริ่ม" | "จบ") => panel(page).getByRole("textbox", { name, exact: true })

async function openAdvanced(page: Page) {
  const trigger = button(page, ADVANCED)
  if ((await trigger.getAttribute("aria-expanded")) !== "true") await trigger.click()
  await expect(trigger).toHaveAttribute("aria-expanded", "true")
}

async function setRange(page: Page, start: string, end: string) {
  await openAdvanced(page)
  await field(page, "เริ่ม").fill(start)
  await field(page, "จบ").fill(end)
  await field(page, "จบ").blur()
}

/**
 * ดัก GET/PATCH /api/settings: อ่านค่าจริงครั้งแรกครั้งเดียว แล้วตอบจากสำเนาในเทส (PATCH รวมค่าที่ส่งมา ไม่แตะ backend)
 * GET ที่ตามมา (เช่น react-query โหลดใหม่) จึงเห็นค่าที่ติ๊กไว้ ไม่เด้งกลับเป็นค่าของ backend
 */
async function mockSettings(page: Page): Promise<{ bodies: Partial<Settings>[] }> {
  const bodies: Partial<Settings>[] = []
  let current: Settings | null = null
  await page.route("**/api/settings", async (route) => {
    const method = route.request().method()
    if (method !== "GET" && method !== "PATCH") return route.fallback()
    if (current === null) current = (await (await route.fetch({ method: "GET" })).json()) as Settings
    if (method === "PATCH") {
      const body = route.request().postDataJSON() as Partial<Settings>
      bodies.push(body)
      current = { ...current, ...body }
    }
    await route.fulfill({ json: current })
  })
  return { bodies }
}

async function seriousViolations(page: Page) {
  const results = await new AxeBuilder({ page }).analyze()
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target.join(" ")).slice(0, 5) }))
}

test.describe("ตัวเลือกขั้นสูง: ช่วงเวลา", () => {
  test("พับไว้ตอนแรก · ตั้ง 1:30-5:00 แล้วทุกแท็บเห็นค่าเดียวกัน ป้ายปุ่มและป้าย 'ใช้ตัวเลือกขั้นสูงอยู่' · ส่งช่วงไปกับงาน", async ({ page }) => {
    const { bodies } = await mockEnqueue(page)
    await page.goto(`/v/${THAI}?tab=video`)
    await expect(button(page, "โหลด mp4")).toBeEnabled()
    await expect(button(page, ADVANCED)).toHaveAttribute("aria-expanded", "false")
    await expect(page.getByText(ACTIVE)).toHaveCount(0)
    await setRange(page, "1:30", "5:00")
    await expect(panel(page).getByText(ACTIVE)).toBeVisible()
    await expect(panel(page).getByText("ตัดตรงจุดที่ตั้งเป๊ะ ใช้เวลาแปลงไฟล์เพิ่ม")).toBeVisible()
    await button(page, "โหลด mp4 (1:30-5:00)").click()
    await expect.poll(() => bodies.length).toBe(1)
    expect((bodies[0][0].params as VideoJobParams).range).toEqual({ startMs: 90_000, endMs: 300_000 })

    await tab(page, "เสียง").click()
    await expect(panel(page).getByText(ACTIVE)).toBeVisible()
    await button(page, "โหลด m4a (1:30-5:00)").click()
    await expect.poll(() => bodies.length).toBe(2)
    expect((bodies[1][0].params as AudioJobParams).range).toEqual({ startMs: 90_000, endMs: 300_000 })

    await tab(page, "ซับ").click()
    await expect(page.getByRole("heading", { name: "ตัวอย่าง 5 ซับแรก (1:30-5:00)" })).toBeVisible()
    await button(page, "โหลด .srt (1:30-5:00)").click()
    await expect.poll(() => bodies.length).toBe(3)
    expect((bodies[2][0].params as SubtitleJobParams).range).toEqual({ startMs: 90_000, endMs: 300_000 })
    await expect(button(page, "โหลด .txt (1:30-5:00)")).toBeVisible()
  })

  test("ช่องผิดรูปแบบ / เริ่มไม่ก่อนจบ / เกินความยาวคลิป: ปุ่มยังกดได้ error ใต้ช่อง ไม่สร้างงาน (AC-ADV-02)", async ({ page }) => {
    const { bodies } = await mockEnqueue(page)
    await page.goto(`/v/${THAI}?tab=video`)
    await setRange(page, "5:00", "1:30")
    const start = field(page, "เริ่ม")
    await expect(panel(page).getByText("จุดเริ่มต้องมาก่อนจุดจบ")).toBeVisible()
    await expect(start).toHaveAttribute("aria-invalid", "true")
    await expect(start).toHaveAccessibleDescription("จุดเริ่มต้องมาก่อนจุดจบ")
    await button(page, "โหลด mp4").click()
    await setRange(page, "1:3x", "")
    await expect(panel(page).getByText("พิมพ์เวลาแบบ 1:30 หรือ 1:02:30")).toBeVisible()
    await setRange(page, "", "9:00")
    await expect(panel(page).getByText("เกินความยาวคลิป (6:12)")).toBeVisible()
    await button(page, "โหลด mp4").click()
    await expect(field(page, "จบ")).toBeFocused()
    await page.waitForTimeout(300)
    expect(bodies).toHaveLength(0)
  })

  test("เปิดคลิปอื่น = ค่าเริ่มใหม่ (D3)", async ({ page }) => {
    await page.goto(`/v/${THAI}?tab=video`)
    await setRange(page, "1:30", "5:00")
    await page.goto(`/v/${BBB}?tab=video`)
    await expect(button(page, "โหลด mp4")).toBeVisible()
    await expect(page.getByText(ACTIVE)).toHaveCount(0)
    await openAdvanced(page)
    await expect(field(page, "เริ่ม")).toHaveValue("")
  })

  test("คลิปที่ไม่รู้ความยาว: ช่องเวลากดไม่ได้พร้อมเหตุผล", async ({ page }) => {
    await page.route(
      (url) => url.pathname === `/api/videos/${BBB}`,
      async (route) => {
        const response = await route.fetch()
        await route.fulfill({ response, json: { ...((await response.json()) as object), durationS: 0 } })
      },
    )
    await page.goto(`/v/${BBB}?tab=video`)
    await openAdvanced(page)
    await expect(field(page, "เริ่ม")).toBeDisabled()
    await expect(panel(page).getByText("คลิปสดหรือคลิปที่ไม่รู้ความยาว ตั้งช่วงเวลาไม่ได้")).toBeVisible()
  })

  test("ขนาดประมาณย่อตามช่วง", async ({ page }) => {
    await page.goto(`/v/${BBB}?tab=video`)
    const estimate = panel(page).getByText(/^ขนาดประมาณ /)
    const before = await estimate.textContent()
    await setRange(page, "0:00", "1:00")
    await expect(estimate).not.toHaveText(before ?? "")
  })
})

test.describe("ตัวเลือกขั้นสูง: แยกไฟล์ตาม chapter", () => {
  test("มีเฉพาะคลิปที่มี >= 2 chapter และไม่อยู่ในแท็บซับ", async ({ page }) => {
    await page.goto(`/v/${BBB}?tab=video`)
    await openAdvanced(page)
    await expect(page.getByRole("switch", { name: CHAPTERS })).toHaveCount(0)
    await page.goto(`/v/${ZOO}?tab=audio`)
    await openAdvanced(page)
    await expect(page.getByRole("switch", { name: CHAPTERS })).toBeVisible()
    await tab(page, "ซับ").click()
    await expect(button(page, ADVANCED)).toBeVisible()
    await expect(page.getByRole("switch", { name: CHAPTERS })).toHaveCount(0)
  })

  test("เปิดแล้ว: ป้ายปุ่ม ช่องเวลา/ตัดโฆษณา/ฝังซับกดไม่ได้ · ส่ง splitChapters อย่างเดียว", async ({ page }) => {
    const { bodies } = await mockEnqueue(page)
    await page.goto(`/v/${ZOO}?tab=video`)
    await openAdvanced(page)
    await page.getByRole("switch", { name: CHAPTERS }).click()
    await expect(panel(page).getByText("ได้ไฟล์ละ 1 chapter ในโฟลเดอร์ย่อย · ขอบแต่ละ chapter อาจคลาด 1-3 วินาที")).toBeVisible()
    await expect(field(page, "เริ่ม")).toBeDisabled()
    await expect(page.getByRole("switch", { name: ADS })).toBeDisabled()
    await expect(page.getByRole("combobox", { name: "ฝังซับ (เปิด/ปิดได้)", exact: true })).toBeDisabled()
    await expect(panel(page).getByText("ปิด 'แยกไฟล์ตาม chapter' ก่อน").first()).toBeVisible()
    await button(page, "โหลด mp4 (แยก chapter)").click()
    await expect.poll(() => bodies.length).toBe(1)
    const params = bodies[0][0].params as VideoJobParams
    expect(params.splitChapters).toBe(true)
    expect(params).not.toHaveProperty("range")
    expect(params).not.toHaveProperty("sponsorblock")
    expect(params).not.toHaveProperty("embedSubs")
  })

  test("ตั้งช่วงไว้ก่อน = สวิตช์แยก chapter กดไม่ได้พร้อมเหตุผล", async ({ page }) => {
    await page.goto(`/v/${ZOO}?tab=video`)
    await setRange(page, "0:05", "")
    await expect(page.getByRole("switch", { name: CHAPTERS })).toBeDisabled()
    await expect(page.getByRole("switch", { name: CHAPTERS })).toHaveAccessibleDescription("ใช้คู่กับช่วงเวลาไม่ได้ ล้างช่วงเวลาก่อน")
  })
})

test.describe("ตัวเลือกขั้นสูง: ตัดโฆษณา", () => {
  test("เริ่มปิด · เปิดแล้วเห็น 3 หมวดเริ่มต้น · ติ๊กแล้วบันทึกลงการตั้งค่า · หมวดสุดท้ายเอาออกไม่ได้ · ส่งหมวดไปกับงาน", async ({ page }) => {
    const { bodies } = await mockEnqueue(page)
    const settings = await mockSettings(page)
    await page.goto(`/v/${BBB}?tab=video`)
    await openAdvanced(page)
    const sponsor = page.getByRole("switch", { name: ADS })
    await expect(sponsor).not.toBeChecked()
    await sponsor.click()
    await expect(button(page, "โหลด mp4 (ตัดโฆษณา)")).toBeVisible()
    for (const name of ["ช่วงสปอนเซอร์", "ช่วงโปรโมตตัวเอง", "ช่วงขอให้กดติดตามหรือไลก์"]) {
      await expect(page.getByRole("checkbox", { name })).toBeChecked()
    }
    await expect(page.getByRole("checkbox", { name: "ช่วงนอกเรื่อง" })).not.toBeChecked()
    await page.getByRole("checkbox", { name: "ช่วงสปอนเซอร์" }).click()
    await expect.poll(() => settings.bodies.at(-1)).toEqual({ sponsorblockDefault: ["selfpromo", "interaction"] })
    await page.getByRole("checkbox", { name: "ช่วงโปรโมตตัวเอง" }).click()
    await expect(page.getByRole("checkbox", { name: "ช่วงขอให้กดติดตามหรือไลก์" })).toBeDisabled()
    await setRange(page, "1:30", "5:00")
    await button(page, "โหลด mp4 (1:30-5:00, ตัดโฆษณา)").click()
    await expect.poll(() => bodies.length).toBe(1)
    expect((bodies[0][0].params as VideoJobParams).sponsorblock).toEqual(["interaction"])
  })

  test("ฝังซับอยู่ = เตือนใต้สวิตช์ในแท็บวิดีโอ · แท็บซับเตือนเหนือปุ่ม", async ({ page }) => {
    await page.goto(`/v/${THAI}?tab=video`)
    const embed = page.getByRole("combobox", { name: "ฝังซับ (เปิด/ปิดได้)", exact: true })
    await expect(embed).toBeEnabled()
    await embed.click()
    await page.getByRole("option").nth(1).click()
    await openAdvanced(page)
    await page.getByRole("switch", { name: ADS }).click()
    await expect(panel(page).getByText("เวลาซับจะไม่ตรงกับวิดีโอที่ตัดโฆษณาแล้ว")).toBeVisible()
    await tab(page, "ซับ").click()
    await expect(panel(page).getByText("เวลาซับจะไม่ตรงกับวิดีโอที่ตัดโฆษณาแล้ว")).toBeVisible()
  })
})

test.describe("ตัวเลือกขั้นสูง: การเข้าถึงและจอแคบ", () => {
  for (const scheme of ["dark", "light"] as const) {
    test(`ส่วนตัวเลือกที่กางพร้อม error ไม่มีปัญหาระดับ serious/critical (${scheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme })
      await page.goto(`/v/${ZOO}?tab=video`)
      await setRange(page, "0:10", "0:05")
      await expect(panel(page).getByText("จุดเริ่มต้องมาก่อนจุดจบ")).toBeVisible()
      expect(await seriousViolations(page)).toEqual([])
      await page.goto(`/v/${BBB}?tab=audio`)
      await openAdvanced(page)
      await page.getByRole("switch", { name: ADS }).click()
      expect(await seriousViolations(page)).toEqual([])
    })
  }

  test("จอ 640 × 800: ทั้งสามแท็บไม่ล้นแนวนอนตอนกางส่วนตัวเลือก", async ({ page }) => {
    await page.setViewportSize({ width: 640, height: 800 })
    for (const which of ["video", "audio", "subs"] as const) {
      await page.goto(`/v/${ZOO}?tab=${which}`)
      await openAdvanced(page)
      if (which !== "subs") await page.getByRole("switch", { name: ADS }).click()
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(640)
    }
  })
})
