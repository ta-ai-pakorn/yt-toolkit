import { describe, expect, it } from "vitest"

import type { VideoInfo } from "@/lib/types"

import { cleanTags, infoSections } from "./info-sections"

const base: VideoInfo = {
  videoId: "abc",
  title: "คลิป",
  channel: "ช่อง",
  durationS: 60,
  thumbnailUrl: "",
  chapters: [],
  video: [],
  audio: [],
  hasStoryboard: true,
  isLive: false,
}

describe("infoSections", () => {
  it("ไม่มีข้อมูลเลยและปิดคอมเมนต์ = ไม่มีส่วนไหน (แท็บขึ้น 'คลิปนี้ไม่มีข้อมูลเพิ่มเติม')", () => {
    expect(infoSections({ ...base, description: " \n ", tags: ["", "  "], stats: { comments: 0 } })).toEqual({
      description: false,
      chapters: false,
      replayed: false,
      pinned: false,
      tags: false,
    })
  })

  it("มีข้อมูลครบ = ทุกส่วน · ไม่รู้จำนวนคอมเมนต์ยังมีส่วนคอมเมนต์ปักหมุด", () => {
    expect(
      infoSections({
        ...base,
        description: "คำอธิบาย",
        chapters: [{ startS: 0, endS: 5, title: "Intro" }],
        mostReplayed: [{ startMs: 0, endMs: 1000 }],
        tags: ["แท็ก"],
      }),
    ).toEqual({ description: true, chapters: true, replayed: true, pinned: true, tags: true })
  })

  it("คลิปที่มีคอมเมนต์มีส่วนคอมเมนต์ปักหมุด", () => {
    expect(infoSections({ ...base, stats: { comments: 3 } }).pinned).toBe(true)
  })
})

describe("cleanTags", () => {
  it("ตัดช่องว่างหัวท้ายและข้ามแท็กว่าง ลำดับเดิม", () => {
    expect(cleanTags([" ก ", "", "ข", "  "])).toEqual(["ก", "ข"])
    expect(cleanTags(undefined)).toEqual([])
  })
})
