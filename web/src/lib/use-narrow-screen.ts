import { useSyncExternalStore } from "react"

// จอแคบแบบเดียวกับ max-sm: ของ Tailwind (< 640 px)
const QUERY = "(width < 40rem)"

const media = () => (typeof window !== "undefined" && typeof window.matchMedia === "function" ? window.matchMedia(QUERY) : null)

function subscribe(onChange: () => void): () => void {
  const list = media()
  if (!list) return () => {}
  list.addEventListener("change", onChange)
  return () => list.removeEventListener("change", onChange)
}

const snapshot = () => media()?.matches ?? false

/**
 * จอแคบ (มือถือ < 640 px) ไหม · ใช้เฉพาะตอนที่ต้องย้ายของไปอีกที่ใน DOM (ให้ลำดับ Tab/โปรแกรมอ่านหน้าจอตรงกับที่ตาเห็น)
 * แค่เปลี่ยนหน้าตาให้ใช้ max-sm: ของ CSS แทน
 */
export function useNarrowScreen(): boolean {
  return useSyncExternalStore(subscribe, snapshot, () => false)
}
