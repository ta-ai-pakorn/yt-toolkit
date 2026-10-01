/// <reference lib="dom" />
import fs from "node:fs"
import path from "node:path"

import AxeBuilder from "@axe-core/playwright"
import { expect, test, type Locator, type Page } from "@playwright/test"

const BBB = "aqz-KE-bpKQ"
const BBB_URL = `https://www.youtube.com/watch?v=${BBB}`
const ZOO = "jNQXAC9IVRw"
const ZOO_URL = `https://www.youtube.com/watch?v=${ZOO}`
// คลิปภาษาไทยที่มีซับอัตโนมัติภาษาต้นฉบับ (th-orig) เป็นแทร็กเริ่มต้น
const THAI = "88o5Sk8_m1Y"
const FRAME_COUNT = 128
const FRAME_LIST = "รายการภาพเฟรม"
const TAB_LIST = "เครื่องมือของคลิปนี้"
// M4 (Q8): วิดีโอและเสียงอยู่ระหว่างภาพเฟรมกับซับ แท็บเริ่มต้นยังเป็นภาพเฟรม
const TAB_NAMES = ["ภาพเฟรม", "วิดีโอ", "เสียง", "ซับ", "ทรานสคริปต์", "ข้อมูลคลิป"]
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

/** ความสูงของของในแถวแท็บเทียบกับกล่อง (scrollHeight ยังนับส่วนที่ล้นแม้ซ่อนไว้) และแถบเลื่อนที่เบราว์เซอร์จะวาด */
const tabListBox = (page: Page) =>
  tabList(page).evaluate((list) => {
    const style = getComputedStyle(list)
    return {
      overflowsVertically: list.scrollHeight > list.clientHeight,
      overflowY: style.overflowY,
      scrollbarWidth: style.scrollbarWidth,
    }
  })
const NO_SCROLLBARS = { overflowsVertically: false, overflowY: "hidden", scrollbarWidth: "none" }

/**
 * จดข้อความที่หน้าเว็บส่งให้ navigator.clipboard.writeText ตามตัวอักษร แล้วส่งต่อให้คลิปบอร์ดจริง
 * คลิปบอร์ดของ Windows แปลง LF เป็น CRLF เอง ข้อความที่อ่านกลับจึงไม่ตรงไบต์กับที่แอปเขียน
 * เทียบไบต์ตรง ๆ ที่ข้อความที่แอปส่ง ส่วนข้อความที่อ่านกลับเทียบหลังแปลง CRLF เป็น LF (ยืนยันว่าลงคลิปบอร์ดจริง)
 */
async function recordClipboardWrites(page: Page) {
  await page.addInitScript(() => {
    const clipboard = navigator.clipboard
    const original = clipboard.writeText.bind(clipboard)
    const written: string[] = []
    Object.defineProperty(window, "__clipboardWrites", { value: written })
    Object.defineProperty(clipboard, "writeText", {
      value: (text: string) => {
        written.push(text)
        return original(text)
      },
    })
  })
}

