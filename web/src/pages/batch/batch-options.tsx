import { useId, type ReactNode } from "react"

import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { th } from "@/i18n/th"

import { EXTRAS, FOLDER_MAX, type BatchChoice, type ExtraChoice, type WhatChoice } from "./rows"

const t = th.batch

const WHATS: readonly WhatChoice[] = ["video", "audio", "none"]

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
  folder: string
  onFolderChange: (folder: string) => void
}

/**
 * ตัวเลือกของหน้า W3 ใช้กับทุกคลิปที่เลือก (owner round 2):
 * "โหลดอะไร" (วิดีโอ / เสียง / ไม่เอา) · "ไฟล์เพิ่มเติม" ติ๊กได้หลายอย่าง (ค่าเริ่มต้นไม่ติ๊ก)
 * · "ชื่อโฟลเดอร์" ที่ทุกคลิปจะไปอยู่ข้างใน (ว่าง = ส่งไม่ได้ ยาวไม่เกิน 80 ตัวอักษร)
 */
export function BatchOptions({ choice, onChange, folder, onFolderChange }: Props) {
  const folderId = useId()
  const folderHintId = useId()

  function toggleExtra(extra: ExtraChoice, checked: boolean) {
    const extras = new Set(choice.extras)
    if (checked) extras.add(extra)
    else extras.delete(extra)
    onChange({ ...choice, extras })
  }

  return (
    <div className="flex flex-col gap-4">
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
        <Labelled label={t.extras}>
          {(labelId) => (
            // จอแคบ: ช่องติ๊กขึ้นบรรทัดใหม่เองทีละช่อง ไม่ล้นข้าง
            <div role="group" aria-labelledby={labelId} className="flex min-w-0 flex-wrap gap-x-5 gap-y-1">
              {EXTRAS.map((extra) => (
                // ชื่อของช่องมาจาก label ที่ครอบ (Base UI ผูกให้เอง) กดข้อความก็ติ๊กได้
                <label key={extra} className="flex min-h-8 cursor-pointer items-center gap-2 text-sm">
                  <Checkbox
                    checked={choice.extras.has(extra)}
                    onCheckedChange={(checked) => toggleExtra(extra, checked)}
                  />
                  {t.extraItems[extra]}
                </label>
              ))}
            </div>
          )}
        </Labelled>
      </div>
      <div className="flex min-w-0 flex-col gap-2">
        <label htmlFor={folderId} className="text-sm font-medium">
          {t.folder}
        </label>
        <Input
          id={folderId}
          value={folder}
          required
          maxLength={FOLDER_MAX}
          spellCheck={false}
          autoComplete="off"
          aria-describedby={folderHintId}
          aria-invalid={folder.trim() === "" ? true : undefined}
          className="max-w-md"
          onChange={(event) => onFolderChange(event.target.value)}
        />
        <p id={folderHintId} className="text-sm text-muted-foreground">
          {t.folderHint}
        </p>
      </div>
    </div>
  )
}
