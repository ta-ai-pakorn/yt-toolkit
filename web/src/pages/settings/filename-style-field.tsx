import { useQuery } from "@tanstack/react-query"

import { Field, FieldDescription, FieldTitle } from "@/components/ui/field"
import { fill, th } from "@/i18n/th"
import { FILENAME_STYLES, type FilenameStyle } from "@/lib/filename"
import { recentQuery } from "@/pages/history/queries"

import { ChoiceSelect } from "./choice-select"
import { exampleFileName } from "./filename-example"

const t = th.general

type Props = {
  /** ค่าที่แสดงอยู่ (ระหว่างรอบันทึก = ค่าที่เพิ่งเลือก บรรทัดตัวอย่างจึงเปลี่ยนทันที) */
  value: FilenameStyle
  outputDir: string
  onChange: (value: FilenameStyle) => void
}

/**
 * รูปแบบชื่อไฟล์ + บรรทัด "ตัวอย่าง: …" (M6 รอบ A spec 2.6, PRD :306, AC-OUT-10)
 * ตัวอย่างคำนวณในหน้าเว็บจากคลิปที่เปิดล่าสุด (คีย์เดียวกับ "ล่าสุด" ใน W1 ใช้ cache ร่วม) เปลี่ยนรูปแบบแล้วไม่เรียก API
 * โหลดคลิปล่าสุดไม่ได้หรือยังไม่เคยเปิดคลิป = ชื่อตัวอย่างภาษาไทย
 */
export function FilenameStyleField({ value, outputDir, onChange }: Props) {
  const recent = useQuery(recentQuery())
  const latest = recent.data?.items[0]
  const name = exampleFileName(value, latest, outputDir)
  return (
    <Field>
      <FieldTitle id="general-filename">{t.filenameStyle}</FieldTitle>
      <ChoiceSelect
        labelId="general-filename"
        hintId="general-filename-example"
        value={value}
        options={FILENAME_STYLES.map((style) => ({ value: style, label: t.filenameStyles[style] }))}
        onChange={(next) => {
          const style = FILENAME_STYLES.find((s) => s === next)
          if (style) onChange(style)
        }}
      />
      <FieldDescription id="general-filename-example" className="font-mono break-all">
        {fill(t.filenameExample, { name })}
      </FieldDescription>
    </Field>
  )
}
