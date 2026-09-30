import { useEffect, useRef } from "react"

import { ScrollArea } from "@/components/ui/scroll-area"
import { th } from "@/i18n/th"
import { formatTimecode } from "@/lib/format"
import type { Cue } from "@/lib/types"

import { centerInScrollArea, revealAndFocus } from "../frame-target"
import { lineRanges, type PreparedLine } from "./search"

const t = th.transcript

// ความสูงสูงสุดของรายการ (เกินนี้เลื่อนในกรอบ) ต้องตั้งที่ viewport ของ ScrollArea เพราะตัวนั้นเป็นส่วนที่เลื่อนได้
const AREA = "rounded-md border [&>[data-slot=scroll-area-viewport]]:max-h-[360px]"

// คลิปยาวมีเป็นพันบรรทัด: บรรทัดที่อยู่นอกกรอบไม่ต้องวาดจนกว่าจะเลื่อนถึง (content-visibility)
// content-visibility ตัดทุกอย่างที่ล้นกรอบ li จึงเว้น padding 3px ให้วงโฟกัสของปุ่มไม่ถูกตัด
const ITEM = "p-[3px] [contain-intrinsic-size:auto_36px] [content-visibility:auto]"

// บรรทัดของเวลาที่มาจาก "ดูซับช่วงนี้" = แถบซ้ายสีอำพันเข้ม (--accent-text ผ่าน 3:1 ทั้งสองธีม) + พื้นจาง
// ต่างจากวงโฟกัส (วงรอบทั้งปุ่ม) จึงเห็นทั้งสองอย่างพร้อมกันได้โดยไม่สับสน
const LINE =
  "flex w-full items-baseline gap-3 rounded-sm border-l-2 border-transparent px-2 py-1.5 text-left text-sm outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 aria-[current=true]:border-accent-text aria-[current=true]:bg-muted"

/** ข้อความของบรรทัด โดยครอบคำที่ตรงคำค้นด้วย <mark> (คำนวณเฉพาะบรรทัดที่แสดง) */
function Highlighted({ line, needle }: { line: PreparedLine; needle: string }) {
  const ranges = lineRanges(line, needle)
  const { text } = line
  if (ranges.length === 0) return <>{text}</>
  const parts = []
  let from = 0
  for (const [start, end] of ranges) {
    if (start > from) parts.push(text.slice(from, start))
    parts.push(
      <mark key={start} className="rounded-sm bg-primary px-0.5 text-primary-foreground">
        {text.slice(start, end)}
      </mark>,
    )
    from = end
  }
  if (from < text.length) parts.push(text.slice(from))
  return <>{parts}</>
}

type Props = {
  cues: Cue[]
  /** ข้อความที่เตรียมไว้ค้นหา ตำแหน่งเดียวกับ cues */
  lines: PreparedLine[]
  /** ตำแหน่งของบรรทัดที่แสดง (ผลค้นหา) เรียงตามเวลา */
  visible: number[]
  /** คำค้นหลังจัดรูป (searchNeedle) ใช้เน้นคำ */
  needle: string
  /** บรรทัดของเวลาที่ส่งมาใน URL (at) · -1 = ไม่มี */
  current: number
  /** เวลาใน URL: เปลี่ยนค่าเมื่อไร เลื่อนไปบรรทัด current และโฟกัสหนึ่งครั้ง · null = ไม่มี */
  revealKey: number | null
  onPick: (cue: Cue) => void
}

/**
 * รายการบรรทัดทรานสคริปต์: แต่ละบรรทัดเป็นปุ่มเดียว เวลา HH:MM:SS + ข้อความ กดแล้วไปภาพเฟรมของช่วงนั้น
 * ต้องเรนเดอร์ไว้ตลอด (ผลค้นหาว่างก็คืน null) เพราะจำไว้ว่าเลื่อนไปหาบรรทัดของ at แล้วหรือยัง
 */
export function LineList({ cues, lines, visible, needle, current, revealKey, onPick }: Props) {
  const buttons = useRef(new Map<number, HTMLButtonElement>())
  const revealed = useRef<number | null>(null)
  // บรรทัดที่ไฮไลต์ถูกซ่อนด้วยคำค้นหลังเลื่อนไปหาแล้ว: กลับมาเห็นเมื่อไร เลื่อนกรอบไปหาอีกครั้ง
  const wasHidden = useRef(false)
  const shown = current >= 0 && visible.includes(current)

  useEffect(() => {
    if (revealKey === null) {
      revealed.current = null
      wasHidden.current = false
      return
    }
    // ยังไม่อยู่ในรายการ (ถูกกรองด้วยคำค้น): รอจนกลับมา ค่อยเลื่อนไปหา
    if (!shown) {
      if (revealed.current === revealKey) wasHidden.current = true
      return
    }
    // มาครั้งแรกด้วยเวลานี้: เลื่อนให้อยู่กลางจอและโฟกัส
    if (revealed.current !== revealKey) {
      return revealAndFocus(
        () => buttons.current.get(current),
        () => {
          revealed.current = revealKey
          wasHidden.current = false
        },
      )
    }
    // กลับมาเห็นหลังถูกกรอง (เช่นล้างคำค้น): เลื่อนเฉพาะกรอบ ไม่แย่งโฟกัสจากช่องค้นหา
    if (wasHidden.current) {
      const frame = requestAnimationFrame(() => {
        wasHidden.current = false
        const button = buttons.current.get(current)
        if (button) centerInScrollArea(button)
      })
      return () => cancelAnimationFrame(frame)
    }
  }, [revealKey, current, shown])

  // ค้นไม่เจอ: ไม่วาดรายการ แต่ตัวนี้ยังอยู่ (สถานะการเลื่อนไปหาบรรทัดข้างบนไม่หาย)
  if (visible.length === 0) return null

  return (
    <ScrollArea className={AREA}>
      <ul aria-label={t.linesLabel} className="flex flex-col p-1">
        {visible.map((index) => {
          const cue = cues[index]
          return (
            <li key={`${cue.startMs}-${index}`} className={ITEM}>
              <button
                ref={(element) => {
                  if (element) buttons.current.set(index, element)
                  else buttons.current.delete(index)
                }}
                type="button"
                aria-current={index === current ? "true" : undefined}
                onClick={() => onPick(cue)}
                className={LINE}
              >
                <span className="shrink-0 font-mono text-xs text-muted-foreground tabular-nums">
                  {formatTimecode(cue.startMs)}
                </span>
                <span className="min-w-0">
                  <Highlighted line={lines[index]} needle={needle} />
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </ScrollArea>
  )
}
