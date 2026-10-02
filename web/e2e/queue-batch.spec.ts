/// <reference lib="dom" />
import fs from "node:fs"
import path from "node:path"

import AxeBuilder from "@axe-core/playwright"
import { expect, test, type Page } from "@playwright/test"

import type { Job } from "../src/lib/types"

import { cancelJobsFor, listJobs, resumeQueue } from "./queue-helpers"

// M4 งาน 19 (โปรเจกต์ queue): หน้า W3 เลือกคลิป แล้วส่งเข้าคิวจริงบน backend โหมด fake
// คลิปของ spec นี้ (C14): VTTFALLBAK1, NOORIGSUB01, LONGTHAI1hr (รายการหลายลิงก์) และเพลย์ลิสต์ PLfakeplaylist250 (กล่องถามเท่านั้น ไม่ส่ง)

const CLIPS = ["VTTFALLBAK1", "NOORIGSUB01", "LONGTHAI1hr"] as const
const PLAYLIST_ID = "PLfakeplaylist250"
const PLAYLIST_URL = `https://www.youtube.com/playlist?list=${PLAYLIST_ID}`
const BAD_LINK = "https://example.com/x"
const LIST_TEXT = [...CLIPS.map((id) => `https://youtu.be/${id}`), BAD_LINK].join("\n")
const OPEN_BATCH = "เลือกคลิปที่จะโหลด"
const FIXTURES = path.join(import.meta.dirname, "../../tests/fixtures")

function fixtureTitle(videoId: string): string {
  const file = path.join(FIXTURES, "probe", `${videoId}.json`)
  return (JSON.parse(fs.readFileSync(file, "utf8")) as { title: string }).title
}

const resultRows = (page: Page) => page.locator('section[aria-labelledby="results-title"] [role="listitem"]')
const tableRows = (page: Page) => page.locator("tbody tr")
const rowChecks = (page: Page) => page.locator("tbody").getByRole("checkbox")
const submitButton = (page: Page, n: number) => page.getByRole("button", { name: `ส่งเข้าคิว ${n} คลิป`, exact: true })
const isEnqueue = (url: string, method: string) => new URL(url).pathname === "/api/jobs" && method === "POST"

async function paste(page: Page, text: string) {
  await page.goto("/")
  await page.getByRole("textbox").fill(text)
  await page.getByRole("button", { name: "วิเคราะห์" }).click()
}

/** วางรายการหลายลิงก์ที่หน้าแรก รอชื่อคลิปขึ้นครบ แล้วกด "เลือกคลิปที่จะโหลด" ที่หัวรายการ */
async function openBatchFromList(page: Page) {
  await paste(page, LIST_TEXT)
  await expect(resultRows(page)).toHaveCount(4)
  for (const [index, id] of CLIPS.entries()) await expect(resultRows(page).nth(index)).toContainText(fixtureTitle(id))
  await page.getByRole("link", { name: OPEN_BATCH, exact: true }).first().click()
  await expect(page).toHaveURL(/\/batch\?src=[^&]+$/)
  await expect(rowChecks(page)).toHaveCount(3)
}

async function seriousViolations(page: Page) {
  // รอแอนิเมชันที่มีจุดจบ (toast จางเข้า, กล่องเปิด) ให้จบก่อน: axe วัดสีตอนโปร่งแสงแล้วได้ค่าต่ำเกินจริง
  await page.evaluate(() =>
    Promise.all(
      document
        .getAnimations()
        .filter((a) => a.effect?.getComputedTiming().endTime !== Infinity)
        .map((a) => a.finished.catch(() => undefined)),
    ),
  )
  const results = await new AxeBuilder({ page }).analyze()
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.map((n) => n.target.join(" ")).slice(0, 5) }))
}

test.beforeEach(async ({ request }) => {
  await resumeQueue(request)
  await cancelJobsFor(request, [...CLIPS])
})

