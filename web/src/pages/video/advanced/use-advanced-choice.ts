import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query"
import { showErrorToast } from "@/components/error-report/error-toast"
import { fill, th } from "@/i18n/th"
import {
  chapterBlock,
  chaptersAvailable,
  choiceParts,
  keptSeconds,
  rangeAvailable,
  rangeText,
  validateRange,
  type ChapterBlock,
  type RangeCheck,
} from "@/lib/advanced-options"
import { NO_ADVANCED, SPONSOR_CATEGORIES, sponsorCategories, type AdvancedParams } from "@/lib/download-options"
import { reportRequest } from "@/lib/report"
import { patchSettings, SETTINGS_KEY, settingsQuery } from "@/lib/settings-api"
import type { Settings, SponsorCategory, VideoInfo } from "@/lib/types"

import { advancedActions, advancedActive, useAdvanced, type AdvancedValues } from "./advanced-store"

export type AdvancedTab = "video" | "audio" | "subs"

export type AdvancedChoice = {
  values: AdvancedValues
  patch: (patch: Partial<AdvancedValues>) => void
  /** ป้าย "ใช้ตัวเลือกขั้นสูงอยู่" */
  active: boolean
  /** ตั้งช่วงเวลาได้ (ไม่ใช่คลิปสด รู้ความยาว) */
  rangeOk: boolean
  /** แสดงสวิตช์แยก chapter ในแท็บนี้ (วิดีโอ/เสียง และคลิปมี >= 2 chapter) */
  chaptersOk: boolean
  /** แยก chapter เปิดอยู่ (ทุกแท็บ: ช่องเวลา ตัดโฆษณา และฝังซับกดไม่ได้) */
  split: boolean
  check: RangeCheck
  /** ช่องเวลามี error = กดโหลดแล้วไม่สร้างงาน (AC-ADV-02) */
  invalid: boolean
  /** เหตุผลที่สวิตช์แยก chapter กดไม่ได้ */
  block: ChapterBlock | null
  categories: SponsorCategory[]
  /** ตัวเลือกที่ส่งไปกับงานของแท็บนี้ */
  params: AdvancedParams
  /** ความยาวหลังตัดช่วง (วินาที) ใช้ย่อขนาดประมาณ */
  keptS: number | undefined
  /** ป้ายปุ่มโหลด เช่น "โหลด mp4 (1:30-5:00, ตัดโฆษณา)" */
  label: (base: string) => string
}

/** id ของช่องเวลา (มีแท็บเดียวที่เรนเดอร์อยู่ จึงไม่ซ้ำกัน) */
export const fieldId = (which: "start" | "end", tab: AdvancedTab): string => `advanced-${which}-${tab}`

/**
 * ตัวเลือกขั้นสูงของแท็บหนึ่ง (M5 รอบ A): ค่าจากที่เก็บต่อคลิป + ตรวจช่องเวลา + หมวดโฆษณาจากการตั้งค่า
 * ซับ: ส่งเฉพาะช่วงเวลา · วิดีโอ/เสียง: ช่วงเวลา แยก chapter ตัดโฆษณา (แยก chapter ชนะทุกอย่างที่เปิดทีหลัง)
 */
export function useAdvancedChoice(video: VideoInfo | undefined, tab: AdvancedTab, embedSubsOn: boolean): AdvancedChoice {
  const videoId = video?.videoId ?? ""
  const values = useAdvanced(videoId)
  const settings = useQuery(settingsQuery())
  const rangeOk = video !== undefined && rangeAvailable(video)
  const hasChapters = video !== undefined && chaptersAvailable(video)
  const split = hasChapters && values.splitChapters
  const check: RangeCheck =
    video !== undefined && rangeOk && !split
      ? validateRange(values.startText, values.endText, video.durationS)
      : { range: null, startError: null, endError: null }
  const categories = sponsorCategories(settings.data)
  const media = tab !== "subs"
  const ads = media && values.sponsorblock && !split
  const params: AdvancedParams = { ...NO_ADVANCED, splitChapters: media && split }
  if (check.range) params.range = check.range
  if (ads) params.sponsorblock = categories
  const texts = choiceParts({ range: check.range, splitChapters: params.splitChapters, ads }).map((part) =>
    part.kind === "range" ? rangeText(part.range) : part.kind === "chapters" ? th.advanced.choiceChapters : th.advanced.choiceAds,
  )
  return {
    values,
    patch: (patch) => advancedActions.patch(videoId, patch),
    active: advancedActive(values),
    rangeOk,
    chaptersOk: media && hasChapters,
    split,
    check,
    invalid: check.startError !== null || check.endError !== null,
    block: chapterBlock(values, embedSubsOn),
    categories,
    params,
    keptS: check.range ? keptSeconds(check.range) : undefined,
    label: (base) => (texts.length === 0 ? base : fill(th.advanced.withChoice, { label: base, choice: texts.join(", ") })),
  }
}

