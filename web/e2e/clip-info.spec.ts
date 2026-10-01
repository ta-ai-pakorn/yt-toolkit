/// <reference lib="dom" />
import AxeBuilder from "@axe-core/playwright"
import { expect, test, type Page, type Route } from "@playwright/test"

// owner round 2-4 (หน้าเว็บ): ช่องตัวเลข · แท็บข้อมูลคลิป (คำอธิบาย chapter ช่วงที่คนดูซ้ำ คอมเมนต์ปักหมุด แท็ก)
// · บันทึกเป็นโน้ต · เปิดในยูทูป · ภาพปกขนาดใหญ่ · หัวคลิปแบบกระชับ (สูงคงที่)
// ข้อมูลใหม่ของ backend (stats, tags, categories, mostReplayed, /pinned-comment, /note) จำลองด้วย page.route
// ข้อมูลส่วนอื่นมาจาก backend โหมด fake ตามปกติ

const BBB = "aqz-KE-bpKQ"
const ZOO = "jNQXAC9IVRw"
// คลิปภาษาไทยที่มีภาพเฟรม (ห่างกัน 4895 ms) และซับอัตโนมัติภาษาไทย
const THAI = "88o5Sk8_m1Y"

const NEW_KEYS = ["stats", "tags", "categories", "mostReplayed"]
const PINNED_TITLE = "คอมเมนต์ปักหมุด"
const NO_PINNED = "ไม่มีคอมเมนต์ปักหมุด"
const NOTE_BUTTON = "บันทึกเป็นโน้ต (.md)"
const TAB_LIST = "เครื่องมือของคลิปนี้"
const FRAME_LIST = "รายการภาพเฟรม"
const LINES = "บรรทัดในทรานสคริปต์"
const INFO_TAB = "ข้อมูลคลิป"
const REPLAYED_TITLE = "ช่วงที่คนดูซ้ำบ่อย"
const COVER = "ดูภาพปกขนาดใหญ่"

/**
 * แก้ข้อมูลคลิปที่ backend ส่งมา: ลบคีย์ใหม่ทั้งหมดก่อน (ผลไม่ขึ้นกับว่า backend มีข้อมูลเหล่านี้แล้วหรือยัง) แล้วใส่ patch
 * ใช้ทั้งคำขอปกติและคำขอ peek ของ W1 (pathname เดียวกัน)
 */
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

/** จำลอง /pinned-comment และนับจำนวนคำขอ */
async function mockPinned(page: Page, videoId: string, reply: (route: Route) => Promise<void> | void) {
  const calls = { count: 0 }
  await page.route(`**/api/videos/${videoId}/pinned-comment`, async (route) => {
    calls.count += 1
    await reply(route)
  })
  return calls
}

const envelope = (code: string, message: string) => ({ error: { code, message, detail: null } })

/** จดข้อความที่หน้าเว็บส่งให้ navigator.clipboard.writeText ตามตัวอักษร (คลิปบอร์ด Windows แปลง LF เป็น CRLF เอง) */
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

const lastWrite = (page: Page) =>
  page.evaluate(() => (window as unknown as { __clipboardWrites: string[] }).__clipboardWrites.at(-1))

