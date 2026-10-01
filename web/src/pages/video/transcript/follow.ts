/**
 * "เลื่อนตามบรรทัดที่กำลังเล่น" ของแท็บทรานสคริปต์ (M3.5 ข้อ 4) ส่วนที่ไม่รู้จัก React
 *
 * หยุดเลื่อนตามเมื่อผู้ใช้เลื่อนรายการเอง ดูจาก "เจตนา" (ล้อเมาส์ ลากนิ้ว ปุ่มเลื่อนบนคีย์บอร์ด กดแถบเลื่อน)
 * ไม่ดูจากเหตุการณ์ scroll: การเลื่อนที่แอปสั่งเอง (เลื่อนตามบรรทัด) และการที่บรรทัดไกลจอถูกวาดจริงแล้วขนาดเปลี่ยน
 * (content-visibility) ก็ยิง scroll เหมือนกัน ถ้านับ scroll จะหยุดเลื่อนตามเองโดยที่ผู้ใช้ไม่ได้ทำอะไร
 */

export type FollowInput =
  | { type: "wheel"; ctrlKey?: boolean }
  | { type: "touchmove" }
  /** target = แท็กของ element ที่ได้โฟกัส (ตัวพิมพ์ใหญ่แบบ DOM เช่น "BUTTON") */
  | { type: "keydown"; key: string; target?: string; altKey?: boolean; ctrlKey?: boolean; metaKey?: boolean }
  /** กด/ลากแถบเลื่อนของกรอบรายการ */
  | { type: "scrollbar" }
  /** เหตุการณ์ scroll ทุกแบบ (รวมที่แอปเลื่อนเอง) ไม่ใช่เจตนาของผู้ใช้ */
  | { type: "scroll" }

// ปุ่มที่เลื่อนกรอบรายการเมื่อโฟกัสอยู่ในรายการ (Tab ย้ายโฟกัส ไม่ใช่การเลื่อนดู)
const SCROLL_KEYS = new Set(["ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End"])
// Space บนปุ่ม/ช่องพิมพ์ = กดปุ่ม/พิมพ์ ไม่ใช่เลื่อน
const SPACE_CONSUMERS = new Set(["BUTTON", "INPUT", "TEXTAREA", "SELECT", "A"])

/** เหตุการณ์นี้แปลว่าผู้ใช้เลื่อนรายการเองหรือไม่ (true = หยุดเลื่อนตามบรรทัดที่กำลังเล่น) */
export function isUserScroll(input: FollowInput): boolean {
  switch (input.type) {
    case "wheel":
      // Ctrl + ล้อ = ซูมหน้า ไม่ได้เลื่อนรายการ
      return !input.ctrlKey
    case "touchmove":
    case "scrollbar":
      return true
    case "keydown":
      if (input.altKey || input.ctrlKey || input.metaKey) return false
      if (SCROLL_KEYS.has(input.key)) return true
      return input.key === " " && !SPACE_CONSUMERS.has(input.target ?? "")
    case "scroll":
      return false
  }
}

/**
 * scrollTop ใหม่ของกรอบเลื่อน ให้กึ่งกลางบรรทัด (box) อยู่กึ่งกลางกรอบ (frame) · ตำแหน่งเป็นพิกัดจอ (getBoundingClientRect)
 * ต้นรายการ/ท้ายรายการเลื่อนได้แค่ถึงขอบ (0 ถึง maxScrollTop) บรรทัดแรก ๆ จึงอยู่บน บรรทัดท้าย ๆ อยู่ล่าง ตามธรรมชาติ
 * (owner: บรรทัดที่กำลังเล่นต้องไม่ไปกองที่ขอบล่างของรายการ อ่านบรรทัดถัดไปล่วงหน้าได้)
 */
export function centeredScrollTop(
  scrollTop: number,
  frame: { top: number; bottom: number },
  box: { top: number; bottom: number },
  maxScrollTop: number,
): number {
  const offset = (box.top + box.bottom) / 2 - (frame.top + frame.bottom) / 2
  return Math.round(Math.min(Math.max(0, scrollTop + offset), Math.max(0, maxScrollTop)))
}

/**
 * เลื่อนกรอบรายการ (ScrollArea) ให้บรรทัดอยู่กลางกรอบ โดยไม่เลื่อนหน้า · ไม่อยู่ในกรอบเลื่อน = ไม่ทำอะไร
 * คำนวณ scrollTop เองแทน element.scrollIntoView เพราะตัวนั้นเลื่อนทั้งหน้าด้วย ถ้ารายการอยู่นอกจอ (ผู้ใช้ดูตัวเล่นอยู่) หน้าจะถูกดึงไปเอง
 */
export function centerWithinList(element: HTMLElement): void {
  const viewport = element.closest<HTMLElement>('[data-slot="scroll-area-viewport"]')
  if (!viewport) return
  // ทั้งแถว (ปุ่มเวลา + ข้อความ) ไม่ใช่แค่ปุ่มข้อความ
  const line = element.closest("li") ?? element
  const next = centeredScrollTop(
    viewport.scrollTop,
    viewport.getBoundingClientRect(),
    line.getBoundingClientRect(),
    viewport.scrollHeight - viewport.clientHeight,
  )
  if (next !== viewport.scrollTop) viewport.scrollTop = next
}
