/// <reference lib="dom" />
import AxeBuilder from "@axe-core/playwright"
import { expect, test, type Page } from "@playwright/test"

const BBB = "aqz-KE-bpKQ"
const ZOO = "jNQXAC9IVRw"
const UPCOMING = "UPCOMINGLV1"
const PRIVATE = "PRIVATEVID1"
const PRIVATE_MESSAGE = "คลิปนี้เป็นส่วนตัว เจ้าของต้องเปิดเป็นสาธารณะก่อน"
const BOT_MESSAGE = "ยูทูปขอให้ยืนยันว่าไม่ใช่บอท รอสัก 10 นาทีแล้วค่อยลองใหม่"
const NO_STORYBOARD_MESSAGE = "คลิปนี้ไม่มีภาพตัวอย่างแบบเร็ว ภาพคมจะใช้ได้ในเวอร์ชันถัดไป"
const FRAME_LIST = "รายการภาพเฟรม"
// ภาพเฟรมของ Big Buck Bunny ในชุดทดสอบ: แสดงครบทุกภาพตั้งแต่แรก (D7)
const FRAME_COUNT = 128
// ลิงก์เว็บอื่นยังเป็นแถวสีแดง (ข้อความธรรมดาที่ไม่มีลิงก์ถูกข้ามเงียบ ๆ ตั้งแต่ D1)
const NOT_YOUTUBE = "https://vimeo.com/123"
const MENU_ITEMS = ["คัดลอกภาพ", "โหลดภาพนี้", "คัดลอกเวลา", "คัดลอกลิงก์ช่วงนี้", "เปิดในยูทูปตรงเวลานี้", "เล่นจากตรงนี้"]

const frameSection = (page: Page) => page.getByRole("region", { name: "ภาพเฟรม" })
const frameItems = (page: Page) => page.getByRole("list", { name: FRAME_LIST }).getByRole("listitem")
const frameButton = (page: Page, time: string) => page.getByRole("button", { name: `ภาพเฟรมที่ ${time}` })

async function openBbb(page: Page) {
  await page.goto(`/v/${BBB}`)
  await expect(frameItems(page)).toHaveCount(FRAME_COUNT)
}

test.describe("W2 หัวคลิป", () => {
  test("แสดงปก ชื่อ ช่อง ความยาว วันที่เผยแพร่ และชื่อแท็บ · คลิปไม่มี chapter ไม่มีป้าย", async ({ page }) => {
    await page.goto(`/v/${BBB}`)
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Big Buck Bunny 60fps 4K")
    await expect(page.getByText("ช่อง Blender")).toBeVisible()
    // owner round 4: ความยาวและวันที่อยู่ในช่องตัวเลข (ป้ายเล็ก + ค่าใหญ่) ชื่อเต็มอยู่ใน aria-label และ title
    const duration = page.getByRole("img", { name: "ความยาว 10:35" })
    await expect(duration).toBeVisible()
    await expect(duration).toHaveText("ความยาว10:35")
    const published = page.getByRole("img", { name: "เผยแพร่ 10 พฤศจิกายน 2557" })
    await expect(published).toBeVisible()
    await expect(published).toHaveAttribute("title", "เผยแพร่ 10 พฤศจิกายน 2557")
    await expect(page.getByText(/\d+ ตอน/)).toHaveCount(0)
    await expect(page).toHaveTitle("Big Buck Bunny 60fps 4K - Official Blender Foundation Short Film · YT Toolkit")
  })

  test("คลิปที่มี chapter: จำนวนตอนอยู่ที่หัวข้อ 'Chapter (3 ตอน)' ในแท็บข้อมูลคลิป ไม่มีป้าย '3 ตอน' ซ้ำในแถวข้อมูล · โลโก้พากลับหน้าแรก", async ({
    page,
  }) => {
    await page.goto(`/v/${ZOO}?tab=info`)
    await expect(page.getByRole("heading", { level: 2, name: "Chapter (3 ตอน)" })).toBeVisible()
    // owner round 2: ป้าย "{n} ตอน" ในแถวข้อมูลถูกเอาออก (ซ้ำกับหัวข้อกล่อง chapter)
    await expect(page.getByText("3 ตอน", { exact: true })).toHaveCount(0)
    await expect(page.getByRole("banner").getByRole("link", { name: "YT Toolkit" })).toHaveAttribute("href", "/")
  })

  test("ระหว่างโหลดเห็น Skeleton ทั้งหัวคลิปและภาพเฟรม 6 ช่อง แล้วถูกแทนที่ด้วยข้อมูลจริง", async ({ page }) => {
    await page.route(`**/api/videos/${BBB}`, async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 500))
      await route.continue()
    })
    await page.goto(`/v/${BBB}`)
    await expect(page.getByText("กำลังโหลดข้อมูลคลิป")).toBeAttached()
    await expect(page.getByText("กำลังโหลดภาพเฟรม")).toBeAttached()
    await expect(page.locator('[data-slot="skeleton"].aspect-video')).toHaveCount(7)
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Big Buck Bunny")
    await expect(frameItems(page)).toHaveCount(FRAME_COUNT)
    await expect(page.locator('[data-slot="skeleton"]')).toHaveCount(0)
  })

  test("คลิปส่วนตัว: Alert ข้อความจาก backend + กลับหน้าแรก ไม่มีปุ่มลองใหม่ และไม่มีส่วนภาพเฟรม", async ({ page }) => {
    await page.goto(`/v/${PRIVATE}`)
    const alert = page.getByRole("alert")
    await expect(alert).toContainText("เปิดข้อมูลคลิปไม่สำเร็จ")
    await expect(alert).toContainText(PRIVATE_MESSAGE)
    await expect(alert.getByRole("button", { name: "ลองใหม่" })).toHaveCount(0)
    await expect(alert.getByRole("link", { name: "กลับหน้าแรก" })).toHaveAttribute("href", "/")
    await expect(page.getByRole("heading", { name: "ภาพเฟรม" })).toHaveCount(0)
  })

  test("E_BOT_CHECK: Alert ข้อความรอ 10 นาที ไม่มีปุ่มลองใหม่ (M2 ยังไม่มีคิวพัก) แต่กลับหน้าแรกได้", async ({ page }) => {
    await page.route(`**/api/videos/${BBB}`, (route) =>
      route.fulfill({
        status: 429,
        json: { error: { code: "E_BOT_CHECK", message: BOT_MESSAGE, detail: null } },
      }),
    )
    await page.goto(`/v/${BBB}`)
    const alert = page.getByRole("alert")
    await expect(alert).toContainText("เปิดข้อมูลคลิปไม่สำเร็จ")
    await expect(alert).toContainText(BOT_MESSAGE)
    await expect(alert.getByRole("button", { name: "ลองใหม่" })).toHaveCount(0)
    await expect(page.getByRole("button", { name: "ลองใหม่" })).toHaveCount(0)
    await expect(alert.getByRole("link", { name: "กลับหน้าแรก" })).toHaveAttribute("href", "/")
  })

  test("ไลฟ์ที่ยังไม่เริ่ม: ไม่มีปุ่มลองใหม่", async ({ page }) => {
    await page.goto(`/v/${UPCOMING}`)
    await expect(page.getByRole("alert")).toContainText("ยังถ่ายทอดสดอยู่")
    await expect(page.getByRole("button", { name: "ลองใหม่" })).toHaveCount(0)
  })

  test("เน็ตหลุด: มีปุ่มลองใหม่ กดแล้วโหลดสำเร็จ", async ({ page }) => {
    let fail = true
    await page.route(`**/api/videos/${BBB}`, (route) =>
      fail
        ? route.fulfill({
            status: 502,
            json: { error: { code: "E_NETWORK", message: "เน็ตหลุด ลองใหม่อีกครั้ง", detail: null } },
          })
        : route.continue(),
    )
    await page.goto(`/v/${BBB}`)
    await expect(page.getByRole("alert")).toContainText("เน็ตหลุด ลองใหม่อีกครั้ง")
    fail = false
    await page.getByRole("button", { name: "ลองใหม่" }).click()
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Big Buck Bunny")
    await expect(page.getByRole("alert")).toHaveCount(0)
  })
})

