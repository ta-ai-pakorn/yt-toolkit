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

test("ปุ่มตั้งค่าที่หัวหน้าเป็นลิงก์จริง ไม่ใช่ปุ่ม", async ({ page }) => {
  await page.goto("/")
  await expect(page.getByRole("link", { name: "ตั้งค่า" })).toHaveAttribute("href", "/settings/health")
  await expect(page.getByRole("button", { name: "ตั้งค่า" })).toHaveCount(0)
  await page.getByRole("link", { name: "ตั้งค่า" }).click()
  await expect(page.getByRole("link", { name: "ตั้งค่า" })).toHaveAttribute("aria-current", "page")
})

test("พิมพ์ในช่องหลังกดวิเคราะห์ ข้อความแจ้งเตือนหายไป", async ({ page }) => {
  await page.goto("/")
  await page.getByRole("textbox").fill("https://youtu.be/dQw4w9WgXcQ")
  await page.getByRole("button", { name: "วิเคราะห์" }).click()
  await expect(page.getByRole("status")).toBeVisible()
  await page.getByRole("textbox").fill("https://youtu.be/abc")
  await expect(page.getByRole("status")).toHaveCount(0)
})

const readColorScheme = "document.documentElement.style.colorScheme"

test.describe("ธีมตั้งก่อนหน้าโหลดเสร็จ", () => {
  for (const scheme of ["dark", "light"] as const) {
    test(`ไม่ตั้งค่าไว้ ตามระบบ (${scheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme })
      // เก็บคลาสของ <html> ทันทีที่ DOM พร้อม ก่อนที่ React จะทำงาน
      await page.addInitScript(
        'document.addEventListener("DOMContentLoaded", function () { window.earlyClass = document.documentElement.className })',
      )
      await page.goto("/")
      expect(await page.evaluate("window.earlyClass")).toBe(scheme)
      await expect(page.locator("html")).toHaveClass(scheme)
      expect(await page.evaluate(readColorScheme)).toBe(scheme)
    })
  }

  test("ค่าที่บันทึกไว้ชนะระบบ และไม่มีทั้งสองคลาสพร้อมกัน", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "dark" })
    await page.addInitScript('localStorage.setItem("theme", "light")')
    await page.goto("/")
    await expect(page.locator("html")).toHaveClass("light")
    expect(await page.evaluate(readColorScheme)).toBe("light")
  })
})
