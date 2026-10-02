import { Checkbox } from "@/components/ui/checkbox"
import { th } from "@/i18n/th"
import { SPONSOR_CATEGORIES } from "@/lib/download-options"

import { SwitchRow } from "./switch-row"
import { useSponsorCategoryToggle, type AdvancedChoice } from "./use-advanced-choice"

const t = th.advanced

/**
 * สวิตช์ "ตัดโฆษณา (SponsorBlock)" (เริ่มปิดทุกคลิป D3/D5) + รายการหมวด (ติ๊กแล้วจำข้ามคลิปในการตั้งค่า)
 * หมวดสุดท้ายเอาติ๊กออกไม่ได้ · แท็บวิดีโอที่ฝังซับอยู่ = เตือนว่าเวลาซับจะไม่ตรง (FR-ADV-4)
 */
export function SponsorControls({ tab, choice, embedSubsOn }: { tab: "video" | "audio"; choice: AdvancedChoice; embedSubsOn: boolean }) {
  const toggle = useSponsorCategoryToggle()
  const { values, patch, categories, split } = choice
  const on = values.sponsorblock && !split
  return (
    <div className="flex flex-col gap-3">
      <SwitchRow
        label={t.sponsorblock}
        hint={t.sponsorblockHint}
        checked={on}
        disabled={split}
        reason={split ? t.blocked.chapters : null}
        onChange={(sponsorblock) => patch({ sponsorblock })}
      />
      {on && (
        <div role="group" aria-label={t.sponsorblock} className="grid gap-x-4 gap-y-1 pl-10 sm:grid-cols-2">
          {SPONSOR_CATEGORIES.map((category) => {
            const ticked = categories.includes(category)
            return (
              // ชื่อของช่องมาจาก label ที่ครอบ (Base UI ผูกให้เอง) กดข้อความก็ติ๊กได้
              <label key={category} className="flex min-h-8 cursor-pointer items-center gap-2 text-sm">
                <Checkbox
                  checked={ticked}
                  disabled={ticked && categories.length === 1}
                  onCheckedChange={(checked) => toggle(category, checked === true)}
                />
                {t.categories[category]}
              </label>
            )
          })}
        </div>
      )}
      {tab === "video" && on && embedSubsOn && <p className="text-sm text-warning">{t.subsWarning}</p>}
    </div>
  )
}
