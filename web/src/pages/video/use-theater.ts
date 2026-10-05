import { useCallback, useEffect, useLayoutEffect, useReducer, useRef } from "react"
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

const CONTROLS = '[data-slot="player-controls"]'
const TOGGLE = '[data-slot="theater-toggle"]'
/** ส่วนในแถวใต้ตัวเล่นที่ต้องคงโฟกัสไว้เมื่อแถวย้ายคอลัมน์ (คลิปแนวตั้ง: แบบปกติ ↔ โรงภาพยนตร์) · รวมปุ่ม "ถ่ายภาพคมตรงนี้" */
const KEEP_FOCUS = [TOGGLE, '[role="slider"]', '[data-slot="capture-button"]']

/** โฟกัสอยู่ที่ปุ่มสลับหรือแถบไทม์ไลน์ในแถวใต้ตัวเล่นไหม (คืน selector ของส่วนนั้น) */
function focusedControl(): string | null {
  const active = document.activeElement
  if (!(active instanceof HTMLElement) || active.closest(CONTROLS) === null) return null
  return KEEP_FOCUS.find((selector) => active.matches(selector)) ?? null
}

/**
 * หลังสลับ: แถวใต้ตัวเล่นถูกสร้างใหม่ในอีกคอลัมน์ (คลิปแนวตั้ง) โฟกัสเดิมจึงหาย ย้ายไปส่วนเดียวกันในแถวใหม่
 * (ก่อน useFocusRescue ส่งไป "ดูภาพปก") · ปุ่มสลับหายไปเลย (ปิดตัวเล่นแล้วย่อกลับ) = ปุ่ม ▶ ในช่องตัวเล่น
 */
function restoreFocus(selector: string): void {
  const target =
    document.querySelector<HTMLElement>(`${CONTROLS} ${selector}`) ??
    (selector === TOGGLE ? document.querySelector<HTMLElement>('[data-slot="video-header"] [data-slot="player-play"]') : null)
  if (target && document.activeElement !== target) target.focus({ preventScroll: true })
}

/**
 * โหมดโรงภาพยนตร์ของหัวคลิป (M5 รอบ B2 spec 1): เลย์เอาต์ที่ใช้ ปุ่มสลับ และปุ่ม T
 * - กด ▶ ในช่องตัวเล่น (onPlayPressed): ค่าที่จำไว้เป็นโรงภาพยนตร์ (ค่าเริ่มต้น) = ขยาย
 * - toggle (ปุ่มหรือ T): สลับแล้วจำค่าไว้ใน localStorage ใช้ครั้งถัดไปที่กด ▶ ทุกคลิป
 * - เปิดคลิปอื่น = แบบปกติจนกว่าจะกด ▶ · จอแคบ = แบบปกติเสมอ ไม่มีปุ่ม T ไม่ทำงาน
 * - ปิดตัวเล่นตอนขยายอยู่ = เลย์เอาต์คงเดิม ปุ่มและ T ยังย่อกลับได้ (ย่อแล้วปุ่มหายจนกว่าจะกด ▶ อีกครั้ง)
 * - แถวใต้ตัวเล่นย้ายคอลัมน์ (คลิปแนวตั้ง) โฟกัสที่ปุ่มสลับหรือแถบไทม์ไลน์ตามไปที่ส่วนเดียวกันในแถวใหม่
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
  // สถานะที่วาดลงจอแล้วล่าสุด (อัปเดตระหว่าง flushSync) ใช้จำค่าตามเลย์เอาต์ที่เห็นจริงหลังสลับ
  const committed = useRef(state)
  useLayoutEffect(() => {
    committed.current = state
  }, [state])
  const started = usePlayerValue((s) => videoId !== null && s.videoId === videoId && s.started)
  // ปิดตัวเล่นตอนอยู่ในโหมดโรงภาพยนตร์ เลย์เอาต์คงเดิม: ยังสลับได้ (ปุ่มและ T) จนกว่าจะย่อกลับ
  const canToggle = (started || on) && !narrow
  const layout = headerLayout({ on, narrow, portrait })

  // ค่าล่าสุดของจอแคบ/ช่องอยู่ในจอ ณ ตอนกด (ตั้งก่อนวาดจอ): ปุ่ม T ที่ผูกไว้ตั้งแต่ก่อนตัวเล่นลอยจะได้ไม่ใช้ค่าเก่าแล้วเล่นแอนิเมชัน
  const live = useRef({ narrow, inView })
  useLayoutEffect(() => {
    live.current = { narrow, inView }
  }, [narrow, inView])

  const change = useCallback((action: TheaterAction, remember = false) => {
    const apply = () => {
      const focused = focusedControl()
      flushSync(() => dispatch(action))
      // จำค่าจากสถานะหลังสลับ ไม่ใช่จาก on ตอนวาดจอ: กด T สองครั้งก่อนวาดจอใหม่ = สลับสองครั้ง ค่าที่จำต้องตรงกับที่เห็น
      if (remember) writeTheaterPreference(safeStorage(), isTheaterOn(committed.current, action.videoId))
      if (focused !== null) restoreFocus(focused)
    }
    runLayoutTransition(apply, {
      doc: document,
      animate: !live.current.narrow && live.current.inView && !prefersReducedMotion(),
    })
  }, [])

  const toggle = useCallback(() => {
    if (videoId === null) return
    change({ type: "toggle", videoId }, true)
  }, [videoId, change])

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
