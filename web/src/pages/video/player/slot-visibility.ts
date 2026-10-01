import { useEffect, useState } from "react"

/** เห็นช่องตัวเล่นน้อยกว่าครึ่งหนึ่ง = ลอย (ช่องที่เหลือในจอจึงเห็นปกจาง ๆ "กำลังเล่นที่มุมจอ" ให้กดกลับได้) */
const VISIBLE_RATIO = 0.5

/**
 * ช่องตัวเล่นที่หัวคลิปอยู่ในจอหรือไม่ (IntersectionObserver) · ไม่มีช่อง หรือเบราว์เซอร์ไม่มี IO = ถือว่าอยู่ในจอ (ไม่ลอย)
 * หัวคลิปถือค่านี้ไว้ที่เดียว แล้วส่งให้ทั้งช่องตัวเล่น (ลอยไหม) และแถวไทม์ไลน์ (ซ่อนตอนลอย)
 * ทั้งสองจึงเปลี่ยนในการวาดรอบเดียวกัน ไม่มีจังหวะที่แถวไทม์ไลน์โผล่แวบแล้วดันหน้าเลื่อน
 * node มาจาก callback ref (ช่องเกิดใหม่เมื่อเปลี่ยนคลิป หรือหลังข้อมูลคลิปโหลดเสร็จ)
 */
export function useSlotInView(node: HTMLElement | null): boolean {
  const [inView, setInView] = useState(true)
  useEffect(() => {
    if (!node || typeof IntersectionObserver === "undefined") return
    // ช่องสูงคงที่ตอนลอย (ตัวเล่นออกไปเป็น position: fixed) สัดส่วนจึงขึ้นกับการเลื่อนจออย่างเดียว ไม่สลับไปมาเอง
    const observer = new IntersectionObserver(
      ([entry]) => setInView(entry.isIntersecting && entry.intersectionRatio >= VISIBLE_RATIO),
      { threshold: [0, VISIBLE_RATIO, 1] },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [node])
  return inView
}
