import { analyzeSettled } from "./axe-settled"
import { expect, test, type Locator, type Page, type Route } from "@playwright/test"

import type { HistoryItem, HistoryPage, JobKind } from "../src/lib/types"

// หน้า W5 (/history): spec นี้ mock GET /api/history ทั้งหมด จึงไม่สร้างงานจริง (งานจริงอยู่ที่ queue-history.spec.ts)
const ZOO = "jNQXAC9IVRw"
const ZOO_TITLE = "Me at the zoo"

const PIXEL = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
)

function item(videoId: string, title: string, outputs: JobKind[] = [], minutesAgo = 5): HistoryItem {
  return {
    videoId,
    title,
    channel: "",
    thumbnailUrl: `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`,
    durationS: 19,
    outputs,
    lastAt: new Date(Date.now() - minutesAgo * 60_000).toISOString(),
  }
}

async function clickCenter(page: Page, target: Locator, options: { button?: "left" | "middle"; modifiers?: "Control"[] } = {}) {
  const box = await target.boundingBox()
  if (!box) throw new Error("ไม่พบตำแหน่งขององค์ประกอบที่จะคลิก")
  for (const key of options.modifiers ?? []) await page.keyboard.down(key)
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2, { button: options.button })
  for (const key of options.modifiers ?? []) await page.keyboard.up(key)
}

const json = (route: Route, body: HistoryPage) => route.fulfill({ json: body })

async function mockThumbnails(page: Page) {
  await page.route("https://i.ytimg.com/**", (route) => route.fulfill({ contentType: "image/png", body: PIXEL }))
}

async function seriousViolations(page: Page) {
  const results = await analyzeSettled(page)
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.map((n) => n.target.join(" ")).slice(0, 5) }))
}

