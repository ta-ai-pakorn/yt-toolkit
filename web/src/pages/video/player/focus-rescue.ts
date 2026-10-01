import { useLayoutEffect, useRef, type RefObject } from "react"

/**
 * ปุ่มของตัวเล่นที่หายไปเองได้ (ไม่ได้มาจากการกดของผู้ใช้): แถบไทม์ไลน์หายตอนตัวเล่นลอย, ปุ่มบนตัวเล่นลอยหายตอนกลับเข้าหัวคลิป,
 * ปุ่มหยุดช่วงไฮไลต์หายตอนเล่นจบ · ถ้าโฟกัสอยู่ที่ปุ่มนั้น เบราว์เซอร์ปล่อยโฟกัสหลุดไป body (ผู้ใช้คีย์บอร์ดหลงที่)
 * hook นี้: ตอนส่วนนั้นหายไป ถ้าโฟกัสอยู่ข้างใน ย้ายโฟกัสไปที่ fallback() หลังวาดเสร็จ (เฉพาะเมื่อโฟกัสหลุดไป body จริง)
 */
export function useFocusRescue(ref: RefObject<HTMLElement | null>, fallback: () => HTMLElement | null | undefined): void {
  const latest = useRef(fallback)
  useLayoutEffect(() => {
    latest.current = fallback
  })
  useLayoutEffect(() => {
    const node = ref.current
    // ตอน cleanup ของ layout effect ส่วนนี้ยังอยู่ใน DOM: ดูได้ว่าโฟกัสอยู่ข้างในไหม
    return () => {
      if (node === null || !node.contains(document.activeElement)) return
      requestAnimationFrame(() => {
        const active = document.activeElement
        if (active === null || active === document.body) latest.current()?.focus({ preventScroll: true })
      })
    }
  }, [ref])
}

/** ที่หมายของโฟกัส (ตาม data-slot) ตัวแรกที่มีอยู่ในหน้าตอนนี้ */
export function firstSlot(...slots: string[]): HTMLElement | null {
  for (const slot of slots) {
    const element = document.querySelector<HTMLElement>(`[data-slot="${slot}"]`)
    if (element) return element
  }
  return null
}

/** data-slot ของที่หมายที่อยู่นิ่ง ๆ */
export const FOCUS_SLOTS = {
  /** "กลับไปที่หัวคลิป" บนตัวเล่นลอย */
  dockBack: "dock-back",
  /** แถบไทม์ไลน์ใต้ตัวเล่นในหัวคลิป */
  timeline: "player-timeline",
  /** "เล่นเฉพาะช่วงที่ดูซ้ำบ่อย" ในแถวปุ่มของหัวคลิป */
  reel: "player-reel",
  /** "ดูภาพปก" ในแถวปุ่มของหัวคลิป (มีทุกสถานะของตัวเล่น) */
  cover: "cover-button",
} as const