const descriptionRegion = (page: Page) => page.getByRole("region", { name: "คำอธิบาย" })
const chapterRegion = (page: Page) => page.getByRole("region", { name: /^Chapter \(/ })
const chapterRows = (page: Page) => chapterRegion(page).getByRole("listitem")

/** ข้อความถูกตัด (สูงเกินกล่องที่เห็น) อยู่หรือไม่ */
const isCut = (locator: Locator) => locator.evaluate((el) => el.scrollHeight > el.clientHeight + 1)

/** หน้า W2 ที่แท็บข้อมูลคลิป (คำอธิบาย chapter ช่วงดูซ้ำ คอมเมนต์ปักหมุด แท็ก อยู่ในแท็บนี้ตั้งแต่ owner round 4) */
const gotoInfo = (page: Page, videoId: string) => page.goto(`/v/${videoId}?tab=info`)

/** แก้ข้อมูลคลิปที่ backend ส่งมาบางช่อง (เช่น chapter หลายตอน คำอธิบายว่าง) ส่วนอื่นมาจากชุดทดสอบตามปกติ */
async function withVideo(page: Page, videoId: string, patch: Record<string, unknown>) {
  await page.route(
    (url) => url.pathname === `/api/videos/${videoId}`,
    async (route) => {
      const response = await route.fetch()
      route.fulfill({ response, json: { ...((await response.json()) as object), ...patch } })
    },
  )
}

const lastWrite = (page: Page) =>
  page.evaluate(() => (window as unknown as { __clipboardWrites: string[] }).__clipboardWrites.at(-1))

const toLf = (text: string) => text.replaceAll("\r\n", "\n")

const readClipboardLf = async (page: Page) => toLf(await readClipboard(page))

test.describe("W2 แถบแท็บ", () => {
  test("มี 6 แท็บตามลำดับ (ภาพเฟรม · วิดีโอ · เสียง · ซับ · ทรานสคริปต์ · ข้อมูลคลิป) · เริ่มที่ภาพเฟรมพร้อมภาพครบ 128 ภาพ", async ({ page }) => {
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

  test("?tab=info เปิดแท็บข้อมูลคลิป · โหลดหน้าใหม่ยังอยู่ที่แท็บนี้ · ค่า tab ที่ไม่รู้จักกลับไปภาพเฟรม", async ({ page }) => {
    await page.goto(`/v/${ZOO}?tab=info`)
    await expect(tab(page, "ข้อมูลคลิป")).toHaveAttribute("aria-selected", "true")
    await expect(descriptionRegion(page)).toBeVisible()
    await expect(page.getByRole("tabpanel")).toHaveAccessibleName("ข้อมูลคลิป")
    await page.reload()
    await expect(tab(page, "ข้อมูลคลิป")).toHaveAttribute("aria-selected", "true")

    for (const bad of ["Info", "about", ""]) {
      await page.goto(`/v/${ZOO}?tab=${bad}`)
      await expect(tab(page, "ภาพเฟรม")).toHaveAttribute("aria-selected", "true")
    }
  })

  test("คีย์บอร์ด: จากแท็บภาพเฟรมกด End ไปแท็บข้อมูลคลิป · เปิดแท็บด้วย Enter → URL ?tab=info", async ({ page }) => {
    await page.goto(`/v/${ZOO}`)
    await tab(page, "ภาพเฟรม").focus()
    await page.keyboard.press("End")
    await expect(tab(page, "ข้อมูลคลิป")).toBeFocused()
    await page.keyboard.press("Enter")
    await expect(tab(page, "ข้อมูลคลิป")).toHaveAttribute("aria-selected", "true")
    await expect(page).toHaveURL(new RegExp(`/v/${ZOO}\\?tab=info$`))
    await expect(descriptionRegion(page)).toBeVisible()
    // ลูกศรซ้ายกลับไปแท็บทรานสคริปต์ได้ (วนตามลำดับแท็บ)
    await page.keyboard.press("ArrowLeft")
    await expect(tab(page, "ทรานสคริปต์")).toBeFocused()
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
    await expect(tabList(page).getByRole("tab")).toHaveCount(TAB_NAMES.length)
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
    expect(await tabListBox(page)).toEqual(NO_SCROLLBARS)
    if (layout.scrolls) await tabList(page).evaluate((list) => list.scrollTo({ left: list.scrollWidth }))
    await tab(page, "ทรานสคริปต์").click()
    await expect(tab(page, "ทรานสคริปต์")).toHaveAttribute("aria-selected", "true")
    for (const height of layout.heights) expect(height).toBeGreaterThanOrEqual(44)
  })
})

test.describe("W2 แถบแท็บ ไม่มีแถบเลื่อน", () => {
  // Windows แสดงแถบเลื่อนแนวตั้ง (มีลูกศรขึ้น/ลง) ที่ปลายแถวแท็บ ถ้าของในแถวสูงเกินกล่องแม้ 1-2 px
  for (const [label, width] of [
    ["จอกว้าง", 1280],
    ["จอ 360 px", 360],
  ] as const) {
    test(`${label}: แถวแท็บไม่ล้นแนวตั้ง และไม่แสดงแถบเลื่อน`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 })
      await page.goto(`/v/${BBB}`)
      await expect(tabList(page).getByRole("tab")).toHaveCount(TAB_NAMES.length)
      expect(await tabListBox(page)).toEqual(NO_SCROLLBARS)
    })
  }

  test("จอ 360 px: กดลูกศรขวาไปแท็บสุดท้าย แท็บที่โฟกัสเลื่อนมาอยู่ในกรอบแถว", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 800 })
    await page.goto(`/v/${BBB}`)
    await tab(page, "ภาพเฟรม").focus()
    for (let i = 0; i < TAB_NAMES.length - 1; i++) await page.keyboard.press("ArrowRight")
    const last = tab(page, "ข้อมูลคลิป")
    await expect(last).toBeFocused()
    const inView = await tabList(page).evaluate((list) => {
      const box = list.getBoundingClientRect()
      const item = list.querySelector<HTMLElement>('[role="tab"]:last-child')!.getBoundingClientRect()
      return item.left >= box.left - 1 && item.right <= box.right + 1
    })
    expect(inView).toBe(true)
  })

  test("จอ 280 px: แถวแท็บล้นจริง (เลื่อนแนวนอนได้) · โฟกัสแท็บสุดท้ายแล้วแท็บเลื่อนมาอยู่ในกรอบแถว · หน้าไม่ล้น", async ({
    page,
  }) => {
    // review owner fb1: เทสที่ 360 px อาจไม่ล้นเลย (แท็บพอดีจอ) จอ 280 px ล้นแน่นอน จึงพิสูจน์การเลื่อนแนวนอนได้จริง
    await page.setViewportSize({ width: 280, height: 700 })
    await page.goto(`/v/${BBB}`)
    await expect(tabList(page).getByRole("tab")).toHaveCount(TAB_NAMES.length)
    const sizes = await tabList(page).evaluate((list) => ({ scroll: list.scrollWidth, client: list.clientWidth, left: list.scrollLeft }))
    expect(sizes.scroll).toBeGreaterThan(sizes.client)
    expect(sizes.left).toBe(0)
    const last = tab(page, "ข้อมูลคลิป")
    // แท็บสุดท้ายเริ่มแรกอยู่นอกกรอบ (ล้นไปทางขวา)
    const startsOutside = await tabList(page).evaluate((list) => {
      const box = list.getBoundingClientRect()
      return list.querySelector<HTMLElement>('[role="tab"]:last-child')!.getBoundingClientRect().right > box.right + 1
    })
    expect(startsOutside).toBe(true)
    await tab(page, "ภาพเฟรม").focus()
    await page.keyboard.press("End")
    await expect(last).toBeFocused()
    await expect
      .poll(() =>
        tabList(page).evaluate((list) => {
          const box = list.getBoundingClientRect()
          const item = list.querySelector<HTMLElement>('[role="tab"]:last-child')!.getBoundingClientRect()
          return item.left >= box.left - 1 && item.right <= box.right + 1 && list.scrollLeft > 0
        }),
      )
      .toBe(true)
    expect(await tabListBox(page)).toEqual(NO_SCROLLBARS)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(280)
  })
})

