import { describe, expect, it } from "vitest"

import type { HistoryItem, HistoryPage } from "@/lib/types"

import { HISTORY_PAGE_SIZE, historyPath, historyQuery, nextHistoryOffset, outputLabels, RECENT_LIMIT, recentQuery } from "./queries"

const item = (n: number): HistoryItem => ({
  videoId: `video${n}`,
  title: `คลิป ${n}`,
  channel: "",
  thumbnailUrl: "",
  durationS: 10,
  outputs: [],
  lastAt: "2026-10-01T00:00:00Z",
})
const page = (count: number, total: number): HistoryPage => ({ items: Array.from({ length: count }, (_, i) => item(i)), total })

describe("historyPath", () => {
  it("หน้าแรกของ W1 'ล่าสุด': limit กับ scope เท่านั้น", () => {
    expect(historyPath({ limit: 5, scope: "opened" })).toBe("/history?limit=5&scope=opened")
  })

  it("หน้าประวัติ: scope=all ไม่ส่ง q และ offset เมื่อว่าง/ศูนย์", () => {
    expect(historyPath({ q: "", limit: HISTORY_PAGE_SIZE, offset: 0, scope: "all" })).toBe("/history?limit=50&scope=all")
    expect(historyPath({ q: "   ", limit: 50, scope: "all" })).toBe("/history?limit=50&scope=all")
  })

  it("ส่ง q (ตัดช่องว่างหัวท้าย) และ offset ของหน้าถัดไป", () => {
    expect(historyPath({ q: "  zoo ", limit: 50, offset: 100, scope: "all" })).toBe("/history?q=zoo&limit=50&offset=100&scope=all")
  })

  it("เข้ารหัสอักขระพิเศษและภาษาไทยในคำค้น", () => {
    expect(historyPath({ q: "a&b=c", limit: 50, scope: "all" })).toBe("/history?q=a%26b%3Dc&limit=50&scope=all")
    const path = historyPath({ q: "แมว", limit: 50, scope: "all" })
    expect(new URL(path, "http://x").searchParams.get("q")).toBe("แมว")
  })
})

describe("nextHistoryOffset", () => {
  it("ยังเหลือ: ตำแหน่งถัดไป = จำนวนคลิปที่โหลดแล้วทุกหน้า", () => {
    expect(nextHistoryOffset([page(50, 120)])).toBe(50)
    expect(nextHistoryOffset([page(50, 120), page(50, 120)])).toBe(100)
  })

  it("ครบแล้ว: undefined", () => {
    expect(nextHistoryOffset([page(50, 50)])).toBeUndefined()
    expect(nextHistoryOffset([page(50, 120), page(50, 120), page(20, 120)])).toBeUndefined()
    expect(nextHistoryOffset([page(0, 0)])).toBeUndefined()
  })

  it("หน้าล่าสุดว่างทั้งที่ total ยังมากกว่า (ข้อมูลเปลี่ยนระหว่างโหลด) ไม่วนขอซ้ำ", () => {
    expect(nextHistoryOffset([page(50, 120), page(0, 120)])).toBeUndefined()
  })
})

describe("historyQuery", () => {
  it("key รวม q ที่ตัดช่องว่างแล้ว และ scope=all (ขึ้นต้น 'history' ให้ล้างแคชพร้อมกับรายการล่าสุดของ W1 ได้)", () => {
    expect(historyQuery(" zoo ").queryKey).toEqual(["history", { q: "zoo", scope: "all" }])
    expect(historyQuery("").queryKey).toEqual(["history", { q: "", scope: "all" }])
  })

  it("หน้าแรกเริ่มที่ offset 0 และหน้าถัดไปคำนวณจากจำนวนที่โหลดแล้ว", () => {
    const options = historyQuery("")
    expect(options.initialPageParam).toBe(0)
    const next = options.getNextPageParam as (last: HistoryPage, pages: HistoryPage[], p: number, ps: number[]) => number | undefined
    expect(next(page(50, 70), [page(50, 70)], 0, [0])).toBe(50)
    expect(next(page(20, 70), [page(50, 70), page(20, 70)], 50, [0, 50])).toBeUndefined()
  })
})

describe("recentQuery", () => {
  it("คีย์เดิมของ W1 'ล่าสุด' (5 คลิป scope=opened) หน้าตั้งค่าใช้ตัวเดียวกันจึงได้ cache เดียวกัน", () => {
    expect(RECENT_LIMIT).toBe(5)
    expect(recentQuery().queryKey).toEqual(["history", { limit: 5, scope: "opened" }])
    expect(recentQuery(1).queryKey).toEqual(["history", { limit: 1, scope: "opened" }])
  })
})

describe("outputLabels", () => {
  it("ป้ายไทยตามชนิด ลำดับเดิม", () => {
    expect(outputLabels(["video", "audio", "subtitle"])).toEqual(["วิดีโอ", "เสียง", "ซับ"])
  })

  it("ชนิดที่ป้ายซ้ำกันเหลือป้ายเดียว", () => {
    expect(outputLabels(["contact_sheet", "frames_zip"])).toEqual(["ภาพ"])
    expect(outputLabels(["audio", "contact_sheet", "frames_sharp", "frames_zip"])).toEqual(["เสียง", "ภาพ"])
  })

  it("ไม่มีไฟล์ = ไม่มีป้าย", () => {
    expect(outputLabels([])).toEqual([])
  })
})
