import { useId } from "react"

import { Field, FieldContent, FieldDescription, FieldLabel } from "@/components/ui/field"
import { Switch } from "@/components/ui/switch"

type Props = {
  label: string
  hint: string
  checked: boolean
  onChange: (checked: boolean) => void
  disabled?: boolean
  /** เหตุผลที่กดไม่ได้ (แสดงแทนคำอธิบาย ผูกกับสวิตช์เหมือนคำอธิบาย) null = ไม่มี */
  reason?: string | null
}

/** สวิตช์พร้อมคำอธิบายใต้ชื่อ (คำอธิบายหรือเหตุผลผูกกับสวิตช์ผ่าน aria-describedby) */
export function SwitchRow({ label, hint, checked, onChange, disabled = false, reason = null }: Props) {
  const id = useId()
  const hintId = useId()
  return (
    <Field orientation="horizontal" className="items-start" data-disabled={disabled || undefined}>
      <Switch
        id={id}
        checked={checked}
        onCheckedChange={onChange}
        disabled={disabled}
        aria-describedby={hintId}
        className="mt-0.5"
      />
      <FieldContent>
        <FieldLabel htmlFor={id}>{label}</FieldLabel>
        <FieldDescription id={hintId}>{reason ?? hint}</FieldDescription>
      </FieldContent>
    </Field>
  )
}
