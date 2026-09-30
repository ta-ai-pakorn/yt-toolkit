import fs from "node:fs"
import path from "node:path"

import { expect, test, type Page } from "@playwright/test"

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
// คำขอข้อมูลคลิปแบบปกติ (ไม่ใช่ peek และไม่ใช่ /storyboard) ของหน้า W2
const isNormalVideoGet = (url: string) => {
  const parsed = new URL(url)
  return /^\/api\/videos\/[^/]+$/.test(parsed.pathname) && !parsed.searchParams.has("peek")
}
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
    await expect(button).toHaveCSS("opacity", "0.5")
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

  test("รายการผล: กด Tab จากปุ่มวิเคราะห์ผ่าน 'ล้างรายการ' ไปถึงลิงก์ 'เปิดดู' ได้ แล้วกด Enter เข้าหน้าคลิป", async ({ page }) => {
    await page.goto("/")
    await page.getByRole("textbox").fill([`https://youtu.be/${ZOO}`, "ไม่ใช่ลิงก์"].join("\n"))
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    const link = page.getByRole("link", { name: /เปิดดู/ })
    await expect(link).toBeVisible()
    await page.getByRole("button", { name: "วิเคราะห์" }).focus()
    await page.keyboard.press("Tab")
    await expect(page.getByRole("button", { name: "ล้างรายการ" })).toBeFocused()
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
    await page.getByRole("banner").getByRole("link", { name: "หน้าแรก" }).click()
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

  test("กด 'เปิดดู' ตอนที่ peek ยังไม่เสร็จ → หน้าคลิปยังยิงคำขอปกติ (ไม่ใช่ peek) เพื่อให้คลิปเข้า 'ล่าสุด'", async ({
    page,
  }) => {
    const requests: string[] = []
    page.on("request", (request) => {
      if (request.url().includes(`/api/videos/${BBB}`)) requests.push(request.url())
    })
    await page.route(`**/api/videos/${BBB}?peek=1`, async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 1500))
      await route.continue()
    })
    await page.goto("/")
    await page.getByRole("textbox").fill([`https://youtu.be/${BBB}`, "ไม่ใช่ลิงก์"].join("\n"))
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    await page.getByRole("link", { name: /เปิดดู/ }).click()
    await expect(page).toHaveURL(new RegExp(`/v/${BBB}$`))
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Big Buck Bunny")
    expect(requests.filter(isNormalVideoGet)).toHaveLength(1)
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
    expect(requests.filter(isNormalVideoGet)).toHaveLength(1)
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
    await expect(row).toHaveAttribute("aria-busy", "true")
    await expect(row.locator("[data-slot=skeleton]")).toBeVisible()
    // โครงรอต้องไม่ถูกประกาศทีละแถว
    await expect(row.getByRole("status")).toHaveCount(0)
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

  const BOT_MESSAGE = "ยูทูปขอให้ยืนยันว่าไม่ใช่บอท รอสัก 10 นาทีแล้วค่อยลองใหม่"
  const BOT_NOTE = "หยุดดึงชื่อชั่วคราว ยูทูปขอให้ยืนยันว่าไม่ใช่บอท"
  const botCheckBody = { error: { code: "E_BOT_CHECK", message: BOT_MESSAGE, detail: null } }

  test("E_BOT_CHECK ตอนดึงชื่อ → หยุดยิงคำขอที่เหลือ แถวที่เหลือแสดงรหัสกับหมายเหตุ ปุ่ม 'แสดงชื่อ' ปิด · วิเคราะห์ใหม่ลองได้อีกครั้ง", async ({
    page,
  }) => {
    const ids = clipIds(12)
    const peeks: string[] = []
    await page.route("**/api/videos/*", async (route) => {
      peeks.push(new URL(route.request().url()).pathname.split("/").pop() ?? "")
      await new Promise((resolve) => setTimeout(resolve, 150))
      await route.fulfill({ status: 429, json: botCheckBody })
    })
    await page.goto("/")
    await page.getByRole("textbox").fill(ids.join("\n"))
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    const rows = page.locator(RESULT_ROWS)
    await expect(rows).toHaveCount(12)
    // ทุกแถวที่ยังไม่มีชื่อ = รหัส + หมายเหตุเล็ก ๆ (ไม่มีโครงรอค้าง ไม่มีข้อความ error ดิบ)
    for (let i = 0; i < 12; i += 1) {
      await expect(rows.nth(i)).toContainText(ids[i])
      await expect(rows.nth(i)).toContainText(BOT_NOTE)
      await expect(rows.nth(i).getByRole("link", { name: /เปิดดู/ })).toHaveAttribute("href", `/v/${ids[i]}`)
    }
    await expect(page.locator(`${RESULT_ROWS} [data-slot=skeleton]`)).toHaveCount(0)
    // ออกไปได้แค่ชุดแรก (ครั้งละ 3) ก่อนเบรก ที่เหลือ (ตั้งแต่แถวที่ 4) ไม่ถูกยิงเลย
    await page.waitForTimeout(600)
    expect(peeks.sort()).toEqual(ids.slice(0, 3))
    // ปุ่ม "แสดงชื่อ" ของแถวที่ 11-12 ปิดด้วย aria-disabled และกดแล้วไม่มีคำขอใหม่
    const showTitle = page.getByRole("button", { name: "แสดงชื่อ" })
    await expect(showTitle).toHaveCount(2)
    await expect(showTitle.first()).toHaveAttribute("aria-disabled", "true")
    await expect(showTitle.last()).toHaveAttribute("aria-disabled", "true")
    await showTitle.first().click({ force: true })
    await page.waitForTimeout(300)
    expect(peeks).toHaveLength(3)

    // กดวิเคราะห์ใหม่ = รายการใหม่ ลองยิงได้อีกครั้ง
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    await expect.poll(() => peeks.length).toBeGreaterThan(3)
  })

  test("E_BOT_CHECK ตอนดึงเพลย์ลิสต์ → เพลย์ลิสต์ที่รอคิวไม่ถูกยิง และแสดงหมายเหตุ (ไม่มีปุ่มลองใหม่)", async ({
    page,
  }) => {
    const requests: string[] = []
    await page.route("**/api/playlists/*", async (route) => {
      requests.push(route.request().url())
      await new Promise((resolve) => setTimeout(resolve, 150))
      await route.fulfill({ status: 429, json: botCheckBody })
    })
    await page.goto("/")
    const lines = Array.from({ length: 5 }, (_, i) => `https://www.youtube.com/playlist?list=PLtest00000${i}`)
    await page.getByRole("textbox").fill(lines.join("\n"))
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    const rows = page.locator(RESULT_ROWS)
    await expect(rows).toHaveCount(5)
    await expect(rows.filter({ hasText: BOT_NOTE })).toHaveCount(5)
    await expect(page.getByRole("button", { name: "ลองใหม่" })).toHaveCount(0)
    await page.waitForTimeout(500)
    expect(requests).toHaveLength(3)
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

test.describe("โหลดไฟล์โค้ดของหน้าไม่ได้ (แท็บเก่าหลังอัปเดตโปรแกรม)", () => {
  for (const [name, url, chunk] of [
    ["หน้าคลิป", `/v/${BBB}`, "video"],
    ["หน้าตั้งค่า", "/settings/health", "settings"],
  ] as const) {
    test(`${name}: โหลดใหม่ให้เองหนึ่งครั้ง แล้วแจ้งภาษาไทยพร้อมปุ่มโหลดหน้าใหม่ ไม่ใช่หน้า error ของ router`, async ({
      page,
    }) => {
      let aborted = 0
      await page.route(`**/assets/${chunk}-*.js`, (route) => {
        aborted += 1
        return route.abort()
      })
      await page.goto(url)
      await expect(page.getByText("โปรแกรมเพิ่งอัปเดต โหลดหน้านี้ใหม่อีกครั้ง")).toBeVisible()
      await expect(page.getByRole("link", { name: "หน้าแรก" })).toBeVisible()
      // ครั้งแรก + โหลดใหม่อัตโนมัติหนึ่งครั้ง เท่านั้น ไม่วน
      expect(aborted).toBe(2)
      await page.waitForTimeout(500)
      expect(aborted).toBe(2)
      // ไฟล์กลับมาแล้ว กดปุ่มแล้วหน้าเปิดได้
      await page.unroute(`**/assets/${chunk}-*.js`)
      await page.getByRole("button", { name: "โหลดหน้าใหม่" }).click()
      await expect(page.getByText("โปรแกรมเพิ่งอัปเดต โหลดหน้านี้ใหม่อีกครั้ง")).toHaveCount(0)
      await expect(page.getByRole("main")).toBeVisible()
    })
  }
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

const MIX_ID = "RDaqz-KE-bpKQ"
const MIX_URL = `${BBB_URL}&list=${MIX_ID}&start_radio=1`
const MIX_DIALOG = "ลิงก์นี้เป็นมิกซ์อัตโนมัติของยูทูป จะเอาแค่คลิปนี้ หรือ 25 คลิปแรกของมิกซ์?"
const MIX_NOTE = "มิกซ์อัตโนมัติ แต่ละคนอาจได้รายการไม่เหมือนกัน"

test.describe("W1 ลิงก์มิกซ์ (list=RD...)", () => {
  test("ลิงก์มิกซ์ → กล่องถามแบบมิกซ์ · 'ทั้งมิกซ์ (25 คลิปแรก)' แสดงแถวมิกซ์ 25 คลิปพร้อมหมายเหตุ", async ({ page }) => {
    const playlistUrls: string[] = []
    page.on("request", (request) => {
      if (request.url().includes("/api/playlists/")) playlistUrls.push(request.url())
    })
    await page.goto("/")
    await page.getByRole("textbox").fill(MIX_URL)
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    const dialog = page.getByRole("dialog")
    await expect(dialog).toContainText(MIX_DIALOG)
    await expect(dialog.getByRole("button")).toHaveText(["คลิปนี้", "ทั้งมิกซ์ (25 คลิปแรก)", "ปิด"])
    await dialog.getByRole("button", { name: "ทั้งมิกซ์ (25 คลิปแรก)" }).click()
    const rows = page.locator(RESULT_ROWS)
    await expect(rows).toHaveCount(1)
    await expect(rows).toContainText("มิกซ์ - Big Buck Bunny")
    await expect(rows).toContainText("25 คลิป")
    await expect(rows).toContainText(MIX_NOTE)
    await expect(rows).not.toContainText("แสดงแค่")
    expect(playlistUrls.map((url) => new URL(url).pathname + new URL(url).search)).toEqual([
      `/api/playlists/${MIX_ID}?v=${BBB}`,
    ])
  })

  test("ลิงก์มิกซ์ → 'คลิปนี้' ไปหน้าคลิป", async ({ page }) => {
    await page.goto("/")
    await page.getByRole("textbox").fill(MIX_URL)
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    await page.getByRole("dialog").getByRole("button", { name: "คลิปนี้" }).click()
    await expect(page).toHaveURL(new RegExp(`/v/${BBB}$`))
  })

  test("ลิงก์มิกซ์ปนในหลายบรรทัด → แถวคลิปมีปุ่ม 'ทั้งมิกซ์ (25 คลิปแรก)' กดแล้วเป็นแถวมิกซ์", async ({ page }) => {
    await page.goto("/")
    await page.getByRole("textbox").fill([MIX_URL, `https://youtu.be/${ZOO}`].join("\n"))
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    const rows = page.locator(RESULT_ROWS)
    await expect(rows).toHaveCount(2)
    await rows.first().getByRole("button", { name: "ทั้งมิกซ์ (25 คลิปแรก)" }).click()
    await expect(rows.first()).toContainText("มิกซ์ - Big Buck Bunny")
    await expect(rows.first()).toContainText(MIX_NOTE)
  })
})

const THREE_LINKS = [`https://youtu.be/${BBB}`, `https://youtu.be/${ZOO}`, PLAYLIST_URL].join("\n")
const OPENED = "เปิดดูแล้ว"

async function pasteThree(page: Page) {
  await page.goto("/")
  await page.getByRole("textbox").fill(THREE_LINKS)
  await page.getByRole("button", { name: "วิเคราะห์" }).click()
  const rows = page.locator(RESULT_ROWS)
  await expect(rows).toHaveCount(3)
  await expect(rows.nth(1)).toContainText("Me at the zoo")
  return rows
}

async function expectListIntact(page: Page, openedRow: number) {
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole("textbox")).toHaveValue(THREE_LINKS)
  const rows = page.locator(RESULT_ROWS)
  await expect(rows).toHaveCount(3)
  await expect(rows.nth(0)).toContainText("Big Buck Bunny")
  await expect(rows.nth(1)).toContainText("Me at the zoo")
  await expect(rows.nth(2)).toContainText(PLAYLIST_TITLE)
  for (let i = 0; i < 3; i++) {
    if (i === openedRow) await expect(rows.nth(i)).toContainText(OPENED)
    else await expect(rows.nth(i)).not.toContainText(OPENED)
  }
}

test.describe("W1 จำรายการที่วางไว้", () => {
  test("วาง 3 ลิงก์ เปิดหนึ่งคลิป แล้วกดย้อนกลับของเบราว์เซอร์ → ข้อความ รายการ และป้าย 'เปิดดูแล้ว' อยู่ครบ", async ({ page }) => {
    const rows = await pasteThree(page)
    let resolves = 0
    page.on("request", (request) => {
      if (request.url().endsWith("/api/resolve")) resolves += 1
    })
    await rows.nth(1).getByRole("link", { name: /เปิดดู/ }).click()
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Me at the zoo")
    await page.goBack()
    await expectListIntact(page, 1)
    // กลับมาแล้วไม่เรียก /resolve ใหม่
    expect(resolves).toBe(0)
  })

  test("breadcrumb 'รายการที่วาง (3 ลิงก์)' พากลับรายการเดิม", async ({ page }) => {
    const rows = await pasteThree(page)
    await rows.nth(0).getByRole("link", { name: /เปิดดู/ }).click()
    const crumbs = page.getByRole("navigation", { name: "ตำแหน่งของหน้านี้" })
    await expect(crumbs.locator('[data-slot="breadcrumb-item"]')).toHaveText([
      "หน้าแรก",
      "รายการที่วาง (3 ลิงก์)",
      /^Big Buck Bunny/,
    ])
    await expect(crumbs.locator('[aria-current="page"]')).toContainText("Big Buck Bunny")
    await crumbs.getByRole("link", { name: "รายการที่วาง (3 ลิงก์)" }).click()
    await expectListIntact(page, 0)
  })

  test("breadcrumb 'หน้าแรก' ก็เห็นรายการเดิม", async ({ page }) => {
    const rows = await pasteThree(page)
    await rows.nth(0).getByRole("link", { name: /เปิดดู/ }).click()
    await page.getByRole("navigation", { name: "ตำแหน่งของหน้านี้" }).getByRole("link", { name: "หน้าแรก" }).click()
    await expectListIntact(page, 0)
  })

  test("โหลดหน้าใหม่ (F5) ในแท็บเดิม → รายการยังอยู่ โดยไม่เรียก /resolve ใหม่", async ({ page }) => {
    const rows = await pasteThree(page)
    await rows.nth(1).getByRole("link", { name: /เปิดดู/ }).click()
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Me at the zoo")
    await page.goBack()
    let resolves = 0
    page.on("request", (request) => {
      if (request.url().endsWith("/api/resolve")) resolves += 1
    })
    await page.reload()
    await expectListIntact(page, 1)
    // W2 ที่โหลดใหม่ก็ยังรู้ว่ามาจากรายการ
    await page.goForward()
    await expect(page.getByRole("navigation", { name: "ตำแหน่งของหน้านี้" })).toContainText("รายการที่วาง (3 ลิงก์)")
    expect(resolves).toBe(0)
  })

  test("'ล้างรายการ' ล้างข้อความ รายการ และสิ่งที่จำไว้ · โฟกัสกลับช่องวางลิงก์", async ({ page }) => {
    const rows = await pasteThree(page)
    await rows.nth(1).getByRole("link", { name: /เปิดดู/ }).click()
    await page.goBack()
    await page.getByRole("button", { name: "ล้างรายการ" }).click()
    await expect(page.getByRole("textbox")).toHaveValue("")
    await expect(page.getByRole("textbox")).toBeFocused()
    await expect(page.locator(RESULT_ROWS)).toHaveCount(0)
    await expect(page.getByRole("heading", { name: "ผลการวิเคราะห์" })).toHaveCount(0)
    await expect(page.getByRole("status").filter({ hasText: "ล้างรายการแล้ว" })).toBeAttached()
    await page.reload()
    await expect(page.getByRole("textbox")).toHaveValue("")
    await expect(page.locator(RESULT_ROWS)).toHaveCount(0)
  })

  test("กด 'ทั้งเพลย์ลิสต์' ในแถวแล้วไปหน้าคลิปอื่นแล้วกลับมา → แถวนั้นยังเป็นเพลย์ลิสต์", async ({ page }) => {
    await page.goto("/")
    await page.getByRole("textbox").fill([AMBIGUOUS_URL, `https://youtu.be/${ZOO}`].join("\n"))
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    const rows = page.locator(RESULT_ROWS)
    await rows.first().getByRole("button", { name: "ทั้งเพลย์ลิสต์" }).click()
    await expect(rows.first()).toContainText(PLAYLIST_TITLE)
    await rows.nth(1).getByRole("link", { name: /เปิดดู/ }).click()
    await page.goBack()
    await expect(rows.first()).toContainText(PLAYLIST_TITLE)
  })

  test("sessionStorage ใช้ไม่ได้ → ยังใช้งานได้ปกติ และสลับหน้าแล้วรายการยังอยู่", async ({ page }) => {
    await page.addInitScript(() => {
      Object.defineProperty(window, "sessionStorage", {
        get() {
          throw new Error("SecurityError")
        },
      })
    })
    const rows = await pasteThree(page)
    await rows.nth(1).getByRole("link", { name: /เปิดดู/ }).click()
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Me at the zoo")
    await page.getByRole("navigation", { name: "ตำแหน่งของหน้านี้" }).getByRole("link", { name: /รายการที่วาง/ }).click()
    await expectListIntact(page, 1)
  })

  test("ย้อนกลับมาหน้าแรกแล้วกลับไปตำแหน่งเลื่อนเดิม", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 500 })
    await page.goto("/")
    const ids = clipIds(12)
    await page.getByRole("textbox").fill(ids.join("\n"))
    await page.getByRole("button", { name: "วิเคราะห์" }).click()
    const target = page.locator(RESULT_ROWS).nth(10)
    await target.scrollIntoViewIfNeeded()
    const before = await page.evaluate(() => window.scrollY)
    expect(before).toBeGreaterThan(200)
    await target.getByRole("link", { name: /เปิดดู/ }).click()
    await expect(page).toHaveURL(new RegExp(`/v/${ids[10]}$`))
    await page.getByRole("navigation", { name: "ตำแหน่งของหน้านี้" }).getByRole("link", { name: /รายการที่วาง/ }).click()
    await expect(page).toHaveURL(/\/$/)
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(before)

    await target.getByRole("link", { name: /เปิดดู/ }).click()
    await page.goBack()
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(before)
  })
})
