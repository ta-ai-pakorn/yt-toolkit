import { ChevronDown } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { th } from "@/i18n/th"
import type { VideoInfo } from "@/lib/types"

import { RangeFields } from "./range-fields"
import { SponsorControls } from "./sponsor-controls"
import { SwitchRow } from "./switch-row"
import type { AdvancedChoice, AdvancedTab } from "./use-advanced-choice"

const t = th.advanced

type Props = {
  video: VideoInfo
  tab: AdvancedTab
  choice: AdvancedChoice
  /** แท็บวิดีโอฝังซับอยู่ (คำเตือน SponsorBlock) */
  embedSubsOn: boolean
}

/**
 * "ตัวเลือกขั้นสูง" (M5 รอบ A): พับไว้ตอนแรก ค่าชุดเดียวกันทุกแท็บ (ที่เก็บต่อคลิป) · ป้าย "ใช้ตัวเลือกขั้นสูงอยู่" ข้างหัวข้อ
 * วิดีโอ/เสียง: ช่วงเวลา · แยกไฟล์ตาม chapter (คลิปมี >= 2 chapter) · ตัดโฆษณา · ซับ: ช่วงเวลาเท่านั้น
 */
export function AdvancedSection({ video, tab, choice, embedSubsOn }: Props) {
  const { values, patch } = choice
  const chapterReason = !values.splitChapters && choice.block !== null ? t.blocked[choice.block] : null
  return (
    <Collapsible open={values.open} onOpenChange={(open) => patch({ open })} className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <CollapsibleTrigger render={<Button variant="ghost" size="sm" className="group/advanced -ml-2.5" />}>
          {t.title}
          <ChevronDown aria-hidden className="transition-transform group-data-[panel-open]/advanced:rotate-180" />
        </CollapsibleTrigger>
        {choice.active && (
          <Badge variant="secondary" data-slot="advanced-active">
            {t.active}
          </Badge>
        )}
      </div>
      <CollapsibleContent className="flex min-w-0 flex-col gap-5 rounded-lg border p-4">
        <RangeFields video={video} tab={tab} choice={choice} />
        {choice.chaptersOk && (
          <SwitchRow
            label={t.chapters}
            hint={tab === "video" ? t.chaptersHint + t.chaptersVideoHint : t.chaptersHint}
            checked={values.splitChapters}
            disabled={chapterReason !== null}
            reason={chapterReason}
            onChange={(splitChapters) => patch({ splitChapters })}
          />
        )}
        {tab !== "subs" && <SponsorControls tab={tab} choice={choice} embedSubsOn={embedSubsOn} />}
      </CollapsibleContent>
    </Collapsible>
  )
}
