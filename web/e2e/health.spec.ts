import { expect, test } from "@playwright/test"

test("AC-SET-02: ไม่มี ffmpeg → แสดงใช้ไม่ได้พร้อมปุ่มโหลดใหม่", async ({ page }) => {
  await page.goto("/settings/health")
  const row = page.getByTestId("tool-ffmpeg")
  await expect(row).toContainText("ใช้ไม่ได้", { timeout: 15_000 })
  await expect(row.getByRole("button", { name: "โหลด ffmpeg ใหม่" })).toBeVisible()
})

test("ตัวช่วยของ yt-dlp เป็น deno", async ({ page }) => {
  await page.goto("/settings/health")
  await expect(page.getByTestId("tool-jsRuntime")).toContainText("deno", { timeout: 15_000 })
})

test("แท็บเกี่ยวกับแสดงเวอร์ชัน", async ({ page }) => {
  await page.goto("/settings/about")
  await expect(page.getByText("0.1.0")).toBeVisible()
})
