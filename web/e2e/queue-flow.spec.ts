import { analyzeSettled } from "./axe-settled"
import { expect, test, type APIRequestContext, type Locator, type Page } from "@playwright/test"

import type { Job, NewJob } from "../src/lib/types"

import { cancelJobsFor, enqueue, gotoReady, listJobs, openQueueSheet, resumeQueue, token, waitForJob } from "./queue-helpers"

// W4 แถบคิว + ชีตคิว และ W7 ยืนยันปิดโปรแกรม กับคิวจริงของ backend ปลอม (โปรเจกต์ queue, ทีละเทส)
// คลิปของไฟล์นี้ (C14): SLOWDOWNLD1..4, BOTCHECKDL1, NETRETRYDL1, REFUSEDDL01 · พฤติกรรมอยู่ใน tests/fixtures/downloads/behaviors.json

const SLOW = ["SLOWDOWNLD1", "SLOWDOWNLD2", "SLOWDOWNLD3", "SLOWDOWNLD4"]
const ALL = [...SLOW, "BOTCHECKDL1", "NETRETRYDL1", "REFUSEDDL01"]
const TITLE: Record<string, string> = {
  SLOWDOWNLD1: "คลิปโหลดช้า 1",
  SLOWDOWNLD2: "คลิปโหลดช้า 2",
  SLOWDOWNLD3: "คลิปโหลดช้า 3",
  SLOWDOWNLD4: "คลิปโหลดช้า 4",
  BOTCHECKDL1: "คลิปติดบอท",
  NETRETRYDL1: "คลิปเน็ตหลุด",
  REFUSEDDL01: "คลิปที่ยูทูปไม่ส่งไฟล์",
}

test.describe.configure({ mode: "serial" })

const video = (videoId: string): NewJob => ({
  videoId,
  kind: "video",
  params: { maxQuality: false, splitChapters: false, noAudio: false, audioLanguage: "original" },
  title: TITLE[videoId],
})

/** videoId ของงานที่รอคิว เรียงตามลำดับคิวจริงของ backend */
async function queuedOrder(request: APIRequestContext): Promise<string[]> {
  return (await listJobs(request, "queued")).sort((a, b) => a.position - b.position).map((j) => j.videoId)
}

/** ลำดับของ SLOWDOWNLD3 กับ 4 ในคิว (งานอื่นในคิวไม่สน) */
async function order34(request: APIRequestContext): Promise<string[]> {
  return (await queuedOrder(request)).filter((id) => id === "SLOWDOWNLD3" || id === "SLOWDOWNLD4")
}

async function getConcurrency(page: Page): Promise<number> {
  const response = await page.request.get("/api/settings")
  expect(response.ok(), `GET /api/settings ตอบ ${response.status()}`).toBe(true)
  return ((await response.json()) as { concurrency: number }).concurrency
}

/** ตั้งจำนวนงานพร้อมกันของ backend คิว (ต้องคืนค่าเดิมเสมอ spec อื่นในโปรเจกต์ queue ใช้ backend เดียวกัน) */
async function setConcurrency(page: Page, n: number) {
  const response = await page.request.fetch("/api/settings", {
    method: "PATCH",
    headers: { "X-Toolkit-Token": await token(page), Origin: new URL(page.url()).origin },
    data: { concurrency: n },
  })
  expect(response.ok(), `PATCH /api/settings ตอบ ${response.status()}`).toBe(true)
}

const row = (sheet: Locator, job: Job) => sheet.locator(`[data-job-id="${job.id}"]`)

const noOverflow = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)

async function seriousViolations(page: Page) {
  const results = await analyzeSettled(page)
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.map((n) => n.target.join(" ")).slice(0, 5) }))
}

