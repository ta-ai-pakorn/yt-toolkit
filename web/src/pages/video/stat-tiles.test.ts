import { describe, expect, it } from "vitest"

import type { VideoInfo } from "@/lib/types"

import { statTiles } from "./stat-tiles"

const base: VideoInfo = {
  videoId: "abc",
  title: "คลิป",
  channel: "ช่อง",
  durationS: 212,
  publishedAt: "2005-04-23",
  thumbnailUrl: "",
  chapters: [],
  video: [],
  audio: [],
  hasStoryboard: true,
  isLive: false,
}

describe("statTiles", () => {
  it("ครบทุกค่า: 6 ช่องตามลำดับ ค่าย่อแบบไทย ชื่อเต็มมีตัวเลขเต็ม", () => {
    const tiles = statTiles({
      ...base,
      stats: { views: 580_123, likes: 4567, comments: 89, channelFollowers: 2_000_000 },
    })
    expect(tiles.map((tile) => tile.label)).toEqual(["ยอดวิว", "ไลก์", "คอมเมนต์", "ผู้ติดตาม", "ความยาว", "เผยแพร่"])
    expect(tiles[0]).toEqual({ key: "views", label: "ยอดวิว", value: "5.8 แสน", full: "ยอดวิว 580,123 ครั้ง" })
    expect(tiles[1].full).toBe("ไลก์ 4,567 ครั้ง")
    expect(tiles[2]).toMatchObject({ value: "89", full: "คอมเมนต์ 89 รายการ" })
    expect(tiles[3]).toMatchObject({ value: "2 ล้าน", full: "ผู้ติดตาม 2,000,000 คน" })
    expect(tiles[4]).toMatchObject({ value: "3:32", full: "ความยาว 3:32" })
    // ช่องแคบใช้วันที่แบบสั้น ชื่อเต็มใช้แบบยาว
    expect(tiles[5]).toMatchObject({ value: "23 เม.ย. 48", full: "เผยแพร่ 23 เมษายน 2548" })
  })

  it("ค่าที่ไม่มีไม่ขึ้นช่อง · 0 ยังขึ้นเป็น 0", () => {
    const tiles = statTiles({ ...base, publishedAt: undefined, stats: { views: 0 } })
    expect(tiles.map((tile) => tile.key)).toEqual(["views", "duration"])
    expect(tiles[0].value).toBe("0")
  })

  it("ไม่มี stats ความยาว 0 และวันที่อ่านไม่ได้ = ไม่มีช่องเลย", () => {
    expect(statTiles({ ...base, durationS: 0, publishedAt: "not-a-date" })).toEqual([])
  })
})
