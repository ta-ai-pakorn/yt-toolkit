import { expect, test } from "@playwright/test"

test("หน้าแรก W1 แสดงหัวข้อ ช่องวางลิงก์ และปุ่มหลักปุ่มเดียว", async ({ page }) => {
  await page.goto("/")
  await expect(page.getByRole("heading", { name: "วางลิงก์ยูทูป แล้วเลือกสิ่งที่อยากได้" })).toBeVisible()
  await expect(page.getByRole("textbox")).toBeVisible()
  await expect(page.getByRole("button", { name: "วิเคราะห์" })).toBeVisible()
  await expect(page.locator('meta[name="yt-token"]')).toHaveAttribute("content", /.{20,}/)
})
