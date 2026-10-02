import { expect, test, type Page } from "@playwright/test"

import { installFakeYT } from "./fake-yt"

/**
 * M5 รอบ A (D7): "ตั้งจุดเริ่ม/ตั้งจุดจบ" ใต้ตัวเล่น บนตัวเล่นลอย ในเมนูคลิกขวาของภาพเฟรม และปุ่ม "ใช้เวลาที่ตัวเล่นอยู่ตอนนี้"
 * ตัวเล่นปลอม (installFakeYT) เวลาเดินช้ามาก (rate 0.001) เวลาที่ตั้งจึงคงที่ ไม่ต่อยูทูปจริง ไม่สร้างงาน
 */

const THAI = "88o5Sk8_m1Y" // 372 วิ มีภาพเฟรม

const button = (page: Page, name: string) => page.getByRole("button", { name, exact: true })
const toast = (page: Page, text: string) => page.locator("[data-sonner-toast]").filter({ hasText: text })
const timeField = (page: Page, name: "เริ่ม" | "จบ") => page.getByRole("tabpanel").getByRole("textbox", { name, exact: true })

/** "00:00:20" (timecode ของภาพเฟรม) -> "0:20" (เวลาแบบที่ช่องและ toast ใช้) */
function clock(timecode: string): string {
  const [h, m, s] = timecode.split(":").map(Number)
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`
}

async function thirdFrame(page: Page) {
  const image = page.getByRole("img", { name: /^ภาพเฟรมที่ / }).nth(2)
  await expect(image).toBeVisible()
  const alt = (await image.getAttribute("alt")) ?? ""
  return { image, time: clock(alt.replace("ภาพเฟรมที่ ", "")) }
}

test("เมนูภาพเฟรม 'ตั้งเป็นจุดเริ่ม' ตั้งค่าในช่อง เปิดส่วนตัวเลือก และแจ้ง toast", async ({ page }) => {
  await page.goto(`/v/${THAI}`)
  const { image, time } = await thirdFrame(page)
  await image.click({ button: "right" })
  await page.getByRole("menuitem", { name: "ตั้งเป็นจุดเริ่ม" }).click()
  await expect(toast(page, `ตั้งจุดเริ่มที่ ${time} แล้ว`)).toBeVisible()
  await page.getByRole("tab", { name: "วิดีโอ", exact: true }).click()
  await expect(button(page, "ตัวเลือกขั้นสูง")).toHaveAttribute("aria-expanded", "true")
  await expect(timeField(page, "เริ่ม")).toHaveValue(time)
  await expect(page.getByRole("tabpanel").getByText("ใช้ตัวเลือกขั้นสูงอยู่")).toBeVisible()
})

test("ปุ่มใต้ตัวเล่นมีหลังเริ่มเล่นเท่านั้น · ตั้งจุดเริ่ม/จบจากเวลาตัวเล่น · ปุ่มข้างช่องใช้เวลาเดียวกัน", async ({ page }) => {
  await installFakeYT(page, { durationS: 372, rate: 0.001 })
  await page.goto(`/v/${THAI}?tab=video`)
  await expect(button(page, "ตั้งจุดเริ่ม")).toHaveCount(0)
  await button(page, "ตัวเลือกขั้นสูง").click()
  const startGroup = page.getByRole("group", { name: "เริ่ม" })
  await expect(startGroup.getByRole("button", { name: "ใช้เวลาที่ตัวเล่นอยู่ตอนนี้" })).toBeDisabled()

  await button(page, "เล่นคลิป").click()
  await expect(button(page, "ตั้งจุดเริ่ม")).toBeVisible()
  await button(page, "ตั้งจุดเริ่ม").click()
  await expect(toast(page, "ตั้งจุดเริ่มที่ 0:00 แล้ว")).toBeVisible()
  await expect(timeField(page, "เริ่ม")).toHaveValue("0:00")

  await page.getByRole("tab", { name: "ภาพเฟรม", exact: true }).click()
  const { image, time } = await thirdFrame(page)
  await image.click({ button: "right" })
  await page.getByRole("menuitem", { name: "เล่นจากตรงนี้" }).click()
  await button(page, "ตั้งจุดจบ").click()
  await expect(toast(page, `ตั้งจุดจบที่ ${time} แล้ว`)).toBeVisible()
  await page.getByRole("tab", { name: "วิดีโอ", exact: true }).click()
  await expect(timeField(page, "จบ")).toHaveValue(time)
  await expect(button(page, `โหลด mp4 (0:00-${time})`)).toBeVisible()
  await timeField(page, "เริ่ม").fill("")
  await page.getByRole("group", { name: "เริ่ม" }).getByRole("button", { name: "ใช้เวลาที่ตัวเล่นอยู่ตอนนี้" }).click()
  await expect(timeField(page, "เริ่ม")).toHaveValue(time)
  // เริ่ม = จบ ใช้ไม่ได้: ป้ายปุ่มไม่มีช่วง และมี error ใต้ช่องเริ่ม
  await expect(button(page, "โหลด mp4")).toBeVisible()
  await expect(page.getByRole("tabpanel").getByText("จุดเริ่มต้องมาก่อนจุดจบ")).toBeVisible()
})

test("ตัวเล่นลอยมีปุ่มตั้งจุดด้วย", async ({ page }) => {
  await installFakeYT(page, { durationS: 372, rate: 0.001 })
  await page.goto(`/v/${THAI}`)
  await button(page, "เล่นคลิป").click()
  await expect(button(page, "ตั้งจุดเริ่ม")).toBeVisible()
  await page.mouse.wheel(0, 4000)
  const dock = page.getByRole("region", { name: "ตัวเล่นคลิป (ลอย)" })
  await expect(dock).toBeVisible()
  await expect(dock.getByRole("button", { name: "ตั้งจุดเริ่ม", exact: true })).toBeVisible()
  await expect(dock.getByRole("button", { name: "ตั้งจุดจบ", exact: true })).toBeVisible()
})