test.describe("W2 ลำดับการโหลดและความทนทาน", () => {
  test("ยังไม่ขอ storyboard จนกว่าข้อมูลคลิปจะมา", async ({ page }) => {
    const storyboardRequests: string[] = []
    page.on("request", (request) => {
      if (request.url().includes("/storyboard")) storyboardRequests.push(request.url())
    })
    await page.route(`**/api/videos/${BBB}`, async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 1200))
      await route.continue()
    })
    await page.goto(`/v/${BBB}`)
    await expect(page.getByText("กำลังโหลดข้อมูลคลิป")).toBeAttached()
    await page.waitForTimeout(700)
    expect(storyboardRequests).toEqual([])
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Big Buck Bunny")
    await expect(frameItems(page)).toHaveCount(FRAME_COUNT)
    expect(storyboardRequests.filter((url) => url.endsWith("/storyboard"))).toHaveLength(1)
  })

  test("รีเฟรชเบื้องหลังล้มเหลว แต่มีข้อมูลจากรายการผลของ W1 อยู่แล้ว → คงข้อมูลไว้ และแจ้งด้วย toast ไม่ใช่ Alert", async ({ page }) => {
    await page.goto("/")
    await page.getByRole("textbox").fill([`https://youtu.be/${BBB}`, NOT_YOUTUBE].join("\n"))
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    await expect(page.locator('section[aria-labelledby="results-title"] [role="listitem"]').first()).toContainText("Big Buck Bunny")
    await page.route(`**/api/videos/${BBB}`, (route) =>
      route.fulfill({
        status: 502,
        json: { error: { code: "E_NETWORK", message: "เน็ตหลุด ลองใหม่อีกครั้ง", detail: null } },
      }),
    )
    await page.getByRole("link", { name: /เปิดดู/ }).click()
    await expect(page.getByText("เน็ตหลุด ลองใหม่อีกครั้ง")).toBeVisible()
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Big Buck Bunny")
    await expect(page.locator('[data-slot="alert"]')).toHaveCount(0)
    await expect(frameItems(page)).toHaveCount(FRAME_COUNT)
  })

  test("หน้าพัง (ข้อมูลผิดรูป) แล้วเปลี่ยนไปคลิปอื่นในหน้าเดิม → กล่อง error ถูกล้าง แสดงคลิปใหม่ได้", async ({ page }) => {
    await page.route(`**/api/videos/${BBB}`, async (route) => {
      const response = await route.fetch()
      const body = await response.json()
      await route.fulfill({ response, json: { ...body, chapters: null } })
    })
    await page.goto(`/v/${BBB}`)
    await expect(page.getByRole("alert")).toBeVisible()
    await expect(page.getByRole("button", { name: "โหลดหน้าใหม่" })).toBeVisible()
    await page.evaluate((id) => {
      window.history.pushState({}, "", `/v/${id}`)
      window.dispatchEvent(new PopStateEvent("popstate"))
    }, ZOO)
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Me at the zoo")
    await expect(page.getByRole("alert")).toHaveCount(0)
  })
})

