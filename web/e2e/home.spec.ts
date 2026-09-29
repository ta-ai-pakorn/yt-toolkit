import fs from "node:fs"
import path from "node:path"

import { expect, test } from "@playwright/test"

test("หน้าแรก W1 แสดงหัวข้อ ช่องวางลิงก์ และปุ่มหลักปุ่มเดียว", async ({ page }) => {
  await page.goto("/")
  await expect(page.getByRole("heading", { name: "วางลิงก์ยูทูป แล้วเลือกสิ่งที่อยากได้" })).toBeVisible()
  await expect(page.getByRole("textbox")).toBeVisible()
  await expect(page.getByRole("button", { name: "วิเคราะห์" })).toBeVisible()
  await expect(page.locator('meta[name="yt-token"]')).toHaveAttribute("content", /.{20,}/)
})

test("/index.html ได้หน้าที่ฝัง token แล้ว ไม่ใช่ไฟล์ดิบ", async ({ page }) => {
  await page.goto("/index.html")
  await expect(page.locator('meta[name="yt-token"]')).toHaveAttribute("content", /.{20,}/)
})

test("กดปุ่ม d ไม่สลับธีม (ไม่มีปุ่มลัดซ่อน)", async ({ page }) => {
  await page.goto("/")
  await expect(page.getByRole("heading", { name: "วางลิงก์ยูทูป แล้วเลือกสิ่งที่อยากได้" })).toBeVisible()
  const before = await page.locator("html").getAttribute("class")
  await page.locator("body").press("d")
  await expect(page.locator("html")).toHaveAttribute("class", before ?? "")
  expect(await page.evaluate(() => localStorage.getItem("theme"))).toBeNull()
})

test("ปุ่มตั้งค่าที่หัวหน้าเป็นลิงก์จริง ไม่ใช่ปุ่ม", async ({ page }) => {
  await page.goto("/")
  await expect(page.getByRole("link", { name: "ตั้งค่า" })).toHaveAttribute("href", "/settings/health")
  await expect(page.getByRole("button", { name: "ตั้งค่า" })).toHaveCount(0)
  await page.getByRole("link", { name: "ตั้งค่า" }).click()
  await expect(page.getByRole("link", { name: "ตั้งค่า" })).toHaveAttribute("aria-current", "page")
})

const BBB = "aqz-KE-bpKQ"
const BBB_URL = `https://www.youtube.com/watch?v=${BBB}`
const ZOO = "jNQXAC9IVRw"
const PLAYLIST_ID = "PLfakeplaylist250"
const PLAYLIST_URL = `https://www.youtube.com/playlist?list=${PLAYLIST_ID}`
const AMBIGUOUS_URL = `${BBB_URL}&list=${PLAYLIST_ID}`
const INVALID_MESSAGE = "ลิงก์นี้ไม่ใช่ลิงก์ยูทูป ลองคัดลอกจากแถบที่อยู่ของเบราว์เซอร์อีกครั้ง"
const PLAYLIST_TITLE: string = JSON.parse(
  fs.readFileSync(path.join(import.meta.dirname, "../../tests/fixtures/playlist", `${PLAYLIST_ID}.json`), "utf8"),
).title

const DIALOG_TITLE = "ลิงก์นี้อยู่ในเพลย์ลิสต์ จะเอาแค่คลิปนี้ หรือทั้งเพลย์ลิสต์?"
const RESULT_ROWS = 'section[aria-labelledby="results-title"] [role="listitem"]'

