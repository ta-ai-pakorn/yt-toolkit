import { ChevronDown } from "lucide-react"
import { useId, type ReactNode } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Field, FieldGroup, FieldLabel, FieldTitle } from "@/components/ui/field"
import { Slider } from "@/components/ui/slider"
import { Switch } from "@/components/ui/switch"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { fill, th } from "@/i18n/th"
import { clampOptions, DEFAULT_TOKENS_PER_CUE, LIMITS, PRESET_NAMES, presetOf } from "@/lib/sub-options"
import type { SubOptions, SubPreset } from "@/lib/types"

const t = th.subs

// จอแคบ (มือถือ) ปุ่มสูง 44 px ให้นิ้วกดได้ง่าย
const TOUCH = "max-sm:h-11"

const seconds = (ms: number) => (ms / 1000).toFixed(1)

/** ค่าเดียวจากสไลเดอร์ (ส่ง value เป็น [n] จึงได้กลับมาเป็นอาร์เรย์ 1 ช่อง) */
const first = (value: number | readonly number[]) => (typeof value === "number" ? value : value[0])

type SliderFieldProps = {
  label: string
  /** ตัวเลขที่แสดงข้างชื่อ (ตัวอักษร Plex Mono) */
  display: string
  value: number
  min: number
  max: number
  step: number
  onChange: (value: number) => void
}

function SliderField({ label, display, value, min, max, step, onChange }: SliderFieldProps) {
  const labelId = useId()
  return (
    <Field>
      <div className="flex items-baseline justify-between gap-3">
        <FieldTitle id={labelId}>{label}</FieldTitle>
        <span className="font-mono text-sm tabular-nums" aria-hidden>
          {display}
        </span>
      </div>
      <Slider
        aria-labelledby={labelId}
        min={min}
        max={max}
        step={step}
        value={[value]}
        onValueChange={(next) => {
          const n = first(next)
          if (n !== undefined && Number.isFinite(n)) onChange(n)
        }}
        className="py-2"
      />
    </Field>
  )
}

function Labelled({ label, children }: { label: string; children: (labelId: string) => ReactNode }) {
  const labelId = useId()
  return (
    <div className="flex flex-col gap-2">
      <div id={labelId} className="text-sm font-medium">
        {label}
      </div>
      {children(labelId)}
    </div>
  )
}

type Props = {
  /** ตัวเลือกปัจจุบันจาก useSubSettings (ค่าที่บีบช่วงแล้ว) */
  options: SubOptions
  onPreset: (preset: SubPreset) => void
  onCustom: (options: SubOptions) => void
}

/**
 * ความยาวซับ: ปุ่มสำเร็จรูป สั้น/กลาง/ยาว/ทีละคำ + กล่องพับ "ปรับเอง" (ตัวอักษร บรรทัด เวลา นับเป็นคำ)
 * ค่าที่ปรับเองทุกค่าผ่าน clampOptions ก่อนเก็บ · ค่าไม่ตรงสำเร็จรูปแบบไหนเลย = ไม่มีปุ่มไหนถูกเลือก + ป้าย "ใช้ค่าที่ปรับเอง"
 */
