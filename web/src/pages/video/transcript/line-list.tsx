import { useEffect, useRef } from "react"

import { ScrollArea } from "@/components/ui/scroll-area"
import { th } from "@/i18n/th"
import { formatTimecode } from "@/lib/format"
import type { Cue } from "@/lib/types"

import { revealAndFocus } from "../frame-target"
import { cueDisplayText, matchRanges } from "./search"

const t = th.transcript

// ความสูงสูงสุดของรายการ (เกินนี้เลื่อนในกรอบ) ต้องตั้งที่ viewport ของ ScrollArea เพราะตัวนั้นเป็นส่วนที่เลื่อนได้
const AREA = "rounded-md border [&>[data-slot=scroll-area-viewport]]:max-h-[360px]"

// บรรทัดที่มาจาก "ดูซับช่วงนี้" มีกรอบสีอำพัน 2px (สีเดียวกับกรอบภาพเฟรมที่เลือก BRD 10.7)
const LINE =
  "flex w-full items-baseline gap-3 rounded-md px-2 py-1.5 text-left text-sm outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 aria-[current=true]:ring-2 aria-[current=true]:ring-primary"

/** ข้อความของบรรทัด โดยครอบคำที่ตรงคำค้นด้วย <mark> */
function Highlighted({ text, query }: { text: string; query: string }) {
  const ranges = matchRanges(text, query)
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
  /** ตำแหน่งของบรรทัดที่แสดง (ผลค้นหา) เรียงตามเวลา */
  visible: number[]
  query: string
  /** บรรทัดของเวลาที่ส่งมาใน URL (at) · -1 = ไม่มี */
  current: number
  /** เวลาใน URL: เปลี่ยนค่าเมื่อไร เลื่อนไปบรรทัด current และโฟกัสหนึ่งครั้ง · null = ไม่มี */
  revealKey: number | null
  onPick: (cue: Cue) => void
}

/** รายการบรรทัดทรานสคริปต์: แต่ละบรรทัดเป็นปุ่ม เวลา HH:MM:SS + ข้อความ กดแล้วไปภาพเฟรมของช่วงนั้น */
export function LineList({ cues, visible, query, current, revealKey, onPick }: Props) {
  const buttons = useRef(new Map<number, HTMLButtonElement>())
  const revealed = useRef<number | null>(null)

  useEffect(() => {
    if (revealKey === null) {
      revealed.current = null
      return
    }
    if (revealed.current === revealKey || current < 0) return
    return revealAndFocus(
      () => buttons.current.get(current),
      () => {
        revealed.current = revealKey
      },
    )
  }, [revealKey, current])

  return (
    <ScrollArea className={AREA}>
      <ul aria-label={t.linesLabel} className="flex flex-col gap-0.5 p-1.5">
        {visible.map((index) => {
          const cue = cues[index]
          return (
            <li key={`${cue.startMs}-${index}`}>
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
                  <Highlighted text={cueDisplayText(cue)} query={query} />
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </ScrollArea>
  )
}
