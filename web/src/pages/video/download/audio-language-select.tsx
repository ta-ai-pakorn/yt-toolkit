import { useId, type ReactNode } from "react"

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { th } from "@/i18n/th"
import type { LanguageOption } from "@/lib/download-options"

const t = th.download

/** ช่องเลือกของแท็บวิดีโอ/เสียง: เต็มความกว้างบนจอแคบ กว้างคงที่บนจอกว้าง (จอ 640 px ก็ยังไม่ล้น) */
export const SELECT_TRIGGER = "w-full min-w-0 sm:w-80"

/** รายการที่เปิดออกมากว้างตามข้อความ (อย่างน้อยเท่าช่อง) แต่ไม่เกินจอ */
export const SELECT_CONTENT = "w-auto min-w-(--anchor-width) max-w-[calc(100vw-2rem)]"

type ReasonProps = {
  /** เหตุผลที่กดไม่ได้ (null = กดได้ ไม่มี Tooltip) */
  reason: string | null
  children: ReactNode
}

/**
 * ครอบช่องที่อาจกดไม่ได้: ชี้เมาส์ที่ช่องที่กดไม่ได้แล้วขึ้น Tooltip บอกเหตุผล (PRD W2 "ปิดใช้ … พร้อม Tooltip บอกเหตุผล")
 * ผู้เรียกแสดงเหตุผลเดียวกันเป็นข้อความจางใต้ช่องด้วย (เห็นได้โดยไม่ต้องชี้เมาส์ และผูกกับช่องผ่าน aria-describedby)
 * ปุ่มที่ disabled ไม่รับเมาส์ (pointer-events-none) เมาส์จึงตกที่กรอบนี้แทน · โครงสร้างคงเดิมทั้งตอนกดได้และไม่ได้
 */
export function DisabledReason({ reason, children }: ReasonProps) {
  return (
    <Tooltip disabled={reason === null}>
      <TooltipTrigger render={<div className="w-full min-w-0 sm:w-fit [&_button:disabled]:pointer-events-none" />}>
        {children}
      </TooltipTrigger>
      <TooltipContent>{reason}</TooltipContent>
    </Tooltip>
  )
}

type Props = {
  /** ตัวเลือกภาษาของคลิป (null = เสียงภาษาเดียว ไม่แสดงช่องนี้) */
  options: LanguageOption[] | null
  value: string
  onChange: (value: string) => void
  /** "ไม่เอาเสียง" เปิดอยู่ (แท็บวิดีโอ) = กดไม่ได้ พร้อม Tooltip บอกเหตุผล */
  disabled?: boolean
}

/**
 * ช่อง "ภาษาเสียง" ของแท็บวิดีโอและแท็บเสียง (ค่าเดียวกันทั้งสองแท็บ) ตัวแรก = "ต้นฉบับ (<ภาษา>)"
 * ตามด้วยเฉพาะภาษาที่คลิปมีจริง · คลิปเสียงภาษาเดียว = ไม่แสดง (AC-VID-07)
 */
export function AudioLanguageSelect({ options, value, onChange, disabled = false }: Props) {
  const labelId = useId()
  const reasonId = useId()
  if (options === null) return null
  const labels = new Map(options.map((option) => [option.value, option.label]))

  return (
    <div className="flex flex-col gap-2">
      <div id={labelId} className="text-sm font-medium">
        {t.audioLanguage}
      </div>
      <DisabledReason reason={disabled ? t.languageDisabled : null}>
        <Select<string>
          value={value}
          disabled={disabled}
          onValueChange={(next) => {
            if (next !== null && next !== value) onChange(next)
          }}
        >
          <SelectTrigger
            aria-labelledby={labelId}
            aria-describedby={disabled ? reasonId : undefined}
            className={SELECT_TRIGGER}
          >
            <SelectValue>{(current: string | null) => (current ? (labels.get(current) ?? current) : "")}</SelectValue>
          </SelectTrigger>
          <SelectContent alignItemWithTrigger={false} align="start" className={SELECT_CONTENT}>
            {options.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </DisabledReason>
      {disabled && (
        <p id={reasonId} className="text-sm text-muted-foreground">
          {t.languageDisabled}
        </p>
      )}
    </div>
  )
}
