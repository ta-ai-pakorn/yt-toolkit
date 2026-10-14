import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

type ChoiceSelectProps = {
  labelId: string
  hintId?: string
  value: string
  options: { value: string; label: string }[]
  onChange: (value: string) => void
}

/** ช่องเลือกจากรายการของแท็บทั่วไป (ย้ายออกจาก general-panel.tsx ใน M6 รอบ A ให้ช่องรูปแบบชื่อไฟล์ใช้ร่วม) */
export function ChoiceSelect({ labelId, hintId, value, options, onChange }: ChoiceSelectProps) {
  const labels = new Map(options.map((o) => [o.value, o.label]))
  return (
    <Select<string> value={value} onValueChange={(next) => next && onChange(next)}>
      <SelectTrigger aria-labelledby={labelId} aria-describedby={hintId} className="w-full min-w-0 sm:w-72">
        <SelectValue>{(current: string | null) => (current ? (labels.get(current) ?? current) : "")}</SelectValue>
      </SelectTrigger>
      <SelectContent alignItemWithTrigger={false} align="start">
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