test.describe("W2 ภาพเฟรม", () => {
  test("D7: เห็นครบทั้ง 128 ภาพตั้งแต่แรก ไม่มีปุ่ม 'ดูทั้งหมด' หรือ 'ย่อ' · ภาพโหลดแบบ lazy", async ({ page }) => {
    await openBbb(page)
    await expect(page.getByRole("heading", { name: "ภาพเฟรม" })).toBeVisible()
    const first = frameItems(page).first().getByRole("img")
    await expect(first).toHaveAttribute("alt", "ภาพเฟรมที่ 00:00:00")
    await expect(first).toHaveAttribute("loading", "lazy")
    await expect(first).toHaveAttribute("width", "320")
    await expect(first).toHaveAttribute("height", "180")
    await expect(frameSection(page)).toBeVisible()
    await expect(frameSection(page).getByRole("button", { name: /ดูทั้งหมด/ })).toHaveCount(0)
    await expect(frameSection(page).getByRole("button", { name: "ย่อ" })).toHaveCount(0)
  })

  test("D7: ภาพสุดท้ายของคลิปยาว (00:10:3x) อยู่ในหน้าแล้วโดยไม่ต้องกดอะไร · ภาพที่อยู่ไกลจอใช้ content-visibility", async ({
    page,
  }) => {
    await page.goto(`/v/${BBB}`)
    await expect(frameItems(page)).toHaveCount(FRAME_COUNT)
    const last = frameItems(page).last().getByRole("img")
    await expect(last).toBeAttached()
    await expect(last).toHaveAttribute("alt", /ภาพเฟรมที่ 00:10:3\d/)
    await expect(last).toHaveAttribute("loading", "lazy")
    await expect(frameItems(page).last()).toHaveCSS("content-visibility", "auto")
  })

  test("ชี้เมาส์ที่ภาพ: ไม่มี hover card มีแค่วงขอบบาง ๆ กับเวลาบนภาพ", async ({ page }) => {
    await openBbb(page)
    await frameButton(page, "00:00:04").hover()
    const chip = page.getByRole("list", { name: FRAME_LIST }).getByText("00:00:04", { exact: true })
    await expect(chip).toBeVisible()
    await page.waitForTimeout(500)
    await expect(page.locator('[data-slot="hover-card-content"]')).toHaveCount(0)
    await expect(page.getByRole("dialog")).toHaveCount(0)
    await expect(frameButton(page, "00:00:04")).toHaveCSS("cursor", "zoom-in")
  })

  test("คีย์บอร์ด: Tab ถึงภาพเฟรมได้ เห็น timecode ตอนโฟกัส", async ({ page }) => {
    await openBbb(page)
    const first = frameButton(page, "00:00:00")
    // หัวคลิปมีปุ่มที่โฟกัสได้ก่อนแถบแท็บ (ปก โน้ต เปิดในยูทูป ฯลฯ)
    // เทสนี้ตรวจว่ากด Tab ไปถึงภาพเฟรมได้ ไม่ได้ล็อกจำนวนครั้ง จึงให้กดได้ถึง 40 ครั้ง
    for (let i = 0; i < 40 && !(await first.evaluate((el) => el === document.activeElement)); i++) {
      await page.keyboard.press("Tab")
    }
    await expect(first).toBeFocused()
    // ชิป timecode บนภาพ เห็นเฉพาะภาพที่โฟกัสอยู่
    const chip = (time: string) => page.getByRole("list", { name: FRAME_LIST }).getByText(time, { exact: true })
    await expect(chip("00:00:00")).toBeVisible()
    await expect(chip("00:00:04")).toBeHidden()
    // M3.5: ปุ่ม ▶ "เล่นจากตรงนี้" ที่มุมภาพไม่อยู่ในลำดับ Tab (ผู้ใช้คีย์บอร์ดใช้เมนู Shift+F10) แต่ยังมีชื่อให้โปรแกรมอ่านหน้าจอ
    // ภาพละ 1 จุดหยุด: Tab จากภาพแรกไปภาพถัดไปเลย
    const corner = page.getByRole("button", { name: "เล่นจากตรงนี้ 00:00:00", exact: true })
    await expect(corner).toHaveAttribute("tabindex", "-1")
    await page.keyboard.press("Tab")
    await expect(frameButton(page, "00:00:04")).toBeFocused()
    await expect(chip("00:00:04")).toBeVisible()
    await expect(chip("00:00:00")).toBeHidden()
  })

  test("คีย์บอร์ด: Shift+F10 และปุ่ม Menu เปิดเมนู มีห้ารายการ · Esc ปิดแล้วโฟกัสกลับที่ภาพ", async ({ page }) => {
    await openBbb(page)
    const frame = frameButton(page, "00:00:09")
    await frame.focus()
    await page.keyboard.press("Shift+F10")
    const menu = page.getByRole("menu")
    await expect(menu).toBeVisible()
    await expect(menu.getByRole("menuitem")).toHaveText(MENU_ITEMS)
    await page.keyboard.press("Escape")
    await expect(menu).toHaveCount(0)
    await expect(frame).toBeFocused()

    await page.keyboard.press("ContextMenu")
    await expect(menu).toBeVisible()
    await page.keyboard.press("Escape")
    await expect(menu).toHaveCount(0)
  })

  test("คีย์บอร์ด: เปิดเมนูแล้วเลือก 'คัดลอกเวลา' ด้วยลูกศร + Enter", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"])
    await openBbb(page)
    await frameButton(page, "00:00:04").focus()
    await page.keyboard.press("Shift+F10")
    await expect(page.getByRole("menu")).toBeVisible()
    await page.keyboard.press("ArrowDown")
    await page.keyboard.press("ArrowDown")
    await expect(page.getByRole("menuitem", { name: "คัดลอกเวลา" })).toBeFocused()
    await page.keyboard.press("Enter")
    await expect(page.getByText("คัดลอกแล้ว")).toBeVisible()
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe("00:00:04")
  })

  test("คลิกขวาภาพที่สอง (tMs 4961) → 'คัดลอกเวลา' ได้ 00:00:04 พอดีในคลิปบอร์ด และขึ้น toast", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"])
    await openBbb(page)
    await frameItems(page).nth(1).click({ button: "right" })
    await page.getByRole("menuitem", { name: "คัดลอกเวลา" }).click()
    await expect(page.getByText("คัดลอกแล้ว")).toBeVisible()
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe("00:00:04")
  })

  test("AC-FRAME-07: คัดลอกลิงก์ช่วงนี้ ที่ภาพที่สอง (tMs 4961) ได้ลิงก์ youtu.be?t=4 และขึ้น toast", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"])
    await openBbb(page)
    await frameItems(page).nth(1).click({ button: "right" })
    await page.getByRole("menuitem", { name: "คัดลอกลิงก์ช่วงนี้" }).click()
    await expect(page.getByText("คัดลอกแล้ว")).toBeVisible()
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(`https://youtu.be/${BBB}?t=4`)
  })

  test("AC-FRAME-07: เปิดเมนูด้วยคีย์บอร์ดแล้วเลือก คัดลอกลิงก์ช่วงนี้ ได้เหมือนกัน", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"])
    await openBbb(page)
    await frameButton(page, "00:00:09").focus()
    await page.keyboard.press("Shift+F10")
    await expect(page.getByRole("menuitem", { name: "คัดลอกภาพ" })).toBeFocused()
    for (let i = 0; i < 3; i++) await page.keyboard.press("ArrowDown")
    await expect(page.getByRole("menuitem", { name: "คัดลอกลิงก์ช่วงนี้" })).toBeFocused()
    await page.keyboard.press("Enter")
    await expect(page.getByText("คัดลอกแล้ว")).toBeVisible()
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(`https://youtu.be/${BBB}?t=9`)
  })

  /** จด window.open ทุกครั้ง (ไม่เปิดแท็บยูทูปจริงระหว่างทดสอบ) */
  async function recordWindowOpen(page: Page) {
    await page.addInitScript(() => {
      const opened: { url: string; target: string; features: string }[] = []
      Object.defineProperty(window, "__opened", { value: opened })
      window.open = (url?: string | URL, target?: string, features?: string) => {
        opened.push({ url: String(url), target: target ?? "", features: features ?? "" })
        return null
      }
    })
    return () => page.evaluate(() => (window as unknown as { __opened: { url: string; target: string; features: string }[] }).__opened)
  }

  test("คลิกขวาภาพที่สอง (tMs 4961) → 'เปิดในยูทูปตรงเวลานี้' เปิดหน้าคลิปที่ &t=4s ในแท็บใหม่ แบบ noopener", async ({ page }) => {
    const opened = await recordWindowOpen(page)
    await openBbb(page)
    await frameItems(page).nth(1).click({ button: "right" })
    await page.getByRole("menuitem", { name: "เปิดในยูทูปตรงเวลานี้" }).click()
    await expect.poll(opened).toHaveLength(1)
    const [call] = await opened()
    expect(call.url).toBe(`https://www.youtube.com/watch?v=${BBB}&t=4s`)
    expect(call.target).toBe("_blank")
    expect(call.features).toContain("noopener")
    await expect(page.getByRole("menu")).toHaveCount(0)
  })

  test("คีย์บอร์ด: Shift+F10 แล้วลูกศรลง 4 ครั้งถึง 'เปิดในยูทูปตรงเวลานี้' · Enter เปิดที่ &t=9s", async ({ page }) => {
    const opened = await recordWindowOpen(page)
    await openBbb(page)
    await frameButton(page, "00:00:09").focus()
    await page.keyboard.press("Shift+F10")
    await expect(page.getByRole("menuitem", { name: "คัดลอกภาพ" })).toBeFocused()
    for (let i = 0; i < 4; i++) await page.keyboard.press("ArrowDown")
    await expect(page.getByRole("menuitem", { name: "เปิดในยูทูปตรงเวลานี้" })).toBeFocused()
    await page.keyboard.press("Enter")
    await expect.poll(opened).toHaveLength(1)
    const [call] = await opened()
    expect(call.url).toBe(`https://www.youtube.com/watch?v=${BBB}&t=9s`)
    expect(call.target).toBe("_blank")
    expect(call.features).toContain("noopener")
  })

  test("คัดลอกลิงก์ไม่ได้ → toast error", async ({ page }) => {
    await openBbb(page)
    await page.evaluate(() => {
      Object.defineProperty(navigator.clipboard, "writeText", { value: () => Promise.reject(new Error("denied")) })
    })
    await frameItems(page).nth(1).click({ button: "right" })
    await page.getByRole("menuitem", { name: "คัดลอกลิงก์ช่วงนี้" }).click()
    await expect(page.getByText("คัดลอกไม่สำเร็จ ลองอีกครั้ง")).toBeVisible()
  })

  test("ภาพเฟรมบอกว่ากดแล้วเปิดกล่องภาพใหญ่ (aria-haspopup=dialog)", async ({ page }) => {
    await openBbb(page)
    await expect(frameButton(page, "00:00:09")).toHaveAttribute("aria-haspopup", "dialog")
  })

  for (const key of ["Shift+F10", "ContextMenu"]) {
    test(`เปิดเมนูด้วยคีย์บอร์ด (${key}) โฟกัสไปที่รายการแรกของเมนู`, async ({ page }) => {
      await openBbb(page)
      await frameButton(page, "00:00:09").focus()
      await page.keyboard.press(key)
      await expect(page.getByRole("menuitem", { name: "คัดลอกภาพ" })).toBeFocused()
      await page.keyboard.press("ArrowDown")
      await expect(page.getByRole("menuitem", { name: "โหลดภาพนี้" })).toBeFocused()
    })
  }

  test("โหลดภาพนี้ กดซ้ำระหว่างรอ ไม่ส่งคำขอซ้ำ", async ({ page }) => {
    await openBbb(page)
    const frame = frameButton(page, "00:00:09")
    let requests = 0
    await page.route("**/storyboard/f_*.jpg?*download=1", async (route) => {
      requests += 1
      await new Promise((resolve) => setTimeout(resolve, 800))
      await route.continue()
    })
    const downloading = page.waitForEvent("download")
    await frame.click({ button: "right" })
    await page.getByRole("menuitem", { name: "โหลดภาพนี้" }).click()
    await frame.click({ button: "right" })
    await page.getByRole("menuitem", { name: "โหลดภาพนี้" }).click({ force: true })
    await downloading
    await page.waitForTimeout(300)
    expect(requests).toBe(1)
  })

  test("คัดลอกไม่ได้ (เบราว์เซอร์ไม่ให้เขียนคลิปบอร์ด) → toast error", async ({ page }) => {
    await openBbb(page)
    await page.evaluate(() => {
      Object.defineProperty(navigator.clipboard, "writeText", { value: () => Promise.reject(new Error("denied")) })
    })
    await frameItems(page).nth(1).click({ button: "right" })
    await page.getByRole("menuitem", { name: "คัดลอกเวลา" }).click()
    await expect(page.getByText("คัดลอกไม่สำเร็จ ลองอีกครั้ง")).toBeVisible()
  })


  test("'โหลดภาพนี้' ได้ไฟล์ frame_00-00-00.jpg (เป็นภาพจริง ไม่ใช่ JSON)", async ({ page }) => {
    await openBbb(page)
    await frameItems(page).first().click({ button: "right" })
    const downloading = page.waitForEvent("download")
    await page.getByRole("menuitem", { name: "โหลดภาพนี้" }).click()
    const download = await downloading
    expect(download.suggestedFilename()).toBe("frame_00-00-00.jpg")
    const bytes = await download.createReadStream().then(async (stream) => {
      const chunks: Buffer[] = []
      for await (const chunk of stream) chunks.push(chunk as Buffer)
      return Buffer.concat(chunks)
    })
    expect(bytes.subarray(0, 3).toString("hex")).toBe("ffd8ff")
  })

  test("โหลดภาพรวมเฟรม โหลดได้ไฟล์ .jpg และ zip โหลดได้ไฟล์ .zip", async ({ page }) => {
    await openBbb(page)
    const sheet = page.waitForEvent("download")
    await page.getByRole("button", { name: "โหลดภาพรวมเฟรม" }).click()
    expect((await sheet).suggestedFilename()).toMatch(/\.jpg$/)

    const zip = page.waitForEvent("download")
    await page.getByRole("button", { name: "โหลดทั้งหมด (.zip)" }).click()
    const download = await zip
    expect(download.suggestedFilename()).toMatch(/\.zip$/)
    const bytes = await download.createReadStream().then(async (stream) => {
      const chunks: Buffer[] = []
      for await (const chunk of stream) chunks.push(chunk as Buffer)
      return Buffer.concat(chunks)
    })
    expect(bytes.subarray(0, 2).toString("latin1")).toBe("PK")
  })

  test("ภาพที่อยู่ไกลจอ (content-visibility) ยังโฟกัสด้วยคีย์บอร์ดและเปิดเมนูได้", async ({ page }) => {
    await openBbb(page)
    await expect(frameItems(page).first()).toHaveCSS("content-visibility", "auto")
    const last = page.getByRole("button", { name: /ภาพเฟรมที่ 00:10:3\d/ })
    await last.focus()
    await expect(last).toBeFocused()
    await page.keyboard.press("Shift+F10")
    await expect(page.getByRole("menuitem", { name: "คัดลอกภาพ" })).toBeFocused()
  })

  test("ปุ่มโหลดชุดใหญ่เป็นปุ่มรอง ไม่ใช่ปุ่มหลักสีเหลือง และหน้านี้ไม่มีปุ่มหลัก", async ({ page }) => {
    await openBbb(page)
    for (const name of ["โหลดภาพรวมเฟรม", "โหลดทั้งหมด (.zip)"]) {
      await expect(page.getByRole("button", { name })).toHaveClass(/bg-secondary/)
    }
    await expect(page.locator("main [data-slot=button].bg-primary")).toHaveCount(0)
  })

  test("โหลดชุดใหญ่ล้มเหลว: toast ข้อความไทยจาก envelope และไม่ได้ไฟล์ JSON", async ({ page }) => {
    await openBbb(page)
    await page.route("**/storyboard/frames.zip", (route) =>
      route.fulfill({
        status: 502,
        json: { error: { code: "E_NETWORK", message: "เน็ตหลุด ลองใหม่อีกครั้ง", detail: null } },
      }),
    )
    let downloads = 0
    page.on("download", () => (downloads += 1))
    await page.getByRole("button", { name: "โหลดทั้งหมด (.zip)" }).click()
    await expect(page.getByText("เน็ตหลุด ลองใหม่อีกครั้ง")).toBeVisible()
    await expect(page.getByRole("button", { name: "โหลดทั้งหมด (.zip)" })).toBeEnabled()
    expect(downloads).toBe(0)
  })

  test("โหลดชุดใหญ่: ขึ้น toast 'กำลังเตรียมไฟล์…' ระหว่างรอ และปุ่มปิดใช้งานกันกดซ้ำ", async ({ page }) => {
    await openBbb(page)
    await page.route("**/storyboard/contact-sheet.jpg", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 600))
      await route.continue()
    })
    const sheet = page.getByRole("button", { name: "โหลดภาพรวมเฟรม" })
    const downloading = page.waitForEvent("download")
    await sheet.click()
    await expect(page.getByText("กำลังเตรียมไฟล์…")).toBeVisible()
    await expect(sheet).toHaveAttribute("aria-disabled", "true")
    await expect(sheet).toHaveCSS("opacity", "0.5")
    await downloading
    await expect(sheet).not.toHaveAttribute("aria-disabled", "true")
  })

  test("คลิปที่ไม่มี storyboard: Empty พร้อมปุ่ม 'ขอภาพคม' ที่ปิดอยู่ และ tooltip", async ({ page }) => {
    await page.goto(`/v/${ZOO}`)
    await expect(page.getByText(NO_STORYBOARD_MESSAGE)).toBeVisible()
    const button = page.getByRole("button", { name: "ขอภาพคม" })
    await expect(button).toBeDisabled()
    // ปุ่มที่ปิดใช้งานต้องดูจางลง (aria-disabled ไม่ได้ทำให้สไตล์ disabled: ทำงาน)
    await expect(button).toHaveCSS("opacity", "0.5")
    await expect(button).toHaveCSS("cursor", "not-allowed")
    await button.hover()
    await expect(page.locator('[data-slot="tooltip-content"]')).toHaveText("เปิดใช้ในเวอร์ชันถัดไป")
    await expect(page.getByRole("button", { name: "โหลดภาพรวมเฟรม" })).toHaveCount(0)
  })

  test("ภาพเฟรมโหลดไม่ได้: Alert พร้อมลองใหม่ (หัวคลิปยังอยู่)", async ({ page }) => {
    let fail = true
    await page.route(`**/api/videos/${BBB}/storyboard`, (route) =>
      fail
        ? route.fulfill({
            status: 502,
            json: { error: { code: "E_NETWORK", message: "เน็ตหลุด ลองใหม่อีกครั้ง", detail: null } },
          })
        : route.continue(),
    )
    await page.goto(`/v/${BBB}`)
    const alert = page.getByRole("alert")
    await expect(alert).toContainText("โหลดภาพเฟรมไม่สำเร็จ")
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Big Buck Bunny")
    fail = false
    await alert.getByRole("button", { name: "ลองใหม่" }).click()
    await expect(frameItems(page)).toHaveCount(FRAME_COUNT)
  })
})