test("วาง 3 คลิป + ลิงก์เสีย → W3 มี 3 แถวเลือกได้ + 1 แถวแดง · เสียง + .srt → 6 งานเข้าคิวและเสร็จ (คลิปไม่มีแทร็กเริ่มต้น = 'คลิปนี้ไม่มีซับ')", async ({
  page,
  request,
}) => {
  test.setTimeout(120_000)
  await openBatchFromList(page)

  await expect(page.getByRole("heading", { level: 1 })).toHaveText("หลายลิงก์")
  await expect(page.getByRole("status").filter({ hasText: "ทั้งหมด 3 คลิป" })).toHaveText("ทั้งหมด 3 คลิป · เลือกแล้ว 3 คลิป")
  // แถวแดงเลือกไม่ได้: ไม่มีช่องติ๊ก
  await expect(tableRows(page)).toHaveCount(4)
  await expect(page.getByText("ลิงก์นี้อ่านไม่ออก")).toHaveCount(1)
  await expect(page.getByText(BAD_LINK)).toBeVisible()
  await expect(page.getByRole("checkbox", { name: "เลือกทั้งหมด", exact: true })).toBeChecked()
  for (const check of await rowChecks(page).all()) await expect(check).toBeChecked()
  for (const id of CLIPS) {
    await expect(page.getByRole("checkbox", { name: `เลือก ${fixtureTitle(id)}`, exact: true })).toBeVisible()
  }

  await page.getByRole("combobox", { name: "โหลดอะไร", exact: true }).click()
  await page.getByRole("option", { name: "เสียง", exact: true }).click()
  await page.getByRole("group", { name: "ซับ", exact: true }).getByRole("button", { name: ".srt", exact: true }).click()
  await expect(page.getByRole("group", { name: "ซับ", exact: true }).getByRole("button", { name: ".srt" })).toHaveAttribute(
    "aria-pressed",
    "true",
  )

  const posted = page.waitForResponse((response) => isEnqueue(response.url(), response.request().method()))
  await submitButton(page, 3).click()
  const response = await posted
  expect(response.ok(), `POST /api/jobs ตอบ ${response.status()}`).toBe(true)
  const sent = (response.request().postDataJSON() as { items: { videoId: string; kind: string; title?: string; params: object }[] }).items
  const created = ((await response.json()) as { jobs: Job[] }).jobs
  expect(created).toHaveLength(6)
  expect(sent.map((item) => `${item.videoId}:${item.kind}`)).toEqual(CLIPS.flatMap((id) => [`${id}:audio`, `${id}:subtitle`]))
  for (const item of sent) {
    expect(item.title).toBe(fixtureTitle(item.videoId))
    if (item.kind === "subtitle") {
      expect(item.params).toMatchObject({ format: "srt" })
      expect("trackId" in item.params).toBe(false)
    }
  }

  // อยู่หน้าเดิม: มี toast และแถบคิวขึ้น
  await expect(page).toHaveURL(/\/batch\?src=/)
  await expect(page.getByText("เพิ่มเข้าคิวแล้ว 6 งาน").first()).toBeVisible()
  await expect(page.getByRole("region", { name: "คิวงาน" })).toBeVisible()

  const ids = new Set(created.map((job) => job.id))
  await expect
    .poll(
      async () => {
        const mine = (await listJobs(request)).filter((job) => ids.has(job.id))
        return mine.filter((job) => job.status === "done" || job.status === "failed").length
      },
      { timeout: 90_000 },
    )
    .toBe(6)
  const finished = (await listJobs(request)).filter((job) => ids.has(job.id))
  expect(finished.map((job) => job.status)).toEqual(Array(6).fill("done"))

  // NOORIGSUB01 มีแต่ซับอัตโนมัติ/ซับแปล ไม่มีแทร็กเริ่มต้น: งานซับจบแบบไม่มีไฟล์ พร้อมโน้ตสีเทา
  const noTrack = finished.find((job) => job.videoId === "NOORIGSUB01" && job.kind === "subtitle")
  expect(noTrack?.notes?.map((note) => note.message)).toContain("คลิปนี้ไม่มีซับ")
  expect(noTrack?.outputs ?? []).toHaveLength(0)
})

