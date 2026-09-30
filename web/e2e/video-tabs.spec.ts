/// <reference lib="dom" />
import fs from "node:fs"
import path from "node:path"

import AxeBuilder from "@axe-core/playwright"
import { expect, test, type Page } from "@playwright/test"

const BBB = "aqz-KE-bpKQ"
const BBB_URL = `https://www.youtube.com/watch?v=${BBB}`
const ZOO = "jNQXAC9IVRw"
const ZOO_URL = `https://www.youtube.com/watch?v=${ZOO}`
// คลิปภาษาไทยที่มีซับอัตโนมัติภาษาต้นฉบับ (th-orig) เป็นแทร็กเริ่มต้น
const THAI = "88o5Sk8_m1Y"
const FRAME_COUNT = 128
const FRAME_LIST = "รายการภาพเฟรม"
const TAB_LIST = "เครื่องมือของคลิปนี้"
const TAB_NAMES = ["ภาพเฟรม", "ซับ", "ทรานสคริปต์"]
const NO_SUBS = "คลิปนี้ไม่มีซับ"
const RESULT_ROWS = 'section[aria-labelledby="results-title"] [role="listitem"]'

type ProbeFixture = { description?: unknown; chapters?: { start_time: number; title: string }[] }

/** อ่าน probe ในชุดทดสอบ (ข้อมูลเดียวกับที่ backend โหมด fake ส่งให้หน้าเว็บ) */
function probeFixture(videoId: string): ProbeFixture {
  const file = path.join(import.meta.dirname, "../../tests/fixtures/probe", `${videoId}.json`)
  return JSON.parse(fs.readFileSync(file, "utf8")) as ProbeFixture
}

const tabList = (page: Page) => page.getByRole("tablist", { name: TAB_LIST })
const tab = (page: Page, name: string) => page.getByRole("tab", { name, exact: true })
const frameItems = (page: Page) => page.getByRole("list", { name: FRAME_LIST }).getByRole("listitem")
const readClipboard = (page: Page) => page.evaluate(() => navigator.clipboard.readText())

