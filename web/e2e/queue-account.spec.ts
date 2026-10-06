/// <reference lib="dom" />
import { expect, test, type APIRequestContext, type Page } from "@playwright/test"

import { cancelJobsFor, enqueue, openQueueSheet, token, waitForJob } from "./queue-helpers"

/**
 * M5 รอบ C บัญชียูทูปชั่วคราวกับ backend โหมดปลอมจริง (project queue รันทีละ spec --workers=1):
 * ACCOUNTAGE1 = คลิปปลอมที่ probe แบบไม่ใช้บัญชีได้ E_AGE_RESTRICTED (FakeExtractor "needsAccount")
 * PRIVATEVID1 = ส่วนตัวเสมอแม้ใช้บัญชี (บัญชีไม่มีสิทธิ์ดู)
 * ไฟล์ที่นำเข้าเป็นค่าปลอม (ตัวอ่าน cookies.txt ตัวจริงของ backend อ่าน ไม่มีคำขอไปยูทูป)
 * playwright.config ตั้ง YT_TOOLKIT_ACCOUNT_GRACE_S=5: คิวว่างหลังงานที่ใช้บัญชีจบ 5 วินาทีแล้วบัญชีถูกลบเอง (ของจริง 10 นาที)
 */

const AGE = "ACCOUNTAGE1"
const PRIVATE = "PRIVATEVID1"
const USE = "ใช้บัญชียูทูปชั่วคราว"
const AGE_MESSAGE = "คลิปนี้จำกัดอายุ ต้องเข้าสู่ระบบยูทูปถึงจะเปิดได้"
const TRIED_MESSAGE =
  "ลองด้วยบัญชีแล้วยังเปิดไม่ได้ บัญชีนี้อาจไม่มีสิทธิ์ดูคลิปนี้ หรือการเข้าสู่ระบบหมดอายุแล้ว ลองนำเข้าใหม่"
const REMOVED = "ลบบัญชีออกจากแอพแล้ว · กลับไปกดออกจากระบบในหน้าต่างไม่ระบุตัวตน แล้วปิดหน้าต่าง"
const COOKIES =
  "# Netscape HTTP Cookie File\n" +
  ".youtube.com\tTRUE\t/\tTRUE\t2000000000\tSAPISID\te2e-fake-sapisid\n" +
  ".youtube.com\tTRUE\t/\tTRUE\t2000000000\tLOGIN_INFO\te2e-fake-login\n"
const VIDEO = { maxQuality: false, splitChapters: false, noAudio: false, audioLanguage: "original" }

const banner = (page: Page) => page.getByTestId("account-banner")
const toast = (page: Page, text: string) => page.locator("[data-sonner-toast]").filter({ hasText: text })

async function accountStatus(request: APIRequestContext): Promise<{ active: boolean }> {
  return (await (await request.get("/api/cookies")).json()) as { active: boolean }
}

/** ลบบัญชีที่ค้าง (spec ถัดไปของ project queue ต้องเริ่มแบบไม่มีบัญชี) */
async function dropAccount(page: Page): Promise<void> {
  const origin = new URL(page.url()).origin
  await page.request.delete("/api/cookies", { headers: { "X-Toolkit-Token": await token(page), Origin: origin } })
}

test("งานคลิปจำกัดอายุพลาด → ปุ่มในแถวคิว → นำเข้า → ลองงานเดิมใหม่เอง → เสร็จ · บัญชีไม่มีสิทธิ์ = ข้อความ ลองด้วยบัญชีแล้ว… · คิวว่างแล้วลบเอง", async ({
  page,
  request,
}) => {
  test.setTimeout(60_000)
  await page.goto("/")
  try {
    expect((await accountStatus(request)).active).toBe(false)
    const [job] = await enqueue(request, [{ videoId: AGE, kind: "video", params: VIDEO, title: "คลิปจำกัดอายุ" }])
    const failed = await waitForJob(request, (j) => j.id === job.id && j.status === "failed")
    expect(failed.error).toMatchObject({ code: "E_AGE_RESTRICTED", message: AGE_MESSAGE })

    const sheet = await openQueueSheet(page)
    const row = sheet.locator(`[data-job-id="${job.id}"]`)
    await expect(row).toContainText(AGE_MESSAGE)
    await row.getByRole("button", { name: USE }).click()
    const dialog = page.getByRole("dialog", { name: USE })
    await dialog.getByLabel("cookies.txt").setInputFiles({ name: "cookies.txt", mimeType: "text/plain", buffer: Buffer.from(COOKIES) })
    await dialog.getByRole("button", { name: "นำเข้าแล้วลองใหม่" }).click()
    await expect(dialog).toHaveCount(0)
    await expect(banner(page)).toContainText("กำลังใช้บัญชียูทูปชั่วคราว")
    const done = await waitForJob(request, (j) => j.id === job.id && j.status === "done")
    expect(done.outputs?.length).toBe(1)

    // บัญชียังอยู่ (grace เพิ่งเริ่ม) งานใหม่ของคลิปที่บัญชีไม่มีสิทธิ์: ลองด้วยบัญชีแล้วยังพลาด ข้อความเปลี่ยน ไม่มีปุ่ม
    const [denied] = await enqueue(request, [{ videoId: PRIVATE, kind: "video", params: VIDEO }])
    const deniedJob = await waitForJob(request, (j) => j.id === denied.id && j.status === "failed")
    expect(deniedJob.error).toMatchObject({ code: "E_VIDEO_PRIVATE", message: TRIED_MESSAGE })
    const deniedRow = sheet.locator(`[data-job-id="${denied.id}"]`)
    await expect(deniedRow).toContainText(TRIED_MESSAGE)
    await expect(deniedRow.getByRole("button", { name: USE })).toHaveCount(0)

    // คิวว่างครบ grace (5 วินาทีในโหมดทดสอบ): ลบเอง แถบหาย toast บอกให้ไปออกจากระบบ (ค้างไว้ ไม่หายเอง)
    await expect(toast(page, REMOVED)).toBeVisible({ timeout: 15_000 })
    await expect(banner(page)).toHaveCount(0)
    expect((await accountStatus(request)).active).toBe(false)
  } finally {
    await cancelJobsFor(request, [AGE, PRIVATE])
    await dropAccount(page)
  }
})