test.describe("W1 วิเคราะห์ลิงก์", () => {
  test("กดวิเคราะห์ลิงก์คลิปเดียว → ไปหน้าคลิป และปุ่มหมุนพร้อมปิดใช้งานระหว่างรอ", async ({ page }) => {
    await page.route("**/api/resolve", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 400))
      await route.continue()
    })
    await page.goto("/")
    await page.getByRole("textbox").fill(BBB_URL)
    const button = page.getByRole("button", { name: "วิเคราะห์" })
    await button.click()
    await expect(button).toBeDisabled()
    await expect(button.getByRole("status", { name: "กำลังโหลด" })).toBeVisible()
    await expect(page).toHaveURL(new RegExp(`/v/${BBB}$`))
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Big Buck Bunny")
  })

  test("Ctrl+Enter ในช่อง = วิเคราะห์ · Enter เฉย ๆ ขึ้นบรรทัดใหม่", async ({ page }) => {
    await page.goto("/")
    const box = page.getByRole("textbox")
    await box.fill(BBB_URL)
    await box.press("Enter")
    await expect(page).toHaveURL(/\/$/)
    await box.press("Control+Enter")
    await expect(page).toHaveURL(new RegExp(`/v/${BBB}$`))
  })

  test("AC-IN-06: กด Ctrl+V นอกช่องกรอก วางลิงก์แล้ววิเคราะห์ทันที", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"])
    await page.goto("/")
    await page.evaluate(`navigator.clipboard.writeText(${JSON.stringify(BBB_URL)})`)
    await page.locator("body").click({ position: { x: 5, y: 300 } })
    await expect(page.getByRole("textbox")).not.toBeFocused()
    await page.keyboard.press("Control+V")
    await expect(page).toHaveURL(new RegExp(`/v/${BBB}$`))
  })

  test("Ctrl+V ตอนโฟกัสอยู่ในช่องกรอก ไม่วิเคราะห์เอง (วางลงช่องตามปกติ)", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"])
    await page.goto("/")
    await page.evaluate(`navigator.clipboard.writeText(${JSON.stringify(BBB_URL)})`)
    await page.getByRole("textbox").focus()
    await page.keyboard.press("Control+V")
    await expect(page.getByRole("textbox")).toHaveValue(BBB_URL)
    await expect(page).toHaveURL(/\/$/)
  })

  test("ข้อความว่างหรือมีแต่ช่องว่าง กดวิเคราะห์แล้วโฟกัสกลับช่อง ไม่เรียก backend", async ({ page }) => {
    let calls = 0
    await page.route("**/api/resolve", (route) => {
      calls += 1
      return route.continue()
    })
    await page.goto("/")
    await page.getByRole("textbox").fill("   ")
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    await expect(page.getByRole("textbox")).toBeFocused()
    expect(calls).toBe(0)
  })

  test("ช่องกรอกสูงขึ้นเองตามจำนวนบรรทัด แต่ไม่เกิน 8 บรรทัด", async ({ page }) => {
    await page.goto("/")
    const box = page.getByRole("textbox")
    const height = async () => (await box.boundingBox())!.height
    const lines = (n: number) => Array.from({ length: n }, (_, i) => `ลิงก์ที่ ${i + 1}`).join("\n")
    const h1 = await height()
    await box.fill(lines(8))
    const h8 = await height()
    await box.fill(lines(20))
    const h20 = await height()
    expect(h8).toBeGreaterThan(h1)
    expect(h20).toBe(h8)
    expect(await box.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true)
  })

  test("ลิงก์ที่มีทั้งคลิปและเพลย์ลิสต์ → กล่องถาม เลือก 'คลิปนี้' ไปหน้าคลิป", async ({ page }) => {
    await page.goto("/")
    await page.getByRole("textbox").fill(AMBIGUOUS_URL)
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    const dialog = page.getByRole("dialog")
    await expect(dialog).toContainText(DIALOG_TITLE)
    await dialog.getByRole("button", { name: "คลิปนี้" }).click()
    await expect(page).toHaveURL(new RegExp(`/v/${BBB}$`))
  })

  test("ลิงก์ที่มีทั้งคลิปและเพลย์ลิสต์ → เลือก 'ทั้งเพลย์ลิสต์' แสดงแถวเพลย์ลิสต์", async ({ page }) => {
    await page.goto("/")
    await page.getByRole("textbox").fill(AMBIGUOUS_URL)
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    await page.getByRole("dialog").getByRole("button", { name: "ทั้งเพลย์ลิสต์" }).click()
    await expect(page.getByRole("dialog")).toHaveCount(0)
    await expect(page).toHaveURL(/\/$/)
    const rows = page.locator(RESULT_ROWS)
    await expect(rows).toHaveCount(1)
    await expect(rows).toContainText(PLAYLIST_TITLE)
    await expect(rows).toContainText("250 คลิป")
    await expect(rows).toContainText("เลือกคลิปจากเพลย์ลิสต์ได้ในเวอร์ชันถัดไป")
    await expect(rows).toContainText("แสดงแค่ 200 คลิปแรก")
  })

  test("กล่องถามกักโฟกัสไว้ข้างใน Tab วนไม่หลุด และ Esc ปิดกล่อง", async ({ page }) => {
    await page.goto("/")
    await page.getByRole("textbox").fill(AMBIGUOUS_URL)
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    const dialog = page.getByRole("dialog")
    await expect(dialog.getByRole("button", { name: "คลิปนี้" })).toBeFocused()
    for (let i = 0; i < 6; i++) {
      await page.keyboard.press("Tab")
      // Base UI มีตัวกั้นโฟกัส (focus guard) ที่ส่งโฟกัสกลับเข้ากล่อง จึงรอให้เสร็จก่อนตรวจ
      await expect
        .poll(() => page.evaluate(`!!document.activeElement?.closest('[role="dialog"]')`))
        .toBe(true)
    }
    await page.keyboard.press("Escape")
    await expect(dialog).toHaveCount(0)
    await expect(page.getByRole("textbox")).toHaveValue(AMBIGUOUS_URL)
  })

  test("หลายบรรทัด → แสดงรายการ: คลิป 1, ลิงก์อ่านไม่ออก 1, เพลย์ลิสต์ 1 ตามลำดับที่วาง", async ({ page }) => {
    await page.goto("/")
    await page.getByRole("textbox").fill([`https://youtu.be/${ZOO}`, "สวัสดี ไม่ใช่ลิงก์", PLAYLIST_URL].join("\n"))
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    await expect(page.getByRole("heading", { name: "ผลการวิเคราะห์" })).toBeVisible()
    await expect(page).toHaveURL(/\/$/)
    const rows = page.locator(RESULT_ROWS)
    await expect(rows).toHaveCount(3)

    await expect(rows.nth(0)).toContainText(ZOO)
    await expect(rows.nth(0).getByRole("link", { name: /เปิดดู/ })).toHaveAttribute("href", `/v/${ZOO}`)

    await expect(rows.nth(1)).toContainText("สวัสดี ไม่ใช่ลิงก์")
    const message = rows.nth(1).getByText(INVALID_MESSAGE)
    await expect(message).toBeVisible()
    await expect(message).toHaveClass(/text-destructive/)

    await expect(rows.nth(2)).toContainText(PLAYLIST_TITLE)
    await expect(rows.nth(2)).toContainText("250 คลิป")
    await expect(rows.nth(2)).toContainText("เลือกคลิปจากเพลย์ลิสต์ได้ในเวอร์ชันถัดไป")
    await expect(rows.nth(2)).toContainText("แสดงแค่ 200 คลิปแรก")
  })

  test("รายการผล: กด Tab จากปุ่มวิเคราะห์ไปถึงลิงก์ 'เปิดดู' ได้ แล้วกด Enter เข้าหน้าคลิป", async ({ page }) => {
    await page.goto("/")
    await page.getByRole("textbox").fill([`https://youtu.be/${ZOO}`, "ไม่ใช่ลิงก์"].join("\n"))
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    const link = page.getByRole("link", { name: /เปิดดู/ })
    await expect(link).toBeVisible()
    await page.getByRole("button", { name: "วิเคราะห์" }).focus()
    await page.keyboard.press("Tab")
    await expect(link).toBeFocused()
    await page.keyboard.press("Enter")
    await expect(page).toHaveURL(new RegExp(`/v/${ZOO}$`))
  })

  test("ลิงก์ที่อ่านไม่ออกลิงก์เดียว → แสดงเป็นแถวสีแดง ไม่ไปหน้าไหน", async ({ page }) => {
    await page.goto("/")
    await page.getByRole("textbox").fill("https://example.com/abc")
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    await expect(page.getByText(INVALID_MESSAGE)).toBeVisible()
    await expect(page).toHaveURL(/\/$/)
  })

  test("ทุกแถวมีสถานะของตัวเอง: เพลย์ลิสต์โหลดไม่ได้ → ข้อความ + ลองใหม่ แถวอื่นไม่กระทบ", async ({ page }) => {
    let fail = true
    await page.route(`**/api/playlists/${PLAYLIST_ID}`, (route) =>
      fail
        ? route.fulfill({
            status: 502,
            json: { error: { code: "E_NETWORK", message: "ต่อยูทูปไม่ได้ ตรวจอินเทอร์เน็ตแล้วลองใหม่", detail: null } },
          })
        : route.continue(),
    )
    await page.goto("/")
    await page.getByRole("textbox").fill([`https://youtu.be/${ZOO}`, PLAYLIST_URL].join("\n"))
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    const rows = page.locator(RESULT_ROWS)
    await expect(rows.nth(1)).toContainText("ต่อยูทูปไม่ได้ ตรวจอินเทอร์เน็ตแล้วลองใหม่")
    await expect(rows.nth(0)).toContainText(ZOO)
    fail = false
    await rows.nth(1).getByRole("button", { name: "ลองใหม่" }).click()
    await expect(rows.nth(1)).toContainText(PLAYLIST_TITLE)
  })

  test("แถวเพลย์ลิสต์ระหว่างโหลดแสดงโครงรอ แล้วกลายเป็นข้อมูลจริง", async ({ page }) => {
    await page.route(`**/api/playlists/${PLAYLIST_ID}`, async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 600))
      await route.continue()
    })
    await page.goto("/")
    await page.getByRole("textbox").fill(PLAYLIST_URL)
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    const row = page.locator(RESULT_ROWS)
    await expect(row.getByText("กำลังโหลดข้อมูลเพลย์ลิสต์")).toBeAttached()
    await expect(row).toContainText(PLAYLIST_TITLE)
  })

  test("วิเคราะห์ไม่สำเร็จ (backend ตอบ error) → แสดงข้อความแดงใต้ช่อง และกดใหม่ได้", async ({ page }) => {
    await page.route("**/api/resolve", (route) =>
      route.fulfill({
        status: 422,
        json: { error: { code: "E_INVALID_INPUT", message: "ข้อความยาวเกินไป", detail: null } },
      }),
    )
    await page.goto("/")
    await page.getByRole("textbox").fill(BBB_URL)
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    const alert = page.getByRole("alert")
    await expect(alert).toContainText("วิเคราะห์ลิงก์ไม่สำเร็จ")
    await expect(alert).toContainText("ข้อความยาวเกินไป")
    await expect(page.getByRole("button", { name: "วิเคราะห์" })).toBeEnabled()
  })

  test("คลิปที่ยังไม่เปิดตัว (live) → หน้าคลิปแสดงข้อความผิดพลาด พร้อมทางกลับหน้าแรก", async ({ page }) => {
    await page.goto("/")
    await page.getByRole("textbox").fill("UPCOMINGLV1")
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    await expect(page).toHaveURL(/\/v\/UPCOMINGLV1$/)
    await expect(page.getByRole("alert")).toContainText("คลิปนี้ยังถ่ายทอดสดอยู่หรือยังไม่เผยแพร่")
    await page.getByRole("link", { name: "กลับหน้าแรก" }).click()
    await expect(page).toHaveURL(/\/$/)
  })
})