test.describe("W2 จอแคบ", () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test("grid 3 คอลัมน์ เห็นครบทุกภาพ ไม่ต้องกดดูทั้งหมด", async ({ page }) => {
    await page.goto(`/v/${BBB}`)
    await expect(frameItems(page).first()).toBeVisible()
    const columns = await page
      .getByRole("list", { name: FRAME_LIST })
      .evaluate((el) => getComputedStyle(el).gridTemplateColumns.split(" ").length)
    expect(columns).toBe(3)
    await expect(frameItems(page).locator("visible=true")).toHaveCount(FRAME_COUNT)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await expect(frameSection(page)).toBeVisible()
    await expect(frameSection(page).getByRole("button", { name: /ดูทั้งหมด/ })).toHaveCount(0)
  })
})

test.describe("การเข้าถึง (axe)", () => {
  for (const scheme of ["dark", "light"] as const) {
    test(`หน้าแรกไม่มีปัญหาระดับ serious/critical (${scheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme })
      await page.goto("/")
      await expect(page.getByRole("button", { name: "วิเคราะห์" })).toBeVisible()
      await expect(page.locator("html")).toHaveClass(scheme === "dark" ? /dark/ : /light/)
      expect(await seriousViolations(page)).toEqual([])
    })

    test(`หน้าผลลัพธ์ W2 (ภาพเฟรมครบทุกภาพ) ไม่มีปัญหาระดับ serious/critical (${scheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme })
      await page.goto(`/v/${BBB}`)
      await expect(frameItems(page)).toHaveCount(FRAME_COUNT)
      await expect(page.locator("html")).toHaveClass(scheme === "dark" ? /dark/ : /light/)
      expect(await seriousViolations(page)).toEqual([])
    })
  }

  test("หน้าผลลัพธ์ W2 ตอนเมนูเปิดอยู่ และตอนไม่มี storyboard ก็ไม่มีปัญหา", async ({ page }) => {
    await openBbb(page)
    await frameButton(page, "00:00:04").focus()
    await page.keyboard.press("Shift+F10")
    await expect(page.getByRole("menu")).toBeVisible()
    expect(await seriousViolations(page)).toEqual([])
    await page.keyboard.press("Escape")

    await page.goto(`/v/${ZOO}`)
    await expect(page.getByRole("button", { name: "ขอภาพคม" })).toBeVisible()
    expect(await seriousViolations(page)).toEqual([])

    await page.goto(`/v/${PRIVATE}`)
    await expect(page.getByRole("alert")).toBeVisible()
    expect(await seriousViolations(page)).toEqual([])
  })
})

