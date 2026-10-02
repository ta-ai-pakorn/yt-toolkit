import { describe, expect, it } from "vitest"

import type { VideoInfo } from "@/lib/types"

import { cleanTags, creditLine, infoSections } from "./info-sections"

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
      credit: true,
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
    ).toEqual({ credit: true, description: true, chapters: true, replayed: true, pinned: true, tags: true })
  })

  it("เครดิตมีเมื่อคลิปมีชื่อ · ชื่อว่าง (หรือมีแต่ช่องว่าง) = ไม่มีส่วนเครดิต", () => {
    expect(infoSections(base).credit).toBe(true)
    expect(infoSections({ ...base, title: "" }).credit).toBe(false)
    expect(infoSections({ ...base, title: "  " }).credit).toBe(false)
  })

  it("คลิปที่มีคอมเมนต์มีส่วนคอมเมนต์ปักหมุด", () => {
    expect(infoSections({ ...base, stats: { comments: 3 } }).pinned).toBe(true)
  })
})

describe("creditLine", () => {
  it("รูปแบบเดียวกับ credit_line ของ Python: ที่มา: ชื่อ — ช่อง (YouTube) https://youtu.be/<id>", () => {
    expect(creditLine(base)).toBe("ที่มา: คลิป — ช่อง (YouTube) https://youtu.be/abc")
  })

  it("ชื่อหรือช่องที่มีช่องว่างซ้อนหรือขึ้นบรรทัดใหม่ = บรรทัดเดียว (ยุบช่องว่าง ตัดหัวท้าย เหมือน _one_line)", () => {
    const line = creditLine({ ...base, title: "  ชื่อ  คลิป\nบรรทัดสอง\t", channel: "ช่อง\r\n  ทดสอบ " })
    expect(line).toBe("ที่มา: ชื่อ คลิป บรรทัดสอง — ช่อง ทดสอบ (YouTube) https://youtu.be/abc")
    expect(line).not.toMatch(/\s{2}|[\r\n\t]/)
  })
})

describe("cleanTags", () => {
  it("ตัดช่องว่างหัวท้ายและข้ามแท็กว่าง ลำดับเดิม", () => {
    expect(cleanTags([" ก ", "", "ข", "  "])).toEqual(["ก", "ข"])
    expect(cleanTags(undefined)).toEqual([])
  })
})
