import { analyzeSettled } from "./axe-settled"
import { expect, test, type Locator, type Page, type Route } from "@playwright/test"

import type { Job, QueueState } from "../src/lib/types"

import { openQueueSheet } from "./queue-helpers"

// เมนูบนหัว (ประวัติ) และแถบคิว/ชีตคิว/หน้าต่างยืนยันปิดโปรแกรมของ layout
// โปรเจกต์ chromium ห้ามสร้างงานจริง: ทุกเทสในไฟล์นี้ตอบ /api/jobs /api/queue /api/events ด้วย page.route

const noOverflow = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)

async function seriousViolations(page: Page) {
  const results = await analyzeSettled(page)
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.map((n) => n.target.join(" ")).slice(0, 5) }))
}

const dockOffset = (page: Page) =>
  page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--dock-bottom-offset").trim())

// ---------- เมนู ----------

test.describe("เมนูบนหัว: ประวัติ", () => {
  test.beforeEach(async ({ page }) => {
    await mockQueue(page, [])
  })

  test("ลิงก์ประวัติอยู่ระหว่างหน้าแรกกับตั้งค่า และเป็นหน้าปัจจุบันที่ /history", async ({ page }) => {
    await page.goto("/")
    const nav = page.getByRole("navigation", { name: "เมนูหลัก" })
    await expect(nav.getByRole("link")).toHaveText(["หน้าแรก", "ประวัติ", "ตั้งค่า"])
    const history = nav.getByRole("link", { name: "ประวัติ" })
    await expect(history).toHaveAttribute("href", "/history")
    await expect(history).not.toHaveAttribute("aria-current", "page")
    // /settings พาไปแท็บแรกของหน้าตั้งค่าเอง (router)
    await expect(nav.getByRole("link", { name: "ตั้งค่า" })).toHaveAttribute("href", "/settings")

    await page.goto("/history")
    await expect(nav.getByRole("link", { name: "ประวัติ" })).toHaveAttribute("aria-current", "page")
    await expect(nav.getByRole("link", { name: "หน้าแรก" })).not.toHaveAttribute("aria-current", "page")
  })

  test("จอ 360 px: เมนูเหลือแต่ไอคอน มีชื่อสำหรับโปรแกรมอ่านหน้าจอ และ tooltip", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 800 })
    await page.goto("/")
    const nav = page.getByRole("navigation", { name: "เมนูหลัก" })
    for (const name of ["หน้าแรก", "ประวัติ", "ตั้งค่า"]) {
      const link = nav.getByRole("link", { name, exact: true })
      await expect(link).toBeVisible()
      await expect(link.getByText(name, { exact: true })).toBeHidden()
    }
    await nav.getByRole("link", { name: "ประวัติ" }).hover()
    await expect(page.locator('[data-slot="tooltip-content"]')).toHaveText("ประวัติ")
    expect(await noOverflow(page)).toBe(true)
  })

  for (const width of [360, 640]) {
    test(`จอ ${width} px: หน้าแรก ประวัติ ตั้งค่า ไม่ล้นแนวนอน`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 })
      for (const path of ["/", "/history", "/settings/health"]) {
        await page.goto(path)
        await expect(page.getByRole("navigation", { name: "เมนูหลัก" })).toBeVisible()
        expect(await noOverflow(page), path).toBe(true)
      }
    })
  }
})

// ---------- แถบคิวและชีตคิว (ข้อมูลปลอม) ----------

const RUNNING = "0192a000-0000-7000-8000-000000000001"
const QUEUED_A = "0192a000-0000-7000-8000-000000000002"
const QUEUED_B = "0192a000-0000-7000-8000-000000000003"
const FAILED = "0192a000-0000-7000-8000-000000000004"
const DONE = "0192a000-0000-7000-8000-000000000005"

const VIDEO_PARAMS = { maxQuality: false, splitChapters: false as const, noAudio: false, audioLanguage: "original" }

function job(over: Partial<Job> & Pick<Job, "id" | "status">): Job {
  return {
    videoId: "aqz-KE-bpKQ",
    title: "Big Buck Bunny 60fps 4K - Official Blender Foundation Short Film",
    kind: "video",
    params: VIDEO_PARAMS,
    position: 1,
    createdAt: "2026-10-01T10:00:00+00:00",
    ...over,
  }
}