/** กดโหลดตอนช่องเวลามี error: กางส่วนตัวเลือก แสดง error แล้วโฟกัสช่องแรกที่ผิด (ไม่สร้างงาน AC-ADV-02) */
export function revealRangeErrors(choice: AdvancedChoice, videoId: string, tab: AdvancedTab): void {
  advancedActions.patch(videoId, { checked: true, open: true })
  const which = choice.check.startError !== null ? "start" : "end"
  requestAnimationFrame(() => document.getElementById(fieldId(which, tab))?.focus())
}

const SPONSOR_MUTATION_KEY = ["settings", "sponsorblockDefault"] as const

/**
 * การบันทึกหมวด SponsorBlock: คำขอเข้าแถวทีละคำขอ (scope เดียวกัน) ติ๊กเร็ว ๆ หลายช่องจึงไม่แซงกันจนติ๊กหาย
 * เห็นผลทันที (onMutate) · ยังมีคำขอรออยู่ = ยังไม่เอาค่าจากเซิร์ฟเวอร์มาทับ (ช่องไม่เด้งกลับชั่วคราว)
 */
export function sponsorToggleMutation(
  client: QueryClient,
  save: (next: SponsorCategory[]) => Promise<Settings> = (next) => patchSettings({ sponsorblockDefault: next }),
) {
  return {
    mutationKey: SPONSOR_MUTATION_KEY,
    scope: { id: "sponsorblockDefault" },
    mutationFn: save,
    onMutate: async (next: SponsorCategory[]) => {
      await client.cancelQueries({ queryKey: SETTINGS_KEY })
      const previous = client.getQueryData<Settings>(SETTINGS_KEY)
      if (previous) client.setQueryData<Settings>(SETTINGS_KEY, { ...previous, sponsorblockDefault: next })
      return { previous }
    },
    onError: (error: unknown, _next: SponsorCategory[], context: { previous: Settings | undefined } | undefined) => {
      if (context?.previous) client.setQueryData(SETTINGS_KEY, context.previous)
      showErrorToast(th.general.saveFailed, { id: "advanced-save", request: reportRequest(error, { context: "advanced-save" }) })
    },
    onSuccess: (saved: Settings) => {
      if (client.isMutating({ mutationKey: SPONSOR_MUTATION_KEY }) <= 1) client.setQueryData(SETTINGS_KEY, saved)
    },
  }
}

/** หมวดที่จะบันทึกหลังติ๊ก/เอาติ๊ก คิดจากค่าล่าสุดในแคช (รวมที่ติ๊กไปแล้วแต่ยังบันทึกไม่เสร็จ) */
export function nextSponsorCategories(client: QueryClient, category: SponsorCategory, on: boolean): SponsorCategory[] {
  const current = sponsorCategories(client.getQueryData<Settings>(SETTINGS_KEY))
  return SPONSOR_CATEGORIES.filter((c) => (c === category ? on : current.includes(c)))
}

/**
 * ติ๊ก/เอาติ๊กหมวด SponsorBlock: บันทึกลงการตั้งค่า sponsorblockDefault (D3 จำข้ามคลิป) แบบเห็นผลทันที
 * บันทึกไม่สำเร็จ = คืนค่าเดิม + toast · หมวดสุดท้ายเอาติ๊กออกไม่ได้ (ผู้เรียกปิดช่องนั้นไว้ด้วย)
 */
export function useSponsorCategoryToggle(): (category: SponsorCategory, on: boolean) => void {
  const client = useQueryClient()
  const mutation = useMutation(sponsorToggleMutation(client))
  return (category, on) => {
    const next = nextSponsorCategories(client, category, on)
    if (next.length > 0) mutation.mutate(next)
  }
}