async function seriousViolations(page: Page) {
  const results = await new AxeBuilder({ page }).analyze()
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.map((n) => n.target.join(" ")).slice(0, 5) }))
}

const lightbox = (page: Page) => page.getByRole("dialog")
const lightboxImage = (page: Page) => lightbox(page).locator("img")
const frameSrc = (page: Page, time: string) => frameButton(page, time).locator("img").getAttribute("src")

test.describe("W2 ภาพใหญ่ (lightbox)", () => {
  test("คลิกภาพ → เห็นภาพเดียวกันขนาดใหญ่บนพื้นมืด ไม่มีปุ่ม ไม่มีคำบรรยาย · ขยายไม่เกิน 2 เท่า", async ({ page }) => {
    await openBbb(page)
    // เปิดกล่องแล้วส่วนอื่นของหน้าถูกซ่อนจากโปรแกรมอ่านหน้าจอ จึงอ่าน src ของภาพเฟรมไว้ก่อน
    const src = (await frameSrc(page, "00:00:04"))!
    await frameButton(page, "00:00:04").click()
    await expect(lightbox(page)).toBeVisible()
    await expect(lightbox(page)).toHaveAttribute("aria-label", "ภาพเฟรมที่ 00:00:04")
    await expect(lightboxImage(page)).toHaveAttribute("src", src)
    await expect(lightbox(page).getByRole("button")).toHaveCount(0)
    await expect.poll(() => lightboxImage(page).evaluate((el) => (el as HTMLImageElement).naturalWidth)).toBe(320)
    // จอ 1280×720: 90vw = 1152, 85vh ตามสัดส่วน = 1088 → ติดเพดาน 2 เท่า = 640
    // รอแอนิเมชันขยายตอนเปิดจบก่อนวัด
    const size = async () => {
      const box = (await lightboxImage(page).boundingBox())!
      return [Math.round(box.width), Math.round(box.height)]
    }
    await expect.poll(size).toEqual([640, 360])
  })

  test("ภาพเล็ก (160×90) ที่ยังโหลดไม่เสร็จ: ซ่อนไว้ก่อน ไม่แวบขึ้นมาใหญ่ตามขนาดเดา · โหลดแล้วได้ 2 เท่า = 320 px", async ({
    page,
  }) => {
    await page.goto("/")
    // ภาพ PNG 160×90 วาดจาก canvas ในหน้า (ภาพเฟรมจริงของชุดทดสอบเป็น 320×180)
    const small = await page.evaluate(() => {
      const canvas = document.createElement("canvas")
      canvas.width = 160
      canvas.height = 90
      const context = canvas.getContext("2d")!
      context.fillStyle = "#3a7"
      context.fillRect(0, 0, 160, 90)
      return canvas.toDataURL("image/png").split(",")[1]
    })
    let release = () => {}
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    await page.route("**/api/cache/**", async (route) => {
      await gate
      await route.fulfill({ contentType: "image/png", body: Buffer.from(small, "base64") })
    })
    await openBbb(page)
    await frameButton(page, "00:00:04").click()
    await expect(lightbox(page)).toHaveAttribute("aria-label", "ภาพเฟรมที่ 00:00:04")
    await expect(lightboxImage(page)).toHaveCSS("visibility", "hidden")
    release()
    await expect(lightboxImage(page)).toHaveCSS("visibility", "visible")
    await expect.poll(async () => Math.round((await lightboxImage(page).boundingBox())!.width)).toBe(320)
    // ภาพถัดไปใช้ขนาดเดิมทันที ไม่ต้องซ่อนอีก
    await page.keyboard.press("ArrowRight")
    await expect(lightbox(page)).toHaveAttribute("aria-label", "ภาพเฟรมที่ 00:00:09")
    await expect(lightboxImage(page)).toHaveCSS("visibility", "visible")
    await expect.poll(async () => Math.round((await lightboxImage(page).boundingBox())!.width)).toBe(320)
  })

  test("จอเตี้ย: ภาพหดให้อยู่ในกรอบ 85vh", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 400 })
    await openBbb(page)
    await frameButton(page, "00:00:04").click()
    await expect.poll(() => lightboxImage(page).evaluate((el) => (el as HTMLImageElement).naturalWidth)).toBe(320)
    const box = (await lightboxImage(page).boundingBox())!
    expect(box.height).toBeLessThanOrEqual(400 * 0.85 + 1)
  })

  test("Esc ปิด แล้วโฟกัสกลับที่ภาพเฟรม", async ({ page }) => {
    await openBbb(page)
    await frameButton(page, "00:00:09").click()
    await expect(lightbox(page)).toBeVisible()
    await page.keyboard.press("Escape")
    await expect(lightbox(page)).toHaveCount(0)
    await expect(frameButton(page, "00:00:09")).toBeFocused()
  })

  test("คลิกพื้นหลังมืดปิด", async ({ page }) => {
    await openBbb(page)
    await frameButton(page, "00:00:09").click()
    await expect(lightbox(page)).toBeVisible()
    await page.mouse.click(20, 700)
    await expect(lightbox(page)).toHaveCount(0)
    await expect(frameButton(page, "00:00:09")).toBeFocused()
  })

  test("คลิกที่ภาพก็ปิด", async ({ page }) => {
    await openBbb(page)
    await frameButton(page, "00:00:09").click()
    await lightboxImage(page).click()
    await expect(lightbox(page)).toHaveCount(0)
    await expect(frameButton(page, "00:00:09")).toBeFocused()
  })

  test("←/→ เปลี่ยนภาพ ชื่อกล่อง และเวลาที่ประกาศ · สุดทางแล้วไม่วน · ปิดแล้วโฟกัสอยู่ที่ภาพที่ดูล่าสุด", async ({ page }) => {
    await openBbb(page)
    const src = (await frameSrc(page, "00:00:09"))!
    await frameButton(page, "00:00:00").click()
    await expect(lightbox(page)).toHaveAttribute("aria-label", "ภาพเฟรมที่ 00:00:00")
    await page.keyboard.press("ArrowLeft")
    await expect(lightbox(page)).toHaveAttribute("aria-label", "ภาพเฟรมที่ 00:00:00")
    await page.keyboard.press("ArrowRight")
    await page.keyboard.press("ArrowRight")
    await expect(lightbox(page)).toHaveAttribute("aria-label", "ภาพเฟรมที่ 00:00:09")
    await expect(lightboxImage(page)).toHaveAttribute("src", src)
    await expect(lightbox(page).locator("[aria-live]")).toHaveText("00:00:09")
    await page.keyboard.press("ArrowLeft")
    await expect(lightbox(page)).toHaveAttribute("aria-label", "ภาพเฟรมที่ 00:00:04")
    await page.keyboard.press("Escape")
    await expect(frameButton(page, "00:00:04")).toBeFocused()
  })

  test("→ ไปภาพถัดไปที่ต้องเลื่อนจอถึงจะเห็นได้ · ปิดแล้วโฟกัสอยู่ที่ภาพนั้น", async ({ page }) => {
    await openBbb(page)
    await frameButton(page, "00:00:54").click()
    await page.keyboard.press("ArrowRight")
    await expect(lightbox(page)).toHaveAttribute("aria-label", /ภาพเฟรมที่ 00:00:59/)
    await page.keyboard.press("Escape")
    await expect(frameButton(page, "00:00:59")).toBeFocused()
  })

  for (const key of ["Enter", "Space"]) {
    test(`คีย์บอร์ด: ${key} ที่ภาพเฟรมเปิดภาพใหญ่`, async ({ page }) => {
      await openBbb(page)
      await frameButton(page, "00:00:04").focus()
      await page.keyboard.press(key)
      await expect(lightbox(page)).toHaveAttribute("aria-label", "ภาพเฟรมที่ 00:00:04")
      await page.keyboard.press("Escape")
      await expect(frameButton(page, "00:00:04")).toBeFocused()
    })
  }

  test("คลิกขวายังเปิดเมนูเหมือนเดิม (ไม่เปิดภาพใหญ่)", async ({ page }) => {
    await openBbb(page)
    await frameItems(page).nth(2).click({ button: "right" })
    await expect(page.getByRole("menu").getByRole("menuitem")).toHaveText(MENU_ITEMS)
    await expect(lightbox(page)).toHaveCount(0)
  })
})

