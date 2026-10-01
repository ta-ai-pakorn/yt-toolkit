import { expect, test } from "@playwright/test"

import { enqueue, waitForJob } from "./queue-helpers"

// AC-OUT-05 (E): คลิปที่โหลดไฟล์แล้ว ขึ้นในหน้าประวัติพร้อมป้ายชนิดไฟล์ และเปิดหน้า W2 จากข้อมูลที่เก็บไว้ได้
// ใช้ project "queue" (backend แยก) เพราะสร้างงานจริง · คลิปของ spec นี้คือ jNQXAC9IVRw เท่านั้น (ตาราง C14)
const ZOO = "jNQXAC9IVRw"
const ZOO_TITLE = "Me at the zoo"

test("โหลดเสียงของคลิปผ่าน API แล้วขึ้นหน้าประวัติพร้อมป้าย 'เสียง' และเปิด W2 ได้", async ({ page, request }) => {
  test.setTimeout(90_000)

  // ไม่เคยเปิดคลิปนี้ในหน้า W2: ที่ขึ้นประวัติได้เพราะมีงานโหลดที่เสร็จแล้วเท่านั้น (scope=all)
  const [created] = await enqueue(request, [
    { videoId: ZOO, kind: "audio", params: { format: "m4a", splitChapters: false, audioLanguage: "original" }, title: ZOO_TITLE },
  ])
  await waitForJob(request, (job) => job.id === created.id && job.status === "done", { timeout: 60_000 })

  await page.goto("/history")
  const row = page.locator("tbody tr", { has: page.getByRole("link", { name: ZOO_TITLE }) })
  await expect(row).toHaveCount(1)
  await expect(row.locator('[data-slot="badge"]')).toHaveText(["เสียง"])
  await expect(row).toContainText(/เมื่อสักครู่|นาทีก่อน/)

  // ค้นจากชื่อ (ค้นแล้วคลิปนี้ยังอยู่)
  await page.getByRole("textbox", { name: "ค้นหาจากชื่อคลิป" }).fill("zoo")
  await expect(page).toHaveURL(/\/history\?q=zoo$/)
  await expect(row).toHaveCount(1)

  const opened = page.waitForResponse(
    (response) => new URL(response.url()).pathname === `/api/videos/${ZOO}` && response.request().method() === "GET",
  )
  await row.getByRole("link", { name: ZOO_TITLE }).click()
  await expect(page).toHaveURL(new RegExp(`/v/${ZOO}$`))
  expect((await opened).ok()).toBe(true)
  await expect(page.getByRole("heading", { level: 1 })).toContainText(ZOO_TITLE)
})