test.describe("W1 ล่าสุด", () => {
  test("เปิดคลิปแล้วกลับหน้าแรก → ขึ้นในรายการล่าสุด พร้อมชื่อ ความยาว และลิงก์", async ({ page }) => {
    await page.goto(`/v/${ZOO}`)
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Me at the zoo")
    await page.getByRole("link", { name: "หน้าแรก" }).click()
    const section = page.locator("section[aria-labelledby=recent-title]")
    await expect(section.getByRole("heading", { name: "ล่าสุด" })).toBeVisible()
    const item = section.getByRole("link", { name: /Me at the zoo/ })
    await expect(item).toHaveAttribute("href", `/v/${ZOO}`)
    await expect(item).toContainText("0:19")
    await expect(item).toContainText(/เมื่อสักครู่|นาทีก่อน/)
  })

  test("ไม่มีประวัติ → ซ่อนทั้งส่วน", async ({ page }) => {
    await page.route("**/api/history*", (route) => route.fulfill({ json: { items: [], total: 0 } }))
    await page.goto("/")
    await expect(page.getByRole("textbox")).toBeVisible()
    await expect(page.getByText("ล่าสุด", { exact: true })).toHaveCount(0)
    await expect(page.locator("[aria-busy=true]")).toHaveCount(0)
  })

  test("ระหว่างโหลดแสดงโครงรอ", async ({ page }) => {
    await page.route("**/api/history*", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 800))
      await route.fulfill({ json: { items: [], total: 0 } })
    })
    await page.goto("/")
    await expect(page.locator("section[aria-busy=true] [data-slot=skeleton]").first()).toBeVisible()
    await expect(page.locator("section[aria-busy=true]")).toHaveCount(0)
  })

  test("โหลดไม่สำเร็จ → ซ่อนเงียบ ๆ ไม่มี toast ไม่มีข้อความแดง", async ({ page }) => {
    const warnings: string[] = []
    page.on("console", (message) => {
      if (message.type() === "warning") warnings.push(message.text())
    })
    await page.route("**/api/history*", (route) =>
      route.fulfill({ status: 500, json: { error: { code: "E_UNKNOWN", message: "ผิดพลาด", detail: null } } }),
    )
    await page.goto("/")
    await expect(page.getByRole("textbox")).toBeVisible()
    await expect.poll(() => warnings.some((text) => text.includes("[recent] failed to load history"))).toBe(true)
    await expect(page.getByText("ล่าสุด", { exact: true })).toHaveCount(0)
    await expect(page.locator("[data-sonner-toast]")).toHaveCount(0)
    await expect(page.getByRole("alert")).toHaveCount(0)
  })

  test("แสดง 5 รายการ และภาพปกเสียก็ยังแสดงชื่อ ความยาว เวลาได้", async ({ page }) => {
    const items = Array.from({ length: 5 }, (_, i) => ({
      videoId: `abcdefghij${i}`,
      title: `คลิปทดสอบ ${i + 1}`,
      thumbnailUrl: "http://127.0.0.1:1/missing.jpg",
      durationS: 3725,
      outputs: [],
      lastAt: new Date(Date.now() - 3 * 86400_000).toISOString(),
    }))
    await page.route("**/api/history*", (route) => route.fulfill({ json: { items, total: 9 } }))
    await page.goto("/")
    const section = page.locator("section[aria-labelledby=recent-title]")
    await expect(section.getByRole("link")).toHaveCount(5)
    await expect(section.getByRole("link").first()).toContainText("คลิปทดสอบ 1")
    await expect(section.getByRole("link").first()).toContainText("1:02:05")
    await expect(section.getByRole("link").first()).toContainText("3 วันก่อน")
    await expect(section.locator("img")).toHaveCount(0)
  })
})