test.describe("W2 คัดลอกภาพ", () => {
  test("'คัดลอกภาพ' → คลิปบอร์ดมีภาพ PNG ขนาดเท่าภาพเฟรม และขึ้น toast 'คัดลอกภาพแล้ว'", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"])
    await openBbb(page)
    await frameItems(page).nth(1).click({ button: "right" })
    await page.getByRole("menuitem", { name: "คัดลอกภาพ" }).click()
    await expect(page.getByText("คัดลอกภาพแล้ว")).toBeVisible()
    const found = await page.evaluate(async () => {
      const items = await navigator.clipboard.read()
      const item = items.find((entry) => entry.types.includes("image/png"))
      if (!item) return null
      const bitmap = await createImageBitmap(await item.getType("image/png"))
      return { width: bitmap.width, height: bitmap.height }
    })
    expect(found).toEqual({ width: 320, height: 180 })
  })

  test("คัดลอกภาพไม่ได้ (ถูกปฏิเสธ) → toast แนะนำให้ใช้ โหลดภาพนี้ แทน", async ({ page }) => {
    await openBbb(page)
    await page.evaluate(() => {
      Object.defineProperty(navigator.clipboard, "write", { value: () => Promise.reject(new Error("denied")) })
    })
    await frameItems(page).nth(1).click({ button: "right" })
    await page.getByRole("menuitem", { name: "คัดลอกภาพ" }).click()
    await expect(page.getByText("คัดลอกภาพไม่สำเร็จ ลองใช้ โหลดภาพนี้ แทน")).toBeVisible()
  })

  test("เบราว์เซอร์ไม่รองรับการคัดลอกภาพ → toast แนะนำเหมือนกัน", async ({ page }) => {
    await openBbb(page)
    await page.evaluate(() => {
      Object.defineProperty(window, "ClipboardItem", { value: undefined, configurable: true })
    })
    await frameItems(page).nth(1).click({ button: "right" })
    await page.getByRole("menuitem", { name: "คัดลอกภาพ" }).click()
    await expect(page.getByText("คัดลอกภาพไม่สำเร็จ ลองใช้ โหลดภาพนี้ แทน")).toBeVisible()
  })
})