test.describe("W5 ประวัติ", () => {
  test("ยังไม่มีประวัติ → ข้อความว่าง + คำอธิบาย + ปุ่มกลับหน้าแรก (ไม่มีช่องค้นหา)", async ({ page }) => {
    await page.route("**/api/history*", (route) => json(route, { items: [], total: 0 }))
    await page.goto("/history")
    await expect(page).toHaveTitle("ประวัติ · YT Toolkit")
    await expect(page.getByRole("heading", { level: 1, name: "ประวัติ" })).toBeVisible()
    await expect(page.getByText("ยังไม่มีประวัติ", { exact: true })).toBeVisible()
    await expect(page.getByText("คลิปที่เปิดดูหรือโหลดจะขึ้นที่นี่")).toBeVisible()
    await expect(page.getByRole("textbox", { name: "ค้นหาจากชื่อคลิป" })).toHaveCount(0)
    await expect(page.getByRole("table")).toHaveCount(0)
    await page.getByRole("link", { name: "กลับหน้าแรก" }).first().click()
    await expect(page).toHaveURL(/\/$/)
  })

  test("ระหว่างโหลดแสดงโครงรอ แล้วเป็นตาราง", async ({ page }) => {
    // กั้นคำตอบไว้จนเห็นโครงรอ: หน่วงด้วยเวลาตายตัว runner ที่ช้าตรวจไม่ทันก่อนตารางมา
    let release!: () => void
    const held = new Promise<void>((resolve) => (release = resolve))
    await page.route("**/api/history*", async (route) => {
      await held
      await json(route, { items: [item(ZOO, ZOO_TITLE)], total: 1 })
    })
    await mockThumbnails(page)
    await page.goto("/history")
    await expect(page.locator("[aria-busy=true] [data-slot=skeleton]").first()).toBeVisible()
    release()
    await expect(page.getByRole("link", { name: ZOO_TITLE })).toBeVisible()
    await expect(page.locator("[aria-busy=true]")).toHaveCount(0)
  })

  test("โหลดไม่สำเร็จ → กล่องข้อผิดพลาดพร้อมปุ่มลองใหม่ แล้วลองใหม่สำเร็จ", async ({ page }) => {
    let fail = true
    await page.route("**/api/history*", (route) =>
      fail
        ? route.fulfill({ status: 500, json: { error: { code: "E_UNKNOWN", message: "ระบบขัดข้อง", detail: null } } })
        : json(route, { items: [item(ZOO, ZOO_TITLE)], total: 1 }),
    )
    await mockThumbnails(page)
    await page.goto("/history")
    const alert = page.getByRole("alert")
    await expect(alert).toContainText("โหลดประวัติไม่สำเร็จ")
    await expect(alert).toContainText("ระบบขัดข้อง")
    fail = false
    await alert.getByRole("button", { name: "ลองใหม่" }).click()
    await expect(page.getByRole("link", { name: ZOO_TITLE })).toBeVisible()
    await expect(page.getByRole("alert")).toHaveCount(0)
  })

  test("โหลดไม่สำเร็จตอนเน็ตหลุด แล้วเบราว์เซอร์แจ้งว่าเน็ตกลับมา (online) → โหลดใหม่เอง ไม่ต้องกดลองใหม่", async ({ page }) => {
    // networkMode "always" (router.tsx) ปิด refetchOnReconnect ของ react-query เป็นค่าเริ่มต้น จึงตั้งกลับเป็น true ไว้เอง
    let fail = true
    let calls = 0
    await page.route("**/api/history*", (route) => {
      calls += 1
      return fail
        ? route.fulfill({ status: 503, json: { error: { code: "E_NETWORK", message: "เน็ตหลุด ลองใหม่อีกครั้ง", detail: null } } })
        : json(route, { items: [item(ZOO, ZOO_TITLE)], total: 1 })
    })
    await mockThumbnails(page)
    await page.goto("/history")
    const alert = page.getByRole("alert")
    await expect(alert).toContainText("โหลดประวัติไม่สำเร็จ")
    const failed = calls
    fail = false
    // เน็ตหลุดแล้วกลับมา: onlineManager เปลี่ยนสถานะเฉพาะตอนสลับ จึงส่ง offline ก่อน online
    await page.evaluate(() => {
      window.dispatchEvent(new Event("offline"))
      window.dispatchEvent(new Event("online"))
    })
    await expect(page.getByRole("link", { name: ZOO_TITLE })).toBeVisible()
    await expect(page.getByRole("alert")).toHaveCount(0)
    expect(calls).toBeGreaterThan(failed)
  })

  test("ตารางมีหัวคอลัมน์ครบ ป้ายไฟล์ไม่ซ้ำ (ภาพ) และเวลาแบบสัมพัทธ์ · แถวที่ไม่มีไฟล์ไม่มีป้าย", async ({ page }) => {
    await page.route("**/api/history*", (route) =>
      json(route, {
        items: [
          item("AAAAAAAAAAA", "คลิปที่โหลดครบ", ["video", "audio", "subtitle", "contact_sheet", "frames_zip"], 3),
          item("BBBBBBBBBBB", "คลิปที่แค่เปิดดู", [], 3 * 24 * 60),
        ],
        total: 2,
      }),
    )
    await mockThumbnails(page)
    await page.goto("/history")
    for (const name of ["ปก", "ชื่อคลิป", "ไฟล์ที่ได้", "เวลา"]) {
      await expect(page.getByRole("columnheader", { name })).toBeVisible()
    }
    const rows = page.locator("tbody tr")
    await expect(rows).toHaveCount(2)
    // contact_sheet กับ frames_zip ใช้ป้ายเดียวกัน = แสดง "ภาพ" ครั้งเดียว
    await expect(rows.nth(0).locator('[data-slot="badge"]')).toHaveText(["วิดีโอ", "เสียง", "ซับ", "ภาพ"])
    await expect(rows.nth(0)).toContainText("นาทีก่อน")
    await expect(rows.nth(1).locator('[data-slot="badge"]')).toHaveCount(0)
    await expect(rows.nth(1)).toContainText("3 วันก่อน")
    await expect(page.getByText("แสดง 2 จาก 2 คลิป")).toBeVisible()
    await expect(page.getByRole("button", { name: "แสดงเพิ่ม" })).toHaveCount(0)
  })

  test("ค้นหา: รอ 300 ms แล้วยิงคำขอครั้งเดียว · เก็บใน ?q= · ไม่พบ → ข้อความมีคำค้น · ล้างคำค้นกลับมาครบ", async ({ page }) => {
    const requests: string[] = []
    await page.route("**/api/history*", (route) => {
      const url = new URL(route.request().url())
      requests.push(url.search)
      if (url.searchParams.get("q")) return json(route, { items: [], total: 0 })
      return json(route, { items: [item(ZOO, ZOO_TITLE)], total: 1 })
    })
    await mockThumbnails(page)
    await page.goto("/history")
    await expect(page.getByRole("link", { name: ZOO_TITLE })).toBeVisible()

    const search = page.getByRole("textbox", { name: "ค้นหาจากชื่อคลิป" })
    await search.pressSequentially("zzz", { delay: 40 })
    await expect(page.getByText("ไม่พบคลิปที่ตรงกับ “zzz”")).toBeVisible()
    await expect(page).toHaveURL(/\/history\?q=zzz$/)
    await expect(page.getByRole("table")).toHaveCount(0)
    // ไม่ยิงคำขอระหว่างพิมพ์ (q=z, q=zz): มีแค่คำขอแรกกับคำขอ q=zzz
    expect(requests.filter((query) => query.includes("q="))).toEqual(["?q=zzz&limit=50&scope=all"])

    await page.getByRole("button", { name: "ล้างคำค้น" }).click()
    await expect(search).toBeFocused()
    await expect(page.getByRole("link", { name: ZOO_TITLE })).toBeVisible()
    await expect(page).toHaveURL(/\/history$/)
  })

  test("เปิดหน้าด้วย ?q= → ช่องค้นหามีคำเดิม และคำขอส่ง q ตั้งแต่ครั้งแรก", async ({ page }) => {
    const requests: string[] = []
    await page.route("**/api/history*", (route) => {
      requests.push(new URL(route.request().url()).search)
      return json(route, { items: [item(ZOO, ZOO_TITLE)], total: 1 })
    })
    await mockThumbnails(page)
    await page.goto("/history?q=zoo")
    await expect(page.getByRole("textbox", { name: "ค้นหาจากชื่อคลิป" })).toHaveValue("zoo")
    await expect(page.getByRole("link", { name: ZOO_TITLE })).toBeVisible()
    expect(requests[0]).toBe("?q=zoo&limit=50&scope=all")
  })

  test("แสดงเพิ่ม: หน้าละ 50 · ขอ offset ถัดไป · ตัวนับ 'แสดง N จาก M คลิป' · ปุ่มหายเมื่อครบ", async ({ page }) => {
    const all = Array.from({ length: 70 }, (_, i) => item(`CLIP${String(i).padStart(7, "0")}`, `คลิปที่ ${i + 1}`, [], i + 1))
    const requests: string[] = []
    await page.route("**/api/history*", (route) => {
      const url = new URL(route.request().url())
      requests.push(url.search)
      const offset = Number(url.searchParams.get("offset") ?? 0)
      return json(route, { items: all.slice(offset, offset + Number(url.searchParams.get("limit"))), total: all.length })
    })
    await mockThumbnails(page)
    await page.goto("/history")
    await expect(page.locator("tbody tr")).toHaveCount(50)
    await expect(page.getByText("แสดง 50 จาก 70 คลิป")).toBeVisible()
    await page.getByRole("button", { name: "แสดงเพิ่ม" }).click()
    await expect(page.locator("tbody tr")).toHaveCount(70)
    // โฟกัสย้ายไปลิงก์ของแถวแรกที่เพิ่มมา (ปุ่มหายไปเมื่อครบ โฟกัสไม่หลุดไปที่ body)
    await expect(page.getByRole("link", { name: "คลิปที่ 51", exact: true })).toBeFocused()
    await expect(page.getByText("แสดง 70 จาก 70 คลิป")).toBeVisible()
    await expect(page.getByRole("button", { name: "แสดงเพิ่ม" })).toHaveCount(0)
    expect(requests).toEqual(["?limit=50&scope=all", "?limit=50&offset=50&scope=all"])
  })

  test("กดชื่อคลิป หรือกดที่ส่วนอื่นของแถว → เปิดหน้า W2 ของคลิปนั้น · ชื่อเป็น tab stop เดียวของแถว", async ({ page }) => {
    await page.route("**/api/history*", (route) => json(route, { items: [item(ZOO, ZOO_TITLE, ["audio"])], total: 1 }))
    await mockThumbnails(page)
    await page.goto("/history")
    const link = page.getByRole("link", { name: ZOO_TITLE })
    await expect(link).toHaveAttribute("href", `/v/${ZOO}`)
    await expect(page.locator("tbody tr a")).toHaveCount(1)

    await link.click()
    await expect(page).toHaveURL(new RegExp(`/v/${ZOO}$`))
    await expect(page.getByRole("heading", { level: 1 })).toContainText(ZOO_TITLE)

    await page.goBack()
    await expect(link).toBeVisible()
    // กดที่ช่องเวลา (ส่วนอื่นของแถว) ก็เปิดคลิป: ลิงก์ชื่อขยายคลุมทั้งแถว จึงคลิกด้วยพิกัดเมาส์ (ตัวช่วย click() ของ Playwright มองว่าลิงก์บังเซลล์)
    await clickCenter(page, page.locator("tbody tr").first().locator("td").last())
    await expect(page).toHaveURL(new RegExp(`/v/${ZOO}$`))
    await expect(page.getByRole("heading", { level: 1 })).toContainText(ZOO_TITLE)
  })

  test("ค้นอยู่แล้วเปลี่ยนไป /history (ไม่มี q) ด้วยการนำทางในหน้า → ช่องค้นหาว่าง รายการเต็ม URL ไม่ถูกเขียน q กลับ", async ({ page }) => {
    await page.route("**/api/history*", (route) => {
      const q = new URL(route.request().url()).searchParams.get("q")
      return json(route, q ? { items: [], total: 0 } : { items: [item(ZOO, ZOO_TITLE)], total: 1 })
    })
    await mockThumbnails(page)
    await page.goto("/history")
    const search = page.getByRole("textbox", { name: "ค้นหาจากชื่อคลิป" })
    await search.fill("zoo")
    await expect(page).toHaveURL(/\/history\?q=zoo$/)
    await expect(page.getByText("ไม่พบคลิปที่ตรงกับ “zoo”")).toBeVisible()

    // เหมือนกดเมนู "ประวัติ" ที่หัวหน้า (React Router นำทางฝั่งหน้าเว็บ ไม่โหลดหน้าใหม่)
    await page.evaluate(() => {
      window.history.pushState({}, "", "/history")
      window.dispatchEvent(new PopStateEvent("popstate"))
    })
    await expect(search).toHaveValue("")
    await expect(page.getByRole("link", { name: ZOO_TITLE })).toBeVisible()
    await page.waitForTimeout(600)
    await expect(page).toHaveURL(/\/history$/)
    await expect(search).toHaveValue("")
  })

  test("Ctrl-คลิปที่ส่วนอื่นของแถวเปิดคลิปในแท็บใหม่ และหน้าประวัติยังอยู่", async ({ page, context }) => {
    await page.route("**/api/history*", (route) => json(route, { items: [item(ZOO, ZOO_TITLE, ["audio"])], total: 1 }))
    await mockThumbnails(page)
    await page.goto("/history")
    await expect(page.getByRole("link", { name: ZOO_TITLE })).toBeVisible()
    const opened = context.waitForEvent("page")
    await clickCenter(page, page.locator("tbody tr").first().locator("td").nth(2), { modifiers: ["Control"] })
    const tab = await opened
    await tab.waitForLoadState("domcontentloaded")
    expect(new URL(tab.url()).pathname).toBe(`/v/${ZOO}`)
    await expect(page).toHaveURL(/\/history$/)
  })

  test("/settings พาไป /settings/general", async ({ page }) => {
    await page.goto("/settings")
    await expect(page).toHaveURL(/\/settings\/general$/)
  })

  test("หน้าแรก 'ล่าสุด' ขอเฉพาะคลิปที่เปิดดู: /history?limit=5&scope=opened", async ({ page }) => {
    const requests: string[] = []
    await page.route("**/api/history*", (route) => {
      requests.push(new URL(route.request().url()).search)
      return json(route, { items: [item(ZOO, ZOO_TITLE)], total: 1 })
    })
    await mockThumbnails(page)
    await page.goto("/")
    await expect(page.locator("section[aria-labelledby=recent-title]").getByRole("link", { name: /Me at the zoo/ })).toBeVisible()
    expect(requests).toEqual(["?limit=5&scope=opened"])
  })

  test("จอแคบ 640 px (ซูม 200%): ชื่อยาวมากตัดบรรทัด ไม่มีแถบเลื่อนข้าง", async ({ page }) => {
    await page.setViewportSize({ width: 640, height: 800 })
    const longTitle = "ชื่อคลิปภาษาไทยที่ยาวมากมากมากมากมากมากมากมากมากมากมาก ".repeat(4) + "A".repeat(80)
    await page.route("**/api/history*", (route) =>
      json(route, {
        items: [
          item("AAAAAAAAAAA", longTitle, ["video", "audio", "subtitle", "contact_sheet"], 3),
          item("BBBBBBBBBBB", "คลิปสั้น", ["audio"], 30),
        ],
        total: 2,
      }),
    )
    await mockThumbnails(page)
    await page.goto("/history")
    await expect(page.getByRole("link", { name: /ชื่อคลิปภาษาไทย/ })).toBeVisible()
    const overflow = await page.evaluate(() => {
      const table = document.querySelector("[data-slot=table-container]") as HTMLElement
      return {
        page: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        table: table.scrollWidth - table.clientWidth,
      }
    })
    expect(overflow).toEqual({ page: 0, table: 0 })
  })

  for (const scheme of ["dark", "light"] as const) {
    test(`axe: หน้าประวัติไม่มีปัญหาระดับ serious/critical (${scheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme })
      await page.route("**/api/history*", (route) =>
        json(route, {
          items: [
            item("AAAAAAAAAAA", "คลิปที่โหลดครบ", ["video", "audio", "subtitle", "contact_sheet"], 3),
            item("BBBBBBBBBBB", "คลิปที่แค่เปิดดู", [], 90),
          ],
          total: 120,
        }),
      )
      await mockThumbnails(page)
      await page.goto("/history")
      await expect(page.getByRole("link", { name: "คลิปที่โหลดครบ" })).toBeVisible()
      await expect(page.locator("html")).toHaveClass(scheme === "dark" ? /dark/ : /light/)
      expect(await seriousViolations(page)).toEqual([])
    })
  }

  test("axe: หน้าว่าง และผลค้นหาไม่พบ (dark)", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "dark" })
    await page.route("**/api/history*", (route) => json(route, { items: [], total: 0 }))
    await page.goto("/history")
    await expect(page.getByText("ยังไม่มีประวัติ", { exact: true })).toBeVisible()
    expect(await seriousViolations(page)).toEqual([])
    await page.goto("/history?q=ไม่มี")
    await expect(page.getByText("ไม่พบคลิปที่ตรงกับ “ไม่มี”")).toBeVisible()
    expect(await seriousViolations(page)).toEqual([])
  })
})
