import { expect, test } from "@playwright/test"

test("หน้าแรก W1 แสดงหัวข้อ ช่องวางลิงก์ และปุ่มหลักปุ่มเดียว", async ({ page }) => {
  await page.goto("/")
  await expect(page.getByRole("heading", { name: "วางลิงก์ยูทูป แล้วเลือกสิ่งที่อยากได้" })).toBeVisible()
  await expect(page.getByRole("textbox")).toBeVisible()
  await expect(page.getByRole("button", { name: "วิเคราะห์" })).toBeVisible()
  await expect(page.locator('meta[name="yt-token"]')).toHaveAttribute("content", /.{20,}/)
})

test("/index.html ได้หน้าที่ฝัง token แล้ว ไม่ใช่ไฟล์ดิบ", async ({ page }) => {
  await page.goto("/index.html")
  await expect(page.locator('meta[name="yt-token"]')).toHaveAttribute("content", /.{20,}/)
})

test("กดวิเคราะห์ตอนนี้ แจ้งว่าจะเปิดใช้ในเวอร์ชันถัดไป", async ({ page }) => {
  await page.goto("/")
  await page.getByRole("textbox").fill("https://youtu.be/dQw4w9WgXcQ")
  await page.getByRole("button", { name: "วิเคราะห์" }).click()
  await expect(page.getByRole("status")).toHaveText("ระบบวิเคราะห์ลิงก์จะเปิดใช้ในเวอร์ชันถัดไป")
})

test("กดปุ่ม d ไม่สลับธีม (ไม่มีปุ่มลัดซ่อน)", async ({ page }) => {
  await page.goto("/")
  await expect(page.getByRole("heading", { name: "วางลิงก์ยูทูป แล้วเลือกสิ่งที่อยากได้" })).toBeVisible()
  const before = await page.locator("html").getAttribute("class")
  await page.locator("body").press("d")
  await expect(page.locator("html")).toHaveAttribute("class", before ?? "")
  expect(await page.evaluate(() => localStorage.getItem("theme"))).toBeNull()
})
