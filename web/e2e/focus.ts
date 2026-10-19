import { expect, type Locator } from "@playwright/test"

/**
 * รอจนโฟกัสย้ายเข้าไปอยู่ใน popup (กล่อง ภาพใหญ่ เมนู รายการตัวเลือก) แล้ว ก่อนกดปุ่มที่ popup ฟังเอง
 * popup ขึ้นจอก่อน แล้ว Base UI จึงย้ายโฟกัสเข้าไปในเฟรมถัดไป: กดลูกศรระหว่างนั้น ปุ่มไปถึงสิ่งที่โฟกัสอยู่เดิม
 * (เช่นภาพในแถบ) ไม่ใช่ popup · กล่องซ้อนกล่อง: Esc ระหว่างนั้นไม่ปิดกล่องบน
 */
export async function expectFocusInside(popup: Locator): Promise<void> {
  await expect.poll(() => popup.evaluate((el) => el.contains(document.activeElement))).toBe(true)
}