test("ไม่เลือกอะไร หรือเอาคลิปออกหมด → ปุ่มส่งจางแต่โฟกัสได้ พร้อมคำบอก ไม่ส่งงาน · ติ๊กบางแถว → ช่อง 'เลือกทั้งหมด' เป็นสถานะกึ่งเลือก", async ({
  page,
}) => {
  const requests: string[] = []
  page.on("request", (request) => {
    if (isEnqueue(request.url(), request.method())) requests.push(request.url())
  })
  await openBatchFromList(page)
  const all = page.getByRole("checkbox", { name: "เลือกทั้งหมด", exact: true })
  const hint = "เลือกคลิป และเลือกวิดีโอ เสียง หรือซับอย่างน้อยหนึ่งอย่าง"

  // ค่าเริ่มต้น: วิดีโอ + ซับไม่เอา = ส่งได้
  await expect(submitButton(page, 3)).not.toHaveAttribute("aria-disabled", "true")
  await expect(page.getByText(hint)).toHaveCount(0)

  // เอาคลิปแรกออก → ครึ่ง ๆ กลาง ๆ
  await rowChecks(page).first().click()
  await expect(all).toHaveAttribute("aria-checked", "mixed")
  await expect(page.getByRole("status").filter({ hasText: "ทั้งหมด 3 คลิป" })).toHaveText("ทั้งหมด 3 คลิป · เลือกแล้ว 2 คลิป")
  await expect(submitButton(page, 2)).toBeVisible()

  // ช่องกึ่งเลือกกด = เลือกทั้งหมด · กดอีกที = เอาออกหมด
  await all.click()
  await expect(all).toBeChecked()
  await expect(submitButton(page, 3)).toBeVisible()
  await all.click()
  await expect(all).not.toBeChecked()
  const none = submitButton(page, 0)
  await expect(none).toHaveAttribute("aria-disabled", "true")
  await expect(page.getByText(hint)).toBeVisible()
  await none.focus()
  await expect(none).toBeFocused()
  // aria-disabled = Playwright ถือว่ากดไม่ได้ ต้อง force เพื่อลองกดจริง (ผู้ใช้กดได้ แต่ต้องไม่มีอะไรเกิดขึ้น)
  await none.click({ force: true })

  // เลือกทั้งหมดอีกครั้ง แต่ "โหลดอะไร" = ไม่เอา และซับ = ไม่เอา
  await all.click()
  await expect(all).toBeChecked()
  await page.getByRole("combobox", { name: "โหลดอะไร", exact: true }).click()
  await page.getByRole("option", { name: "ไม่เอา", exact: true }).click()
  const nothing = submitButton(page, 3)
  await expect(nothing).toHaveAttribute("aria-disabled", "true")
  await expect(page.getByText(hint)).toBeVisible()
  await nothing.click({ force: true })
  // ซับอย่างเดียวก็ส่งได้
  await page.getByRole("group", { name: "ซับ", exact: true }).getByRole("button", { name: ".txt", exact: true }).click()
  await expect(nothing).not.toHaveAttribute("aria-disabled", "true")
  await expect(page.getByText(hint)).toHaveCount(0)

  expect(requests).toEqual([])
})

test("เพลย์ลิสต์ PLfakeplaylist250 → W3 มี 200 แถว · ส่งเข้าคิวถามยืนยัน 'ส่ง 200 คลิปเข้าคิว?' · 'ยกเลิก' = ไม่มีงานเกิดขึ้น", async ({
  page,
  request,
}) => {
  const requests: string[] = []
  page.on("request", (req) => {
    if (isEnqueue(req.url(), req.method())) requests.push(req.url())
  })
  await paste(page, PLAYLIST_URL)
  const row = resultRows(page).first()
  await row.getByRole("link", { name: OPEN_BATCH, exact: true }).click()
  await expect(page).toHaveURL(new RegExp(`/batch\\?src=[^&]+&playlist=${PLAYLIST_ID}$`))
  await expect(rowChecks(page)).toHaveCount(200)
  await expect(page.getByRole("status").filter({ hasText: "ทั้งหมด 200 คลิป" })).toHaveText("ทั้งหมด 200 คลิป · เลือกแล้ว 200 คลิป")

  await submitButton(page, 200).click()
  const dialog = page.getByRole("alertdialog")
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole("heading", { name: "ส่ง 200 คลิปเข้าคิว?" })).toBeVisible()
  await expect(dialog).toContainText("ใช้เวลาประมาณ")
  await dialog.getByRole("button", { name: "ยกเลิก", exact: true }).click()
  await expect(dialog).toHaveCount(0)
  await expect(submitButton(page, 200)).toBeFocused()

  expect(requests).toEqual([])
  const queued = (await listJobs(request)).filter((job) => job.videoId.startsWith("fake"))
  expect(queued).toEqual([])
})