test.describe("W2 แถบแท็บ", () => {
  test("มี 3 แท็บตามลำดับ · เริ่มที่ภาพเฟรมพร้อมภาพครบ 128 ภาพ", async ({ page }) => {
    await page.goto(`/v/${BBB}`)
    await expect(tabList(page).getByRole("tab")).toHaveText(TAB_NAMES)
    await expect(tab(page, "ภาพเฟรม")).toHaveAttribute("aria-selected", "true")
    await expect(frameItems(page)).toHaveCount(FRAME_COUNT)
    await expect(page).toHaveURL(new RegExp(`/v/${BBB}$`))
  })

  test("กดแท็บซับ → URL ?tab=subs และเห็น 'คลิปนี้ไม่มีซับ' · โหลดหน้าใหม่ยังอยู่ที่แท็บซับ", async ({ page }) => {
    await page.goto(`/v/${BBB}`)
    await expect(frameItems(page)).toHaveCount(FRAME_COUNT)
    await tab(page, "ซับ").click()
    await expect(page).toHaveURL(new RegExp(`/v/${BBB}\\?tab=subs$`))
    await expect(tab(page, "ซับ")).toHaveAttribute("aria-selected", "true")
    await expect(page.getByText(NO_SUBS)).toBeVisible()
    await expect(frameItems(page)).toHaveCount(0)

    await page.reload()
    await expect(tab(page, "ซับ")).toHaveAttribute("aria-selected", "true")
    await expect(page.getByText(NO_SUBS)).toBeVisible()
  })

  test("แท็บทรานสคริปต์ของคลิปที่ไม่มีซับก็บอก 'คลิปนี้ไม่มีซับ'", async ({ page }) => {
    await page.goto(`/v/${BBB}?tab=transcript`)
    await expect(tab(page, "ทรานสคริปต์")).toHaveAttribute("aria-selected", "true")
    await expect(page.getByText(NO_SUBS)).toBeVisible()
  })

  test("เปลี่ยนแท็บแล้วล้างเวลาที่ไฮไลต์ไว้ (at) · กลับภาพเฟรมไม่มี ?tab ใน URL", async ({ page }) => {
    await page.goto(`/v/${BBB}?tab=transcript&at=5000`)
    await expect(tab(page, "ทรานสคริปต์")).toHaveAttribute("aria-selected", "true")
    await tab(page, "ภาพเฟรม").click()
    await expect(page).toHaveURL(new RegExp(`/v/${BBB}$`))
    await expect(frameItems(page)).toHaveCount(FRAME_COUNT)
  })

  test("W1 → W2 → เปลี่ยนแท็บหลายครั้ง → ย้อนกลับครั้งเดียวถึง W1", async ({ page }) => {
    await page.goto("/")
    await page.getByRole("textbox").fill(BBB_URL)
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    await expect(page).toHaveURL(new RegExp(`/v/${BBB}$`))
    await tab(page, "ซับ").click()
    await expect(page).toHaveURL(/\?tab=subs$/)
    await tab(page, "ทรานสคริปต์").click()
    await expect(page).toHaveURL(/\?tab=transcript$/)
    await tab(page, "ซับ").click()
    await expect(page).toHaveURL(/\?tab=subs$/)
    await page.goBack()
    await expect(page).toHaveURL(/\/$/)
    await expect(page.getByRole("textbox")).toBeVisible()
  })

  test("ปุ่มคลิปถัดไปอยู่ที่แท็บเดิม และย้อนกลับครั้งเดียวยังถึง W1", async ({ page }) => {
    await page.goto("/")
    await page.getByRole("textbox").fill([BBB_URL, ZOO_URL].join("\n"))
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    const rows = page.locator(RESULT_ROWS)
    await expect(rows).toHaveCount(2)
    await rows.nth(0).getByRole("link", { name: /เปิดดู/ }).click()
    await expect(page).toHaveURL(new RegExp(`/v/${BBB}$`))
    await tab(page, "ซับ").click()
    await expect(page).toHaveURL(/\?tab=subs$/)
    await page.getByRole("button", { name: "ถัดไป" }).click()
    await expect(page).toHaveURL(new RegExp(`/v/${ZOO}\\?tab=subs$`))
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Me at the zoo")
    await expect(tab(page, "ซับ")).toHaveAttribute("aria-selected", "true")
    await page.goBack()
    await expect(page).toHaveURL(/\/$/)
  })

  test("จอกว้าง 360 px: แถวแท็บไม่ตัดขึ้นบรรทัดใหม่ (เลื่อนแนวนอนได้) และแต่ละแท็บสูงอย่างน้อย 44 px", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 800 })
    await page.goto(`/v/${BBB}`)
    await expect(tabList(page).getByRole("tab")).toHaveCount(3)
    const layout = await tabList(page).evaluate((list) => {
      const tabs = [...list.querySelectorAll<HTMLElement>('[role="tab"]')]
      return {
        scrolls: list.scrollWidth > list.clientWidth,
        tops: [...new Set(tabs.map((element) => element.offsetTop))],
        heights: tabs.map((element) => element.getBoundingClientRect().height),
        overflowX: getComputedStyle(list).overflowX,
      }
    })
    // แท็บทั้งหมดอยู่บรรทัดเดียวกันเสมอ: ถ้าจอแคบกว่าแถว แถวต้องเลื่อนแนวนอนได้ (ไม่ตัดขึ้นบรรทัดใหม่)
    expect(layout.tops).toHaveLength(1)
    expect(layout.overflowX).toBe("auto")
    if (layout.scrolls) await tabList(page).evaluate((list) => list.scrollTo({ left: list.scrollWidth }))
    await tab(page, "ทรานสคริปต์").click()
    await expect(tab(page, "ทรานสคริปต์")).toHaveAttribute("aria-selected", "true")
    for (const height of layout.heights) expect(height).toBeGreaterThanOrEqual(44)
  })
})

