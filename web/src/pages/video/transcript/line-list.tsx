import { Play } from "lucide-react"
import { memo, useCallback, useEffect, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { fill, th } from "@/i18n/th"
import { formatTimecode } from "@/lib/format"
import type { Cue } from "@/lib/types"

import { centerInScrollArea, cueIndexAt, revealAndFocus } from "../frame-target"
import { hasPlayhead, nowPlayingLine } from "../playback-sync"
import { getPlayerState, playerActions, usePlayerValue } from "../player/player-store"
import { ReplayedMark } from "../replayed-mark"
import { isUserScroll, scrollIntoViewWithinList, type FollowInput } from "./follow"
import { lineRanges, type PreparedLine } from "./search"

const t = th.transcript

// ความสูงสูงสุดของรายการ (เกินนี้เลื่อนในกรอบ) ต้องตั้งที่ viewport ของ ScrollArea เพราะตัวนั้นเป็นส่วนที่เลื่อนได้
const AREA = "rounded-md border [&>[data-slot=scroll-area-viewport]]:max-h-[360px]"

// คลิปยาวมีเป็นพันบรรทัด: บรรทัดที่อยู่นอกกรอบไม่ต้องวาดจนกว่าจะเลื่อนถึง (content-visibility)
// content-visibility ตัดทุกอย่างที่ล้นกรอบ li จึงเว้น padding 3px ให้วงโฟกัสของปุ่มไม่ถูกตัด
// บรรทัดที่กำลังเล่น (M3.5) = แถบพื้นอำพันจางเต็มแถว (แบบคาราโอเกะ) ครอบทั้งปุ่มเวลาและข้อความ
const ITEM =
  "flex items-stretch gap-1 rounded-md p-[3px] [contain-intrinsic-size:auto_36px] [content-visibility:auto] data-playing:bg-primary/20"

// ปุ่มเวลาหน้าบรรทัด (M3.5): กดแล้วเล่นคลิปจากบรรทัดนั้น · ไอคอน ▶ เล็ก ๆ บอกว่ากดแล้วเล่น
const TIME =
  "inline-flex shrink-0 items-baseline gap-1 rounded-sm px-1.5 py-1.5 font-mono text-xs text-muted-foreground tabular-nums outline-none hover:bg-muted hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 in-data-playing:text-foreground"

// บรรทัดของเวลาที่มาจาก "ดูซับช่วงนี้" (?at=) = แถบซ้ายสีอำพันเข้ม (--accent-text ผ่าน 3:1 ทั้งสองธีม) + พื้นจาง
// ต่างจากวงโฟกัส (วงรอบทั้งปุ่ม) และแถบพื้นของบรรทัดที่กำลังเล่น จึงเห็นทั้งหมดพร้อมกันได้โดยไม่สับสน
const LINE =
  "flex min-w-0 flex-1 items-baseline gap-2 rounded-sm border-l-2 border-transparent px-2 py-1.5 text-left text-sm outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 data-highlighted:border-accent-text data-highlighted:bg-muted"

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

type LineProps = {
  index: number
  cue: Cue
  line: PreparedLine
  needle: string
  /** บรรทัดของเวลาใน URL (?at=) */
  highlighted: boolean
  /** บรรทัดที่กำลังเล่น */
  playing: boolean
  /** บรรทัดนี้ได้ aria-current: บรรทัดที่กำลังเล่นเมื่อตัวเล่นมีตำแหน่ง ไม่งั้นบรรทัดของ ?at= */
  current: boolean
  replayed: boolean
  onPick: (cue: Cue) => void
  onPlay: (cue: Cue) => void
  setButton: (index: number, element: HTMLButtonElement | null) => void
}

/** บรรทัดเดียว: ปุ่มเวลา (เล่นจากตรงนี้) + ปุ่มข้อความ (ไปภาพเฟรมของช่วงนั้น) · memo: เวลาเดินแล้วเรนเดอร์ใหม่เฉพาะบรรทัดที่สถานะเปลี่ยน */
const Line = memo(function Line({
  index,
  cue,
  line,
  needle,
  highlighted,
  playing,
  current,
  replayed,
  onPick,
  onPlay,
  setButton,
}: LineProps) {
  const time = formatTimecode(cue.startMs)
  const ref = useCallback((element: HTMLButtonElement | null) => setButton(index, element), [index, setButton])
  return (
    <li className={ITEM} data-playing={playing ? "" : undefined}>
      <button type="button" aria-label={fill(t.playFromAt, { time })} onClick={() => onPlay(cue)} className={TIME}>
        <Play aria-hidden className="size-2.5 shrink-0 self-center fill-current" />
        {time}
      </button>
      <button
        ref={ref}
        type="button"
        data-highlighted={highlighted ? "" : undefined}
        aria-current={current ? "true" : undefined}
        onClick={() => onPick(cue)}
        className={LINE}
      >
        {replayed && <ReplayedMark className="inline-flex shrink-0 self-center" />}
        <span className="min-w-0">
          <Highlighted line={line} needle={needle} />
        </span>
      </button>
    </li>
  )
})

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
  /** บรรทัดไหนอยู่ในช่วงที่คนดูซ้ำมากที่สุด (ตำแหน่งเดียวกับ cues) ไม่มี = ไม่มีป้าย */
  replayed?: readonly boolean[]
  /** เวลาใน URL: เปลี่ยนค่าเมื่อไร เลื่อนไปบรรทัด current และโฟกัสหนึ่งครั้ง · null = ไม่มี */
  revealKey: number | null
  onPick: (cue: Cue) => void
}

