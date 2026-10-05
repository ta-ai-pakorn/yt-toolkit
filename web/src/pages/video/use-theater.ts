import { useCallback, useEffect, useReducer } from "react"
import { flushSync } from "react-dom"

import { usePlayerValue } from "./player/player-store"
import {
  headerLayout,
  isTheaterOn,
  prefersReducedMotion,
  readTheaterPreference,
  runLayoutTransition,
  safeStorage,
  theaterKeyAllowed,
  theaterReducer,
  writeTheaterPreference,
  type HeaderLayout,
  type TheaterAction,
} from "./theater"

/** กล่องหรือเมนูที่เปิดอยู่ (Base UI ถอดออกจาก DOM เมื่อปิด) ปุ่ม T ต้องไม่ทำงานระหว่างนั้น */
const OVERLAYS = '[role="dialog"], [role="alertdialog"], [role="menu"], [role="listbox"]'

/**
 * โหมดโรงภาพยนตร์ของหัวคลิป (M5 รอบ B2 spec 1): เลย์เอาต์ที่ใช้ ปุ่มสลับ และปุ่ม T
 * - กด ▶ ในช่องตัวเล่น (onPlayPressed): ค่าที่จำไว้เป็นโรงภาพยนตร์ (ค่าเริ่มต้น) = ขยาย
 * - toggle (ปุ่มหรือ T): สลับแล้วจำค่าไว้ใน localStorage ใช้ครั้งถัดไปที่กด ▶ ทุกคลิป
 * - เปิดคลิปอื่น = แบบปกติจนกว่าจะกด ▶ · จอแคบ = แบบปกติเสมอ ไม่มีปุ่ม T ไม่ทำงาน
 * - สลับผ่าน View Transition (flushSync ให้ DOM ใหม่พร้อมก่อนจับภาพ) ยกเว้นลดการเคลื่อนไหวหรือตัวเล่นลอยอยู่
 */
export function useTheater(o: { videoId: string | null; portrait: boolean; narrow: boolean; inView: boolean }): {
  layout: HeaderLayout
  on: boolean
  canToggle: boolean
  toggle: () => void
  onPlayPressed: () => void
} {
  const { videoId, portrait, narrow, inView } = o
  const [state, dispatch] = useReducer(theaterReducer, { videoId: null, on: false })
  const on = videoId !== null && isTheaterOn(state, videoId)
  const started = usePlayerValue((s) => videoId !== null && s.videoId === videoId && s.started)
  const canToggle = started && !narrow
  const layout = headerLayout({ on, narrow, portrait })

  const change = useCallback(
    (action: TheaterAction) => {
      runLayoutTransition(() => flushSync(() => dispatch(action)), {
        doc: document,
        animate: !narrow && inView && !prefersReducedMotion(),
      })
    },
    [narrow, inView],
  )

  const toggle = useCallback(() => {
    if (videoId === null) return
    writeTheaterPreference(safeStorage(), !on)
    change({ type: "toggle", videoId })
  }, [videoId, on, change])

  const onPlayPressed = useCallback(() => {
    if (videoId === null) return
    const preference = readTheaterPreference(safeStorage())
    const action: TheaterAction = { type: "play", videoId, preference }
    if (preference && !on && !narrow) change(action)
    else dispatch(action)
  }, [videoId, on, narrow, change])

  useEffect(() => {
    if (!canToggle) return
    const onKey = (event: KeyboardEvent) => {
      if (!theaterKeyAllowed(event, { canToggle, overlayOpen: document.querySelector(OVERLAYS) !== null })) return
      event.preventDefault()
      toggle()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [canToggle, toggle])

  return { layout, on, canToggle, toggle, onPlayPressed }
}
