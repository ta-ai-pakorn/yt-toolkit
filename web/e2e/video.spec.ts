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
const MENU_ITEMS = ["โหลดภาพนี้", "คัดลอกเวลา", "คัดลอกลิงก์ช่วงนี้"]

const frameItems = (page: Page) => page.getByRole("list", { name: FRAME_LIST }).getByRole("listitem")
const frameButton = (page: Page, time: string) => page.getByRole("button", { name: `ภาพเฟรมที่ ${time}` })

async function openBbb(page: Page) {
  await page.goto(`/v/${BBB}`)
  await expect(frameItems(page)).toHaveCount(12)
}

test.describe("W2 หัวคลิป", () => {
  test("แสดงปก ชื่อ ช่อง ความยาว วันที่เผยแพร่ และชื่อแท็บ · คลิปไม่มี chapter ไม่มีป้าย", async ({ page }) => {
    await page.goto(`/v/${BBB}`)
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Big Buck Bunny 60fps 4K")
    await expect(page.getByText("ช่อง Blender")).toBeVisible()
    await expect(page.getByText("ความยาว 10:35")).toBeVisible()
    await expect(page.getByText("เผยแพร่ 10 พฤศจิกายน 2557")).toBeVisible()
    await expect(page.getByText(/\d+ ตอน/)).toHaveCount(0)
    await expect(page).toHaveTitle("Big Buck Bunny 60fps 4K - Official Blender Foundation Short Film · YT Toolkit")
  })

  test("คลิปที่มี chapter แสดงป้าย '3 ตอน' และโลโก้พากลับหน้าแรก", async ({ page }) => {
    await page.goto(`/v/${ZOO}`)
    await expect(page.getByText("3 ตอน")).toBeVisible()
    await expect(page.getByRole("link", { name: "หน้าแรก" })).toHaveAttribute("href", "/")
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
    await expect(frameItems(page)).toHaveCount(12)
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
    await expect(frameItems(page)).toHaveCount(12)
    expect(storyboardRequests.filter((url) => url.endsWith("/storyboard"))).toHaveLength(1)
  })

  test("รีเฟรชเบื้องหลังล้มเหลว แต่มีข้อมูลจากรายการผลของ W1 อยู่แล้ว → คงข้อมูลไว้ และแจ้งด้วย toast ไม่ใช่ Alert", async ({ page }) => {
    await page.goto("/")
    await page.getByRole("textbox").fill([`https://youtu.be/${BBB}`, "ไม่ใช่ลิงก์"].join("\n"))
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    await expect(page.getByRole("listitem").first()).toContainText("Big Buck Bunny")
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
    await expect(frameItems(page)).toHaveCount(12)
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
  test("เห็น 12 ภาพก่อน · 'ดูทั้งหมด (128)' แสดงครบ 128 · 'ย่อ' กลับเป็น 12", async ({ page }) => {
    await openBbb(page)
    await expect(page.getByRole("heading", { name: "ภาพเฟรม" })).toBeVisible()
    const first = frameItems(page).first().getByRole("img")
    await expect(first).toHaveAttribute("alt", "ภาพเฟรมที่ 00:00:00")
    await expect(first).toHaveAttribute("loading", "lazy")
    await expect(first).toHaveAttribute("width", "320")
    await expect(first).toHaveAttribute("height", "180")

    await page.getByRole("button", { name: "ดูทั้งหมด (128)" }).click()
    await expect(frameItems(page)).toHaveCount(128)
    await expect(page.getByRole("button", { name: "ย่อ" })).toBeVisible()
    await page.getByRole("button", { name: "ย่อ" }).click()
    await expect(frameItems(page)).toHaveCount(12)
  })

  test("ชี้เมาส์ที่ภาพ: เห็นภาพขยาย 1.5 เท่า พร้อม timecode", async ({ page }) => {
    await openBbb(page)
    await frameButton(page, "00:00:04").hover()
    const card = page.locator('[data-slot="hover-card-content"]')
    await expect(card).toContainText("00:00:04")
    const image = card.locator("img")
    await expect.poll(() => image.evaluate((el) => (el as HTMLImageElement).naturalWidth)).toBeGreaterThan(0)
    const box = await image.boundingBox()
    expect(Math.round(box!.width)).toBeGreaterThanOrEqual(460)
    expect(Math.round(box!.width)).toBeLessThanOrEqual(480)
  })

  test("คีย์บอร์ด: Tab ถึงภาพเฟรมได้ เห็น timecode ตอนโฟกัส", async ({ page }) => {
    await openBbb(page)
    const first = frameButton(page, "00:00:00")
    for (let i = 0; i < 10 && !(await first.evaluate((el) => el === document.activeElement)); i++) {
      await page.keyboard.press("Tab")
    }
    await expect(first).toBeFocused()
    await expect(page.locator('[data-slot="hover-card-content"]')).toContainText("00:00:00")
    // ชิป timecode บนภาพเอง (ไม่พึ่ง hover card) เห็นเฉพาะภาพที่โฟกัสอยู่
    const chip = (time: string) => page.getByRole("list", { name: FRAME_LIST }).getByText(time, { exact: true })
    await expect(chip("00:00:00")).toBeVisible()
    await expect(chip("00:00:04")).toBeHidden()
    await page.keyboard.press("Tab")
    await expect(frameButton(page, "00:00:04")).toBeFocused()
    await expect(chip("00:00:04")).toBeVisible()
    await expect(chip("00:00:00")).toBeHidden()
  })

  test("คีย์บอร์ด: Shift+F10 และปุ่ม Menu เปิดเมนู มีสามรายการ · Esc ปิดแล้วโฟกัสกลับที่ภาพ", async ({ page }) => {
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
    await expect(page.getByRole("menuitem", { name: "โหลดภาพนี้" })).toBeFocused()
    await page.keyboard.press("ArrowDown")
    await page.keyboard.press("ArrowDown")
    await expect(page.getByRole("menuitem", { name: "คัดลอกลิงก์ช่วงนี้" })).toBeFocused()
    await page.keyboard.press("Enter")
    await expect(page.getByText("คัดลอกแล้ว")).toBeVisible()
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(`https://youtu.be/${BBB}?t=9`)
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

  test("ภาพเฟรมบอกว่าเปิดเมนู (aria-haspopup) และสถานะเปิด/ปิด (aria-expanded) เปลี่ยนตามจริง", async ({ page }) => {
    await openBbb(page)
    // เมนูเปิดอยู่ Base UI ซ่อนเนื้อหานอกเมนูจากโปรแกรมอ่านหน้าจอ (aria-hidden) จึงต้องรวมองค์ประกอบที่ถูกซ่อน
    const frame = (time: string) => page.getByRole("button", { name: `ภาพเฟรมที่ ${time}`, includeHidden: true })
    await expect(frame("00:00:09")).toHaveAttribute("aria-haspopup", "menu")
    await expect(frame("00:00:09")).toHaveAttribute("aria-expanded", "false")
    await frame("00:00:09").click({ button: "right" })
    await expect(page.getByRole("menu")).toBeVisible()
    await expect(frame("00:00:09")).toHaveAttribute("aria-expanded", "true")
    await expect(frame("00:00:04")).toHaveAttribute("aria-expanded", "false")
    await page.keyboard.press("Escape")
    await expect(page.getByRole("menu")).toHaveCount(0)
    await expect(frame("00:00:09")).toHaveAttribute("aria-expanded", "false")
  })

  for (const key of ["Enter", "Space", "Shift+F10", "ContextMenu"]) {
    test(`เปิดเมนูด้วยคีย์บอร์ด (${key}) โฟกัสไปที่รายการแรกของเมนู`, async ({ page }) => {
      await openBbb(page)
      await frameButton(page, "00:00:09").focus()
      await page.keyboard.press(key)
      await expect(page.getByRole("menuitem", { name: "โหลดภาพนี้" })).toBeFocused()
      await page.keyboard.press("ArrowDown")
      await expect(page.getByRole("menuitem", { name: "คัดลอกเวลา" })).toBeFocused()
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

  test("คลิกซ้ายที่ภาพก็เปิดเมนู (คนที่ไม่รู้ว่าคลิกขวาได้)", async ({ page }) => {
    await openBbb(page)
    await frameItems(page).nth(2).click()
    await expect(page.getByRole("menu").getByRole("menuitem")).toHaveText(MENU_ITEMS)
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

  test("Contact sheet โหลดได้ไฟล์ .jpg และ zip โหลดได้ไฟล์ .zip", async ({ page }) => {
    await openBbb(page)
    const sheet = page.waitForEvent("download")
    await page.getByRole("button", { name: "Contact sheet" }).click()
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

  test("ตอนขยายทั้งหมด ภาพที่อยู่ไกลจอ (content-visibility) ยังโฟกัสด้วยคีย์บอร์ดและเปิดเมนูได้", async ({ page }) => {
    await openBbb(page)
    await page.getByRole("button", { name: "ดูทั้งหมด (128)" }).click()
    await expect(frameItems(page)).toHaveCount(128)
    await expect(frameItems(page).first()).toHaveCSS("content-visibility", "auto")
    const last = page.getByRole("button", { name: /ภาพเฟรมที่ 00:10:3\d/ })
    await last.focus()
    await expect(last).toBeFocused()
    await page.keyboard.press("Shift+F10")
    await expect(page.getByRole("menuitem", { name: "โหลดภาพนี้" })).toBeFocused()
  })

  test("ปุ่มโหลดชุดใหญ่เป็นปุ่มรอง ไม่ใช่ปุ่มหลักสีเหลือง และหน้านี้ไม่มีปุ่มหลัก", async ({ page }) => {
    await openBbb(page)
    for (const name of ["Contact sheet", "โหลดทั้งหมด (.zip)"]) {
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
    const sheet = page.getByRole("button", { name: "Contact sheet" })
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
    await expect(page.getByRole("button", { name: "Contact sheet" })).toHaveCount(0)
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
    await expect(frameItems(page)).toHaveCount(12)
  })
})

test.describe("W2 จอแคบ", () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test("grid 3 คอลัมน์ เห็น 2 แถว (6 ภาพ) แล้วกดดูทั้งหมด", async ({ page }) => {
    await page.goto(`/v/${BBB}`)
    await expect(frameItems(page).first()).toBeVisible()
    const columns = await page
      .getByRole("list", { name: FRAME_LIST })
      .evaluate((el) => getComputedStyle(el).gridTemplateColumns.split(" ").length)
    expect(columns).toBe(3)
    await expect(frameItems(page).locator("visible=true")).toHaveCount(6)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.getByRole("button", { name: "ดูทั้งหมด (128)" }).click()
    await expect(frameItems(page).locator("visible=true")).toHaveCount(128)
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

    test(`หน้าผลลัพธ์ W2 ไม่มีปัญหาระดับ serious/critical (${scheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme })
      await page.goto(`/v/${BBB}`)
      await expect(frameItems(page)).toHaveCount(12)
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