const crumbs = (page: Page) => page.getByRole("navigation", { name: "ตำแหน่งของหน้านี้" })
// รหัสคลิปปลอม 11 ตัว (ดึงชื่อไม่ได้ก็ไม่เป็นไร เทสนี้ดูแค่รายการ)
const clipLines = (n: number) => Array.from({ length: n }, (_, i) => `https://youtu.be/vid${String(i).padStart(8, "0")}`)

test.describe("W2 breadcrumb และเมนูบนหัว", () => {
  test("เปิดตรง ๆ: หน้าแรก › ชื่อคลิป · ขั้นสุดท้ายเป็นหน้านี้ (ไม่ใช่ลิงก์) · ไม่มี 'รายการที่วาง'", async ({ page }) => {
    await page.goto(`/v/${BBB}`)
    const nav = crumbs(page)
    await expect(nav.locator('[data-slot="breadcrumb-item"]')).toHaveText(["หน้าแรก", /^Big Buck Bunny 60fps 4K/])
    await expect(nav.getByRole("link")).toHaveCount(1)
    await expect(nav.getByRole("link", { name: "หน้าแรก" })).toHaveAttribute("href", "/")
    await expect(nav.locator('[aria-current="page"]')).toContainText("Big Buck Bunny")
    await expect(nav.getByText(/รายการที่วาง/)).toHaveCount(0)
  })

  test("ขั้น breadcrumb กดง่าย: สูงอย่างน้อย 32 px และมีวงโฟกัสเมื่อกด Tab", async ({ page }) => {
    await page.goto(`/v/${BBB}`)
    const home = crumbs(page).getByRole("link", { name: "หน้าแรก" })
    expect((await home.boundingBox())!.height).toBeGreaterThanOrEqual(32)
    await home.focus()
    await page.keyboard.press("Shift+Tab")
    await page.keyboard.press("Tab")
    await expect(home).toBeFocused()
    await expect(home).not.toHaveCSS("box-shadow", "none")
  })

  test("คลิปเปิดไม่ได้: ขั้นสุดท้ายเป็นรหัสคลิป", async ({ page }) => {
    await page.goto(`/v/${PRIVATE}`)
    await expect(crumbs(page).locator('[aria-current="page"]')).toHaveText(PRIVATE)
  })

  test("เมนูบนหัว: โลโก้เป็นลิงก์ใหญ่ ≥ 44 px · 'หน้าแรก' กับ 'ตั้งค่า' บอกหน้าที่อยู่ด้วย aria-current", async ({ page }) => {
    await page.goto("/")
    const header = page.getByRole("banner")
    const logo = header.getByRole("link", { name: "YT Toolkit" })
    expect((await logo.boundingBox())!.height).toBeGreaterThanOrEqual(44)
    const menu = header.getByRole("navigation", { name: "เมนูหลัก" })
    const home = menu.getByRole("link", { name: "หน้าแรก" })
    const settings = menu.getByRole("link", { name: "ตั้งค่า" })
    expect((await home.boundingBox())!.height).toBeGreaterThanOrEqual(44)
    await expect(home).toHaveAttribute("aria-current", "page")
    await expect(settings).not.toHaveAttribute("aria-current", "page")

    await page.goto(`/v/${BBB}`)
    await expect(home).not.toHaveAttribute("aria-current", "page")
    await home.click()
    await expect(page).toHaveURL(/\/$/)

    await settings.click()
    await expect(settings).toHaveAttribute("aria-current", "page")
    await page.getByRole("tab", { name: "เกี่ยวกับ" }).click()
    await expect(page).toHaveURL(/\/settings\/about$/)
    await expect(settings).toHaveAttribute("aria-current", "page")
    // หน้าตั้งค่าไม่มี breadcrumb (เมนูบนหัวบอกอยู่แล้วว่าอยู่หน้าไหน)
    await expect(crumbs(page)).toHaveCount(0)
  })

  test("เปิดหน้าคลิปแล้วเริ่มที่บนสุดของหน้าเสมอ", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 500 })
    await page.goto("/")
    await page.getByRole("textbox").fill(clipLines(12).join("\n"))
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    const last = page.locator('section[aria-labelledby="results-title"] [role="listitem"]').last()
    await last.scrollIntoViewIfNeeded()
    expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(200)
    await last.getByRole("link", { name: /เปิดดู/ }).click()
    await expect(page).toHaveURL(/\/v\//)
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0)
  })
})