test.describe("W2 แถบแท็บ คีย์บอร์ด", () => {
  test("กด Tab หนึ่งครั้งจากแท็บภาพเฟรม → ไปปุ่มแรกของภาพเฟรม (แผงไม่เป็นจุด Tab เพิ่ม)", async ({ page }) => {
    await page.goto(`/v/${BBB}`)
    await expect(frameItems(page)).toHaveCount(FRAME_COUNT)
    await tab(page, "ภาพเฟรม").focus()
    await page.keyboard.press("Tab")
    // owner round 5: คลิปที่มีช่วงดูซ้ำบ่อย ปุ่มตัวกรอง "ดูซ้ำบ่อย (n ภาพ)" อยู่ก่อนปุ่มโหลด (ซ้ายมือ ลำดับเดียวกับที่ตาเห็น)
    await expect(page.getByRole("button", { name: /^ดูซ้ำบ่อย \(\d+ ภาพ\)$/ })).toBeFocused()
    await page.keyboard.press("Tab")
    await expect(page.getByRole("button", { name: "โหลดภาพรวมเฟรม" })).toBeFocused()
  })

  test("แผงแท็บซับรับโฟกัสด้วย Tab แล้วเห็นวงโฟกัส", async ({ page }) => {
    // แผงว่าง (ไม่มีปุ่มข้างใน) จึงเป็นจุด Tab ของตัวเอง: จำลองรายการแทร็กว่าง ไม่ขึ้นกับ API ซับ
    await page.route(`**/api/videos/${BBB}/subtitles`, (route) => route.fulfill({ json: { tracks: [] } }))
    await page.goto(`/v/${BBB}?tab=subs`)
    await expect(page.getByText(NO_SUBS)).toBeVisible()
    await tab(page, "ซับ").focus()
    await page.keyboard.press("Tab")
    const panel = page.getByRole("tabpanel")
    await expect(panel).toBeFocused()
    await expect(panel).not.toHaveCSS("box-shadow", "none")
  })
})