const PIXEL = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
)

const fakeVideo = (videoId: string, title = `คลิปทดสอบ ${videoId}`) => ({
  videoId,
  title,
  channel: "ช่องทดสอบ",
  durationS: 60,
  thumbnailUrl: "",
  chapters: [],
  video: [],
  audio: [],
  hasStoryboard: false,
  isLive: false,
})

const clipIds = (n: number) => Array.from({ length: n }, (_, i) => `vid${String(i).padStart(8, "0")}`)

test.describe("W1 รายการผล: ภาพปกและชื่อคลิป", () => {
  test("แถวคลิปแสดงภาพปกจากรหัสทันที และชื่อคลิป ดึงแบบ peek", async ({ page }) => {
    await page.route("https://i.ytimg.com/**", (route) => route.fulfill({ contentType: "image/png", body: PIXEL }))
    const peekUrls: string[] = []
    page.on("request", (request) => {
      if (request.url().includes(`/api/videos/${ZOO}`)) peekUrls.push(request.url())
    })
    await page.goto("/")
    await page.getByRole("textbox").fill([`https://youtu.be/${ZOO}`, "ไม่ใช่ลิงก์"].join("\n"))
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    const row = page.locator(RESULT_ROWS).first()
    await expect(row.locator("img")).toHaveAttribute("src", `https://i.ytimg.com/vi/${ZOO}/mqdefault.jpg`)
    await expect(row).toContainText("Me at the zoo")
    await expect(row).toContainText(ZOO)
    expect(peekUrls.length).toBeGreaterThan(0)
    expect(peekUrls.every((url) => url.endsWith("?peek=1"))).toBe(true)
  })

  test("คลิปที่ดึงแค่ชื่อในรายการผล ไม่ขึ้นใน 'ล่าสุด' จนกว่าจะกดเปิดดู", async ({ page }) => {
    // ตัวตรวจอยู่ที่ pytest (peek ไม่แตะ opened_at) ที่นี่ดูว่าหน้าเว็บส่ง peek จริง และตอนเปิดหน้าคลิปไม่ส่ง
    const requests: string[] = []
    page.on("request", (request) => {
      if (request.url().includes(`/api/videos/${BBB}`)) requests.push(request.url())
    })
    await page.goto("/")
    await page.getByRole("textbox").fill([`https://youtu.be/${BBB}`, "ไม่ใช่ลิงก์"].join("\n"))
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    await expect(page.locator(RESULT_ROWS).first()).toContainText("Big Buck Bunny")
    expect(requests.every((url) => url.endsWith("?peek=1"))).toBe(true)
    await page.getByRole("link", { name: /เปิดดู/ }).click()
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Big Buck Bunny")
    expect(requests.some((url) => !url.includes("peek"))).toBe(true)
  })

  test("ดึงชื่อครั้งละไม่เกิน 3 คลิป และเฉพาะ 10 แถวแรก · แถวที่ 11 เป็นต้นไปกด 'แสดงชื่อ'", async ({ page }) => {
    const ids = clipIds(12)
    let inFlight = 0
    let peak = 0
    const fetched: string[] = []
    await page.route("**/api/videos/*", async (route) => {
      const id = new URL(route.request().url()).pathname.split("/").pop() ?? ""
      fetched.push(id)
      inFlight += 1
      peak = Math.max(peak, inFlight)
      await new Promise((resolve) => setTimeout(resolve, 150))
      inFlight -= 1
      await route.fulfill({ json: fakeVideo(id) })
    })
    await page.goto("/")
    await page.getByRole("textbox").fill(ids.join("\n"))
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    const rows = page.locator(RESULT_ROWS)
    await expect(rows).toHaveCount(12)
    await expect(rows.nth(9)).toContainText(`คลิปทดสอบ ${ids[9]}`, { timeout: 10_000 })
    expect(peak).toBe(3)
    expect(fetched.sort()).toEqual(ids.slice(0, 10))
    // แถวที่ 11-12 ยังไม่ดึง: แสดงรหัสกับปุ่ม
    await expect(page.getByRole("button", { name: "แสดงชื่อ" })).toHaveCount(2)
    await expect(rows.nth(10)).toContainText(ids[10])
    await rows.nth(10).getByRole("button", { name: "แสดงชื่อ" }).click()
    await expect(rows.nth(10)).toContainText(`คลิปทดสอบ ${ids[10]}`)
    await expect(page.getByRole("button", { name: "แสดงชื่อ" })).toHaveCount(1)
    expect(fetched).toHaveLength(11)
  })

  test("ดึงชื่อไม่สำเร็จ → แสดงรหัสคลิปกับข้อความเล็ก ๆ และลิงก์เปิดดูยังใช้ได้", async ({ page }) => {
    await page.route("**/api/videos/PRIVATEVID1*", (route) =>
      route.fulfill({
        status: 404,
        json: { error: { code: "E_VIDEO_PRIVATE", message: "คลิปนี้เป็นส่วนตัว", detail: null } },
      }),
    )
    await page.goto("/")
    await page.getByRole("textbox").fill(["PRIVATEVID1", "ไม่ใช่ลิงก์"].join("\n"))
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    const row = page.locator(RESULT_ROWS).first()
    await expect(row).toContainText("PRIVATEVID1")
    await expect(row).toContainText("ดึงชื่อคลิปไม่สำเร็จ")
    await expect(row).toContainText("คลิปนี้เป็นส่วนตัว")
    await expect(row.getByRole("link", { name: /เปิดดู/ })).toHaveAttribute("href", "/v/PRIVATEVID1")
  })

  test("ระหว่างรอชื่อ แสดงโครงรอ", async ({ page }) => {
    await page.route("**/api/videos/*", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 700))
      await route.continue()
    })
    await page.goto("/")
    await page.getByRole("textbox").fill([`https://youtu.be/${ZOO}`, "ไม่ใช่ลิงก์"].join("\n"))
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    const row = page.locator(RESULT_ROWS).first()
    await expect(row.getByText("กำลังโหลดชื่อคลิป")).toBeAttached()
    await expect(row.locator("[data-slot=skeleton]")).toBeVisible()
    await expect(row).toContainText("Me at the zoo")
  })

  test("เพลย์ลิสต์ดึงข้อมูลครั้งละไม่เกิน 3 รายการ", async ({ page }) => {
    let inFlight = 0
    let peak = 0
    await page.route("**/api/playlists/*", async (route) => {
      inFlight += 1
      peak = Math.max(peak, inFlight)
      await new Promise((resolve) => setTimeout(resolve, 150))
      inFlight -= 1
      await route.fulfill({ json: { title: "รายการทดสอบ", total: 3, truncated: false, entries: [{ videoId: ZOO }] } })
    })
    await page.goto("/")
    const lines = Array.from({ length: 6 }, (_, i) => `https://www.youtube.com/playlist?list=PLtest00000${i}`)
    await page.getByRole("textbox").fill(lines.join("\n"))
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    const rows = page.locator(RESULT_ROWS)
    await expect(rows).toHaveCount(6)
    await expect(rows.filter({ hasText: "รายการทดสอบ" })).toHaveCount(6, { timeout: 10_000 })
    expect(peak).toBe(3)
  })
})