test.describe("W2 วางลิงก์ที่หน้าคลิป", () => {
  test.beforeEach(async ({ context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"])
  })

  async function pasteOnPage(page: Page, text: string) {
    await page.evaluate((value) => navigator.clipboard.writeText(value), text)
    await page.locator("body").click({ position: { x: 5, y: 400 } })
    await page.keyboard.press("Control+V")
  }

  test("วางลิงก์คลิปเดียว → ไปหน้าคลิปนั้น", async ({ page }) => {
    await page.goto(`/v/${BBB}`)
    await expect(frameItems(page)).toHaveCount(FRAME_COUNT)
    await pasteOnPage(page, `https://youtu.be/${ZOO}`)
    await expect(page).toHaveURL(new RegExp(`/v/${ZOO}$`))
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Me at the zoo")
  })

  test("วางหลายลิงก์ → กลับหน้าแรกพร้อมรายการผลและข้อความที่วาง", async ({ page }) => {
    await page.goto(`/v/${BBB}`)
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Big Buck Bunny")
    const text = [`https://youtu.be/${ZOO}`, NOT_YOUTUBE].join("\n")
    await pasteOnPage(page, text)
    await expect(page).toHaveURL(/\/$/)
    await expect(page.locator('section[aria-labelledby="results-title"] [role="listitem"]')).toHaveCount(2)
    await expect(page.getByRole("textbox")).toHaveValue(text)
  })

  test("วางลิงก์ที่เป็นทั้งคลิปและเพลย์ลิสต์ → กล่องถามขึ้นที่หน้าคลิป · 'คลิปนี้' ไปคลิปนั้น", async ({ page }) => {
    await page.goto(`/v/${BBB}`)
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Big Buck Bunny")
    await pasteOnPage(page, `https://www.youtube.com/watch?v=${ZOO}&list=PLfakeplaylist250`)
    const dialog = page.getByRole("dialog")
    await expect(dialog).toContainText("ลิงก์นี้อยู่ในเพลย์ลิสต์")
    await dialog.getByRole("button", { name: "คลิปนี้" }).click()
    await expect(page).toHaveURL(new RegExp(`/v/${ZOO}$`))
  })

  test("วางข้อความที่ไม่ใช่ลิงก์ยูทูป → ไม่มีอะไรเกิดขึ้น", async ({ page }) => {
    let calls = 0
    await page.route("**/api/resolve", (route) => {
      calls += 1
      return route.continue()
    })
    await page.goto(`/v/${BBB}`)
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Big Buck Bunny")
    await pasteOnPage(page, "ข้อความธรรมดา")
    await page.waitForTimeout(400)
    expect(calls).toBe(0)
    await expect(page).toHaveURL(new RegExp(`/v/${BBB}$`))
  })

  test("วิเคราะห์ไม่สำเร็จ → toast แจ้ง (หน้าคลิปไม่มีช่องให้แสดงข้อความ)", async ({ page }) => {
    await page.route("**/api/resolve", (route) => route.abort())
    await page.goto(`/v/${BBB}`)
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Big Buck Bunny")
    await pasteOnPage(page, `https://youtu.be/${ZOO}`)
    await expect(page.getByText(/วิเคราะห์ลิงก์ไม่สำเร็จ/)).toBeVisible()
    await expect(page).toHaveURL(new RegExp(`/v/${BBB}$`))
  })
})

test.describe("การเข้าถึงตอนเปิดภาพใหญ่ (axe)", () => {
  for (const scheme of ["dark", "light"] as const) {
    test(`ภาพใหญ่เปิดอยู่ ไม่มีปัญหาระดับ serious/critical (${scheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme })
      await openBbb(page)
      await frameButton(page, "00:00:04").click()
      await expect(lightbox(page)).toBeVisible()
      await expect.poll(() => lightboxImage(page).evaluate((el) => (el as HTMLImageElement).complete)).toBe(true)
      expect(await seriousViolations(page)).toEqual([])
    })
  }
})

test.describe("W2 บอกวิธีใช้ภาพเฟรม", () => {
  test("มีคำแนะนำใต้หัว 'ภาพเฟรม' ว่าคลิกดูใหญ่ และคลิกขวา/Shift+F10 เพื่อคัดลอกหรือโหลด", async ({ page }) => {
    await openBbb(page)
    await expect(
      page.getByText("คลิกภาพเพื่อดูภาพใหญ่ · กด ▶ ที่มุมภาพเพื่อเล่นคลิปจากตรงนั้น · คลิกขวาหรือกด Shift+F10 เพื่อคัดลอก โหลดภาพ หรือเล่นจากตรงนี้"),
    ).toBeVisible()
  })

  test("คลิปที่ไม่มีภาพเฟรม ไม่มีคำแนะนำนี้", async ({ page }) => {
    await page.goto(`/v/${ZOO}`)
    await expect(page.getByText(NO_STORYBOARD_MESSAGE)).toBeVisible()
    await expect(page.getByText(/คลิกภาพเพื่อดูภาพใหญ่/)).toHaveCount(0)
  })

  test("ชี้ที่ปุ่ม โหลดภาพรวมเฟรม เห็นคำอธิบายภาษาไทย", async ({ page }) => {
    await openBbb(page)
    await page.getByRole("button", { name: "โหลดภาพรวมเฟรม" }).hover()
    await expect(page.locator('[data-slot="tooltip-content"]')).toHaveText("ภาพเดียวที่รวมทุกเฟรม พร้อมเวลาใต้แต่ละภาพ")
  })
})
