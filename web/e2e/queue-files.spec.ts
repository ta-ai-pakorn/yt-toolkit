/// <reference lib="dom" />
import { expect, test, type APIRequestContext, type Page } from "@playwright/test"

import type { Job, JobKind } from "../src/lib/types"
import { enqueue, waitForJob } from "./queue-helpers"

// M4 งาน 16: ไฟล์ซับ ภาพรวมเฟรม และ .zip ผ่านคิวจริง (project "queue" backend ปลอมของตัวเอง)
// ใช้คลิปของไฟล์นี้เท่านั้น (C14): 88o5Sk8_m1Y, OWNERTHSUB1 (ซับ) · aqz-KE-bpKQ (ภาพรวมเฟรมและ zip)
// ปุ่มในหน้าเว็บส่ง payload จริงเข้า backend จริง (ไม่มี mock) แล้วรอจนงานเสร็จและอ่านไฟล์ที่ได้

const THAI = "88o5Sk8_m1Y"
const OWNER = "OWNERTHSUB1"
const BBB = "aqz-KE-bpKQ"
const ADDED = "เพิ่มเข้าคิวแล้ว"

/** รองานของคลิปและชนิดนี้จนจบ (สำเร็จหรือล้มเหลว) แล้วยืนยันว่า "เสร็จ" · ล้มเหลว = ข้อความ error อยู่ในผลที่ขึ้น */
async function finished(request: APIRequestContext, videoId: string, kind: JobKind): Promise<Job> {
  const job = await waitForJob(
    request,
    (j) => j.videoId === videoId && j.kind === kind && (j.status === "done" || j.status === "failed"),
    { timeout: 30_000 },
  )
  expect(job.status, JSON.stringify(job.error ?? null)).toBe("done")
  return job
}

async function output(request: APIRequestContext, job: Job) {
  expect(job.outputs?.length ?? 0).toBeGreaterThan(0)
  const response = await request.get(`/api/jobs/${job.id}/outputs/${job.outputs?.[0].index ?? 0}`)
  expect(response.ok(), `GET output ตอบ ${response.status()}`).toBe(true)
  return response
}

async function openSubs(page: Page, videoId: string) {
  await page.goto(`/v/${videoId}?tab=subs`)
  await expect(page.locator('[data-slot="cue"]')).toHaveCount(5)
}

test.describe("ไฟล์ซับ ภาพรวมเฟรม และ zip ผ่านคิว", () => {
  test("'โหลด .srt' ส่งงานเข้าคิว → เสร็จ · ไฟล์ลงท้าย .srt ขึ้นต้นด้วย 1\\r\\n00:00:00,120 (AC-SUB, UTF-8 ไม่มี BOM)", async ({
    page,
    request,
  }) => {
    await openSubs(page, THAI)
    await page.getByRole("group", { name: "โหลดซับ" }).getByRole("button", { name: "โหลด .srt" }).click()
    await expect(page.getByText(ADDED).first()).toBeVisible()

    const job = await finished(request, THAI, "subtitle")
    expect(job.outputs?.[0].name.endsWith(".srt")).toBe(true)
    const response = await output(request, job)
    const bytes = await response.body()
    expect(bytes.subarray(0, 3).toString("hex")).not.toBe("efbbbf")
    expect(bytes.toString("utf8").startsWith("1\r\n00:00:00,120 --> ")).toBe(true)
  })

  test("ไฟล์โน้ต/ซับ .md ของคลิปที่มีซับเจ้าของคลิป (OWNERTHSUB1) เสร็จ และได้ไฟล์ .md", async ({ request }) => {
    // payload เดียวกับที่ปุ่ม "โหลด .md" ส่ง (ความยาวซับกลาง) ส่งผ่าน API เพื่อไม่ต้องพึ่งการเลือกแทร็กเริ่มต้นของหน้านี้
    const [queued] = await enqueue(request, [
      {
        videoId: OWNER,
        kind: "subtitle",
        params: {
          trackId: "o.th",
          format: "md",
          options: { maxChars: 25, lines: 1, minMs: 1200, maxMs: 5000, mode: "chars" },
        },
      },
    ])
    expect(queued.kind).toBe("subtitle")
    const job = await finished(request, OWNER, "subtitle")
    expect(job.outputs?.[0].name.endsWith(".md")).toBe(true)
    const text = (await (await output(request, job)).body()).toString("utf8")
    // รูปแบบเดียวกับ tests/fixtures/subs/golden/th-owner.md: หัวข้อ "# " ก่อน แล้วลิงก์ดูคลิป แล้วหัวข้อเวลา "## [00:00]"
    expect(text.startsWith("# ")).toBe(true)
    expect(text).toContain(`https://www.youtube.com/watch?v=${OWNER}`)
    expect(text).toContain("## [00:00]")
    expect(text.indexOf(`watch?v=${OWNER}`)).toBeLessThan(text.indexOf("## [00:00]"))
  })

  test("'โหลดภาพรวมเฟรม' ส่งงานเข้าคิว → เสร็จ · ไฟล์เป็น image/jpeg", async ({ page, request }) => {
    await page.goto(`/v/${BBB}`)
    await expect(page.getByRole("list", { name: "รายการภาพเฟรม" }).getByRole("listitem").first()).toBeVisible()
    await page.getByRole("button", { name: "โหลดภาพรวมเฟรม" }).click()
    await expect(page.getByText(ADDED).first()).toBeVisible()

    const job = await finished(request, BBB, "contact_sheet")
    expect(job.outputs?.[0].name).toMatch(/\.jpg$/)
    const response = await output(request, job)
    expect(response.headers()["content-type"]).toContain("image/jpeg")
  })

  test("'โหลดทั้งหมด (.zip)' ส่งงานเข้าคิว → เสร็จ · ไฟล์เป็น application/zip", async ({ page, request }) => {
    await page.goto(`/v/${BBB}`)
    await expect(page.getByRole("list", { name: "รายการภาพเฟรม" }).getByRole("listitem").first()).toBeVisible()
    await page.getByRole("button", { name: "โหลดทั้งหมด (.zip)" }).click()
    await expect(page.getByText(ADDED).first()).toBeVisible()

    const job = await finished(request, BBB, "frames_zip")
    expect(job.outputs?.[0].name).toMatch(/\.zip$/)
    const response = await output(request, job)
    // Windows อาจให้ application/x-zip-compressed จึงรับทั้งสองแบบ
    expect(response.headers()["content-type"]).toMatch(/^application\/(zip|x-zip-compressed)/)
    expect((await response.body()).subarray(0, 2).toString("latin1")).toBe("PK")
  })
})