// owner round 4: คำอธิบายและ chapter ย้ายจากหัวคลิปมาอยู่ในแท็บข้อมูลคลิป แสดงเต็ม ไม่มีพับ/กาง ("ดูทั้งหมด") แล้ว
// เทสชุดนี้ยังตรวจเจตนาเดิม (เห็นก่อนคัดลอก คัดลอกได้ตรงตัว ปุ่มใหญ่พอบนมือถือ ไม่ล้นจอ คีย์บอร์ด axe) แต่ในแท็บใหม่
test.describe("W2 คำอธิบายและ chapter ในแท็บข้อมูลคลิป", () => {
  test("หัวคลิปไม่มีคำอธิบาย chapter หรือปุ่มคัดลอกแล้ว (แท็บภาพเฟรม)", async ({ page }) => {
    await page.goto(`/v/${ZOO}`)
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Me at the zoo")
    await expect(tab(page, "ภาพเฟรม")).toHaveAttribute("aria-selected", "true")
    await expect(descriptionRegion(page)).toHaveCount(0)
    await expect(chapterRegion(page)).toHaveCount(0)
    await expect(page.getByRole("button", { name: /^คัดลอก/ })).toHaveCount(0)
  })

  test("จอแคบ 360 px: ปุ่มคัดลอกและปุ่มเวลาของ chapter สูงอย่างน้อย 44 px · หน้าไม่ล้นแนวนอน", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 800 })
    await gotoInfo(page, ZOO)
    await expect(page.getByRole("button", { name: "คัดลอก chapter" })).toBeVisible()
    for (const name of ["คัดลอก chapter", "คัดลอกคำอธิบาย", "เล่นจาก 00:00:05"]) {
      const box = await page.getByRole("button", { name, exact: true }).boundingBox()
      expect(box?.height ?? 0, name).toBeGreaterThanOrEqual(44)
    }
    // ลิงก์ยาวในคำอธิบาย (แสดงเต็ม) ตัดขึ้นบรรทัดใหม่ได้ ไม่ดันหน้าให้กว้างเกินจอ
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360)
  })

  test("เห็นรายการ chapter ก่อนคัดลอก: หัวข้อ 'Chapter (3 ตอน)' และบรรทัด HH:MM:SS ชื่อตอน", async ({ page }) => {
    await gotoInfo(page, ZOO)
    await expect(page.getByRole("heading", { level: 2, name: "Chapter (3 ตอน)" })).toBeVisible()
    await expect(chapterRows(page)).toHaveText(["00:00:00Intro", "00:00:05The cool thing", "00:00:17End"])
    // แสดงครบทุกตอน ไม่มีพับ/กาง
    await expect(chapterRegion(page).getByRole("button", { name: /ดูทั้งหมด|ย่อ/ })).toHaveCount(0)
    await expect(chapterRegion(page).locator("[aria-expanded]")).toHaveCount(0)
  })

  test("กดเวลาของ chapter → เล่นคลิปจากเวลานั้น (M3.5): อยู่แท็บข้อมูลคลิป URL ไม่เปลี่ยน", async ({ page }) => {
    await withVideo(page, BBB, { chapters: [{ startS: 0, endS: 9, title: "เปิดเรื่อง" }, { startS: 9, endS: 60, title: "ตอนสอง" }] })
    await gotoInfo(page, BBB)
    const time = chapterRegion(page).getByRole("button", { name: "เล่นจาก 00:00:09" })
    await expect(time).toHaveText("00:00:09")
    await time.click()
    await page.waitForTimeout(300)
    await expect(page).toHaveURL(new RegExp(`/v/${BBB}\\?tab=info$`))
    await expect(tab(page, "ข้อมูลคลิป")).toHaveAttribute("aria-selected", "true")
    await expect(time).toBeFocused()
  })

  test("AC-PROBE-03: 'คัดลอก chapter' ได้บรรทัด HH:MM:SS ชื่อตอน ครบ 3 ตอน และขึ้น toast", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"])
    const chapters = probeFixture(ZOO).chapters ?? []
    expect(chapters).toHaveLength(3)
    await recordClipboardWrites(page)
    await gotoInfo(page, ZOO)
    // ปุ่มที่ตาเห็นเขียนว่า "คัดลอก" ชื่อสำหรับโปรแกรมอ่านหน้าจอบอกว่าคัดลอกอะไร
    const button = page.getByRole("button", { name: "คัดลอก chapter" })
    await expect(button).toHaveText("คัดลอก")
    await button.click()
    await expect(page.getByText("คัดลอกแล้ว")).toBeVisible()
    const text = (await lastWrite(page)) ?? ""
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
    // แอปเขียน LF ตรงตัว (AC-PROBE-03)
    expect(text).toBe(expected)
    expect(await readClipboardLf(page)).toBe(expected)
  })

  test("chapter เกิน 5 ตอน: แสดงครบทุกตอนเรียงตามเวลา (ไม่มี 'ดูทั้งหมด') · คัดลอกได้ครบทุกตอน", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"])
    await recordClipboardWrites(page)
    // ส่งคืนลำดับสลับกันโดยตั้งใจ: หน้าเว็บต้องเรียงตามเวลาเอง
    const titles = ["ตอนที่ 1", "ตอนที่ 2", "ตอนที่ 3", "ตอนที่ 4", "ตอนที่ 5", "ตอนที่ 6", "ตอนที่ 7", "ตอนที่ 8"]
    const chapters = titles.map((title, i) => ({ startS: i * 60, endS: i * 60 + 60, title })).reverse()
    await withVideo(page, ZOO, { chapters })
    await gotoInfo(page, ZOO)
    await expect(page.getByRole("heading", { level: 2, name: "Chapter (8 ตอน)" })).toBeVisible()
    await expect(chapterRows(page)).toHaveCount(8)
    await expect(chapterRows(page).first()).toHaveText("00:00:00ตอนที่ 1")
    await expect(chapterRows(page).last()).toHaveText("00:07:00ตอนที่ 8")
    await expect(page.getByRole("button", { name: /ดูทั้งหมด|ย่อ/ })).toHaveCount(0)

    await page.getByRole("button", { name: "คัดลอก chapter" }).click()
    await expect(page.getByText("คัดลอกแล้ว")).toBeVisible()
    expect(((await lastWrite(page)) ?? "").split("\n")).toEqual(titles.map((t, i) => `00:0${i}:00 ${t}`))
  })

  test("คลิปไม่มี chapter ไม่มีส่วน chapter และไม่มีปุ่ม 'คัดลอก chapter'", async ({ page }) => {
    await gotoInfo(page, BBB)
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Big Buck Bunny")
    await expect(page.getByRole("heading", { level: 2, name: "คำอธิบาย" })).toBeVisible()
    await expect(page.getByRole("heading", { name: /^Chapter/ })).toHaveCount(0)
    await expect(page.getByRole("button", { name: "คัดลอก chapter" })).toHaveCount(0)
  })

  test("คลิปไม่มีทั้งคำอธิบายและ chapter (หรือคำอธิบายมีแต่ช่องว่าง) ไม่มีทั้งสองส่วน", async ({ page }) => {
    await withVideo(page, BBB, { description: "  \n ", chapters: [] })
    await gotoInfo(page, BBB)
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Big Buck Bunny")
    await expect(tab(page, "ข้อมูลคลิป")).toHaveAttribute("aria-selected", "true")
    await expect(page.getByRole("heading", { level: 2, name: "คำอธิบาย" })).toHaveCount(0)
    // ไม่มีปุ่มคัดลอกของสองส่วนนี้ (ส่วนแท็กมีปุ่ม "คัดลอกแท็ก" ของตัวเอง เป็นคนละเรื่อง)
    await expect(page.getByRole("button", { name: /^คัดลอก(คำอธิบาย| chapter)/ })).toHaveCount(0)
    await expect(page.getByRole("heading", { name: /^Chapter/ })).toHaveCount(0)
  })

  test("คำอธิบาย: แสดงเต็มทุกบรรทัด (ไม่ตัด 3 บรรทัด ไม่มี 'ดูทั้งหมด') ขึ้นบรรทัดตามต้นฉบับ · ลิงก์เป็นข้อความธรรมดา", async ({
    page,
  }) => {
    const { description } = probeFixture(BBB)
    await gotoInfo(page, BBB)
    const region = descriptionRegion(page)
    const text = region.getByText(/^UHD High Frame rate/)
    await expect(text).toBeVisible()
    expect(await text.evaluate((el) => el.textContent)).toBe(description)
    await expect(text).toHaveCSS("white-space", "pre-line")
    await expect(text).toHaveCSS("-webkit-line-clamp", "none")
    expect(await isCut(text)).toBe(false)
    await expect(region.getByRole("link")).toHaveCount(0)
    await expect(region.getByRole("button", { name: /ดูทั้งหมด|ย่อ/ })).toHaveCount(0)
  })

  test("คำอธิบายสั้นบรรทัดเดียวก็มีปุ่ม 'คัดลอกคำอธิบาย'", async ({ page }) => {
    await withVideo(page, BBB, { description: "คำอธิบายสั้น ๆ บรรทัดเดียว" })
    await gotoInfo(page, BBB)
    await expect(descriptionRegion(page).getByText("คำอธิบายสั้น ๆ บรรทัดเดียว")).toBeVisible()
    await expect(page.getByRole("button", { name: "คัดลอกคำอธิบาย" })).toBeVisible()
  })

  test("จอกว้าง: คำอธิบายอยู่คอลัมน์ซ้าย chapter อยู่บนสุดของคอลัมน์ขวาเหนือคอมเมนต์ปักหมุด (owner round 6) · ปกยังเป็น 16:9", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    await page.route(`**/api/videos/${ZOO}/pinned-comment`, (route) => route.fulfill({ json: { comment: null } }))
    await gotoInfo(page, ZOO)
    const description = await descriptionRegion(page).boundingBox()
    const chapters = await chapterRegion(page).boundingBox()
    const pinned = await page.getByRole("region", { name: "คอมเมนต์ปักหมุด" }).boundingBox()
    expect(description && chapters && pinned).toBeTruthy()
    expect(chapters?.x ?? 0).toBeGreaterThan((description?.x ?? 0) + (description?.width ?? 0))
    expect(Math.abs((chapters?.x ?? 0) - (pinned?.x ?? 1))).toBeLessThan(2)
    expect(pinned?.y ?? 0).toBeGreaterThan((chapters?.y ?? 0) + (chapters?.height ?? 0) - 1)
    // M3.5: ปกเป็นช่องตัวเล่น (ปุ่ม "เล่นคลิป")
    const cover = await page.getByRole("button", { name: "เล่นคลิป" }).boundingBox()
    expect((cover?.width ?? 0) / (cover?.height ?? 1)).toBeCloseTo(16 / 9, 1)
  })

  test("AC-PROBE-04: 'คัดลอกคำอธิบาย' ได้คำอธิบายตรงทุกตัวอักษรตามชุดทดสอบ", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"])
    const { description } = probeFixture(BBB)
    expect(typeof description).toBe("string")
    await recordClipboardWrites(page)
    await gotoInfo(page, BBB)
    const button = descriptionRegion(page).getByRole("button", { name: "คัดลอกคำอธิบาย" })
    await expect(button).toHaveText("คัดลอก")
    await button.click()
    await expect(page.getByText("คัดลอกแล้ว")).toBeVisible()
    expect(await lastWrite(page)).toBe(description)
    expect(await readClipboardLf(page)).toBe(toLf(String(description)))
  })

  test("คัดลอกไม่ได้ (เบราว์เซอร์ไม่ให้เขียนคลิปบอร์ด) → toast error", async ({ page }) => {
    await page.addInitScript(() => {
      Object.defineProperty(navigator.clipboard, "writeText", { value: () => Promise.reject(new Error("denied")) })
    })
    await gotoInfo(page, ZOO)
    await page.getByRole("button", { name: "คัดลอก chapter" }).click()
    await expect(page.getByText("คัดลอกไม่สำเร็จ ลองอีกครั้ง")).toBeVisible()
  })

  test("คีย์บอร์ด: หัวคลิป ชื่อคลิป → โน้ต → เปิดในยูทูป → ดูภาพปก → เล่นเฉพาะช่วงที่ดูซ้ำบ่อย → แท็บภาพเฟรม (ไม่มีจุด Tab ของคำอธิบาย/chapter แล้ว)", async ({ page }) => {
    await page.goto(`/v/${ZOO}`)
    const heading = page.getByRole("heading", { level: 1 })
    await expect(heading).toContainText("Me at the zoo")
    await heading.focus()
    await page.keyboard.press("Tab")
    await expect(page.getByRole("button", { name: "บันทึกเป็นโน้ต (.md)", exact: true })).toBeFocused()
    await page.keyboard.press("Tab")
    await expect(page.getByRole("link", { name: /^เปิดในยูทูป/ })).toBeFocused()
    // M3.5: ปุ่ม "ดูภาพปก" ต่อท้ายแถวปุ่ม
    await page.keyboard.press("Tab")
    await expect(page.getByRole("button", { name: "ดูภาพปก", exact: true })).toBeFocused()
    // M3.5 integration: คลิปที่มีช่วงดูซ้ำบ่อย มีปุ่ม "เล่นเฉพาะช่วงที่ดูซ้ำบ่อย" ท้ายแถวปุ่ม (ย้ายมาจากใต้ตัวเล่น)
    await page.keyboard.press("Tab")
    await expect(page.getByRole("button", { name: "เล่นเฉพาะช่วงที่ดูซ้ำบ่อย", exact: true })).toBeFocused()
    await page.keyboard.press("Tab")
    await expect(tab(page, "ภาพเฟรม")).toBeFocused()
  })

  test("คีย์บอร์ด: แท็บข้อมูลคลิป → คัดลอกเครดิต → คัดลอกคำอธิบาย → คัดลอก chapter → ปุ่มเวลาของ chapter ทีละตอน (แผงไม่เป็นจุด Tab เพิ่ม)", async ({
    page,
  }) => {
    // M4 T16: ส่วนเครดิตอยู่บนสุดของแท็บ ปุ่ม "คัดลอกเครดิต" จึงเป็นจุด Tab แรก
    // ไม่มีแท็ก ไม่มีช่วงดูซ้ำ และไม่มีคอมเมนต์ปักหมุด (ส่วนคอมเมนต์ไม่มีปุ่ม): ลำดับ Tab ไม่ขึ้นกับข้อมูลในชุดทดสอบ
    await withVideo(page, ZOO, { tags: [], mostReplayed: undefined, stats: undefined })
    await page.route(`**/api/videos/${ZOO}/pinned-comment`, (route) => route.fulfill({ json: { comment: null } }))
    await gotoInfo(page, ZOO)
    await expect(page.getByText("ไม่มีคอมเมนต์ปักหมุด")).toBeVisible()
    await tab(page, "ข้อมูลคลิป").focus()
    for (const name of [
      "คัดลอกเครดิต",
      "คัดลอกคำอธิบาย",
      "คัดลอก chapter",
      "เล่นจาก 00:00:00",
      "เล่นจาก 00:00:05",
      "เล่นจาก 00:00:17",
    ]) {
      await page.keyboard.press("Tab")
      await expect(page.getByRole("button", { name, exact: true })).toBeFocused()
    }
  })

  for (const scheme of ["dark", "light"] as const) {
    test(`แท็บข้อมูลคลิปที่มีคำอธิบายและ chapter 6 ตอนไม่มีปัญหาระดับ serious/critical (${scheme})`, async ({ page }) => {
      const titles = ["หนึ่ง", "สอง", "สาม", "สี่", "ห้า", "หก"]
      await withVideo(page, ZOO, { chapters: titles.map((title, i) => ({ startS: i * 3, endS: i * 3 + 3, title })) })
      await page.route(`**/api/videos/${ZOO}/pinned-comment`, (route) => route.fulfill({ json: { comment: null } }))
      await page.emulateMedia({ colorScheme: scheme })
      await gotoInfo(page, ZOO)
      await expect(page.locator("html")).toHaveClass(scheme === "dark" ? /dark/ : /light/)
      await expect(chapterRows(page)).toHaveCount(6)
      await expect(page.getByText("ไม่มีคอมเมนต์ปักหมุด")).toBeVisible()
      expect(await seriousViolations(page)).toEqual([])
    })
  }
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