export function PresetControls({ options, onPreset, onCustom }: Props) {
  const preset = presetOf(options)
  const byWords = options.mode === "tokens"
  const switchId = useId()

  const change = (patch: Partial<SubOptions>) => onCustom(clampOptions({ ...options, ...patch }))

  return (
    <div className="flex flex-col gap-3">
      <Labelled label={t.presetLabel}>
        {(labelId) => (
          <div className="flex flex-wrap items-center gap-3">
            <ToggleGroup
              aria-labelledby={labelId}
              variant="outline"
              spacing={0}
              value={preset ? [preset] : []}
              // กดปุ่มที่เลือกอยู่ซ้ำจะได้ค่าว่าง: ไม่ทำอะไร (ต้องมีสำเร็จรูปหรือค่าที่ปรับเองอยู่เสมอ)
              onValueChange={(value) => {
                const next = PRESET_NAMES.find((name) => name === value[0])
                if (next) onPreset(next)
              }}
            >
              {PRESET_NAMES.map((name) => (
                <Tooltip key={name}>
                  <TooltipTrigger render={<ToggleGroupItem value={name} className={`px-4 ${TOUCH}`} />}>
                    {t.presets[name]}
                  </TooltipTrigger>
                  <TooltipContent>{t.presetHints[name]}</TooltipContent>
                </Tooltip>
              ))}
            </ToggleGroup>
            {preset === null && <Badge variant="secondary">{t.customInUse}</Badge>}
          </div>
        )}
      </Labelled>

      <Collapsible>
        <CollapsibleTrigger
          render={<Button variant="ghost" size="sm" className={`group/custom -ml-2.5 ${TOUCH}`} />}
        >
          {t.custom}
          <ChevronDown
            aria-hidden
            className="transition-transform group-data-[panel-open]/custom:rotate-180 motion-reduce:transition-none"
          />
        </CollapsibleTrigger>
        <CollapsibleContent>
          <FieldGroup className="gap-4 pt-3 sm:max-w-md">
            <SliderField
              label={t.maxChars}
              display={String(options.maxChars)}
              value={options.maxChars}
              min={LIMITS.maxChars[0]}
              max={LIMITS.maxChars[1]}
              step={1}
              onChange={(maxChars) => change({ maxChars })}
            />
            <Labelled label={t.lines}>
              {(labelId) => (
                <ToggleGroup
                  aria-labelledby={labelId}
                  variant="outline"
                  spacing={0}
                  value={[String(options.lines)]}
                  onValueChange={(value) => {
                    if (value[0] === "1" || value[0] === "2") change({ lines: value[0] === "2" ? 2 : 1 })
                  }}
                >
                  {([1, 2] as const).map((n) => (
                    <ToggleGroupItem key={n} value={String(n)} className={`px-4 ${TOUCH}`}>
                      {fill(t.lineCount, { n })}
                    </ToggleGroupItem>
                  ))}
                </ToggleGroup>
              )}
            </Labelled>
            <SliderField
              label={t.minSeconds}
              display={seconds(options.minMs)}
              value={options.minMs / 1000}
              min={LIMITS.minMs[0] / 1000}
              max={LIMITS.minMs[1] / 1000}
              step={0.1}
              onChange={(s) => change({ minMs: Math.round(s * 1000) })}
            />
            <SliderField
              label={t.maxSeconds}
              display={seconds(options.maxMs)}
              value={options.maxMs / 1000}
              min={LIMITS.maxMs[0] / 1000}
              max={LIMITS.maxMs[1] / 1000}
              step={0.5}
              onChange={(s) => change({ maxMs: Math.round(s * 1000) })}
            />
            <Field orientation="horizontal" className="w-fit">
              <Switch
                id={switchId}
                checked={byWords}
                onCheckedChange={(checked) =>
                  change(
                    checked
                      ? { mode: "tokens", tokensPerCue: options.tokensPerCue ?? DEFAULT_TOKENS_PER_CUE }
                      : { mode: "chars" },
                  )
                }
              />
              <FieldLabel htmlFor={switchId}>{t.byWords}</FieldLabel>
            </Field>
            {byWords && (
              <SliderField
                label={t.wordsPerCue}
                display={String(options.tokensPerCue ?? DEFAULT_TOKENS_PER_CUE)}
                value={options.tokensPerCue ?? DEFAULT_TOKENS_PER_CUE}
                min={LIMITS.tokensPerCue[0]}
                max={LIMITS.tokensPerCue[1]}
                step={1}
                onChange={(tokensPerCue) => change({ tokensPerCue })}
              />
            )}
          </FieldGroup>
        </CollapsibleContent>
      </Collapsible>
    </div>
  )
}
