import type { Cue, StoryboardFrame } from "@/lib/types"

/**
 * ภาพเฟรมที่ใกล้เวลา atMs ที่สุด (ห่างเท่ากันเลือกภาพที่มาก่อน) · ไม่มีภาพเลย = -1
 * ใช้ตอนกดบรรทัดทรานสคริปต์แล้วมาที่แท็บภาพเฟรม
 */
export function nearestFrameIndex(frames: readonly StoryboardFrame[], atMs: number): number {
  let best = -1
  let bestDistance = Infinity
  frames.forEach((frame, index) => {
    const distance = Math.abs(frame.tMs - atMs)
    if (distance < bestDistance) {
      best = index
      bestDistance = distance
    }
  })
  return best
}

/**
 * บรรทัดซับของเวลา atMs: บรรทัดสุดท้ายที่เริ่มก่อนหรือตรงเวลานั้น (อยู่ในช่องว่างระหว่างบรรทัดก็ได้บรรทัดก่อนหน้า)
 * เวลาก่อนบรรทัดแรก = บรรทัดแรก · ไม่มีบรรทัดเลย = -1 · ใช้ตอน "ดูซับช่วงนี้" จากภาพเฟรม
 */
export function cueIndexAt(cues: readonly Cue[], atMs: number): number {
  if (cues.length === 0) return -1
  let found = 0
  cues.forEach((cue, index) => {
    if (cue.startMs <= atMs) found = index
  })
  return found
}

/**
 * เลื่อนให้เห็นตรงกลางจอแล้วโฟกัส (ใช้กับภาพเฟรม/บรรทัดทรานสคริปต์ที่มาจากอีกแท็บ) · onDone เมื่อทำสำเร็จ
 * รอหนึ่งเฟรมก่อน ให้แท็บใหม่วางผังเสร็จและเมนูที่เพิ่งปิดคืนโฟกัสไปแล้ว ไม่งั้นโฟกัสจะถูกแย่งกลับ
 * ภาพที่อยู่ไกลจอ (content-visibility) ถูกวาดจริงตอนเลื่อนถึง ขนาดจริงต่างจากขนาดที่จองไว้ จึงเลื่อนซ้ำอีกครั้งในเฟรมถัดไป
 * คืนฟังก์ชันยกเลิก (ยกเลิกก่อนเริ่มทำ = ไม่เรียก onDone ครั้งหน้าจะลองใหม่)
 */
export function revealAndFocus(find: () => HTMLElement | null | undefined, onDone: () => void): () => void {
  let second = 0
  const first = requestAnimationFrame(() => {
    const element = find()
    if (!element) return
    element.focus({ preventScroll: true })
    element.scrollIntoView({ block: "center" })
    onDone()
    second = requestAnimationFrame(() => element.scrollIntoView({ block: "center" }))
  })
  return () => {
    cancelAnimationFrame(first)
    cancelAnimationFrame(second)
  }
}

/**
 * เลื่อนเฉพาะในกรอบเลื่อน (ScrollArea) ให้ element อยู่กลางกรอบ ไม่เลื่อนทั้งหน้า และไม่ย้ายโฟกัส
 * ใช้ตอนบรรทัดที่ไฮไลต์กลับมาให้เห็นอีกครั้ง (เช่นล้างคำค้น) ผู้ใช้ยังพิมพ์ต่อในช่องค้นหาได้
 */
export function centerInScrollArea(element: HTMLElement): void {
  const viewport = element.closest<HTMLElement>('[data-slot="scroll-area-viewport"]')
  if (!viewport) return
  const box = element.getBoundingClientRect()
  const frame = viewport.getBoundingClientRect()
  viewport.scrollTop += box.top - frame.top - (frame.height - box.height) / 2
}