/**
 * รายการบรรทัดทรานสคริปต์: แต่ละบรรทัดมีปุ่มเวลา (เล่นคลิปจากบรรทัดนั้น) + ปุ่มข้อความ (ไปภาพเฟรมของช่วงนั้น)
 * ต้องเรนเดอร์ไว้ตลอด (ผลค้นหาว่างก็คืน null) เพราะจำไว้ว่าเลื่อนไปหาบรรทัดของ at แล้วหรือยัง
 *
 * ระหว่างเล่น (M3.5): บรรทัดที่กำลังเล่นมีแถบพื้นและได้ aria-current · กรอบรายการเลื่อนตามให้เห็นบรรทัดนั้น (nearest)
 * ผู้ใช้เลื่อนรายการเอง = หยุดเลื่อนตาม และขึ้นปุ่ม "กลับไปบรรทัดที่กำลังเล่น" · กดเวลาของบรรทัดไหนก็กลับมาเลื่อนตาม
 */
export function LineList({ cues, lines, visible, needle, current, replayed, revealKey, onPick }: Props) {
  const buttons = useRef(new Map<number, HTMLButtonElement>())
  const revealed = useRef<number | null>(null)
  // บรรทัดที่ไฮไลต์ถูกซ่อนด้วยคำค้นหลังเลื่อนไปหาแล้ว: กลับมาเห็นเมื่อไร เลื่อนกรอบไปหาอีกครั้ง
  const wasHidden = useRef(false)
  const shown = current >= 0 && visible.includes(current)
  // บรรทัดที่กำลังเล่น (ตำแหน่งใน cues) เปลี่ยนเฉพาะตอนเล่นข้ามบรรทัด ไม่ใช่ทุกครั้งที่เวลาเดิน
  const playing = usePlayerValue((state) => nowPlayingLine(cues, state))
  const active = usePlayerValue(hasPlayhead)
  const [following, setFollowing] = useState(true)
  // ตัวเล่นปิด/เล่นจบ (ไม่มีตำแหน่งแล้ว) = ล้างการหยุดเลื่อนตาม เล่นรอบใหม่ก็เลื่อนตามตั้งแต่ต้น
  const [wasActive, setWasActive] = useState(active)
  if (wasActive !== active) {
    setWasActive(active)
    if (!active) setFollowing(true)
  }
  const playingShown = playing >= 0 && visible.includes(playing)

  const setButton = useCallback((index: number, element: HTMLButtonElement | null) => {
    if (element) buttons.current.set(index, element)
    else buttons.current.delete(index)
  }, [])

  const onPlay = useCallback((cue: Cue) => {
    setFollowing(true)
    playerActions.playFrom(cue.startMs)
  }, [])

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

  // เลื่อนกรอบรายการตามบรรทัดที่กำลังเล่น (เลื่อนเฉพาะในกรอบ ไม่ดึงหน้า) · รอหนึ่งเฟรมให้บรรทัดวาดเสร็จก่อน
  useEffect(() => {
    if (!following || !playingShown) return
    const frame = requestAnimationFrame(() => {
      const button = buttons.current.get(playing)
      if (button) scrollIntoViewWithinList(button)
    })
    return () => cancelAnimationFrame(frame)
  }, [following, playing, playingShown])

  // ผู้ใช้เลื่อนรายการเอง (ดูจากเจตนา ไม่ใช่เหตุการณ์ scroll ซึ่งรวมการเลื่อนที่แอปสั่งเอง) = หยุดเลื่อนตาม
  function onIntent(input: FollowInput) {
    if (following && isUserScroll(input)) setFollowing(false)
  }

  // กลับไปเลื่อนตาม: ปุ่มนี้จะหายไป จึงโฟกัสบรรทัดที่กำลังเล่น (อยู่ในช่องว่างระหว่างบรรทัด = บรรทัดก่อนหน้า)
  function resume() {
    setFollowing(true)
    const target = playing >= 0 ? playing : cueIndexAt(cues, getPlayerState().currentMs)
    const button = buttons.current.get(target)
    if (button) {
      button.focus({ preventScroll: true })
      scrollIntoViewWithinList(button)
    }
  }

  // ค้นไม่เจอ: ไม่วาดรายการ แต่ตัวนี้ยังอยู่ (สถานะการเลื่อนไปหาบรรทัดข้างบนไม่หาย)
  if (visible.length === 0) return null

  // aria-current: บรรทัดที่กำลังเล่นเมื่อตัวเล่นมีตำแหน่ง (เล่น/หยุดชั่วคราว) ไม่งั้นบรรทัดของเวลาใน URL
  const currentIndex = active ? playing : current

  return (
    <div className="relative">
      <ScrollArea
        className={AREA}
        onWheel={(event) => onIntent({ type: "wheel", ctrlKey: event.ctrlKey })}
        onTouchMove={() => onIntent({ type: "touchmove" })}
        onKeyDown={(event) =>
          onIntent({
            type: "keydown",
            key: event.key,
            target: (event.target as HTMLElement).tagName,
            altKey: event.altKey,
            ctrlKey: event.ctrlKey,
            metaKey: event.metaKey,
          })
        }
        onPointerDown={(event) => {
          if ((event.target as Element).closest('[data-slot="scroll-area-scrollbar"]')) onIntent({ type: "scrollbar" })
        }}
      >
        <ul aria-label={t.linesLabel} className="flex flex-col p-1">
          {visible.map((index) => (
            <Line
              key={`${cues[index].startMs}-${index}`}
              index={index}
              cue={cues[index]}
              line={lines[index]}
              needle={needle}
              highlighted={index === current}
              playing={index === playing}
              current={index === currentIndex}
              replayed={replayed?.[index] ?? false}
              onPick={onPick}
              onPlay={onPlay}
              setButton={setButton}
            />
          ))}
        </ul>
      </ScrollArea>
      {active && !following && (
        <Button
          variant="secondary"
          size="sm"
          onClick={resume}
          className="absolute bottom-2 left-1/2 -translate-x-1/2 shadow-md max-sm:h-11"
        >
          <Play aria-hidden className="fill-current" />
          {t.backToPlaying}
        </Button>
      )}
    </div>
  )
}