const heading = (page: Page) => page.getByRole("heading", { level: 1 })
const pinnedRegion = (page: Page) => page.getByRole("region", { name: PINNED_TITLE, exact: true })
const tagsRegion = (page: Page) => page.getByRole("region", { name: /^แท็ก \(/ })
const chapterRegion = (page: Page) => page.getByRole("region", { name: /^Chapter \(/ })
const descriptionRegion = (page: Page) => page.getByRole("region", { name: "คำอธิบาย" })
const replayedRegion = (page: Page) => page.getByRole("region", { name: REPLAYED_TITLE })
const frameList = (page: Page) => page.getByRole("list", { name: FRAME_LIST })
const tab = (page: Page, name: string) => page.getByRole("tab", { name, exact: true })
const tile = (page: Page, name: string | RegExp) => page.getByRole("list", { name: "ตัวเลขของคลิป" }).getByRole("img", { name })
const gotoInfo = (page: Page, videoId: string) => page.goto(`/v/${videoId}?tab=info`)

/** ลำดับที่อ่าน (และลำดับ Tab) ของแท็บข้อมูลคลิปที่มีครบทุกส่วน ทั้งจอกว้างและจอแคบ (owner round 5) */
const INFO_ORDER = ["คำอธิบาย", /^Chapter \(/, REPLAYED_TITLE, PINNED_TITLE, /^แท็ก \(/].map(String)

/** หัวข้อของส่วนในแท็บข้อมูลคลิปตามลำดับใน DOM (ส่วนที่เป็น pattern แปลงเป็นสตริงของ pattern ให้เทียบกับ INFO_ORDER ได้) */
async function infoSectionOrder(page: Page): Promise<string[]> {
  const titles = await page.getByRole("tabpanel").locator("section h2").allTextContents()
  return titles.map((title) => {
    if (/^Chapter \(/.test(title)) return String(/^Chapter \(/)
    if (/^แท็ก \(/.test(title)) return String(/^แท็ก \(/)
    return title
  })
}

const STATS = { views: 123_456, likes: 4567, comments: 89, channelFollowers: 2_000_000 }

test.describe("ช่องตัวเลขที่หัวคลิป", () => {
  test("ยอดวิว ไลก์ คอมเมนต์ ผู้ติดตาม ความยาว เผยแพร่: ป้ายเล็กด้านบน ค่าย่อแบบไทยตัวใหญ่ด้านล่าง · ชื่อเต็มเป็นตัวเลขเต็ม", async ({
    page,
  }) => {
    await withVideo(page, ZOO, { stats: STATS, categories: ["Education"] })
    await page.goto(`/v/${ZOO}`)
    await expect(heading(page)).toContainText("Me at the zoo")
    const tiles = page.getByRole("list", { name: "ตัวเลขของคลิป" }).getByRole("img")
    await expect(tiles).toHaveCount(6)
    const views = tile(page, "ยอดวิว 123,456 ครั้ง")
    await expect(views).toHaveAttribute("title", "ยอดวิว 123,456 ครั้ง")
    await expect(views).toHaveText("ยอดวิว1.2 แสน")
    // ป้ายตัวเล็กกว่าค่า และอยู่เหนือค่า
    const [label, value] = [views.locator("span").first(), views.locator("span").last()]
    const labelBox = await label.boundingBox()
    const valueBox = await value.boundingBox()
    expect((labelBox?.y ?? 0) + (labelBox?.height ?? 0)).toBeLessThanOrEqual((valueBox?.y ?? 0) + 1)
    const size = (locator: typeof label) => locator.evaluate((el) => parseFloat(getComputedStyle(el).fontSize))
    expect(await size(value)).toBeGreaterThan(await size(label))
    await expect(tile(page, "ไลก์ 4,567 ครั้ง")).toHaveText("ไลก์4.6 พัน")
    await expect(tile(page, "คอมเมนต์ 89 รายการ")).toHaveText("คอมเมนต์89")
    await expect(tile(page, "ผู้ติดตาม 2,000,000 คน")).toHaveText("ผู้ติดตาม2 ล้าน")
    await expect(tile(page, "ความยาว 0:19")).toHaveText("ความยาว0:19")
    await expect(tile(page, /^เผยแพร่ /)).toBeVisible()
    // หมวดหมู่: ตาเห็นชื่อหมวด โปรแกรมอ่านหน้าจอได้คำว่า "หมวดหมู่" นำหน้า
    const category = page.locator('[data-slot="badge"]', { hasText: "Education" })
    await expect(category).toBeVisible()
    await expect(category).toHaveText("หมวดหมู่ Education")
    await expect(category.getByText("หมวดหมู่")).toHaveClass(/sr-only/)
  })

  for (const [width, perRow] of [
    [1280, 6],
    [360, 3],
  ] as const) {
    test(`จอ ${width} px: ช่องตัวเลขแถวละ ${perRow} ช่อง`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 })
      await withVideo(page, ZOO, { stats: STATS })
      await page.goto(`/v/${ZOO}`)
      const tiles = page.getByRole("list", { name: "ตัวเลขของคลิป" }).getByRole("img")
      await expect(tiles).toHaveCount(6)
      const tops = await tiles.evaluateAll((items) => items.map((item) => Math.round(item.getBoundingClientRect().top)))
      expect(new Set(tops.slice(0, perRow)).size).toBe(1)
      if (perRow < 6) expect(tops[perRow]).toBeGreaterThan(tops[0])
    })
  }

  test("ไม่ซ้ำจำนวนตอน: แถวข้อมูลไม่มีป้าย '3 ตอน' · หัวข้อ Chapter ในแท็บข้อมูลคลิปบอกจำนวนอยู่", async ({ page }) => {
    await withVideo(page, ZOO)
    await gotoInfo(page, ZOO)
    await expect(page.getByRole("heading", { level: 2, name: "Chapter (3 ตอน)" })).toBeVisible()
    await expect(page.getByText("3 ตอน", { exact: true })).toHaveCount(0)
  })

  test("ข้อมูลที่ยูทูปไม่บอกไม่ขึ้นช่อง: ไม่มี stats → ไม่มีช่องยอดวิว/ไลก์/คอมเมนต์/ผู้ติดตาม · ไม่มีป้ายหมวดหมู่ ไม่มีส่วนแท็ก", async ({
    page,
  }) => {
    await withVideo(page, ZOO)
    await page.goto(`/v/${ZOO}`)
    await expect(heading(page)).toContainText("Me at the zoo")
    await expect(tile(page, /^(ยอดวิว|ไลก์|คอมเมนต์|ผู้ติดตาม) /)).toHaveCount(0)
    // ความยาวและวันที่เผยแพร่มีในชุดทดสอบ จึงยังมีสองช่องนี้
    await expect(page.getByRole("list", { name: "ตัวเลขของคลิป" }).getByRole("img")).toHaveCount(2)
    await expect(page.locator('[data-slot="badge"]', { hasText: "หมวดหมู่" })).toHaveCount(0)
    await tab(page, INFO_TAB).click()
    await expect(descriptionRegion(page)).toBeVisible()
    await expect(tagsRegion(page)).toHaveCount(0)
    await expect(page.getByRole("button", { name: "คัดลอกแท็ก" })).toHaveCount(0)
  })

  test("มีแค่บางตัวเลข (ยอดวิวอย่างเดียว) แสดงเฉพาะตัวที่มี · ยอด 0 ยังแสดงเป็น 0", async ({ page }) => {
    await withVideo(page, ZOO, { stats: { views: 0 } })
    await page.goto(`/v/${ZOO}`)
    await expect(tile(page, "ยอดวิว 0 ครั้ง")).toHaveText("ยอดวิว0")
    await expect(tile(page, /^(ไลก์|คอมเมนต์|ผู้ติดตาม) /)).toHaveCount(0)
  })
})

test.describe("แท็บข้อมูลคลิป: แท็ก", () => {
  const TAGS = ["สวนสัตว์", "ช้าง", "คลิปแรกของยูทูป"]

  test("แท็กทั้งหมดเห็นเป็นชิปทันที (ไม่มีพับ/กาง) · หัวข้อ 'แท็ก (3)'", async ({ page }) => {
    await withVideo(page, ZOO, { tags: TAGS })
    await gotoInfo(page, ZOO)
    await expect(page.getByRole("heading", { level: 2, name: "แท็ก (3)" })).toBeVisible()
    await expect(tagsRegion(page).getByRole("listitem")).toHaveText(TAGS)
    await expect(tagsRegion(page).locator("[aria-expanded]")).toHaveCount(0)
  })

  test("'คัดลอกแท็ก' ได้แท็กคั่นด้วย ', ' (ตัดช่องว่าง ข้ามแท็กว่าง) และขึ้น toast · หัวคลิปไม่มีปุ่มนี้", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"])
    await recordClipboardWrites(page)
    await withVideo(page, ZOO, { tags: [" สวนสัตว์ ", "", "ช้าง", "   ", "Zoo"] })
    await page.goto(`/v/${ZOO}`)
    await expect(heading(page)).toContainText("Me at the zoo")
    await expect(page.getByRole("button", { name: "คัดลอกแท็ก" })).toHaveCount(0)
    await tab(page, INFO_TAB).click()
    await expect(page.getByRole("heading", { level: 2, name: "แท็ก (3)" })).toBeVisible()
    const copy = page.getByRole("button", { name: "คัดลอกแท็ก" })
    await expect(copy).toHaveText("คัดลอก")
    await copy.click()
    await expect(page.getByText("คัดลอกแล้ว")).toBeVisible()
    expect(await lastWrite(page)).toBe("สวนสัตว์, ช้าง, Zoo")
  })

  test("แท็กว่างทั้งหมด = ไม่มีส่วนแท็ก", async ({ page }) => {
    await withVideo(page, ZOO, { tags: ["", "  "] })
    await gotoInfo(page, ZOO)
    await expect(descriptionRegion(page)).toBeVisible()
    await expect(tagsRegion(page)).toHaveCount(0)
  })
})

test.describe("แท็บข้อมูลคลิป: ไม่มีข้อมูลเลย", () => {
  test("ไม่มีคำอธิบาย chapter ช่วงดูซ้ำ แท็ก และปิดคอมเมนต์ → ข้อความจาง 'คลิปนี้ไม่มีข้อมูลเพิ่มเติม' บรรทัดเดียว", async ({ page }) => {
    await withVideo(page, ZOO, { description: "", chapters: [], tags: [], stats: { comments: 0 } })
    const calls = await mockPinned(page, ZOO, (route) => route.fulfill({ json: { comment: null } }))
    await gotoInfo(page, ZOO)
    const empty = page.getByRole("tabpanel").getByText("คลิปนี้ไม่มีข้อมูลเพิ่มเติม")
    await expect(empty).toBeVisible()
    await expect(empty).toHaveClass(/text-muted-foreground/)
    await expect(page.getByRole("tabpanel").getByRole("heading")).toHaveCount(0)
    expect(calls.count).toBe(0)
  })
})

test.describe("แท็บข้อมูลคลิป: คอมเมนต์ปักหมุด", () => {
  const COMMENT = {
    text: "ขอบคุณที่ดูนะครับ\nลิงก์คอร์ส: https://example.com/course\n\nบรรทัดสุดท้าย",
    likes: 1520,
    publishedText: "2 years ago",
    byUploader: true,
  }

  test("ขอข้อมูลเมื่อเปิดแท็บข้อมูลคลิปครั้งแรกเท่านั้น: Skeleton → ข้อความคงการขึ้นบรรทัด ไม่มีลิงก์ · คัดลอกได้ตรงตัว · สลับแท็บไปมาไม่ขอซ้ำ", async ({
    page,
    context,
  }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"])
    await recordClipboardWrites(page)
    await withVideo(page, ZOO, { stats: STATS })
    let release = () => {}
    const gate = new Promise<void>((resolve) => (release = resolve))
    const calls = await mockPinned(page, ZOO, async (route) => {
      await gate
      await route.fulfill({ json: { comment: COMMENT } })
    })
    await page.goto(`/v/${ZOO}`)
    await expect(heading(page)).toContainText("Me at the zoo")
    // เปิดหน้า (แท็บภาพเฟรม) ยังไม่ขอคอมเมนต์ปักหมุด และหัวคลิปไม่มีส่วนนี้
    await page.waitForTimeout(300)
    expect(calls.count).toBe(0)
    await expect(pinnedRegion(page)).toHaveCount(0)

    await tab(page, INFO_TAB).click()
    await expect(page.getByRole("heading", { level: 2, name: PINNED_TITLE, exact: true })).toBeVisible()
    await expect(pinnedRegion(page).getByRole("status")).toHaveText("กำลังโหลดคอมเมนต์ปักหมุด")
    await expect(pinnedRegion(page).locator('[data-slot="skeleton"]').first()).toBeVisible()
    // ปุ่มคัดลอกขึ้นหลังได้คอมเมนต์เท่านั้น
    await expect(page.getByRole("button", { name: "คัดลอกคอมเมนต์ปักหมุด" })).toHaveCount(0)
    release()

    const text = pinnedRegion(page).getByText(/^ขอบคุณที่ดูนะครับ/)
    await expect(text).toBeVisible()
    expect(await text.evaluate((el) => el.textContent)).toBe(COMMENT.text)
    await expect(text).toHaveCSS("white-space", "pre-line")
    await expect(pinnedRegion(page).getByRole("link")).toHaveCount(0)
    await expect(pinnedRegion(page).getByRole("img", { name: "ไลก์ 1,520 ครั้ง" })).toHaveText("1.5 พัน")
    expect(calls.count).toBe(1)

    const copy = page.getByRole("button", { name: "คัดลอกคอมเมนต์ปักหมุด" })
    await expect(copy).toHaveText("คัดลอก")
    await copy.click()
    await expect(page.getByText("คัดลอกแล้ว")).toBeVisible()
    expect(await lastWrite(page)).toBe(COMMENT.text)

    // ไปแท็บอื่นแล้วกลับมา ใช้ผลเดิมจาก cache ไม่ขอซ้ำ
    await tab(page, "ซับ").click()
    await expect(text).toHaveCount(0)
    await tab(page, INFO_TAB).click()
    await expect(text).toBeVisible()
    expect(calls.count).toBe(1)
  })

  for (const [byUploader, label] of [
    [true, "เจ้าของช่อง"],
    [false, "ผู้ชม"],
  ] as const) {
    test(`ป้ายผู้เขียน: byUploader ${byUploader} → '${label}' ข้างหัวข้อ (ไม่มีชื่อผู้เขียน)`, async ({ page }) => {
      await withVideo(page, ZOO)
      await mockPinned(page, ZOO, (route) => route.fulfill({ json: { comment: { text: "ปักหมุดไว้", byUploader } } }))
      await gotoInfo(page, ZOO)
      await expect(pinnedRegion(page).getByText("ปักหมุดไว้")).toBeVisible()
      const badge = pinnedRegion(page).locator("[data-author]")
      await expect(badge).toHaveCount(1)
      await expect(badge).toHaveAttribute("data-author", byUploader ? "owner" : "viewer")
      // ตาเห็นแค่ป้าย โปรแกรมอ่านหน้าจอได้ "ผู้เขียน: ..."
      await expect(badge).toHaveText(`ผู้เขียน: ${label}`)
      await expect(badge.getByText("ผู้เขียน:")).toHaveClass(/sr-only/)
      const other = byUploader ? "ผู้ชม" : "เจ้าของช่อง"
      await expect(pinnedRegion(page).getByText(other, { exact: true })).toHaveCount(0)
    })
  }

  test("backend รุ่นเก่าไม่ส่ง byUploader (ไม่มีคีย์): ขึ้นป้าย 'ผู้ชม' ไม่ใช่ 'เจ้าของช่อง' (review I-1)", async ({ page }) => {
    await withVideo(page, ZOO)
    await mockPinned(page, ZOO, (route) => route.fulfill({ json: { comment: { text: "ปักหมุดไว้" } } }))
    await gotoInfo(page, ZOO)
    await expect(pinnedRegion(page).getByText("ปักหมุดไว้")).toBeVisible()
    const badge = pinnedRegion(page).locator("[data-author]")
    await expect(badge).toHaveCount(1)
    await expect(badge).toHaveAttribute("data-author", "viewer")
    await expect(badge).toHaveText("ผู้เขียน: ผู้ชม")
  })

  test("ไม่มีคอมเมนต์ปักหมุด (null): ข้อความจาง ไม่มีป้ายผู้เขียน และไม่มีปุ่มคัดลอก", async ({ page }) => {
    await withVideo(page, ZOO)
    await mockPinned(page, ZOO, (route) => route.fulfill({ json: { comment: null } }))
    await gotoInfo(page, ZOO)
    const none = pinnedRegion(page).getByText(NO_PINNED)
    await expect(none).toBeVisible()
    await expect(none).toHaveClass(/text-muted-foreground/)
    await expect(pinnedRegion(page).locator("[data-author]")).toHaveCount(0)
    await expect(page.getByRole("button", { name: "คัดลอกคอมเมนต์ปักหมุด" })).toHaveCount(0)
  })

  test("คลิปที่ปิดคอมเมนต์หรือมี 0 คอมเมนต์: ไม่มีส่วนคอมเมนต์ปักหมุดเลย และไม่ขอข้อมูล", async ({ page }) => {
    await withVideo(page, ZOO, { stats: { ...STATS, comments: 0 } })
    const calls = await mockPinned(page, ZOO, (route) => route.fulfill({ json: { comment: null } }))
    await gotoInfo(page, ZOO)
    await expect(tile(page, "คอมเมนต์ 0 รายการ")).toBeVisible()
    await expect(descriptionRegion(page)).toBeVisible()
    await expect(pinnedRegion(page)).toHaveCount(0)
    expect(calls.count).toBe(0)
  })

  test("ไม่รู้จำนวนคอมเมนต์ (ไม่มี stats): มีส่วนคอมเมนต์ปักหมุด", async ({ page }) => {
    await withVideo(page, BBB)
    await mockPinned(page, BBB, (route) => route.fulfill({ json: { comment: null } }))
    await gotoInfo(page, BBB)
    await expect(pinnedRegion(page)).toBeVisible()
  })

  test("เน็ตหลุด: Alert ข้อความจาก backend + ลองใหม่ · กดแล้วได้คอมเมนต์", async ({ page }) => {
    await withVideo(page, ZOO)
    let fail = true
    const calls = await mockPinned(page, ZOO, (route) =>
      fail
        ? route.fulfill({ status: 502, json: envelope("E_NETWORK", "เชื่อมต่อยูทูปไม่ได้ ตรวจอินเทอร์เน็ตแล้วลองใหม่") })
        : route.fulfill({ json: { comment: { text: "คอมเมนต์จากเจ้าของช่อง", byUploader: true } } }),
    )
    await gotoInfo(page, ZOO)
    const alert = pinnedRegion(page).getByRole("alert")
    await expect(alert).toContainText("โหลดคอมเมนต์ปักหมุดไม่สำเร็จ")
    await expect(alert).toContainText("เชื่อมต่อยูทูปไม่ได้ ตรวจอินเทอร์เน็ตแล้วลองใหม่")
    fail = false
    await alert.getByRole("button", { name: "ลองใหม่" }).click()
    await expect(pinnedRegion(page).getByText("คอมเมนต์จากเจ้าของช่อง")).toBeVisible()
    expect(calls.count).toBe(2)
  })

  test("E_BOT_CHECK: Alert ไม่มีปุ่มลองใหม่ · สลับแท็บไปมาไม่ยิงซ้ำ", async ({ page }) => {
    await withVideo(page, ZOO)
    const calls = await mockPinned(page, ZOO, (route) =>
      route.fulfill({ status: 429, json: envelope("E_BOT_CHECK", "ยูทูปขอให้ยืนยันว่าไม่ใช่บอท รอสัก 10 นาทีแล้วค่อยลองใหม่") }),
    )
    await gotoInfo(page, ZOO)
    const alert = pinnedRegion(page).getByRole("alert")
    await expect(alert).toContainText("ยูทูปขอให้ยืนยันว่าไม่ใช่บอท")
    await expect(alert.getByRole("button", { name: "ลองใหม่" })).toHaveCount(0)
    await tab(page, "ภาพเฟรม").click()
    await tab(page, INFO_TAB).click()
    await expect(alert).toBeVisible()
    expect(calls.count).toBe(1)
  })
})

test.describe("บันทึกเป็นโน้ต (.md)", () => {
  const NOTE = "---\ntitle: \"ทดสอบ\"\nsource: YT Toolkit\n---\n\n# ทดสอบ\n"

  /** จำลอง /note: จดคำขอ แล้วตอบไฟล์ .md พร้อมชื่อไฟล์ภาษาไทย (filename*) */
  async function mockNote(page: Page, videoId: string) {
    const requests: URL[] = []
    await page.route(`**/api/videos/${videoId}/note?*`, (route) => {
      requests.push(new URL(route.request().url()))
      return route.fulfill({
        body: NOTE,
        headers: {
          "Content-Type": "text/markdown; charset=utf-8",
          "Content-Disposition": `attachment; filename="note.md"; filename*=UTF-8''${encodeURIComponent("คลิปทดสอบ.note.md")}`,
        },
      })
    })
    return requests
  }

  test("ปุ่มรองในหัวคลิป (ไม่ใช่ปุ่มหลักสีเหลือง) · ชี้แล้วมีคำอธิบายว่าใช้กับ Obsidian หรือแอปจดโน้ต", async ({ page }) => {
    await page.goto(`/v/${THAI}`)
    const button = page.getByRole("button", { name: NOTE_BUTTON })
    await expect(button).toBeVisible()
    await expect(button).toHaveClass(/bg-secondary/)
    await expect(button).not.toHaveClass(/bg-primary/)
    await button.hover()
    await expect(page.getByText(/Obsidian หรือแอปจดโน้ตอื่น/)).toBeVisible()
    // หน้า W2 ยังไม่มีปุ่มหลักสีเหลือง
    await expect(page.locator('[data-slot="button"].bg-primary')).toHaveCount(0)
  })

  test("โหลดโน้ตด้วยแทร็กที่ใช้อยู่และความยาวซับกลาง (ค่าเริ่มต้น) · ได้ไฟล์ชื่อตามที่ backend ส่ง เนื้อหาตรงตัว", async ({ page }) => {
    const requests = await mockNote(page, THAI)
    await page.goto(`/v/${THAI}`)
    // รอป้ายแทร็ก = รายการแทร็กโหลดเสร็จแล้ว
    await expect(page.getByText("ซับ: ไทย (อัตโนมัติ)")).toBeVisible()
    const downloading = page.waitForEvent("download")
    await page.getByRole("button", { name: NOTE_BUTTON }).click()
    const download = await downloading
    expect(download.suggestedFilename()).toBe("คลิปทดสอบ.note.md")
    const bytes = await download.createReadStream().then(async (stream) => {
      const chunks: Buffer[] = []
      for await (const chunk of stream) chunks.push(chunk as Buffer)
      return Buffer.concat(chunks)
    })
    expect(bytes.toString("utf8")).toBe(NOTE)
    expect(requests).toHaveLength(1)
    expect(requests[0].search).toBe("?trackId=a.th-orig&maxChars=25&lines=1&minMs=1200&maxMs=5000&mode=chars")
  })

  test("เลือก 'ทีละคำ' ที่แท็บซับ → โน้ตใช้ค่าเดียวกับไฟล์ซับ (mode=tokens, tokensPerCue=1)", async ({ page }) => {
    const requests = await mockNote(page, THAI)
    await page.goto(`/v/${THAI}?tab=subs`)
    const word = page.getByRole("button", { name: "ทีละคำ", exact: true })
    await word.click()
    await expect(word).toHaveAttribute("aria-pressed", "true")
    const downloading = page.waitForEvent("download")
    await page.getByRole("button", { name: NOTE_BUTTON }).click()
    await downloading
    expect(requests[0].search).toBe(
      "?trackId=a.th-orig&maxChars=15&lines=1&minMs=800&maxMs=3000&mode=tokens&tokensPerCue=1",
    )
  })

  test("คลิปที่ไม่มีซับ: ไม่ส่ง trackId (backend ข้ามส่วนทรานสคริปต์เอง)", async ({ page }) => {
    const requests = await mockNote(page, BBB)
    await page.goto(`/v/${BBB}?tab=subs`)
    await expect(page.getByText("คลิปนี้ไม่มีซับ")).toBeVisible()
    const downloading = page.waitForEvent("download")
    await page.getByRole("button", { name: NOTE_BUTTON }).click()
    await downloading
    expect(requests[0].searchParams.has("trackId")).toBe(false)
    expect(requests[0].searchParams.get("mode")).toBe("chars")
  })

  test("โหลดไม่สำเร็จ: toast ข้อความไทยจาก envelope ไม่ได้ไฟล์ JSON · ระหว่างรอขึ้น 'กำลังเตรียมโน้ต…' และกดซ้ำไม่ได้", async ({
    page,
  }) => {
    let release = () => {}
    const gate = new Promise<void>((resolve) => (release = resolve))
    let calls = 0
    await page.route(`**/api/videos/${THAI}/note?*`, async (route) => {
      calls += 1
      await gate
      await route.fulfill({
        status: 503,
        json: envelope("E_TRANSLATION_BLOCKED", "ยูทูปยังไม่ให้โหลดซับแปลอัตโนมัติในตอนนี้ เลือกซับภาษาต้นฉบับแทน"),
      })
    })
    let downloads = 0
    page.on("download", () => (downloads += 1))
    await page.goto(`/v/${THAI}?track=t.en`)
    const button = page.getByRole("button", { name: NOTE_BUTTON })
    await button.click()
    await expect(page.getByText("กำลังเตรียมโน้ต…")).toBeVisible()
    await expect(button).toHaveAttribute("aria-disabled", "true")
    await button.click({ force: true })
    release()
    await expect(page.getByText("ยูทูปยังไม่ให้โหลดซับแปลอัตโนมัติในตอนนี้ เลือกซับภาษาต้นฉบับแทน")).toBeVisible()
    await expect(button).not.toHaveAttribute("aria-disabled", "true")
    expect(calls).toBe(1)
    expect(downloads).toBe(0)
  })
})

test.describe("เปิดในยูทูป และภาพปก", () => {
  test("ปุ่ม 'เปิดในยูทูป' ที่หัวคลิปเป็นลิงก์ไปหน้าคลิป เปิดแท็บใหม่ (noopener noreferrer) · หน้าตาเป็นปุ่มรอง", async ({ page }) => {
    await page.goto(`/v/${BBB}`)
    const link = page.getByRole("link", { name: /^เปิดในยูทูป/ })
    await expect(link).toHaveAccessibleName("เปิดในยูทูป (เปิดในแท็บใหม่)")
    await expect(link).toHaveAttribute("href", `https://www.youtube.com/watch?v=${BBB}`)
    await expect(link).toHaveAttribute("target", "_blank")
    await expect(link).toHaveAttribute("rel", "noopener noreferrer")
    await expect(link).toHaveClass(/bg-secondary/)
  })

  test("ปกไม่ใช่ลิงก์ไปยูทูป: กดแล้วเปิดภาพปกขนาดใหญ่ (กล่องเดียวกับภาพเฟรม) · Esc ปิดแล้วโฟกัสกลับที่ปก", async ({ page }) => {
    const info = await (await page.request.get(`/api/videos/${ZOO}`)).json() as { thumbnailUrl: string }
    expect(info.thumbnailUrl).not.toBe("")
    await page.goto(`/v/${ZOO}`)
    const cover = page.getByRole("button", { name: COVER })
    await expect(cover).toHaveAttribute("aria-haspopup", "dialog")
    // ลิงก์ไปยูทูปในหน้ามีแค่ปุ่ม "เปิดในยูทูป" ปกไม่ได้อยู่ในลิงก์
    await expect(page.locator("a[href^='https://www.youtube.com/watch']")).toHaveCount(1)
    await expect(cover.locator("xpath=ancestor::a")).toHaveCount(0)
    await expect(cover).toHaveCSS("cursor", "zoom-in")

    await cover.click()
    const dialog = page.getByRole("dialog", { name: "ภาพปกของคลิป" })
    await expect(dialog).toBeVisible()
    await expect(dialog.locator("img")).toHaveAttribute("src", info.thumbnailUrl)
    await page.keyboard.press("Escape")
    await expect(dialog).toHaveCount(0)
    await expect(cover).toBeFocused()
  })

  for (const key of ["Enter", "Space"]) {
    test(`คีย์บอร์ด: ${key} ที่ปกเปิดภาพใหญ่ · เห็นไอคอนขยายตอนโฟกัส · คลิกที่ภาพปิดได้`, async ({ page }) => {
      await page.goto(`/v/${ZOO}`)
      const cover = page.getByRole("button", { name: COVER })
      const zoom = cover.locator('[data-slot="cover-zoom"]')
      await expect(zoom).toHaveCSS("opacity", "0")
      await cover.focus()
      await page.keyboard.press("Tab")
      await page.keyboard.press("Shift+Tab")
      await expect(cover).toBeFocused()
      await expect(zoom).toHaveCSS("opacity", "1")
      await page.keyboard.press(key)
      const dialog = page.getByRole("dialog", { name: "ภาพปกของคลิป" })
      await expect(dialog).toBeVisible()
      await expect(dialog.locator("img")).toBeVisible()
      await dialog.locator("img").click()
      await expect(dialog).toHaveCount(0)
      await expect(cover).toBeFocused()
    })
  }

  test("ชี้เมาส์ที่ปกเห็นไอคอนขยาย", async ({ page }) => {
    await page.goto(`/v/${ZOO}`)
    const cover = page.getByRole("button", { name: COVER })
    const zoom = cover.locator('[data-slot="cover-zoom"]')
    await expect(zoom).toHaveCSS("opacity", "0")
    await cover.hover()
    await expect(zoom).toHaveCSS("opacity", "1")
  })
})

test.describe("แท็บข้อมูลคลิป: ช่วงที่คนดูซ้ำบ่อย", () => {
  const SEGMENTS = [
    { startMs: 20_000, endMs: 30_000 },
    { startMs: 60_000, endMs: 66_000 },
  ]

  /** เวลาของภาพเฟรมทุกภาพ (ms) จาก API เดียวกับที่หน้าเว็บใช้ */
  async function frameTimes(page: Page): Promise<number[]> {
    const response = await page.request.get(`/api/videos/${THAI}/storyboard`)
    const data = (await response.json()) as { frames: { tMs: number }[] }
    return data.frames.map((frame) => frame.tMs)
  }

  const inSegments = (ms: number) => SEGMENTS.some((s) => ms >= s.startMs && ms < s.endMs)

  test("ภาพเฟรมในช่วงมีป้าย 'ดูซ้ำบ่อย' (ไอคอน + ชื่อสำหรับโปรแกรมอ่านหน้าจอ) · ภาพอื่นไม่มี", async ({ page }) => {
    await withVideo(page, THAI, { mostReplayed: SEGMENTS })
    await page.goto(`/v/${THAI}`)
    const times = await frameTimes(page)
    await expect(frameList(page).getByRole("listitem")).toHaveCount(times.length)
    const marked = await frameList(page)
      .getByRole("button")
      .evaluateAll((buttons) => buttons.map((button) => button.querySelector("[data-replayed]") !== null))
    const expected = times.map(inSegments)
    expect(expected.filter(Boolean).length).toBeGreaterThan(0)
    expect(marked).toEqual(expected)
    // ชื่อปุ่มของภาพในช่วง: "ภาพเฟรมที่ 00:00:24 ดูซ้ำบ่อย"
    const first = times.findIndex(inSegments)
    const button = frameList(page).getByRole("button").nth(first)
    await expect(button).toHaveAccessibleName(/^ภาพเฟรมที่ \d{2}:\d{2}:\d{2}\s+ดูซ้ำบ่อย$/)
    await expect(button.locator("[data-replayed] svg")).toBeVisible()
    // บรรทัดเวลาของช่วงย้ายไปแท็บข้อมูลคลิปแล้ว ส่วนภาพเฟรมไม่มีบรรทัดนี้
    await expect(page.getByRole("region", { name: "ภาพเฟรม" }).getByRole("button", { name: /^ไปภาพเฟรมช่วง / })).toHaveCount(0)
  })

  test("ส่วน 'ช่วงที่คนดูซ้ำบ่อย' มีปุ่มเวลา 00:00:20, 00:01:00 · กดแล้วไปแท็บภาพเฟรม ภาพแรกในช่วงถูกไฮไลต์ เห็นในจอ และได้โฟกัส", async ({
    page,
  }) => {
    await withVideo(page, THAI, { mostReplayed: SEGMENTS })
    await gotoInfo(page, THAI)
    const times = replayedRegion(page).getByRole("button", { name: /^ไปภาพเฟรมช่วง / })
    await expect(times).toHaveText(["00:00:20", "00:01:00"])
    await times.nth(1).click()
    // review M-2: ภาพแรกที่อยู่ในช่วง 60-66 วินาที (ภาพห่างกัน 4895 ms → 63635 ms = 00:01:03) ไม่ใช่ภาพที่ใกล้ 60 วินาที
    // ที่สุด (58740 ms อยู่นอกช่วงและไม่มีป้าย)
    await expect(page).toHaveURL(new RegExp(`/v/${THAI}\\?at=63635$`))
    await expect(tab(page, "ภาพเฟรม")).toHaveAttribute("aria-selected", "true")
    const highlighted = frameList(page).locator("[data-highlighted]")
    await expect(highlighted).toHaveCount(1)
    await expect(highlighted).toBeFocused()
    await expect(highlighted).toBeInViewport()
    await expect(highlighted.locator("img")).toHaveAttribute("alt", "ภาพเฟรมที่ 00:01:03")
    await expect(highlighted.locator("[data-replayed]")).toHaveCount(1)

    // กลับไปแท็บข้อมูลคลิป (ล้างเวลา) แล้วกดเวลาเดิมซ้ำ ก็กลับมาที่ภาพเดิม
    await tab(page, INFO_TAB).click()
    await replayedRegion(page).getByRole("button", { name: "ไปภาพเฟรมช่วง 00:01:00" }).click()
    await expect(highlighted).toBeFocused()
    await expect(highlighted).toBeInViewport()
  })

  test("เปิด ?tab=info ตรง ๆ ไม่ขอ storyboard จนกว่าจะกดเวลาของช่วงที่คนดูซ้ำ (review M-2)", async ({ page }) => {
    await withVideo(page, THAI, { mostReplayed: SEGMENTS })
    const storyboardCalls: string[] = []
    page.on("request", (request) => {
      if (new URL(request.url()).pathname === `/api/videos/${THAI}/storyboard`) storyboardCalls.push(request.url())
    })
    await gotoInfo(page, THAI)
    const times = replayedRegion(page).getByRole("button", { name: /^ไปภาพเฟรมช่วง / })
    await expect(times).toHaveText(["00:00:20", "00:01:00"])
    await page.waitForTimeout(500)
    expect(storyboardCalls).toHaveLength(0)
    await times.nth(1).click()
    await expect(page).toHaveURL(new RegExp(`/v/${THAI}\\?at=63635$`))
    expect(storyboardCalls.length).toBeGreaterThan(0)
  })

  test("ช่วงสั้นที่ไม่มีภาพอยู่ข้างใน: ภาพที่ใกล้กลางช่วงที่สุดได้ป้าย และปุ่มเวลาพาไปภาพนั้น (review M-2)", async ({ page }) => {
    // 61-62 วินาที: ไม่มีภาพในช่วง กลางช่วง 61.5 วินาที ใกล้ภาพ 63635 ms (00:01:03) ที่สุด
    await withVideo(page, THAI, { mostReplayed: [{ startMs: 61_000, endMs: 62_000 }] })
    await page.goto(`/v/${THAI}`)
    const marked = frameList(page).locator("button:has([data-replayed])")
    await expect(marked).toHaveCount(1)
    await expect(marked.locator("img")).toHaveAttribute("alt", "ภาพเฟรมที่ 00:01:03")
    await tab(page, INFO_TAB).click()
    await page.getByRole("button", { name: /^ไปภาพเฟรมช่วง 00:01:01/ }).click()
    const highlighted = frameList(page).locator("[data-highlighted]")
    await expect(highlighted).toBeFocused()
    await expect(highlighted.locator("[data-replayed]")).toHaveCount(1)
  })

  test("'คัดลอกช่วงที่คนดูซ้ำบ่อย' ได้ช่วงละบรรทัด HH:MM:SS - HH:MM:SS", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"])
    await recordClipboardWrites(page)
    await withVideo(page, THAI, { mostReplayed: SEGMENTS })
    await gotoInfo(page, THAI)
    await replayedRegion(page).getByRole("button", { name: "คัดลอกช่วงที่คนดูซ้ำบ่อย" }).click()
    await expect(page.getByText("คัดลอกแล้ว")).toBeVisible()
    expect(await lastWrite(page)).toBe("00:00:20 - 00:00:30\n00:01:00 - 00:01:06")
  })

  test("ป้ายในแท็บทรานสคริปต์มีคำอธิบายเมื่อชี้เมาส์ (review M-3)", async ({ page }) => {
    await withVideo(page, THAI, { mostReplayed: SEGMENTS })
    await page.goto(`/v/${THAI}?tab=transcript`)
    const mark = page.getByRole("list", { name: LINES }).locator("[data-replayed]").first()
    await expect(mark).toHaveAttribute("title", "ช่วงที่คนดูซ้ำบ่อย")
  })

  test("คลิปที่ไม่มี heatmap: ไม่มีส่วนช่วงที่ดูซ้ำในแท็บข้อมูลคลิป และไม่มีป้ายบนภาพ", async ({ page }) => {
    await withVideo(page, THAI)
    await page.goto(`/v/${THAI}`)
    await expect(frameList(page).getByRole("listitem").first()).toBeVisible()
    await expect(frameList(page).locator("[data-replayed]")).toHaveCount(0)
    await tab(page, INFO_TAB).click()
    await expect(descriptionRegion(page)).toBeVisible()
    await expect(replayedRegion(page)).toHaveCount(0)
  })

  test("แท็บทรานสคริปต์: บรรทัดที่คาบเกี่ยวกับช่วงมีป้ายเดียวกัน บรรทัดอื่นไม่มี", async ({ page }) => {
    await withVideo(page, THAI, { mostReplayed: SEGMENTS })
    await page.goto(`/v/${THAI}?tab=transcript`)
    const lines = page.getByRole("list", { name: LINES }).getByRole("button")
    await expect(lines.first()).toBeVisible()
    const rows = await lines.evaluateAll((buttons) =>
      buttons.map((button) => {
        const [h, m, s] = (button.querySelector(".font-mono")?.textContent ?? "").split(":").map(Number)
        return { startS: (h * 60 + m) * 60 + s, marked: button.querySelector("[data-replayed]") !== null }
      }),
    )
    const marked = rows.filter((row) => row.marked)
    expect(marked.length).toBeGreaterThan(0)
    // บรรทัดที่เริ่มในช่วงต้องมีป้าย · บรรทัดที่มีป้ายต้องเริ่มก่อนปลายช่วง (เวลาที่แสดงตัดเศษวินาที)
    for (const row of rows) {
      if (inSegments(row.startS * 1000) && inSegments(row.startS * 1000 + 999)) expect(row.marked, `${row.startS}`).toBe(true)
      if (row.marked) expect(SEGMENTS.some((s) => row.startS * 1000 < s.endMs), `${row.startS}`).toBe(true)
    }
    await expect(lines.filter({ has: page.locator("[data-replayed]") }).first()).toHaveAccessibleName(/ดูซ้ำบ่อย/)
  })
})

test.describe("หัวคลิปแบบกระชับ (สูงคงที่)", () => {
  // กรณีหนักสุด: ตัวเลขครบ หมวดหมู่ คำอธิบายยาว chapter แท็กหลายอัน ช่วงดูซ้ำ และคอมเมนต์ปักหมุด
  const FULL = {
    stats: STATS,
    categories: ["People & Blogs"],
    tags: Array.from({ length: 12 }, (_, i) => `แท็กทดสอบที่ ${i + 1}`),
    mostReplayed: [{ startMs: 5000, endMs: 9000 }],
  }

  const tabTop = async (page: Page) => (await page.getByRole("tablist", { name: TAB_LIST }).boundingBox())?.y ?? -1

  test("จอ 360×800: แถบแท็บอยู่ในจอแรก (ไม่เกิน 800 px) · ปุ่มในหัวคลิปสูงอย่างน้อย 44 px · หัวคลิปไม่มีกล่องที่กางได้", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 360, height: 800 })
    await withVideo(page, ZOO, FULL)
    await page.goto(`/v/${ZOO}`)
    await expect(heading(page)).toContainText("Me at the zoo")
    await expect(tile(page, "ยอดวิว 123,456 ครั้ง")).toBeVisible()
    // ส่วนที่เคยอยู่ในหัวคลิป (และกางได้) ย้ายไปแท็บข้อมูลคลิปแล้ว
    await expect(page.locator("[aria-expanded]")).toHaveCount(0)
    await expect(pinnedRegion(page)).toHaveCount(0)
    await expect(chapterRegion(page)).toHaveCount(0)

    const tabs = await page.getByRole("tablist", { name: TAB_LIST }).boundingBox()
    expect(tabs).not.toBeNull()
    expect((tabs?.y ?? 0) + (tabs?.height ?? 0)).toBeLessThanOrEqual(800)
    await expect(tab(page, "ภาพเฟรม")).toBeInViewport()

    // ทุกปุ่มในหัวคลิปสูงอย่างน้อย 44 px และหน้าไม่ล้นแนวนอน
    for (const control of [page.getByRole("button", { name: NOTE_BUTTON }), page.getByRole("link", { name: /^เปิดในยูทูป/ })]) {
      const box = await control.boundingBox()
      expect(box?.height ?? 0).toBeGreaterThanOrEqual(44)
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360)

    // แท็บข้อมูลคลิปที่จอแคบ: คอลัมน์เดียว ปุ่มคัดลอกสูงอย่างน้อย 44 px หน้าไม่ล้น
    await mockPinned(page, ZOO, (route) => route.fulfill({ json: { comment: { text: "ปักหมุด", byUploader: true } } }))
    await tab(page, INFO_TAB).click()
    await expect(pinnedRegion(page).getByText("ปักหมุด", { exact: true })).toBeVisible()
    for (const name of ["คัดลอกคำอธิบาย", "คัดลอก chapter", "คัดลอกช่วงที่คนดูซ้ำบ่อย", "คัดลอกคอมเมนต์ปักหมุด", "คัดลอกแท็ก"]) {
      const box = await page.getByRole("button", { name, exact: true }).boundingBox()
      expect(box?.height ?? 0, name).toBeGreaterThanOrEqual(44)
    }
    const order = await Promise.all(
      [descriptionRegion(page), chapterRegion(page), replayedRegion(page), pinnedRegion(page), tagsRegion(page)].map(
        async (region) => (await region.boundingBox())?.y ?? -1,
      ),
    )
    // จอ 360 px คอลัมน์เดียว: คำอธิบาย → Chapter → ช่วงดูซ้ำ → คอมเมนต์ปักหมุด → แท็ก ทั้งตำแหน่งบนจอและลำดับใน DOM
    expect([...order].sort((a, b) => a - b)).toEqual(order)
    expect(new Set(order).size).toBe(order.length)
    expect(await infoSectionOrder(page)).toEqual(INFO_ORDER)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360)
  })

  // review I-3: ชื่อคลิปยาวต้องไม่ดันแถบแท็บพ้นจอแรกของมือถือ (ชื่อ BBB 64 ตัว และชื่อไทย 100 ตัว)
  const LONG_THAI = "วิธีทำการตลาดออนไลน์ให้ได้ลูกค้าจริงสำหรับธุรกิจเล็กด้วยงบประมาณจำกัดและเครื่องมือฟรี".repeat(3)
  const LONG_TITLES = [
    ["ชื่อ BBB 64 ตัว", "Big Buck Bunny 60fps 4K - Official Blender Foundation Short Film"],
    ["ชื่อไทย 100 ตัว", [...LONG_THAI].slice(0, 100).join("")],
  ] as const
  for (const [label, title] of LONG_TITLES) {
    test(`จอ 360×800 กับ${label}: แถบแท็บยังอยู่ในจอแรก (ไม่เกิน 800 px) และอ่านชื่อเต็มได้`, async ({ page }) => {
      await page.setViewportSize({ width: 360, height: 800 })
      await withVideo(page, ZOO, { ...FULL, title })
      await page.goto(`/v/${ZOO}`)
      await expect(heading(page)).toHaveAccessibleName(title)
      await expect(tile(page, "ยอดวิว 123,456 ครั้ง")).toBeVisible()
      const tabs = await page.getByRole("tablist", { name: TAB_LIST }).boundingBox()
      expect(tabs).not.toBeNull()
      expect((tabs?.y ?? 0) + (tabs?.height ?? 0)).toBeLessThanOrEqual(800)
      // ชื่อที่ถูกตัดที่ 3 บรรทัดยังอ่านเต็มได้: ชื่อเต็มอยู่ใน title (ชี้เมาส์/กดค้าง) และโปรแกรมอ่านหน้าจออ่านครบ
      await expect(heading(page)).toHaveAttribute("title", title)
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360)
    })
  }

  for (const width of [1280, 360]) {
    test(`จอ ${width} px: แถบแท็บไม่ขยับหลังข้อมูลที่มาทีหลังโหลดเสร็จ (ป้ายแทร็กซับ) และไม่ขึ้นกับความยาวคำอธิบาย`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 800 })
      // รายการแทร็กมาช้า: ป้าย "ซับ: …" ขึ้นทีหลังหัวคลิป · หมวดหมู่ยาวช่วยให้แถวป้ายเต็ม
      let release = () => {}
      const gate = new Promise<void>((resolve) => (release = resolve))
      await page.route(`**/api/videos/${THAI}/subtitles`, async (route) => {
        await gate
        await route.continue()
      })
      await withVideo(page, THAI, { ...FULL, categories: ["People & Blogs", "Education", "Science & Technology"] })
      await page.goto(`/v/${THAI}`)
      await expect(heading(page)).toBeVisible()
      await expect(tile(page, "ยอดวิว 123,456 ครั้ง")).toBeVisible()
      const before = await tabTop(page)
      release()
      await expect(page.getByText("ซับ: ไทย (อัตโนมัติ)")).toBeVisible()
      expect(await tabTop(page)).toBe(before)

      // คำอธิบายยาวมาก (หลายร้อยบรรทัด) ไม่มีผลกับหัวคลิป
      await page.unrouteAll({ behavior: "wait" })
      await withVideo(page, THAI, { ...FULL, categories: ["People & Blogs", "Education", "Science & Technology"], description: "บรรทัด\n".repeat(400) })
      await page.reload()
      await expect(page.getByText("ซับ: ไทย (อัตโนมัติ)")).toBeVisible()
      expect(await tabTop(page)).toBe(before)
    })
  }

  for (const width of [1280, 360]) {
    test(`จอ ${width} px: Skeleton หัวคลิปสูงใกล้เคียงของจริง แถบแท็บขยับไม่เกิน 40 px ตอนโหลดเสร็จ`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 })
      await withVideo(page, BBB, FULL)
      let release = () => {}
      const gate = new Promise<void>((resolve) => (release = resolve))
      // ลงทะเบียนทีหลัง = ทำงานก่อน: หน่วงคำขอข้อมูลคลิปแล้วส่งต่อให้ตัวแก้ข้อมูลด้านบน
      await page.route(
        (url) => url.pathname === `/api/videos/${BBB}`,
        async (route) => {
          await gate
          await route.fallback()
        },
      )
      await page.goto(`/v/${BBB}`)
      await expect(page.getByRole("status").filter({ hasText: "กำลังโหลด" }).first()).toBeAttached()
      const skeletonTop = await tabTop(page)
      expect(skeletonTop).toBeGreaterThan(0)
      release()
      await expect(tile(page, "ยอดวิว 123,456 ครั้ง")).toBeVisible()
      const loadedTop = await tabTop(page)
      expect(Math.abs(loadedTop - skeletonTop)).toBeLessThanOrEqual(40)
    })
  }

  test("จอกว้าง 1280 px แท็บข้อมูลคลิป: ซ้าย คำอธิบาย → Chapter · ขวา ช่วงดูซ้ำ → คอมเมนต์ปักหมุด → แท็ก (owner round 5)", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    await withVideo(page, ZOO, FULL)
    await mockPinned(page, ZOO, (route) => route.fulfill({ json: { comment: { text: "ปักหมุด", byUploader: false } } }))
    await gotoInfo(page, ZOO)
    await expect(pinnedRegion(page).getByText("ปักหมุด", { exact: true })).toBeVisible()
    const [description, chapters, replayed, pinned, tags] = await Promise.all(
      [descriptionRegion(page), chapterRegion(page), replayedRegion(page), pinnedRegion(page), tagsRegion(page)].map((region) =>
        region.boundingBox(),
      ),
    )
    const x = (box: typeof description) => box?.x ?? -1
    const y = (box: typeof description) => box?.y ?? -1
    expect(Math.abs(x(chapters) - x(description))).toBeLessThan(2)
    expect(y(description)).toBeLessThan(y(chapters))
    // คอลัมน์ขวา: ช่วงดูซ้ำอยู่บนสุด เหนือคอมเมนต์ปักหมุด แล้วแท็ก
    expect(Math.abs(x(replayed) - x(pinned))).toBeLessThan(2)
    expect(Math.abs(x(tags) - x(pinned))).toBeLessThan(2)
    expect(y(replayed)).toBeLessThan(y(pinned))
    expect(y(pinned)).toBeLessThan(y(tags))
    expect(x(replayed)).toBeGreaterThan(x(description) + (description?.width ?? 0))
    // คอลัมน์ขวาเริ่มบรรทัดเดียวกับคอลัมน์ซ้าย
    expect(Math.abs(y(replayed) - y(description))).toBeLessThan(2)
    // ลำดับใน DOM (= ลำดับ Tab) ตรงกับลำดับที่อ่าน: คอลัมน์ซ้ายก่อน แล้วคอลัมน์ขวา
    expect(await infoSectionOrder(page)).toEqual(INFO_ORDER)
  })

  for (const scheme of ["dark", "light"] as const) {
    test(`แท็บข้อมูลคลิปที่มีครบทุกส่วน (ป้ายผู้เขียนทั้งสองแบบ) และภาพเฟรมที่มีป้ายไม่มีปัญหาระดับ serious/critical (${scheme})`, async ({
      page,
    }) => {
      await withVideo(page, THAI, { ...FULL, mostReplayed: [{ startMs: 0, endMs: 20_000 }] })
      let byUploader = true
      await mockPinned(page, THAI, (route) =>
        route.fulfill({ json: { comment: { text: "คอมเมนต์ปักหมุด\nบรรทัดสอง", likes: 12, byUploader } } }),
      )
      await page.emulateMedia({ colorScheme: scheme })
      await page.goto(`/v/${THAI}`)
      await expect(page.locator("html")).toHaveClass(scheme === "dark" ? /dark/ : /light/)
      await expect(frameList(page).locator("[data-replayed]").first()).toBeVisible()
      expect(await seriousViolations(page)).toEqual([])

      await tab(page, INFO_TAB).click()
      await expect(pinnedRegion(page).getByText(/บรรทัดสอง/)).toBeVisible()
      await expect(pinnedRegion(page).locator('[data-author="owner"]')).toBeVisible()
      expect(await seriousViolations(page)).toEqual([])

      // ป้าย "ผู้ชม" (โหลดหน้าใหม่ = cache ใหม่)
      byUploader = false
      await page.reload()
      await expect(pinnedRegion(page).locator('[data-author="viewer"]')).toBeVisible()
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

// review M-8: รอยต่อกับ backend ปลอมจริง (ไม่ mock /pinned-comment และ /note) ล็อกว่ารูปแบบคำตอบตรงกับที่หน้าเว็บอ่าน
test.describe("รอยต่อกับ backend (ไม่ mock)", () => {
  const OWNER = "OWNERTHSUB1"

  test("คอมเมนต์ปักหมุด: 88o5Sk8_m1Y มี · aqz-KE-bpKQ ไม่มี (null) · OWNERTHSUB1 เน็ตหลุดและลองใหม่ได้จริง", async ({ page }) => {
    const calls: string[] = []
    page.on("request", (request) => {
      if (request.url().includes("/pinned-comment")) calls.push(new URL(request.url()).pathname)
    })

    await gotoInfo(page, THAI)
    await expect(pinnedRegion(page).getByText(/^ขอบคุณที่ดูคลิปนี้นะครับ/)).toBeVisible()
    await expect(pinnedRegion(page).getByRole("button", { name: "คัดลอกคอมเมนต์ปักหมุด" })).toBeVisible()

    await gotoInfo(page, BBB)
    await expect(pinnedRegion(page).getByText(NO_PINNED)).toBeVisible()

    await gotoInfo(page, OWNER)
    const alert = pinnedRegion(page).getByRole("alert")
    await expect(alert).toContainText("โหลดคอมเมนต์ปักหมุดไม่สำเร็จ")
    await expect(alert).toContainText("เน็ตหลุด ลองใหม่อีกครั้ง")
    // review I-1: backend ไม่จำ E_NETWORK ปุ่มลองใหม่จึงยิงคำขอใหม่ถึง backend จริง
    const before = calls.filter((path) => path.includes(OWNER)).length
    await alert.getByRole("button", { name: "ลองใหม่" }).click()
    await expect.poll(() => calls.filter((path) => path.includes(OWNER)).length).toBe(before + 1)
    await expect(pinnedRegion(page).getByRole("alert")).toContainText("เน็ตหลุด ลองใหม่อีกครั้ง")
  })

  // C-A2 v2: backend ปลอมมีคลิป VIEWERPIN01 ที่คอมเมนต์ปักหมุดเป็นของผู้ชม (byUploader: false)
  // (เพิ่มโดยฝั่ง backend ของ owner round 4: เทสนี้ผ่านเมื่อรวมงานฝั่ง backend แล้ว)
  test("คอมเมนต์ปักหมุดของผู้ชม: VIEWERPIN01 แสดงข้อความพร้อมป้าย 'ผู้ชม'", async ({ page }) => {
    await gotoInfo(page, "VIEWERPIN01")
    const badge = pinnedRegion(page).locator("[data-author]")
    await expect(badge).toHaveAttribute("data-author", "viewer")
    await expect(badge).toHaveText("ผู้เขียน: ผู้ชม")
    await expect(pinnedRegion(page).getByRole("button", { name: "คัดลอกคอมเมนต์ปักหมุด" })).toBeVisible()
  })

  test("โน้ต: backend ปลอมส่งไฟล์ .md (LF) ชื่อไทย มี front matter แท็กแบบ Obsidian และทรานสคริปต์", async ({ page }) => {
    await page.goto(`/v/${THAI}`)
    await expect(page.getByText("ซับ: ไทย (อัตโนมัติ)")).toBeVisible()
    const downloading = page.waitForEvent("download")
    await page.getByRole("button", { name: NOTE_BUTTON }).click()
    const download = await downloading
    expect(download.suggestedFilename()).toBe("Thai Listening Practice EP.1 Beginner.note.md")
    const text = await download.createReadStream().then(async (stream) => {
      const chunks: Buffer[] = []
      for await (const chunk of stream) chunks.push(chunk as Buffer)
      return Buffer.concat(chunks).toString("utf8")
    })
    expect(text.startsWith('---\ntitle: "Thai Listening Practice | EP.1 | Beginner"\n')).toBe(true)
    expect(text).not.toContain("\r")
    expect(text).toContain("\nsource: YT Toolkit\n---\n")
    expect(text).toContain("\n## ทรานสคริปต์\n")
    const tags = text.match(/^tags: \[(.*)\]$/m)?.[1] ?? ""
    // แท็กไม่มีช่องว่างข้างใน (Obsidian ใช้ไม่ได้) ทุกอันอยู่ในเครื่องหมายคำพูด
    for (const tag of tags.split(", ").filter(Boolean)) expect(tag).toMatch(/^"[^\s"]+"$/)
  })
})
