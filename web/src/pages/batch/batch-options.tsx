import { useId, type ReactNode } from "react"

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { th } from "@/i18n/th"

import type { BatchChoice, SubChoice, WhatChoice } from "./rows"

const t = th.batch

const WHATS: readonly WhatChoice[] = ["video", "audio", "none"]
// ชื่อชนิดไฟล์ซับเป็นนามสกุลไฟล์ ไม่แปล
const SUBS: readonly { value: SubChoice; label: string }[] = [
  { value: "none", label: t.subsNone },
  { value: "srt", label: ".srt" },
  { value: "txt", label: ".txt" },
  { value: "md", label: ".md" },
]

function Labelled({ label, children }: { label: string; children: (labelId: string) => ReactNode }) {
  const labelId = useId()
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <div id={labelId} className="text-sm font-medium">
        {label}
      </div>
      {children(labelId)}
    </div>
  )
}

type Props = {
  choice: BatchChoice
  onChange: (choice: BatchChoice) => void
}

/** ตัวเลือกของหน้า W3: "โหลดอะไร" (วิดีโอ / เสียง / ไม่เอา) และ "ซับ" (ไม่เอา / .srt / .txt / .md) ใช้กับทุกคลิปที่เลือก */
export function BatchOptions({ choice, onChange }: Props) {
  return (
    <div className="flex flex-wrap items-start gap-x-8 gap-y-4">
      <Labelled label={t.what}>
        {(labelId) => (
          <Select<WhatChoice>
            value={choice.what}
            onValueChange={(next) => {
              if (next !== null && WHATS.includes(next)) onChange({ ...choice, what: next })
            }}
          >
            <SelectTrigger aria-labelledby={labelId} className="w-48 max-w-full min-w-0">
              <SelectValue>{(current: WhatChoice | null) => (current ? t.whats[current] : "")}</SelectValue>
            </SelectTrigger>
            <SelectContent alignItemWithTrigger={false} align="start">
              {WHATS.map((value) => (
                <SelectItem key={value} value={value}>
                  {t.whats[value]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </Labelled>
      <Labelled label={t.subs}>
        {(labelId) => (
          <ToggleGroup
            aria-labelledby={labelId}
            variant="outline"
            spacing={0}
            value={[choice.sub]}
            // กดปุ่มที่เลือกอยู่ซ้ำจะได้ค่าว่าง: ไม่ทำอะไร (ต้องมีตัวเลือกหนึ่งอยู่เสมอ)
            onValueChange={(value) => {
              const next = SUBS.find((option) => option.value === value[0])
              if (next) onChange({ ...choice, sub: next.value })
            }}
          >
            {SUBS.map((option) => (
              <ToggleGroupItem key={option.value} value={option.value} className="px-4">
                {option.label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        )}
      </Labelled>
    </div>
  )
}
