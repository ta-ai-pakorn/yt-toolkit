import { infiniteQueryOptions, keepPreviousData, queryOptions } from "@tanstack/react-query"

import { th } from "@/i18n/th"
import { api } from "@/lib/api"
import type { HistoryPage, JobKind } from "@/lib/types"

/** หน้าละ 50 คลิป (สัญญา C15) */
export const HISTORY_PAGE_SIZE = 50

export type HistoryScope = "all" | "opened"

type PathOptions = { q?: string; limit: number; offset?: number; scope: HistoryScope }

/**
 * เส้นทาง GET /history ตามสัญญา C15: ลำดับพารามิเตอร์คงที่ (q, limit, offset, scope)
 * q ว่าง = ไม่ส่ง · offset 0 = ไม่ส่ง
 */
export function historyPath({ q = "", limit, offset = 0, scope }: PathOptions): string {
  const params = new URLSearchParams()
  const term = q.trim()
  if (term) params.set("q", term)
  params.set("limit", String(limit))
  if (offset > 0) params.set("offset", String(offset))
  params.set("scope", scope)
  return `/history?${params.toString()}`
}

/** ตำแหน่งเริ่มของหน้าถัดไป: นับจากจำนวนคลิปที่โหลดแล้ว · ไม่เหลือแล้ว (หรือหน้าล่าสุดว่าง) = undefined */
export function nextHistoryOffset(pages: readonly HistoryPage[]): number | undefined {
  const last = pages[pages.length - 1]
  if (!last || last.items.length === 0) return undefined
  const loaded = pages.reduce((sum, page) => sum + page.items.length, 0)
  return loaded < last.total ? loaded : undefined
}

/** หน้า W5: คลิปทั้งหมดที่เปิดดูหรือโหลดไฟล์ เรียงใหม่สุดก่อน · ค้นจากชื่อด้วย q */
export function historyQuery(q: string) {
  const term = q.trim()
  return infiniteQueryOptions({
    queryKey: ["history", { q: term, scope: "all" }],
    queryFn: ({ pageParam, signal }) =>
      api<HistoryPage>(historyPath({ q: term, limit: HISTORY_PAGE_SIZE, offset: pageParam, scope: "all" }), { signal }),
    initialPageParam: 0,
    getNextPageParam: (_last, pages) => nextHistoryOffset(pages),
    // พิมพ์ค้นหาแล้วรอผลใหม่: ยังแสดงรายการเดิมไว้ ไม่วูบเป็นโครงรอทุกครั้งที่พิมพ์
    placeholderData: keepPreviousData,
  })
}

/** W1 "ล่าสุด" จำนวนคลิป */
export const RECENT_LIMIT = 5

/**
 * คลิปที่เปิดดูล่าสุด (W1 "ล่าสุด" และตัวอย่างชื่อไฟล์ในหน้าตั้งค่า M6 รอบ A) ใช้คีย์เดียวกันจึงใช้ cache ร่วมกัน
 * "opened" = เฉพาะคลิปที่เคยเปิดดูในหน้า W2 (หน้า /history แสดงคลิปที่โหลดไฟล์ด้วย)
 */
export function recentQuery(limit = RECENT_LIMIT) {
  return queryOptions({
    queryKey: ["history", { limit, scope: "opened" }] as const,
    queryFn: () => api<HistoryPage>(historyPath({ limit, scope: "opened" })),
  })
}

/** ป้ายชนิดไฟล์ของแถว: ชนิดที่ใช้ป้ายเดียวกัน (เช่น contact sheet กับ zip ภาพ = "ภาพ") แสดงครั้งเดียว ลำดับตามที่ backend ส่งมา */
export function outputLabels(outputs: readonly JobKind[]): string[] {
  return [...new Set(outputs.map((kind) => th.history.kinds[kind]))]
}