test.describe("W1 การวาง การเข้าถึง และข้อผิดพลาด", () => {
  test("วางลิงก์ใหม่ระหว่างกำลังวิเคราะห์ → ไม่ทำอะไร: เรียก /resolve ครั้งเดียว ช่องไม่ถูกทับ", async ({
    page,
    context,
  }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"])
    let calls = 0
    await page.route("**/api/resolve", async (route) => {
      calls += 1
      await new Promise((resolve) => setTimeout(resolve, 700))
      await route.continue()
    })
    await page.goto("/")
    await page.getByRole("textbox").fill(BBB_URL)
    const button = page.getByRole("button", { name: "วิเคราะห์" })
    await button.click()
    await expect(button).toHaveAttribute("aria-disabled", "true")
    await expect(button).toBeFocused()
    await page.evaluate(`navigator.clipboard.writeText(${JSON.stringify(`https://youtu.be/${ZOO}`)})`)
    await page.keyboard.press("Control+V")
    await expect(page.getByRole("textbox")).toHaveValue(BBB_URL)
    await expect(page).toHaveURL(new RegExp(`/v/${BBB}$`))
    expect(calls).toBe(1)
  })

  test("Ctrl+V ที่ไม่ใช่ลิงก์ยูทูป (ประโยคที่มีคำว่า youtube) → ไม่มีอะไรเกิดขึ้น", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"])
    let calls = 0
    await page.route("**/api/resolve", (route) => {
      calls += 1
      return route.continue()
    })
    await page.goto("/")
    await page.evaluate(`navigator.clipboard.writeText("ดูคลิปนี้ใน youtube ตอนพักเที่ยง")`)
    await page.locator("body").click({ position: { x: 5, y: 300 } })
    await page.keyboard.press("Control+V")
    await page.waitForTimeout(500)
    expect(calls).toBe(0)
    await expect(page.getByRole("textbox")).toHaveValue("")
    await expect(page).toHaveURL(/\/$/)
  })

  test("ช่องวางลิงก์มีป้ายชื่อจริง ไม่ใช่แค่ตัวอย่าง URL", async ({ page }) => {
    await page.goto("/")
    await expect(page.getByLabel("ลิงก์ยูทูป")).toBeVisible()
    await expect(page.getByRole("textbox", { name: "ลิงก์ยูทูป" })).toHaveAttribute("placeholder", /youtube\.com/)
  })

  test("แสดงผลแล้วประกาศจำนวนรายการให้โปรแกรมอ่านหน้าจอ", async ({ page }) => {
    await page.goto("/")
    await page.getByRole("textbox").fill([`https://youtu.be/${ZOO}`, "ไม่ใช่ลิงก์", PLAYLIST_URL].join("\n"))
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    await expect(page.getByRole("status").filter({ hasText: "ผลการวิเคราะห์ 3 รายการ" })).toBeAttached()
  })

  test("ต่อ backend ไม่ได้ (E_OFFLINE) → แจ้งข้อความภาษาไทยใต้ช่อง", async ({ page }) => {
    await page.route("**/api/resolve", (route) => route.abort())
    await page.goto("/")
    await page.getByRole("textbox").fill(BBB_URL)
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    const alert = page.getByRole("alert")
    await expect(alert).toContainText("วิเคราะห์ลิงก์ไม่สำเร็จ")
    await expect(alert).toContainText("เชื่อมต่อโปรแกรมไม่ได้")
  })
})

const readColorScheme = "document.documentElement.style.colorScheme"

test.describe("ธีมตั้งก่อนหน้าโหลดเสร็จ", () => {
  for (const scheme of ["dark", "light"] as const) {
    test(`ไม่ตั้งค่าไว้ ตามระบบ (${scheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme })
      // เก็บคลาสของ <html> ทันทีที่ DOM พร้อม ก่อนที่ React จะทำงาน
      await page.addInitScript(
        'document.addEventListener("DOMContentLoaded", function () { window.earlyClass = document.documentElement.className })',
      )
      await page.goto("/")
      expect(await page.evaluate("window.earlyClass")).toBe(scheme)
      await expect(page.locator("html")).toHaveClass(scheme)
      expect(await page.evaluate(readColorScheme)).toBe(scheme)
    })
  }

  test("ค่าที่บันทึกไว้ชนะระบบ และไม่มีทั้งสองคลาสพร้อมกัน", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "dark" })
    await page.addInitScript('localStorage.setItem("theme", "light")')
    await page.goto("/")
    await expect(page.locator("html")).toHaveClass("light")
    expect(await page.evaluate(readColorScheme)).toBe("light")
  })
})