function sampleJobs(): Job[] {
  return [
    job({
      id: RUNNING,
      status: "running",
      title: "คลิปที่กำลังโหลด ชื่อยาวมากเพื่อดูว่าตัดคำได้โดยไม่ล้นจอแม้หน้าต่างแคบ",
      stage: "downloading_video",
      progress: 0.42,
      speedBps: 2_400_000,
      etaS: 65,
      startedAt: "2026-10-01T10:00:01+00:00",
    }),
    job({ id: QUEUED_A, status: "queued", title: "คลิปรอคิว ก", position: 2 }),
    job({ id: QUEUED_B, status: "queued", title: "คลิปรอคิว ข", position: 3 }),
    job({
      id: FAILED,
      status: "failed",
      title: "คลิปที่ยูทูปไม่ส่งไฟล์",
      kind: "audio",
      params: { format: "m4a", splitChapters: false, audioLanguage: "original" },
      error: { code: "E_YT_REFUSED", message: "ยูทูปไม่ยอมส่งไฟล์ของคลิปนี้ตอนนี้ ลองใหม่ภายหลัง", detail: "HTTP Error 403: Forbidden" },
      finishedAt: "2026-10-01T10:00:05+00:00",
    }),
    job({
      id: DONE,
      status: "done",
      title: "คลิปที่โหลดเสร็จ",
      notes: [{ code: "AUDIO_LANG_FALLBACK", message: "คลิปนี้ไม่มีเสียงภาษาที่เลือก ใช้เสียงต้นฉบับแทน" }],
      outputs: [{ index: 0, name: "คลิปที่โหลดเสร็จ.mp4", sizeBytes: 12_000_000 }],
      finishedAt: "2026-10-01T10:00:04+00:00",
    }),
  ]
}

const NOT_PAUSED: QueueState = { pausedUntil: null, reason: null, concurrency: 2 }

type MockOptions = { queue?: QueueState; events?: string; eventsAfterJobs?: boolean; jobsAfterEvents?: Job[] }

/**
 * ตอบ GET /api/jobs และ /api/queue ด้วยข้อมูลปลอม · /api/events = สตรีมที่ส่งเหตุการณ์ที่ให้มาแล้วจบ
 * (retry ยาว เบราว์เซอร์จะไม่ต่อใหม่ระหว่างเทส) · eventsAfterJobs = ค้างสตรีมไว้จนเทสเรียก releaseEvents()
 * (หลังเห็นรายการงานบนหน้าแล้ว: เหตุการณ์ที่มาก่อนแคชมีรายการงานถูกข้าม · เดิมหน่วง 300 ms หลังตอบรายการ runner ที่ช้าไม่พอ)
 * · jobsAfterEvents = รายการที่ตอบตั้งแต่ครั้งที่สอง (หน้าเว็บโหลดใหม่ตอน SSE ต่อติด backend จริงตอบสถานะหลังเหตุการณ์)
 */
async function mockQueue(page: Page, jobs: Job[], opts: MockOptions = {}) {
  let releaseEvents!: () => void
  const eventsHeld = new Promise<void>((resolve) => (releaseEvents = resolve))
  let jobsCalls = 0
  await page.route(/\/api\/jobs(\?.*)?$/, async (route: Route) => {
    if (route.request().method() !== "GET") return route.fallback()
    const body = jobsCalls > 0 && opts.jobsAfterEvents ? opts.jobsAfterEvents : jobs
    jobsCalls += 1
    await route.fulfill({ json: { jobs: body } })
  })
  await page.route("**/api/queue", (route) => route.fulfill({ json: opts.queue ?? NOT_PAUSED }))
  await page.route("**/api/events", async (route) => {
    if (opts.eventsAfterJobs) await eventsHeld
    await route.fulfill({
      status: 200,
      headers: { "Content-Type": "text/event-stream; charset=utf-8", "Cache-Control": "no-cache" },
      body: `retry: 600000\n\n${opts.events ?? ""}`,
    })
  })
  return { releaseEvents }
}

/**
 * ลูกศรขึ้นระหว่างลากด้วยคีย์บอร์ด · dnd-kit เริ่มฟังปุ่มและวัดตำแหน่งแถวหลังประกาศ "ยก…" เล็กน้อย
 * กดเร็วกว่านั้นปุ่มหาย จึงกดซ้ำจนได้ยินตำแหน่งใหม่ (แถวบนสุดแล้วกดขึ้นอีกไม่มีผล)
 */
