/// <reference lib="dom" />
import AxeBuilder from "@axe-core/playwright"
import { expect, test, type Page, type Route } from "@playwright/test"

// owner round 2 (หน้าเว็บ): ข้อมูลคลิป · คอมเมนต์ปักหมุด · บันทึกเป็นโน้ต · ช่วงที่คนดูซ้ำ · หัวคลิปแบบกระชับ
// ข้อมูลใหม่ของ backend (stats, tags, categories, mostReplayed, /pinned-comment, /note) จำลองด้วย page.route
// ข้อมูลส่วนอื่นมาจาก backend โหมด fake ตามปกติ

const BBB = "aqz-KE-bpKQ"
const ZOO = "jNQXAC9IVRw"
// คลิปภาษาไทยที่มีภาพเฟรม (ห่างกัน 4895 ms) และซับอัตโนมัติภาษาไทย
const THAI = "88o5Sk8_m1Y"

const NEW_KEYS = ["stats", "tags", "categories", "mostReplayed"]
const PINNED_TITLE = "คอมเมนต์ปักหมุดจากเจ้าของช่อง"
const NO_PINNED = "ไม่มีคอมเมนต์ปักหมุดจากเจ้าของช่อง"
const NOTE_BUTTON = "บันทึกเป็นโน้ต (.md)"
const TAB_LIST = "เครื่องมือของคลิปนี้"
const FRAME_LIST = "รายการภาพเฟรม"
const LINES = "บรรทัดในทรานสคริปต์"

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
const toggle = (page: Page, name: string | RegExp) => page.getByRole("button", { name, exact: typeof name === "string" })
const pinnedRegion = (page: Page) => page.getByRole("region", { name: PINNED_TITLE })
const tagsRegion = (page: Page) => page.getByRole("region", { name: /^แท็ก \(/ })
const chapterRegion = (page: Page) => page.getByRole("region", { name: /^Chapter \(/ })
const frameList = (page: Page) => page.getByRole("list", { name: FRAME_LIST })
const tab = (page: Page, name: string) => page.getByRole("tab", { name, exact: true })

const STATS = { views: 123_456, likes: 4567, comments: 89, channelFollowers: 2_000_000 }

test.describe("ข้อมูลคลิป: ยอดดู ถูกใจ คอมเมนต์ หมวดหมู่", () => {
  test("แถวข้อมูลแสดงตัวเลขย่อแบบไทยพร้อมไอคอน · ชื่อสำหรับโปรแกรมอ่านหน้าจอเป็นตัวเลขเต็ม · หมวดหมู่เป็นป้ายเล็ก", async ({
    page,
  }) => {
    await withVideo(page, ZOO, { stats: STATS, categories: ["Education"] })
    await page.goto(`/v/${ZOO}`)
    await expect(heading(page)).toContainText("Me at the zoo")
    const views = page.getByRole("img", { name: "ยอดดู 123,456 ครั้ง" })
    await expect(views).toHaveText("1.2 แสน ครั้ง")
    await expect(views.locator("svg")).toHaveCount(1)
    await expect(views).toHaveAttribute("title", "ยอดดู 123,456 ครั้ง")
    await expect(page.getByRole("img", { name: "ถูกใจ 4,567 ครั้ง" })).toHaveText("4.6 พัน")
    await expect(page.getByRole("img", { name: "คอมเมนต์ 89 รายการ" })).toHaveText("89")
    // หมวดหมู่: ตาเห็นชื่อหมวด โปรแกรมอ่านหน้าจอได้คำว่า "หมวดหมู่" นำหน้า
    const category = page.locator('[data-slot="badge"]', { hasText: "Education" })
    await expect(category).toBeVisible()
    await expect(category).toHaveText("หมวดหมู่ Education")
    await expect(category.getByText("หมวดหมู่")).toHaveClass(/sr-only/)
  })

  test("ไม่ซ้ำจำนวนตอน: แถวข้อมูลไม่มีป้าย '3 ตอน' แล้ว หัวข้อ Chapter บอกจำนวนอยู่", async ({ page }) => {
    await withVideo(page, ZOO)
    await page.goto(`/v/${ZOO}`)
    await expect(page.getByRole("heading", { level: 2, name: "Chapter (3 ตอน)" })).toBeVisible()
    await expect(page.getByText("3 ตอน", { exact: true })).toHaveCount(0)
  })

  test("ข้อมูลที่ยูทูปไม่บอกไม่แสดง: ไม่มี stats แท็ก หมวดหมู่ → ไม่มีตัวเลข ไม่มีกล่องแท็ก ไม่มีป้ายหมวดหมู่", async ({
    page,
  }) => {
    await withVideo(page, ZOO)
    await page.goto(`/v/${ZOO}`)
    await expect(heading(page)).toContainText("Me at the zoo")
    await expect(page.getByRole("img", { name: /^(ยอดดู|ถูกใจ|คอมเมนต์) / })).toHaveCount(0)
    await expect(tagsRegion(page)).toHaveCount(0)
    await expect(page.getByRole("button", { name: "คัดลอกแท็ก" })).toHaveCount(0)
    await expect(page.locator('[data-slot="badge"]', { hasText: "หมวดหมู่" })).toHaveCount(0)
  })

  test("มีแค่บางตัวเลข (ยอดดูอย่างเดียว) แสดงเฉพาะตัวที่มี · ยอด 0 ยังแสดงเป็น 0", async ({ page }) => {
    await withVideo(page, ZOO, { stats: { views: 0 } })
    await page.goto(`/v/${ZOO}`)
    await expect(page.getByRole("img", { name: "ยอดดู 0 ครั้ง" })).toHaveText("0 ครั้ง")
    await expect(page.getByRole("img", { name: /^(ถูกใจ|คอมเมนต์) / })).toHaveCount(0)
  })
})

test.describe("ข้อมูลคลิป: แท็ก", () => {
  const TAGS = ["สวนสัตว์", "ช้าง", "คลิปแรกของยูทูป"]

  test("เริ่มแบบพับ: เห็นแค่ 'แท็ก (3)' · กางแล้วเห็นแท็กเป็นชิป · พับกลับได้", async ({ page }) => {
    await withVideo(page, ZOO, { tags: TAGS })
    await page.goto(`/v/${ZOO}`)
    const button = toggle(page, "แท็ก (3)")
    await expect(button).toHaveAttribute("aria-expanded", "false")
    await expect(page.getByRole("heading", { level: 2, name: "แท็ก (3)" })).toBeVisible()
    // ตอนพับรายการถูกซ่อน (ไม่อยู่ใน accessibility tree) จึงหาด้วยแท็ก ul
    const list = tagsRegion(page).locator("ul")
    await expect(list).toBeHidden()
    await expect(button).toHaveAttribute("aria-controls", (await list.getAttribute("id")) ?? "")
    await button.click()
    await expect(button).toHaveAttribute("aria-expanded", "true")
    await expect(list.getByRole("listitem")).toHaveText(TAGS)
    await button.click()
    await expect(list).toBeHidden()
  })

  test("'คัดลอกแท็ก' ได้แท็กคั่นด้วย ', ' (ตัดช่องว่าง ข้ามแท็กว่าง) แม้กล่องพับอยู่ และขึ้น toast", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"])
    await recordClipboardWrites(page)
    await withVideo(page, ZOO, { tags: [" สวนสัตว์ ", "", "ช้าง", "   ", "Zoo"] })
    await page.goto(`/v/${ZOO}`)
    await expect(toggle(page, "แท็ก (3)")).toBeVisible()
    const copy = page.getByRole("button", { name: "คัดลอกแท็ก" })
    await expect(copy).toHaveText("คัดลอก")
    await copy.click()
    await expect(page.getByText("คัดลอกแล้ว")).toBeVisible()
    expect(await lastWrite(page)).toBe("สวนสัตว์, ช้าง, Zoo")
  })

  test("แท็กว่างทั้งหมด = ไม่มีกล่องแท็ก", async ({ page }) => {
    await withVideo(page, ZOO, { tags: ["", "  "] })
    await page.goto(`/v/${ZOO}`)
    await expect(heading(page)).toContainText("Me at the zoo")
    await expect(tagsRegion(page)).toHaveCount(0)
  })
})

test.describe("คอมเมนต์ปักหมุดจากเจ้าของช่อง", () => {
  const COMMENT = {
    text: "ขอบคุณที่ดูนะครับ\nลิงก์คอร์ส: https://example.com/course\n\nบรรทัดสุดท้าย",
    likes: 1520,
    publishedText: "2 years ago",
  }

  test("คลิปที่มีคอมเมนต์: แถวพับอยู่และยังไม่ขอข้อมูล · กางแล้วเห็น Skeleton → ข้อความคงการขึ้นบรรทัด ไม่มีลิงก์ · คัดลอกได้ตรงตัว", async ({
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
    const button = toggle(page, PINNED_TITLE)
    await expect(button).toHaveAttribute("aria-expanded", "false")
    await expect(page.getByRole("heading", { level: 2, name: PINNED_TITLE })).toBeVisible()
    expect(calls.count).toBe(0)

    await button.click()
    await expect(button).toHaveAttribute("aria-expanded", "true")
    await expect(pinnedRegion(page).getByRole("status")).toHaveText("กำลังโหลดคอมเมนต์ปักหมุด")
    await expect(pinnedRegion(page).locator('[data-slot="skeleton"]').first()).toBeVisible()
    release()

    const text = pinnedRegion(page).getByText(/^ขอบคุณที่ดูนะครับ/)
    await expect(text).toBeVisible()
    expect(await text.evaluate((el) => el.textContent)).toBe(COMMENT.text)
    await expect(text).toHaveCSS("white-space", "pre-line")
    await expect(pinnedRegion(page).getByRole("link")).toHaveCount(0)
    await expect(pinnedRegion(page).getByRole("img", { name: "ถูกใจ 1,520 ครั้ง" })).toHaveText("1.5 พัน")
    expect(calls.count).toBe(1)

    const copy = page.getByRole("button", { name: "คัดลอกคอมเมนต์ปักหมุด" })
    await expect(copy).toHaveText("คัดลอก")
    await copy.click()
    await expect(page.getByText("คัดลอกแล้ว")).toBeVisible()
    expect(await lastWrite(page)).toBe(COMMENT.text)

    // พับแล้วกางใหม่ใช้ผลเดิม ไม่ขอซ้ำ
    await button.click()
    await expect(text).toBeHidden()
    await button.click()
    await expect(text).toBeVisible()
    expect(calls.count).toBe(1)
  })

  test("ไม่มีคอมเมนต์ปักหมุด (null): ข้อความจาง และไม่มีปุ่มคัดลอก", async ({ page }) => {
    await withVideo(page, ZOO)
    await mockPinned(page, ZOO, (route) => route.fulfill({ json: { comment: null } }))
    await page.goto(`/v/${ZOO}`)
    await toggle(page, PINNED_TITLE).click()
    const none = pinnedRegion(page).getByText(NO_PINNED)
    await expect(none).toBeVisible()
    await expect(none).toHaveClass(/text-muted-foreground/)
    await expect(page.getByRole("button", { name: "คัดลอกคอมเมนต์ปักหมุด" })).toHaveCount(0)
  })

  test("คลิปที่ปิดคอมเมนต์หรือมี 0 คอมเมนต์: ไม่มีแถวคอมเมนต์ปักหมุดเลย", async ({ page }) => {
    await withVideo(page, ZOO, { stats: { ...STATS, comments: 0 } })
    await page.goto(`/v/${ZOO}`)
    await expect(page.getByRole("img", { name: "คอมเมนต์ 0 รายการ" })).toBeVisible()
    await expect(pinnedRegion(page)).toHaveCount(0)
  })

  test("ไม่รู้จำนวนคอมเมนต์ (ไม่มี stats): มีแถวคอมเมนต์ปักหมุด", async ({ page }) => {
    await withVideo(page, BBB)
    await page.goto(`/v/${BBB}`)
    await expect(toggle(page, PINNED_TITLE)).toBeVisible()
  })

  test("เน็ตหลุด: Alert ข้อความจาก backend + ลองใหม่ · กดแล้วได้คอมเมนต์", async ({ page }) => {
    await withVideo(page, ZOO)
    let fail = true
    const calls = await mockPinned(page, ZOO, (route) =>
      fail
        ? route.fulfill({ status: 502, json: envelope("E_NETWORK", "เชื่อมต่อยูทูปไม่ได้ ตรวจอินเทอร์เน็ตแล้วลองใหม่") })
        : route.fulfill({ json: { comment: { text: "คอมเมนต์จากเจ้าของช่อง" } } }),
    )
    await page.goto(`/v/${ZOO}`)
    await toggle(page, PINNED_TITLE).click()
    const alert = pinnedRegion(page).getByRole("alert")
    await expect(alert).toContainText("โหลดคอมเมนต์ปักหมุดไม่สำเร็จ")
    await expect(alert).toContainText("เชื่อมต่อยูทูปไม่ได้ ตรวจอินเทอร์เน็ตแล้วลองใหม่")
    fail = false
    await alert.getByRole("button", { name: "ลองใหม่" }).click()
    await expect(pinnedRegion(page).getByText("คอมเมนต์จากเจ้าของช่อง")).toBeVisible()
    expect(calls.count).toBe(2)
  })

  test("E_BOT_CHECK: Alert ไม่มีปุ่มลองใหม่ · พับแล้วกางใหม่ไม่ยิงซ้ำ", async ({ page }) => {
    await withVideo(page, ZOO)
    const calls = await mockPinned(page, ZOO, (route) =>
      route.fulfill({ status: 429, json: envelope("E_BOT_CHECK", "ยูทูปขอให้ยืนยันว่าไม่ใช่บอท รอสัก 10 นาทีแล้วค่อยลองใหม่") }),
    )
    await page.goto(`/v/${ZOO}`)
    const button = toggle(page, PINNED_TITLE)
    await button.click()
    const alert = pinnedRegion(page).getByRole("alert")
    await expect(alert).toContainText("ยูทูปขอให้ยืนยันว่าไม่ใช่บอท")
    await expect(alert.getByRole("button", { name: "ลองใหม่" })).toHaveCount(0)
    await button.click()
    await button.click()
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

test.describe("ช่วงที่คนดูซ้ำมากที่สุด", () => {
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
  })

  test("บรรทัด 'ช่วงที่คนดูซ้ำมากที่สุด: 00:00:20, 00:01:00' · กดเวลาแล้วภาพที่ใกล้ที่สุดถูกไฮไลต์ เลื่อนมาให้เห็น และได้โฟกัส", async ({
    page,
  }) => {
    await withVideo(page, THAI, { mostReplayed: SEGMENTS })
    await page.goto(`/v/${THAI}`)
    const section = page.getByRole("region", { name: "ภาพเฟรม" })
    await expect(section.getByText("ช่วงที่คนดูซ้ำมากที่สุด:")).toBeVisible()
    const times = section.getByRole("button", { name: /^ไปภาพเฟรมช่วง / })
    await expect(times).toHaveText(["00:00:20", "00:01:00"])
    await times.nth(1).click()
    await expect(page).toHaveURL(/[?&]at=60000(&|$)/)
    const highlighted = frameList(page).locator("[data-highlighted]")
    await expect(highlighted).toHaveCount(1)
    await expect(highlighted).toBeFocused()
    await expect(highlighted).toBeInViewport()
    // ภาพที่ใกล้ 60 วินาทีที่สุด (ภาพห่างกัน 4895 ms → 58740 ms = 00:00:58)
    await expect(highlighted.locator("img")).toHaveAttribute("alt", "ภาพเฟรมที่ 00:00:58")

    // กดเวลาเดิมซ้ำหลังโฟกัสไปที่อื่น ก็กลับมาที่ภาพเดิม
    await page.evaluate(() => window.scrollTo(0, 0))
    await times.nth(1).focus()
    await times.nth(1).click()
    await expect(highlighted).toBeFocused()
    await expect(highlighted).toBeInViewport()
  })

  test("คลิปที่ไม่มี heatmap: ไม่มีบรรทัดช่วงที่ดูซ้ำ และไม่มีป้ายบนภาพ", async ({ page }) => {
    await withVideo(page, THAI)
    await page.goto(`/v/${THAI}`)
    await expect(frameList(page).getByRole("listitem").first()).toBeVisible()
    await expect(page.getByText("ช่วงที่คนดูซ้ำมากที่สุด:")).toHaveCount(0)
    await expect(frameList(page).locator("[data-replayed]")).toHaveCount(0)
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

test.describe("หัวคลิปแบบกระชับ", () => {
  // กรณีหนักสุดของหัวคลิป: ตัวเลข หมวดหมู่ คำอธิบายยาว chapter แท็กหลายอัน และแถวคอมเมนต์ปักหมุด
  const FULL = {
    stats: STATS,
    categories: ["People & Blogs"],
    tags: Array.from({ length: 12 }, (_, i) => `แท็กทดสอบที่ ${i + 1}`),
    mostReplayed: [{ startMs: 5000, endMs: 9000 }],
  }

  test("จอ 360×800: chapter เริ่มแบบพับ · แถบแท็บอยู่ในจอแรก (ไม่เกิน 800 px) · กาง chapter ได้", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 800 })
    await withVideo(page, ZOO, FULL)
    await page.goto(`/v/${ZOO}`)
    await expect(heading(page)).toContainText("Me at the zoo")
    await expect(page.getByRole("img", { name: "ยอดดู 123,456 ครั้ง" })).toBeVisible()
    await expect(toggle(page, PINNED_TITLE)).toBeVisible()
    await expect(toggle(page, "แท็ก (12)")).toBeVisible()
    const chapters = toggle(page, "Chapter (3 ตอน)")
    await expect(chapters).toHaveAttribute("aria-expanded", "false")
    await expect(chapterRegion(page).locator("li")).toHaveCount(3)
    await expect(chapterRegion(page).locator("ol")).toBeHidden()

    const tabs = await page.getByRole("tablist", { name: TAB_LIST }).boundingBox()
    expect(tabs).not.toBeNull()
    expect((tabs?.y ?? 0) + (tabs?.height ?? 0)).toBeLessThanOrEqual(800)
    await expect(tab(page, "ภาพเฟรม")).toBeInViewport()

    // ทุกปุ่มในหัวคลิปสูงอย่างน้อย 44 px และหน้าไม่ล้นแนวนอน
    for (const name of [NOTE_BUTTON, "คัดลอกคำอธิบาย", "ดูทั้งหมด", PINNED_TITLE, "Chapter (3 ตอน)", "คัดลอก chapter", "แท็ก (12)", "คัดลอกแท็ก"]) {
      const box = await page.getByRole("button", { name, exact: true }).boundingBox()
      expect(box?.height ?? 0, name).toBeGreaterThanOrEqual(44)
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360)

    await chapters.click()
    await expect(chapters).toHaveAttribute("aria-expanded", "true")
    await expect(chapterRegion(page).getByRole("listitem")).toHaveText(["00:00:00Intro", "00:00:05The cool thing", "00:00:17End"])
  })

  test("จอกว้าง: chapter เริ่มแบบกาง (เห็นรายการเลย) พับได้จากหัวข้อ", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    await withVideo(page, ZOO, FULL)
    await page.goto(`/v/${ZOO}`)
    const chapters = toggle(page, "Chapter (3 ตอน)")
    await expect(chapters).toHaveAttribute("aria-expanded", "true")
    await expect(chapterRegion(page).getByRole("listitem")).toHaveCount(3)
    await expect(chapterRegion(page).getByRole("list")).toBeVisible()
    await chapters.click()
    await expect(chapterRegion(page).locator("ol")).toBeHidden()
    // ซ้าย: คำอธิบาย + คอมเมนต์ปักหมุด · ขวา: chapter + แท็ก
    const description = await page.getByRole("region", { name: "คำอธิบาย" }).boundingBox()
    const pinned = await pinnedRegion(page).boundingBox()
    const chapterBox = await chapterRegion(page).boundingBox()
    const tags = await tagsRegion(page).boundingBox()
    expect(Math.abs((pinned?.x ?? 0) - (description?.x ?? 1))).toBeLessThan(2)
    expect(Math.abs((tags?.x ?? 0) - (chapterBox?.x ?? 1))).toBeLessThan(2)
    expect(chapterBox?.x ?? 0).toBeGreaterThan((description?.x ?? 0) + (description?.width ?? 0))
  })

  test("คีย์บอร์ด: ชื่อคลิป → โน้ต → คัดลอกคำอธิบาย → ดูทั้งหมด → คอมเมนต์ปักหมุด → Chapter → คัดลอก chapter → แท็ก → คัดลอกแท็ก → แท็บภาพเฟรม", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    await withVideo(page, ZOO, FULL)
    await page.goto(`/v/${ZOO}`)
    await expect(toggle(page, "แท็ก (12)")).toBeVisible()
    await heading(page).focus()
    for (const name of [
      NOTE_BUTTON,
      "คัดลอกคำอธิบาย",
      "ดูทั้งหมด",
      PINNED_TITLE,
      "Chapter (3 ตอน)",
      "คัดลอก chapter",
      "แท็ก (12)",
      "คัดลอกแท็ก",
    ]) {
      await page.keyboard.press("Tab")
      await expect(page.getByRole("button", { name, exact: true })).toBeFocused()
    }
    await page.keyboard.press("Tab")
    await expect(tab(page, "ภาพเฟรม")).toBeFocused()
  })

  for (const scheme of ["dark", "light"] as const) {
    test(`หัวคลิปที่กางทุกกล่อง (แท็ก คอมเมนต์ปักหมุด) และภาพเฟรมที่มีป้ายไม่มีปัญหาระดับ serious/critical (${scheme})`, async ({
      page,
    }) => {
      await withVideo(page, THAI, { ...FULL, mostReplayed: [{ startMs: 0, endMs: 20_000 }] })
      await mockPinned(page, THAI, (route) =>
        route.fulfill({ json: { comment: { text: "คอมเมนต์ปักหมุด\nบรรทัดสอง", likes: 12 } } }),
      )
      await page.emulateMedia({ colorScheme: scheme })
      await page.goto(`/v/${THAI}`)
      await expect(page.locator("html")).toHaveClass(scheme === "dark" ? /dark/ : /light/)
      await toggle(page, "แท็ก (12)").click()
      await toggle(page, PINNED_TITLE).click()
      await expect(pinnedRegion(page).getByText(/บรรทัดสอง/)).toBeVisible()
      await expect(frameList(page).locator("[data-replayed]").first()).toBeVisible()
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
