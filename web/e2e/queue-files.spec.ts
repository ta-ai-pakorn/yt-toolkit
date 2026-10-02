/// <reference lib="dom" />
import { expect, test, type APIRequestContext, type Page } from "@playwright/test"

import type { Job, JobKind } from "../src/lib/types"
import { enqueue, waitForJob } from "./queue-helpers"

// M4 งาน 16: ไฟล์ซับ ภาพรวมเฟรม และ .zip ผ่านคิวจริง (project "queue" backend ปลอมของตัวเอง)
// owner round 2: โน้ต .md ของปุ่ม "บันทึกเป็นโน้ต (.md)" เป็นงาน "note" ในคิวแล้ว (ย้ายเทสรอยต่อไฟล์โน้ตมาจาก clip-info.spec.ts)
// ใช้คลิปของไฟล์นี้เท่านั้น (C14): 88o5Sk8_m1Y, OWNERTHSUB1 (ซับ โน้ต) · aqz-KE-bpKQ (ภาพรวมเฟรมและ zip)
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

  test("ซับรูปแบบ .md (ผ่าน API) ของคลิปที่มีซับเจ้าของคลิป (OWNERTHSUB1) เสร็จ และได้ไฟล์ .md", async ({ request }) => {
    // owner round 2: หน้าเว็บไม่มีปุ่ม "โหลด .md" ในแท็บซับแล้ว แต่ backend ยังรับ format "md" (ส่งตรงผ่าน API)
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

  test("'บันทึกเป็นโน้ต (.md)' ส่งงาน note เข้าคิว → เสร็จ · ไฟล์ .note.md (LF) ในโฟลเดอร์ของคลิป มี front matter แท็กแบบ Obsidian และทรานสคริปต์", async ({
    page,
    request,
  }) => {
    await page.goto(`/v/${THAI}`)
    // รอป้ายแทร็ก = รายการแทร็กโหลดเสร็จแล้ว (งานโน้ตใช้แทร็กที่ใช้อยู่)
    await expect(page.getByText("ซับ: ไทย (อัตโนมัติ)")).toBeVisible()
    let downloads = 0
    page.on("download", () => (downloads += 1))
    const posted = page.waitForResponse(
      (response) => new URL(response.url()).pathname === "/api/jobs" && response.request().method() === "POST",
    )
    await page.getByRole("button", { name: "บันทึกเป็นโน้ต (.md)" }).click()
    const sent = (await posted).request().postDataJSON() as { items: { videoId: string; kind: string; params: object }[] }
    expect(sent.items).toEqual([{ videoId: THAI, kind: "note", params: { trackId: "a.th-orig" } }])
    await expect(page.getByText(ADDED).first()).toBeVisible()

    const job = await finished(request, THAI, "note")
    expect(job.outputs?.[0].name.endsWith(".note.md")).toBe(true)
    const text = (await (await output(request, job)).body()).toString("utf8")
    expect(text.startsWith('---\ntitle: "Thai Listening Practice | EP.1 | Beginner"\n')).toBe(true)
    expect(text).not.toContain("\r")
    expect(text).toContain("\nsource: YT Toolkit\n---\n")
    expect(text).toContain("\n## ทรานสคริปต์\n")
    const tags = text.match(/^tags: \[(.*)\]$/m)?.[1] ?? ""
    // แท็กไม่มีช่องว่างข้างใน (Obsidian ใช้ไม่ได้) ทุกอันอยู่ในเครื่องหมายคำพูด
    for (const tag of tags.split(", ").filter(Boolean)) expect(tag).toMatch(/^"[^\s"]+"$/)
    expect(downloads).toBe(0)
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