async function moveUpWhileDragging(page: Page, sheet: Locator, announced: string) {
  await expect(async () => {
    await page.keyboard.press("ArrowUp")
    await expect(sheet.getByText(announced)).toBeAttached({ timeout: 500 })
  }).toPass()
}

const sse = (name: string, data: unknown) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`

test.describe("แถบคิวงาน (ข้อมูลปลอม)", () => {
  test("ไม่มีงาน = ไม่มีแถบ และ --dock-bottom-offset เป็น 0px", async ({ page }) => {
    await mockQueue(page, [])
    await page.goto("/")
    await expect(page.getByRole("textbox")).toBeVisible()
    await expect(page.getByRole("region", { name: "คิวงาน" })).toHaveCount(0)
    expect(await dockOffset(page)).toBe("0px")
  })

  test("แถบแสดงงานล่าสุด ขั้นตอน ความเร็ว เวลาที่เหลือ และจำนวนงาน · ตั้ง --dock-bottom-offset เท่าความสูงแถบ", async ({ page }) => {
    await mockQueue(page, sampleJobs())
    await page.goto("/")
    const bar = page.getByRole("region", { name: "คิวงาน" })
    await expect(bar).toContainText("คลิปที่กำลังโหลด")
    await expect(bar).toContainText("โหลดภาพ · 42% · 2.4 MB/วินาที · เหลือ 1:05")
    await expect(bar).toContainText("กำลังทำ 1 · รอ 2 · เสร็จ 1")
    const open = bar.getByRole("button", { name: "เปิดคิวงาน" })
    await expect(open).toHaveAttribute("aria-expanded", "false")
    await expect(bar.getByTestId("queue-bar-progress")).toHaveAttribute("style", /width: 42(\.\d+)?%/)

    const box = await bar.boundingBox()
    expect(await dockOffset(page)).toBe(`${Math.ceil(box!.height)}px`)
  })

  test("ชีตคิว: กลุ่ม แถวแต่ละแบบ รายละเอียดข้อผิดพลาด ลิงก์ดาวน์โหลด และปิดชีต", async ({ page }) => {
    await mockQueue(page, sampleJobs())
    await page.goto("/")
    const sheet = await openQueueSheet(page)
    await expect(sheet.getByText("ปิดแท็บนี้ได้ งานยังทำต่อ")).toBeVisible()
    await expect(sheet.getByRole("heading", { level: 3 })).toHaveText(["กำลังทำ", "รอ", "ผิดพลาด", "เสร็จแล้ว"])

    const running = sheet.locator(`[data-job-id="${RUNNING}"]`)
    await expect(running).toContainText("วิดีโอ")
    await expect(running.getByRole("progressbar")).toBeVisible()
    await expect(running.getByRole("button", { name: /^ยกเลิกงาน คลิปที่กำลังโหลด/ })).toBeVisible()

    await expect(sheet.getByRole("button", { name: "ลากเพื่อเปลี่ยนลำดับ คลิปรอคิว ก" })).toHaveAttribute(
      "aria-roledescription",
      "รายการที่ลากเปลี่ยนลำดับได้",
    )
    await expect(sheet.getByRole("button", { name: "ยกเลิกงาน คลิปรอคิว ข" })).toBeVisible()

    const failed = sheet.locator(`[data-job-id="${FAILED}"]`)
    await expect(failed).toContainText("ยูทูปไม่ยอมส่งไฟล์ของคลิปนี้ตอนนี้ ลองใหม่ภายหลัง")
    await expect(failed.getByText("รหัส E_YT_REFUSED")).toBeHidden()
    await failed.getByRole("button", { name: "ดูรายละเอียด" }).click()
    await expect(failed.getByText("รหัส E_YT_REFUSED")).toBeVisible()
    await expect(failed.getByText("HTTP Error 403: Forbidden")).toBeVisible()
    // M6 รอบ B: ปุ่มคัดลอกรายงานแทนปุ่มคัดลอกรายละเอียดเดิม
    await expect(failed.getByRole("button", { name: "คัดลอกข้อมูลแจ้งปัญหา" })).toBeVisible()
    await expect(failed.getByRole("button", { name: "คัดลอกรายละเอียด" })).toHaveCount(0)
    await expect(failed.getByRole("button", { name: "ลองใหม่ คลิปที่ยูทูปไม่ส่งไฟล์" })).toBeVisible()

    const done = sheet.locator(`[data-job-id="${DONE}"]`)
    await expect(done).toContainText("คลิปที่โหลดเสร็จ.mp4")
    await expect(done).toContainText("คลิปนี้ไม่มีเสียงภาษาที่เลือก ใช้เสียงต้นฉบับแทน")
    const download = done.getByRole("link", { name: "ดาวน์โหลด คลิปที่โหลดเสร็จ.mp4" })
    await expect(download).toHaveAttribute("href", `/api/jobs/${DONE}/outputs/0`)
    await expect(download).toHaveAttribute("download", "คลิปที่โหลดเสร็จ.mp4")
    await expect(done.getByRole("button", { name: "เปิดโฟลเดอร์ของ คลิปที่โหลดเสร็จ" })).toBeVisible()

    const bar = page.getByRole("region", { name: "คิวงาน", includeHidden: true })
    await expect(bar.locator("button[aria-expanded]")).toHaveAttribute("aria-expanded", "true")
    await sheet.getByRole("button", { name: "ปิดคิวงาน" }).click()
    await expect(sheet).toBeHidden()
  })

  test("แถวงานที่พลาดด้วย E_UNKNOWN กางรายละเอียดไว้ตั้งแต่แรก เห็นปุ่มคัดลอกรายงานโดยไม่ต้องกด (M6 รอบ B R1)", async ({ page }) => {
    await mockQueue(page, [
      job({
        id: FAILED,
        status: "failed",
        title: "คลิปที่พังแบบไม่รู้สาเหตุ",
        error: { code: "E_UNKNOWN", message: "เกิดข้อผิดพลาดที่ไม่คาดคิด", detail: "Traceback: boom" },
        finishedAt: "2026-10-01T10:00:05+00:00",
      }),
    ])
    await page.goto("/")
    const sheet = await openQueueSheet(page)
    const failed = sheet.locator(`[data-job-id="${FAILED}"]`)
    await expect(failed.getByText("รหัส E_UNKNOWN")).toBeVisible()
    await expect(failed.getByText("Traceback: boom")).toBeVisible()
    await expect(failed.getByRole("button", { name: "คัดลอกข้อมูลแจ้งปัญหา" })).toBeVisible()
  })

  test("เปิดโฟลเดอร์ไม่เจอไฟล์ (404) = toast ไม่พบไฟล์", async ({ page }) => {
    await mockQueue(page, sampleJobs())
    await page.route(`**/api/jobs/${DONE}/outputs/0/reveal`, (route) =>
      route.fulfill({ status: 404, json: { error: { code: "E_NOT_FOUND", message: "ไม่พบ", detail: null } } }),
    )
    await page.goto("/")
    const sheet = await openQueueSheet(page)
    await sheet.getByRole("button", { name: "เปิดโฟลเดอร์ของ คลิปที่โหลดเสร็จ" }).click()
    await expect(page.getByText("ไม่พบไฟล์ อาจถูกย้ายหรือลบไปแล้ว")).toBeVisible()
  })

  for (const scheme of ["light", "dark"] as const) {
    test(`axe (${scheme}): แถบคิวและชีตที่เปิดอยู่ไม่มีปัญหาร้ายแรง`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme })
      await mockQueue(page, sampleJobs(), { queue: { pausedUntil: new Date(Date.now() + 600_000).toISOString(), reason: "E_BOT_CHECK", concurrency: 2 } })
      await page.goto("/")
      await expect(page.getByRole("region", { name: "คิวงาน" })).toBeVisible()
      expect(await seriousViolations(page)).toEqual([])
      const sheet = await openQueueSheet(page)
      await sheet.locator(`[data-job-id="${FAILED}"]`).getByRole("button", { name: "ดูรายละเอียด" }).click()
      expect(await seriousViolations(page)).toEqual([])
    })
  }

  for (const width of [360, 640]) {
    test(`จอ ${width} px: แถบขึ้นสองบรรทัดได้ ชีตเปิดอยู่ก็ไม่ล้นแนวนอน`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 })
      await mockQueue(page, sampleJobs(), { queue: { pausedUntil: new Date(Date.now() + 600_000).toISOString(), reason: "E_BOT_CHECK", concurrency: 2 } })
      await page.goto("/")
      const bar = page.getByRole("region", { name: "คิวงาน" })
      await expect(bar).toBeVisible()
      expect(await noOverflow(page)).toBe(true)
      const barBox = await bar.boundingBox()
      expect(barBox!.width).toBeLessThanOrEqual(width)
      const sheet = await openQueueSheet(page)
      expect(await noOverflow(page)).toBe(true)
      const sheetBox = await sheet.boundingBox()
      expect(sheetBox!.width).toBeLessThanOrEqual(width)
      expect(sheetBox!.height).toBeLessThanOrEqual(800 * 0.8 + 1)
    })
  }

  test("คิวหยุดพัก: แจ้งในแถบและในชีตพร้อมนับถอยหลัง · ลองต่อเลย = ส่ง resume แล้วแจ้งหายไป", async ({ page }) => {
    const until = new Date(Date.now() + 600_000).toISOString()
    await mockQueue(page, sampleJobs(), { queue: { pausedUntil: until, reason: "E_BOT_CHECK", concurrency: 2 } })
    let resumed = 0
    await page.route("**/api/queue/resume", (route) => {
      resumed += 1
      return route.fulfill({ json: { ok: true } })
    })
    await page.goto("/")
    const bar = page.getByRole("region", { name: "คิวงาน" })
    const alert = bar.getByTestId("queue-paused")
    await expect(alert).toContainText("พักคิวไว้ชั่วคราว")
    await expect(alert).toContainText(/คิวจะเริ่มต่อเองในอีก (10:00|9:5\d)/)

    const sheet = await openQueueSheet(page)
    await expect(sheet.getByTestId("queue-paused")).toContainText(/(10:00|9:5\d)/)
    await sheet.getByRole("button", { name: "ลองต่อเลย" }).click()
    await expect(sheet.getByTestId("queue-paused")).toHaveCount(0)
    expect(resumed).toBe(1)
  })

  test("ลากเปลี่ยนลำดับด้วยคีย์บอร์ด แต่ backend ไม่รับ = กลับลำดับเดิม พร้อม toast", async ({ page }) => {
    await mockQueue(page, sampleJobs())
    const bodies: unknown[] = []
    await page.route("**/api/jobs/order", (route) => {
      bodies.push(route.request().postDataJSON())
      return route.fulfill({ status: 500, json: { error: { code: "E_UNKNOWN", message: "ผิดพลาด", detail: null } } })
    })
    await page.goto("/")
    const sheet = await openQueueSheet(page)
    const handles = sheet.getByRole("button", { name: /^ลากเพื่อเปลี่ยนลำดับ/ })
    await expect(handles).toHaveCount(2)

    await sheet.getByRole("button", { name: "ลากเพื่อเปลี่ยนลำดับ คลิปรอคิว ข" }).focus()
    await page.keyboard.press("Space")
    await expect(sheet.getByText("ยก คลิปรอคิว ข ขึ้นแล้ว", { exact: false })).toBeAttached()
    await moveUpWhileDragging(page, sheet, "คลิปรอคิว ข อยู่ลำดับที่ 1")
    await page.keyboard.press("Space")
    await expect(sheet.getByText("วาง คลิปรอคิว ข ไว้ลำดับที่ 1")).toBeAttached()

    await expect.poll(() => bodies).toEqual([{ ids: [QUEUED_B, QUEUED_A] }])
    await expect(page.getByText("ทำรายการนี้ไม่สำเร็จ ลองรีเฟรชหน้าเว็บ")).toBeVisible()
    await expect(handles.nth(0)).toHaveAccessibleName("ลากเพื่อเปลี่ยนลำดับ คลิปรอคิว ก")
    await expect(handles.nth(1)).toHaveAccessibleName("ลากเพื่อเปลี่ยนลำดับ คลิปรอคิว ข")
  })

  test("Esc ระหว่างลากด้วยคีย์บอร์ด = ยกเลิกการลากอย่างเดียว ชีตยังเปิด ลำดับเดิม", async ({ page }) => {
    await mockQueue(page, sampleJobs())
    let reorders = 0
    await page.route("**/api/jobs/order", (route) => {
      reorders += 1
      return route.fulfill({ json: { ok: true } })
    })
    await page.goto("/")
    const sheet = await openQueueSheet(page)
    await sheet.getByRole("button", { name: "ลากเพื่อเปลี่ยนลำดับ คลิปรอคิว ข" }).focus()
    await page.keyboard.press("Space")
    await expect(sheet.getByText("ยก คลิปรอคิว ข ขึ้นแล้ว", { exact: false })).toBeAttached()
    await moveUpWhileDragging(page, sheet, "คลิปรอคิว ข อยู่ลำดับที่ 1")
    await page.keyboard.press("Escape")
    await expect(sheet.getByText("ยกเลิกการย้าย คลิปรอคิว ข")).toBeAttached()

    await expect(sheet).toBeVisible()
    const handles = sheet.getByRole("button", { name: /^ลากเพื่อเปลี่ยนลำดับ/ })
    await expect(handles.nth(0)).toHaveAccessibleName("ลากเพื่อเปลี่ยนลำดับ คลิปรอคิว ก")
    await expect(handles.nth(1)).toHaveAccessibleName("ลากเพื่อเปลี่ยนลำดับ คลิปรอคิว ข")
    expect(reorders).toBe(0)

    // ไม่ได้ลากอยู่แล้ว Esc = ปิดชีตตามปกติ
    await page.keyboard.press("Escape")
    await expect(sheet).toBeHidden()
  })

  test("ยังไม่รู้ %: เส้นอำพันในแถบเต็มเส้นแบบกะพริบ และแถบความคืบหน้าในชีตไม่ว่าง", async ({ page }) => {
    const probing = job({ id: RUNNING, status: "running", title: "คลิปที่กำลังดึงข้อมูล", stage: "probing", startedAt: "2026-10-01T10:00:01+00:00" })
    await mockQueue(page, [probing])
    await page.goto("/")
    const bar = page.getByRole("region", { name: "คิวงาน" })
    await expect(bar).toContainText("ดึงข้อมูล")
    const line = bar.getByTestId("queue-bar-progress")
    await expect(line).toHaveAttribute("data-indeterminate", "")
    const [lineBox, barBox] = [await line.boundingBox(), await bar.boundingBox()]
    expect(Math.round(lineBox!.width)).toBe(Math.round(barBox!.width))
    expect(lineBox!.height).toBe(4)

    const sheet = await openQueueSheet(page)
    const indicator = sheet.locator(`[data-job-id="${RUNNING}"] [data-slot=progress-indicator]`)
    await expect(indicator).toHaveAttribute("data-indeterminate", "")
    const box = await indicator.boundingBox()
    expect(box!.width).toBeGreaterThan(10)
  })

  test("toast เมื่องานเสร็จหรือพลาดระหว่างเปิดหน้าอยู่ · ดูรายละเอียด = เปิดชีตที่แถวนั้น", async ({ page }) => {
    const jobs = sampleJobs()
    const finishedOutputs = [{ index: 0, name: "a.mp4", sizeBytes: 1 }]
    const networkError = { code: "E_NETWORK", message: "เน็ตหลุด ลองใหม่อีกครั้ง", detail: "timed out" }
    const jobsAfterEvents = jobs.map((j) =>
      j.id === RUNNING
        ? { ...j, status: "done" as const, progress: 1, stage: undefined, speedBps: undefined, etaS: undefined, finishedAt: "2026-10-01T10:01:00+00:00", outputs: finishedOutputs }
        : j.id === QUEUED_A
          ? { ...j, status: "failed" as const, error: networkError, finishedAt: "2026-10-01T10:01:01+00:00" }
          : j,
    )
    const { releaseEvents } = await mockQueue(page, jobs, {
      eventsAfterJobs: true,
      jobsAfterEvents,
      events:
        sse("job.updated", { id: RUNNING, status: "done", progress: 1, stage: null, speedBps: null, etaS: null, finishedAt: "2026-10-01T10:01:00+00:00", outputs: finishedOutputs }) +
        sse("job.updated", {
          id: QUEUED_A,
          status: "failed",
          error: networkError,
          finishedAt: "2026-10-01T10:01:01+00:00",
        }),
    })
    await page.goto("/")
    // แถบคิวขึ้น = รายการงานอยู่ในแคชแล้ว เหตุการณ์ที่ตามมาจึงเทียบกับสถานะเดิมได้
    await expect(page.getByRole("region", { name: "คิวงาน" })).toBeVisible()
    releaseEvents()
    await expect(page.getByText("โหลดเสร็จแล้ว · คลิปที่กำลังโหลด", { exact: false })).toBeVisible()
    const failedToast = page.locator("[data-sonner-toast]").filter({ hasText: "โหลดไม่สำเร็จ · คลิปรอคิว ก" })
    await expect(failedToast).toContainText("เน็ตหลุด ลองใหม่อีกครั้ง")
    await failedToast.getByRole("button", { name: "ดูรายละเอียด" }).click()
    const sheet = page.getByRole("dialog", { name: "คิวงาน" })
    const row = sheet.locator(`[data-job-id="${QUEUED_A}"]`)
    await expect(row.getByText("รหัส E_NETWORK")).toBeVisible()
    await expect(row).toBeInViewport()
    await expect(row.getByRole("button", { name: "ดูรายละเอียด" })).toBeFocused()
  })

  test("โหลดหน้าใหม่: งานในประวัติไม่เด้ง toast", async ({ page }) => {
    await mockQueue(page, sampleJobs())
    await page.goto("/")
    await expect(page.getByRole("region", { name: "คิวงาน" })).toBeVisible()
    await expect(page.locator("[data-sonner-toast]")).toHaveCount(0)
  })
})

// ---------- ยืนยันปิดโปรแกรม (W7) ----------

test.describe("ยืนยันปิดโปรแกรมเมื่อมีงานค้าง", () => {
  test("tray เปิด /?confirmShutdown=1: บอกจำนวนงาน · กลับไปก่อน = ลบพารามิเตอร์ · ปิดเลย = ส่ง force แล้วขึ้นหน้าปิดโปรแกรม", async ({ page }) => {
    await mockQueue(page, sampleJobs())
    const bodies: unknown[] = []
    await page.route("**/api/shutdown", (route) => {
      bodies.push(route.request().postDataJSON())
      return route.fulfill({ json: { ok: true } })
    })
    await page.goto("/?confirmShutdown=1")
    const dialog = page.getByRole("alertdialog", { name: "ปิดโปรแกรมตอนนี้?" })
    await expect(dialog).toContainText("มีงานค้าง 3 งาน ถ้าปิดตอนนี้จะหยุดกลางคัน และลองใหม่ได้ทีหลัง")
    await dialog.getByRole("button", { name: "กลับไปก่อน" }).click()
    await expect(dialog).toBeHidden()
    await expect(page).toHaveURL((url) => !url.searchParams.has("confirmShutdown"))
    expect(bodies).toEqual([])

    await page.goto("/?confirmShutdown=1")
    await page.getByRole("alertdialog").getByRole("button", { name: "ปิดเลย" }).click()
    await expect(page.getByText("ปิดโปรแกรมแล้ว")).toBeVisible()
    expect(bodies).toEqual([{ force: true }])
    await expect(page.getByRole("region", { name: "คิวงาน" })).toHaveCount(0)
    expect(await dockOffset(page)).toBe("0px")
  })

  test("ตั้งค่า > ปิดโปรแกรม ตอบ 409 = หน้าต่างยืนยันพร้อมจำนวนงานจาก backend", async ({ page }) => {
    await mockQueue(page, [])
    const bodies: unknown[] = []
    await page.route("**/api/shutdown", (route) => {
      const body = route.request().postDataJSON() as { force: boolean }
      bodies.push(body)
      return body.force
        ? route.fulfill({ json: { ok: true } })
        : route.fulfill({
            status: 409,
            json: { error: { code: "E_JOBS_PENDING", message: "มีงานค้าง", detail: null }, pendingJobs: 4 },
          })
    })
    await page.goto("/settings/health")
    await page.getByRole("button", { name: "ปิดโปรแกรม" }).click()
    const dialog = page.getByRole("alertdialog", { name: "ปิดโปรแกรมตอนนี้?" })
    await expect(dialog).toContainText("มีงานค้าง 4 งาน")
    await dialog.getByRole("button", { name: "ปิดเลย" }).click()
    await expect(page.getByText("ปิดโปรแกรมแล้ว")).toBeVisible()
    expect(bodies).toEqual([{ force: false }, { force: true }])
  })
})
