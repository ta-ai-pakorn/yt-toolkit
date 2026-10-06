import AxeBuilder from "@axe-core/playwright"
import { expect, type Page } from "@playwright/test"

/**
 * รอให้ทรานซิชัน/แอนิเมชันของหน้าจบก่อน แล้วค่อยให้ axe วัด
 * เหตุผล: axe อ่านสีที่ "คำนวณแล้ว" ตอนนั้น ถ้าปุ่มกำลังไล่สี (เช่น ปุ่มที่เพิ่งกด หรือเพิ่งสลับธีม)
 * จะได้สีกลางทางที่คอนทราสต์ต่ำชั่วขณะ แล้วเทสต์ล้มเป็นครั้งคราวเฉพาะตอนเครื่องหน่วง
 * ทรานซิชันของ CSS นับอยู่ใน document.getAnimations() ด้วย
 * (แอนิเมชันที่วนไม่รู้จบ เช่นวงหมุนโหลด ไม่มีวันจบ จึงข้าม)
 */
export async function settleAnimations(page: Page) {
  await expect
    .poll(
      () =>
        page.evaluate(async () => {
          // รอสองเฟรมก่อน เพื่อให้ทรานซิชันที่เพิ่งถูกสั่งเริ่มวิ่งจริง (จะได้อยู่ในรายการ)
          await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())))
          return document
            .getAnimations()
            .filter((a) => a.playState === "running" && a.effect?.getComputedTiming().iterations !== Infinity).length
        }),
      { message: "รอให้ทรานซิชัน/แอนิเมชันจบก่อนตรวจ axe" },
    )
    .toBe(0)
}

/** รัน axe หลังรอให้หน้านิ่ง (เงื่อนไขตรวจไม่ผ่อน ไม่ยกเว้นกฎหรือโหนดใด ๆ) ใช้ configure ถ้าต้องตั้งขอบเขตเพิ่ม */
export async function analyzeSettled(page: Page, configure?: (builder: AxeBuilder) => AxeBuilder) {
  await settleAnimations(page)
  const builder = new AxeBuilder({ page })
  return (configure ? configure(builder) : builder).analyze()
}