test.describe("W2 ปุ่มคัดลอกที่หัวคลิป", () => {
  test("AC-PROBE-03: 'คัดลอก chapter' ได้บรรทัด HH:MM:SS ชื่อตอน ครบ 3 ตอน และขึ้น toast", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"])
    const chapters = probeFixture(ZOO).chapters ?? []
    expect(chapters).toHaveLength(3)
    await page.goto(`/v/${ZOO}`)
    const group = page.getByRole("group", { name: "คัดลอกข้อมูลคลิป" })
    await group.getByRole("button", { name: "คัดลอก chapter" }).click()
    await expect(page.getByText("คัดลอกแล้ว")).toBeVisible()
    const text = await readClipboard(page)
    const lines = text.split("\n")
    expect(lines).toHaveLength(3)
    for (const line of lines) expect(line).toMatch(/^\d{2}:\d{2}:\d{2} \S/)
    const expected = [...chapters]
      .sort((a, b) => a.start_time - b.start_time)
      .map((chapter) => {
        const s = Math.floor(chapter.start_time)
        const pad = (n: number) => String(n).padStart(2, "0")
        return `${pad(Math.floor(s / 3600))}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)} ${chapter.title}`
      })
      .join("\n")
    expect(text).toBe(expected)
  })

  test("คลิปไม่มี chapter ไม่มีปุ่ม 'คัดลอก chapter'", async ({ page }) => {
    await page.goto(`/v/${BBB}`)
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Big Buck Bunny")
    await expect(page.getByRole("button", { name: "คัดลอก chapter" })).toHaveCount(0)
  })

  test("AC-PROBE-04: 'คัดลอกคำอธิบาย' ได้คำอธิบายตรงทุกตัวอักษรตามชุดทดสอบ", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"])
    const { description } = probeFixture(BBB)
    expect(typeof description).toBe("string")
    await page.goto(`/v/${BBB}`)
    await page
      .getByRole("group", { name: "คัดลอกข้อมูลคลิป" })
      .getByRole("button", { name: "คัดลอกคำอธิบาย" })
      .click()
    await expect(page.getByText("คัดลอกแล้ว")).toBeVisible()
    expect(await readClipboard(page)).toBe(description)
  })

  test("คัดลอกไม่ได้ (เบราว์เซอร์ไม่ให้เขียนคลิปบอร์ด) → toast error", async ({ page }) => {
    await page.addInitScript(() => {
      Object.defineProperty(navigator.clipboard, "writeText", { value: () => Promise.reject(new Error("denied")) })
    })
    await page.goto(`/v/${ZOO}`)
    await page.getByRole("button", { name: "คัดลอก chapter" }).click()
    await expect(page.getByText("คัดลอกไม่สำเร็จ ลองอีกครั้ง")).toBeVisible()
  })
})

test.describe("W2 ป้ายแทร็กซับ", () => {
  test("คลิปภาษาไทยแสดงป้าย 'ซับ: ไทย (อัตโนมัติ)' ที่หัวคลิป", async ({ page }) => {
    await page.goto(`/v/${THAI}`)
    await expect(page.getByText("ซับ: ไทย (อัตโนมัติ)")).toBeVisible()
  })

  test("คลิปที่ไม่มีซับไม่มีป้าย", async ({ page }) => {
    await page.goto(`/v/${BBB}?tab=subs`)
    await expect(page.getByText(NO_SUBS)).toBeVisible()
    await expect(page.getByText(/^ซับ: /)).toHaveCount(0)
  })
})

test.describe("W2 แท็บซับ การเข้าถึง (axe)", () => {
  for (const scheme of ["dark", "light"] as const) {
    test(`แท็บซับของคลิปที่ไม่มีซับไม่มีปัญหาระดับ serious/critical (${scheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme })
      await page.goto(`/v/${BBB}?tab=subs`)
      await expect(page.getByText(NO_SUBS)).toBeVisible()
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