test("รายการหมดอายุ (ลิงก์เก่า หรือล้างรายการแล้ว) → หน้าว่างพร้อมปุ่ม 'กลับหน้าแรก'", async ({ page }) => {
  // src ที่ไม่เคยมี
  await page.goto("/batch?src=deadbeefdeadbeef")
  await expect(page.getByText("รายการนี้ไม่อยู่แล้ว วางลิงก์ใหม่ที่หน้าแรก")).toBeVisible()
  await expect(page.getByRole("checkbox")).toHaveCount(0)
  await page.getByRole("link", { name: "กลับหน้าแรก", exact: true }).click()
  await expect(page).toHaveURL(/\/$/)

  // ล้างรายการหลังเปิดหน้านี้ แล้วเปิดลิงก์เดิมซ้ำ
  await openBatchFromList(page)
  const url = page.url()
  await page.getByRole("navigation", { name: "ตำแหน่งของหน้านี้" }).getByRole("link", { name: "หน้าแรก", exact: true }).click()
  await page.getByRole("button", { name: "ล้างรายการ" }).click()
  await page.goto(url)
  await expect(page.getByText("รายการนี้ไม่อยู่แล้ว วางลิงก์ใหม่ที่หน้าแรก")).toBeVisible()
})

test("จอ 640 px (ซูม 200%): ไม่มีแถบเลื่อนข้างทั้งหน้าและตาราง ทั้งรายการหลายลิงก์และเพลย์ลิสต์ 200 คลิป", async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 800 })
  const noOverflow = async () => {
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(640)
    const table = page.locator('[data-slot="table-container"]')
    expect(await table.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
  }
  await openBatchFromList(page)
  await noOverflow()
  await expect(submitButton(page, 3)).toBeVisible()

  await paste(page, PLAYLIST_URL)
  await resultRows(page).first().getByRole("link", { name: OPEN_BATCH, exact: true }).click()
  await expect(rowChecks(page)).toHaveCount(200)
  await noOverflow()
})

for (const scheme of ["dark", "light"] as const) {
  test(`axe: หน้า W3 ตอนรายการหมดอายุไม่มีปัญหาระดับ serious/critical (${scheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme })
    await page.goto("/batch?src=deadbeefdeadbeef")
    await expect(page.getByText("รายการนี้ไม่อยู่แล้ว วางลิงก์ใหม่ที่หน้าแรก")).toBeVisible()
    await expect(page.locator("html")).toHaveClass(scheme === "dark" ? /dark/ : /light/)
    expect(await seriousViolations(page)).toEqual([])
  })

  test(`axe: หน้า W3 (รายการหลายลิงก์ และกล่องยืนยัน) ไม่มีปัญหาระดับ serious/critical (${scheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme })
    await openBatchFromList(page)
    await expect(page.locator("html")).toHaveClass(scheme === "dark" ? /dark/ : /light/)
    expect(await seriousViolations(page)).toEqual([])

    // กล่องยืนยัน (เพลย์ลิสต์ 200 คลิป)
    await paste(page, PLAYLIST_URL)
    await resultRows(page).first().getByRole("link", { name: OPEN_BATCH, exact: true }).click()
    await expect(rowChecks(page)).toHaveCount(200)
    expect(await seriousViolations(page)).toEqual([])
    await submitButton(page, 200).click()
    await expect(page.getByRole("alertdialog")).toBeVisible()
    expect(await seriousViolations(page)).toEqual([])
    await page.getByRole("button", { name: "ยกเลิก", exact: true }).click()
  })
}
