import type { UseQueryResult } from "@tanstack/react-query"
import { CaptionsOff } from "lucide-react"
import { useId } from "react"

import { Empty, EmptyDescription, EmptyHeader, EmptyMedia } from "@/components/ui/empty"
import { Skeleton } from "@/components/ui/skeleton"
import { fill, th } from "@/i18n/th"
import { ApiError } from "@/lib/api"
import { cueStats } from "@/lib/srt-builder"
import type { SubOptions, SubTokens } from "@/lib/types"

import { LoadError } from "../load-error"
import { useCues } from "../use-cues"
import { previewTime } from "./track-groups"

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
 * ตัวอย่าง 5 ซับแรก + สรุปทั้งแทร็ก: ข้อความและการขึ้นบรรทัดตรงกับที่ตัวสร้างซับให้มาทุกตัว
 * (ไม่ตัดคำหรือขึ้นบรรทัดเพิ่มเอง บรรทัดที่ยาวกว่ากล่องเลื่อนดูแนวนอนได้) จะได้เห็นแบบเดียวกับในไฟล์ .srt
 */
function PreviewBody({ data, options }: { data: SubTokens; options: SubOptions }) {
  const titleId = useId()
  // options มาจาก useSubSettings ตรง ๆ (ก้อนเดิมระหว่าง render) ซับจึงสร้างใหม่เฉพาะเมื่อค่าเปลี่ยนจริง
  const cues = useCues(data.tokens, options)
  const stats = cueStats(cues)

  return (
    <section aria-labelledby={titleId} className="flex flex-col gap-2">
      <h3 id={titleId} className="text-sm font-medium">
        {t.previewTitle}
      </h3>
      <div
        // บรรทัดซับไม่ถูกตัดขึ้นบรรทัดใหม่: จอแคบเลื่อนแนวนอนได้ จึงต้องรับโฟกัสได้ด้วย (เลื่อนด้วยคีย์บอร์ด)
        tabIndex={0}
        role="group"
        aria-labelledby={titleId}
        className="overflow-x-auto rounded-lg border bg-muted/30 outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <ol className="flex w-max min-w-full flex-col divide-y">
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
}

/** ตัวอย่างซับครบ 4 สถานะ: กำลังโหลด = Skeleton 5 แถว · แทร็กไม่มีข้อความ = Empty · ผิดพลาด = Alert + ลองใหม่ */
export function SubsPreview({ query, options }: Props) {
  if (query.isError) {
    if (query.error instanceof ApiError && query.error.code === "E_NO_SUBTITLES") return <NoTokens />
    return <LoadError title={t.loadError} error={query.error} onRetry={() => void query.refetch()} />
  }
  if (!query.isSuccess) return <PreviewSkeleton />
  return <PreviewBody data={query.data} options={options} />
}