/** ลากด้วยเมาส์ทีละนิด (dnd-kit เริ่มลากเมื่อขยับเกิน 4 px) จากที่จับของงานหนึ่งไปเหนือแถวของอีกงาน */
/**
 * หลังยกด้วยคีย์บอร์ด dnd-kit ยังต้องวัดตำแหน่งแถวและเริ่มฟังปุ่มลูกศรอีกเล็กน้อย (หลังประกาศ "ยก…" ขึ้นแล้ว)
 * กดลูกศรเร็วกว่านั้นปุ่มหาย · รอสองเฟรมให้ขั้นนั้นจบก่อน
 */
async function dndReady(page: Page) {
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(resolve, 0)))))
}

async function mouseDrag(page: Page, handle: Locator, target: Locator) {
  const from = (await handle.boundingBox())!
  const to = (await target.boundingBox())!
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2)
  await page.mouse.down()
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2 - 8, { steps: 4 })
  await page.mouse.move(from.x + from.width / 2, to.y + to.height / 4, { steps: 12 })
  await page.mouse.up()
}

test.afterAll(async ({ request }) => {
  await resumeQueue(request)
  await cancelJobsFor(request, ALL)
})

test.describe("W4 คิวงาน", () => {
  test("ส่ง 4 งาน: แถบนับงาน · โหลดหน้าใหม่ยังเห็นงานเดิม · ยกเลิกงานที่กำลังทำ", async ({ page, request }) => {
    test.setTimeout(60_000)
    await gotoReady(page)
    const jobs = await enqueue(request, SLOW.map(video))

    const bar = page.getByRole("region", { name: "คิวงาน" })
    await expect(bar).toContainText("กำลังทำ 2 · รอ 2", { timeout: 15_000 })
    await expect(bar).toContainText(/คลิปโหลดช้า [12]/)

    // AC-Q-04: โหลดหน้าใหม่ = แถวเดิมครบ
    let sheet = await openQueueSheet(page)
    for (const job of jobs) await expect(row(sheet, job)).toBeVisible()
    await page.reload()
    sheet = await openQueueSheet(page)
    for (const job of jobs) await expect(row(sheet, job)).toBeVisible()

    // AC-Q-07: ยกเลิกงานที่กำลังทำ = แถวหายภายใน 3 วิ
    const running = (await listJobs(request, "running")).find((j) => SLOW.includes(j.videoId))!
    const runningRow = row(sheet, running)
    await runningRow.getByRole("button", { name: `ยกเลิกงาน ${TITLE[running.videoId]}` }).click()
    await expect(runningRow).toHaveCount(0, { timeout: 3_000 })

    await cancelJobsFor(request, SLOW)
    await expect
      .poll(async () => (await listJobs(request)).filter((j) => SLOW.includes(j.videoId) && (j.status === "queued" || j.status === "running")))
      .toEqual([])
  })

  test("AC-Q-06 ลากเปลี่ยนลำดับ (เมาส์/คีย์บอร์ด): backend เก็บลำดับ โหลดหน้าใหม่ยังอยู่ และ 4 เริ่มก่อน 3", async ({ page, request }) => {
    test.setTimeout(120_000)
    await gotoReady(page)
    // ทำทีละงานระหว่างลาก ช่องว่างถัดไปจะว่างหลังงานแรกโหลดเสร็จ (~10 วิ) จึงมีเวลาพอ
    const original = await getConcurrency(page)
    await setConcurrency(page, 1)
    try {
      const jobs = await enqueue(request, SLOW.map(video))
      const byVideo = Object.fromEntries(jobs.map((j) => [j.videoId, j]))
      let sheet = await openQueueSheet(page)
      const handle = (id: string) => sheet.getByRole("button", { name: `ลากเพื่อเปลี่ยนลำดับ ${TITLE[id]}` })
      await expect(handle("SLOWDOWNLD4")).toBeVisible()

      // เมาส์: ลาก 4 ขึ้นเหนือ 3
      await mouseDrag(page, handle("SLOWDOWNLD4"), row(sheet, byVideo.SLOWDOWNLD3))
      await expect.poll(() => order34(request)).toEqual(["SLOWDOWNLD4", "SLOWDOWNLD3"])

      // คีย์บอร์ด: ย้าย 4 ลงกลับที่เดิม แล้วย้ายขึ้นอีกครั้ง (Space · ลูกศร · Space)
      await handle("SLOWDOWNLD4").focus()
      await page.keyboard.press("Space")
      await expect(sheet.getByText(`ยก ${TITLE.SLOWDOWNLD4} ขึ้นแล้ว`, { exact: false })).toBeAttached()
      await dndReady(page)
      await page.keyboard.press("ArrowDown")
      await expect(sheet.getByText(new RegExp(`^${TITLE.SLOWDOWNLD4} อยู่ลำดับที่ \\d+$`))).toBeAttached()
      await page.keyboard.press("Space")
      await expect.poll(() => order34(request)).toEqual(["SLOWDOWNLD3", "SLOWDOWNLD4"])

      await handle("SLOWDOWNLD4").focus()
      await page.keyboard.press("Space")
      await expect(sheet.getByText(`ยก ${TITLE.SLOWDOWNLD4} ขึ้นแล้ว`, { exact: false })).toBeAttached()
      await dndReady(page)
      await page.keyboard.press("ArrowUp")
      await expect(sheet.getByText(new RegExp(`^${TITLE.SLOWDOWNLD4} อยู่ลำดับที่ \\d+$`))).toBeAttached()
      await page.keyboard.press("Space")
      await expect(sheet.getByText(new RegExp(`^วาง ${TITLE.SLOWDOWNLD4} ไว้ลำดับที่ \\d+$`))).toBeAttached()
      await expect.poll(() => order34(request)).toEqual(["SLOWDOWNLD4", "SLOWDOWNLD3"])

      // ลำดับคงอยู่หลังโหลดหน้าใหม่
      await page.reload()
      sheet = await openQueueSheet(page)
      const handles34 = sheet.getByRole("button", { name: /^ลากเพื่อเปลี่ยนลำดับ คลิปโหลดช้า [34]$/ })
      await expect(handles34).toHaveCount(2)
      await expect(handles34.first()).toHaveAccessibleName(`ลากเพื่อเปลี่ยนลำดับ ${TITLE.SLOWDOWNLD4}`)

      // กลับไปทำพร้อมกันตามเดิม แล้วรอจนทั้งสองงานเริ่ม: 4 ต้องเริ่มก่อน 3
      await setConcurrency(page, original)
      await expect
        .poll(
          async () => {
            const list = await listJobs(request)
            const four = list.find((j) => j.id === byVideo.SLOWDOWNLD4.id)?.startedAt
            const three = list.find((j) => j.id === byVideo.SLOWDOWNLD3.id)?.startedAt
            return four && three ? four < three : null
          },
          { timeout: 60_000 },
        )
        .toBe(true)
    } finally {
      await setConcurrency(page, original)
      await cancelJobsFor(request, SLOW)
    }
  })

  test("เน็ตหลุด: แถวบอกว่ากำลังลองใหม่ แล้วโหลดเสร็จพร้อม toast", async ({ page, request }) => {
    test.setTimeout(60_000)
    await gotoReady(page)
    const [job] = await enqueue(request, [video("NETRETRYDL1")])
    const sheet = await openQueueSheet(page)
    await expect(row(sheet, job)).toContainText("เน็ตหลุด กำลังลองใหม่ (ครั้งที่ 1/3)", { timeout: 20_000 })
    await expect(page.getByText(`โหลดเสร็จแล้ว · ${TITLE.NETRETRYDL1}`)).toBeVisible({ timeout: 20_000 })
    await expect(sheet.getByRole("region", { name: "เสร็จแล้ว", exact: true }).locator(`[data-job-id="${job.id}"]`)).toBeVisible()
  })

  test("ยูทูปไม่ส่งไฟล์: แถวผิดพลาด รายละเอียดมีรหัส · ลองใหม่ = กลับเข้าคิว", async ({ page, request }) => {
    test.setTimeout(60_000)
    await gotoReady(page)
    const [job] = await enqueue(request, [video("REFUSEDDL01")])
    await expect(page.getByText(`โหลดไม่สำเร็จ · ${TITLE.REFUSEDDL01}`)).toBeVisible({ timeout: 20_000 })
    const first = await waitForJob(request, (j) => j.id === job.id && j.status === "failed")
    const sheet = await openQueueSheet(page)
    const failed = row(sheet, job)
    await expect(failed).toContainText("ยูทูปไม่ยอมส่งไฟล์ของคลิปนี้ตอนนี้ ลองใหม่ภายหลัง")
    await failed.getByRole("button", { name: "ดูรายละเอียด" }).click()
    await expect(failed.getByText("รหัส E_YT_REFUSED")).toBeVisible()
    // M6 รอบ B: แถวที่พลาดมีปุ่มคัดลอกรายงานแทนปุ่มคัดลอกรายละเอียดเดิม
    await expect(failed.getByRole("button", { name: "คัดลอกข้อมูลแจ้งปัญหา" })).toBeVisible()
    await expect(failed.getByRole("button", { name: "คัดลอกรายละเอียด" })).toHaveCount(0)

    const retried = page.waitForResponse((r) => r.url().endsWith(`/api/jobs/${job.id}/retry`) && r.request().method() === "POST")
    await failed.getByRole("button", { name: `ลองใหม่ ${TITLE.REFUSEDDL01}` }).click()
    const response = await retried
    expect(response.status()).toBe(200)
    expect(((await response.json()) as Job).status).toBe("queued")
    // ลองใหม่แล้วพลาดอีก (fake ไม่ส่งไฟล์ทุกครั้ง) = รอบใหม่จบหลังรอบแรก
    await waitForJob(request, (j) => j.id === job.id && j.status === "failed" && (j.finishedAt ?? "") > (first.finishedAt ?? ""), {
      timeout: 20_000,
    })
  })

  test("งานที่เสร็จ: ดาวน์โหลดได้ไฟล์แนบ · เปิดโฟลเดอร์ตอบ ok", async ({ page, request }) => {
    const done = await waitForJob(request, (j) => j.videoId === "NETRETRYDL1" && j.status === "done")
    await page.goto("/")
    const sheet = await openQueueSheet(page)
    const doneRow = row(sheet, done)
    const link = doneRow.getByRole("link", { name: /^ดาวน์โหลด / })
    const href = await link.first().getAttribute("href")
    expect(href).toBe(`/api/jobs/${done.id}/outputs/0`)
    const file = await request.get(href!)
    expect(file.status()).toBe(200)
    expect(file.headers()["content-disposition"]).toMatch(/^attachment/)

    const revealed = page.waitForResponse((r) => r.url().endsWith(`/api/jobs/${done.id}/outputs/0/reveal`))
    await doneRow.getByRole("button", { name: `เปิดโฟลเดอร์ของ ${TITLE.NETRETRYDL1}` }).click()
    const response = await revealed
    expect(response.status()).toBe(200)
    expect(await response.json()).toEqual({ ok: true })
  })

  test("ติดบอท: แจ้งหยุดพักบนแถบและในชีตพร้อมนับถอยหลัง งานกลับไปรอ · ลองต่อเลย = โหลดต่อจนเสร็จ", async ({ page, request }) => {
    test.setTimeout(60_000)
    await gotoReady(page)
    const [job] = await enqueue(request, [video("BOTCHECKDL1")])
    const bar = page.getByRole("region", { name: "คิวงาน" })
    const barAlert = bar.getByTestId("queue-paused")
    await expect(barAlert).toContainText("พักคิวไว้ชั่วคราว", { timeout: 20_000 })
    await expect(barAlert).toContainText(/คิวจะเริ่มต่อเองในอีก (10:00|9:[45]\d)/)

    const sheet = await openQueueSheet(page)
    await expect(sheet.getByTestId("queue-paused")).toContainText(/(10:00|9:[45]\d)/)
    await expect(sheet.getByRole("region", { name: "รอ", exact: true }).locator(`[data-job-id="${job.id}"]`)).toBeVisible()
    expect((await listJobs(request, "queued")).map((j) => j.id)).toContain(job.id)

    await sheet.getByRole("button", { name: "ลองต่อเลย" }).click()
    await expect(sheet.getByTestId("queue-paused")).toHaveCount(0)
    await waitForJob(request, (j) => j.id === job.id && j.status === "done", { timeout: 30_000 })
    await expect(sheet.locator(`[data-job-id="${job.id}"]`)).toContainText(/\.mp4/)
  })

  test("แถบตั้ง --dock-bottom-offset เท่าความสูง · axe ทั้งสองธีมตอนชีตเปิด · 640 × 800 ไม่ล้น", async ({ page, request }) => {
    test.setTimeout(60_000)
    await page.setViewportSize({ width: 640, height: 800 })
    await enqueue(request, [video("SLOWDOWNLD1")])
    await page.goto("/")
    const bar = page.getByRole("region", { name: "คิวงาน" })
    await expect(bar).toBeVisible()
    await expect
      .poll(async () => {
        const box = await bar.boundingBox()
        const offset = await page.evaluate(() =>
          getComputedStyle(document.documentElement).getPropertyValue("--dock-bottom-offset").trim(),
        )
        return offset === `${Math.ceil(box!.height)}px`
      })
      .toBe(true)
    expect(await noOverflow(page)).toBe(true)

    for (const scheme of ["light", "dark"] as const) {
      await page.emulateMedia({ colorScheme: scheme })
      const sheet = await openQueueSheet(page)
      expect(await noOverflow(page)).toBe(true)
      expect(await seriousViolations(page), scheme).toEqual([])
      await sheet.getByRole("button", { name: "ปิดคิวงาน" }).click()
      await expect(sheet).toBeHidden()
    }
    await cancelJobsFor(request, ["SLOWDOWNLD1"])
  })
})

