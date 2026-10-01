import type { UseQueryResult } from "@tanstack/react-query"
import { CaptionsOff } from "lucide-react"
import { useEffect, useId, useRef, useState, type RefObject } from "react"

import { Empty, EmptyDescription, EmptyHeader, EmptyMedia } from "@/components/ui/empty"
import { Skeleton } from "@/components/ui/skeleton"
import { fill, th } from "@/i18n/th"
import { cueStats } from "@/lib/srt-builder"
import type { SubOptions, SubTokens } from "@/lib/types"

import { hasCode } from "../errors"
import { LoadError } from "../load-error"
import { isWarming } from "../session-warming"
import { useCues } from "../use-cues"
import { SessionWarming } from "./session-warming"
import { previewTime } from "./track-groups"
import { TranslationBlocked } from "./translation-blocked"

const t = th.subs

const PREVIEW_CUES = 5

function PreviewSkeleton() {
  return (
    <div className="flex flex-col gap-2" aria-busy="true">
      <span className="sr-only" role="status">
        {t.loading}
      </span>
      {Array.from({ length: PREVIEW_CUES }, (_, index) => (
        <Skeleton key={index} className="h-11 w-full" />
      ))}
    </div>
  )
}

function NoTokens() {
  return (
    <Empty className="border">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <CaptionsOff aria-hidden />
        </EmptyMedia>
        <EmptyDescription>{t.none}</EmptyDescription>
      </EmptyHeader>
    </Empty>
  )
}

/**
 * กล่องเลื่อนแนวนอนกว้างไม่พอกับเนื้อหาหรือไม่ (ตรวจใหม่เมื่อกล่องหรือเนื้อหาเปลี่ยนขนาด)
 * ใช้ตัดสินว่ากล่องต้องเป็นจุด Tab ไหม: เลื่อนได้ต้องเลื่อนด้วยคีย์บอร์ดได้ ไม่ต้องเลื่อนก็ไม่ต้องเป็นจุด Tab เพิ่ม
 */
function useOverflowX(box: RefObject<HTMLElement | null>, content: RefObject<HTMLElement | null>): boolean {
  const [overflowing, setOverflowing] = useState(false)
  useEffect(() => {
    const element = box.current
    if (!element || typeof ResizeObserver === "undefined") return
    const check = () => setOverflowing(element.scrollWidth > element.clientWidth)
    const observer = new ResizeObserver(check)
    observer.observe(element)
    if (content.current) observer.observe(content.current)
    check()
    return () => observer.disconnect()
  }, [box, content])
  return overflowing
}

/**
 * ตัวอย่าง 5 ซับแรก + สรุปทั้งแทร็ก: ข้อความและการขึ้นบรรทัดตรงกับที่ตัวสร้างซับให้มาทุกตัว
 * (ไม่ตัดคำหรือขึ้นบรรทัดเพิ่มเอง บรรทัดที่ยาวกว่ากล่องเลื่อนดูแนวนอนได้) จะได้เห็นแบบเดียวกับในไฟล์ .srt
 */
function PreviewBody({ data, options }: { data: SubTokens; options: SubOptions }) {
  const titleId = useId()
  // options มาจาก useSubSettings ตรง ๆ (ก้อนเดิมระหว่าง render) ซับจึงสร้างใหม่เฉพาะเมื่อค่าเปลี่ยนจริง
  const cues = useCues(data.tokens, options)
  const stats = cueStats(cues)
  const boxRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLOListElement>(null)
  const overflowing = useOverflowX(boxRef, listRef)

  return (
    <section aria-labelledby={titleId} className="flex flex-col gap-2">
      <h3 id={titleId} className="text-sm font-medium">
        {t.previewTitle}
      </h3>
      <div
        ref={boxRef}
        // บรรทัดซับไม่ถูกตัดขึ้นบรรทัดใหม่: จอแคบเลื่อนแนวนอนได้ และเฉพาะตอนเลื่อนได้จึงรับโฟกัส (เลื่อนด้วยคีย์บอร์ด)
        tabIndex={overflowing ? 0 : undefined}
        className="overflow-x-auto rounded-lg border bg-muted/30 outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <ol ref={listRef} className="flex w-max min-w-full flex-col divide-y">
          {cues.slice(0, PREVIEW_CUES).map((cue, index) => (
            <li key={index} data-slot="cue" className="flex flex-col gap-0.5 px-3 py-2">
              <span className="font-mono text-xs text-muted-foreground">
                {previewTime(cue.startMs)} → {previewTime(cue.endMs)}
              </span>
              <span data-slot="cue-lines" className="flex flex-col whitespace-pre">
                {cue.lines.map((line, lineIndex) => (
                  <span key={lineIndex} data-slot="cue-line">
                    {line}
                  </span>
                ))}
              </span>
            </li>
          ))}
        </ol>
      </div>
      <p data-slot="cue-stats" className="text-sm text-muted-foreground">
        {fill(t.stats, { n: stats.count, avg: stats.avgChars, short: stats.underOneSecond })}
      </p>
      {!data.hasWordTiming && <p className="text-sm text-muted-foreground">{t.noWordTiming}</p>}
    </section>
  )
}

type Props = {
  /** ผลของ tokensQuery สำหรับแทร็กที่ใช้อยู่ */
  query: UseQueryResult<SubTokens>
  options: SubOptions
  /** ปุ่ม "ใช้ซับภาษาต้นฉบับ" เมื่อยูทูปไม่ให้โหลดซับแปล null = คลิปไม่มีแทร็กเริ่มต้น (ไม่มีปุ่ม) */
  onUseOriginal: ((button: HTMLButtonElement) => void) | null
}

/**
 * ตัวอย่างซับครบ 4 สถานะ: กำลังโหลด = Skeleton 5 แถว · แทร็กไม่มีข้อความ = Empty
 * ยูทูปไม่ให้โหลดซับแปล = คำแนะนำ + ปุ่มใช้ซับภาษาต้นฉบับ · ซับแปลรอเซสชัน = กล่องนับถอยหลัง (โหลดให้เองเมื่อครบ)
 * ผิดพลาดอื่น = Alert + ลองใหม่ (ถ้าลองแล้วช่วย)
 */
export function SubsPreview({ query, options, onUseOriginal }: Props) {
  if (query.isError) {
    if (hasCode(query.error, "E_NO_SUBTITLES")) return <NoTokens />
    if (hasCode(query.error, "E_TRANSLATION_BLOCKED")) return <TranslationBlocked onUseOriginal={onUseOriginal} />
    if (isWarming(query.error)) return <SessionWarming key={query.errorUpdatedAt} query={query} onUseOriginal={onUseOriginal} />
    return <LoadError title={t.loadError} error={query.error} onRetry={() => void query.refetch()} />
  }
  if (!query.isSuccess) return <PreviewSkeleton />
  return <PreviewBody data={query.data} options={options} />
}