test.describe("W7 ยืนยันปิดโปรแกรม", () => {
  test("ลิงก์จาก tray บอกจำนวนงานค้าง · กลับไปก่อน = ลบพารามิเตอร์ · ปิดเลย = หน้าปิดโปรแกรม", async ({ page, request }) => {
    test.setTimeout(60_000)
    await enqueue(request, [video("SLOWDOWNLD1"), video("SLOWDOWNLD2")])
    // ไม่ปิด backend จริง (spec อื่นในโปรเจกต์ queue ยังใช้อยู่): ตอบ POST /api/shutdown เอง
    const bodies: unknown[] = []
    await page.route("**/api/shutdown", (route) => {
      bodies.push(route.request().postDataJSON())
      return route.fulfill({ json: { ok: true } })
    })

    await page.goto("/?confirmShutdown=1")
    const dialog = page.getByRole("alertdialog", { name: "ปิดโปรแกรมตอนนี้?" })
    await expect(dialog).toContainText("มีงานค้าง 2 งาน")
    await dialog.getByRole("button", { name: "กลับไปก่อน" }).click()
    await expect(dialog).toBeHidden()
    await expect(page).toHaveURL((url) => !url.searchParams.has("confirmShutdown"))

    await page.goto("/?confirmShutdown=1")
    await page.getByRole("alertdialog").getByRole("button", { name: "ปิดเลย" }).click()
    await expect(page.getByText("ปิดโปรแกรมแล้ว")).toBeVisible()
    expect(bodies).toEqual([{ force: true }])
    await cancelJobsFor(request, ["SLOWDOWNLD1", "SLOWDOWNLD2"])
  })
})
