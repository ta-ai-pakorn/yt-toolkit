import { describe, expect, it } from "vitest"

import type { AudioFormat, SubtitleTrack } from "@/lib/types"

import { buildTrackGroups, filterTranslated, originalLanguage, previewTime } from "./track-groups"

const track = (id: string, lang: string, group: SubtitleTrack["group"]): SubtitleTrack => ({
  id,
  lang,
  name: lang,
  group,
})

const audio = (language: string | undefined, isOriginal: boolean): AudioFormat => ({
  formatId: "251",
  language,
  isOriginal,
  acodec: "opus",
})

const ids = (tracks: readonly SubtitleTrack[]) => tracks.map((t) => t.id)

describe("buildTrackGroups", () => {
  it("แยกกลุ่มเจ้าของคลิป · ภาษาต้นฉบับ ตามลำดับนี้ และไม่รวมซับแปลอัตโนมัติ", () => {
    const groups = buildTrackGroups(
      [track("t.fr", "fr", "translated"), track("a.th-orig", "th", "original"), track("o.en", "en", "owner")],
      "th",
    )
    expect(groups.map((g) => g.group)).toEqual(["owner", "original"])
    expect(ids(groups[0].tracks)).toEqual(["o.en"])
    expect(ids(groups[1].tracks)).toEqual(["a.th-orig"])
  })

  it("เรียงตามชื่อภาษาไทย โดยภาษาต้นฉบับ (เทียบรหัสหลัก) ขึ้นก่อน", () => {
    const groups = buildTrackGroups(
      [
        track("o.ja", "ja", "owner"), // ญี่ปุ่น
        track("o.en-GB", "en-GB", "owner"), // อังกฤษ - สหราชอาณาจักร (ภาษาต้นฉบับ en)
        track("o.de", "de", "owner"), // เยอรมัน
        track("o.en", "en", "owner"), // อังกฤษ (ภาษาต้นฉบับ)
        track("o.th", "th", "owner"), // ไทย
      ],
      "en",
    )
    expect(ids(groups[0].tracks)).toEqual(["o.en", "o.en-GB", "o.ja", "o.th", "o.de"])
  })

  it("ไม่รู้ภาษาต้นฉบับ = เรียงตามชื่อภาษาไทยอย่างเดียว", () => {
    const groups = buildTrackGroups(
      [track("a.th-orig", "th", "original"), track("a.en-US-orig", "en-US", "original")],
      null,
    )
    expect(groups.map((g) => g.group)).toEqual(["original"])
    expect(ids(groups[0].tracks)).toEqual(["a.th-orig", "a.en-US-orig"])
  })

  it("กลุ่มที่ไม่มีแทร็กไม่ถูกส่งออก · มีแต่ซับแปล = ไม่มีกลุ่มเลย", () => {
    expect(buildTrackGroups([track("a.yue", "yue", "original"), track("t.en", "en", "translated")], null)).toEqual([
      { group: "original", tracks: [track("a.yue", "yue", "original")] },
    ])
    expect(buildTrackGroups([track("t.en", "en", "translated")], "th")).toEqual([])
    expect(buildTrackGroups([], "th")).toEqual([])
  })

  it("ไม่แก้ลำดับของรายการที่ส่งเข้ามา", () => {
    const input = [track("o.th", "th", "owner"), track("o.en", "en", "owner")]
    buildTrackGroups(input, "en")
    expect(ids(input)).toEqual(["o.th", "o.en"])
  })
})

describe("filterTranslated", () => {
  const tracks = [
    track("t.fr", "fr", "translated"), // ฝรั่งเศส
    track("t.en", "en", "translated"), // อังกฤษ
    track("t.zh-Hans", "zh-Hans", "translated"), // จีน (ตัวย่อ)
    track("t.ja", "ja", "translated"), // ญี่ปุ่น
    track("o.th", "th", "owner"),
  ]

  it("คำค้นว่าง (หรือมีแต่ช่องว่าง) = ซับแปลทั้งหมด เรียงตามชื่อภาษาไทย", () => {
    expect(ids(filterTranslated(tracks, ""))).toEqual(["t.zh-Hans", "t.ja", "t.fr", "t.en"])
    expect(ids(filterTranslated(tracks, "   "))).toEqual(["t.zh-Hans", "t.ja", "t.fr", "t.en"])
  })

  it("ค้นด้วยคำภาษาไทยบางส่วนของชื่อภาษา", () => {
    expect(ids(filterTranslated(tracks, "อังกฤ"))).toEqual(["t.en"])
    expect(ids(filterTranslated(tracks, "ญี่ปุ่น"))).toEqual(["t.ja"])
  })

  it("ค้นด้วยรหัสภาษา ไม่สนตัวพิมพ์เล็ก/ใหญ่", () => {
    expect(ids(filterTranslated(tracks, "EN"))).toEqual(["t.en"])
    expect(ids(filterTranslated(tracks, "zh-hans"))).toEqual(["t.zh-Hans"])
  })

  it("ไม่พบ = รายการว่าง · ไม่รวมแทร็กที่ไม่ใช่ซับแปล", () => {
    expect(filterTranslated(tracks, "สวาฮีลี")).toEqual([])
    expect(ids(filterTranslated(tracks, "th"))).toEqual([])
  })
})

describe("originalLanguage", () => {
  const tracks = [track("a.en-US-orig", "en-US", "original"), track("a.th-orig", "th", "original")]

  it("ใช้ภาษาของเสียงต้นฉบับ (รหัสหลัก ตัวเล็ก) ก่อน", () => {
    expect(originalLanguage(tracks, [audio("en-US", false), audio("TH-th", true)])).toBe("th")
  })

  it("ไม่มีเสียงต้นฉบับที่บอกภาษา = รหัสหลักของแทร็ก -orig ตัวแรก", () => {
    expect(originalLanguage(tracks, [audio(undefined, true)])).toBe("en")
    expect(originalLanguage(tracks, undefined)).toBe("en")
  })

  it("ไม่มีทั้งคู่ = null (แทร็กอัตโนมัติที่ไม่มี -orig ไม่นับ)", () => {
    expect(originalLanguage([track("a.yue", "yue", "original"), track("o.th", "th", "owner")], [])).toBeNull()
  })
})

describe("previewTime", () => {
  it("HH:MM:SS,mmm แบบในไฟล์ .srt", () => {
    expect(previewTime(0)).toBe("00:00:00,000")
    expect(previewTime(120)).toBe("00:00:00,120")
    expect(previewTime(1_560)).toBe("00:00:01,560")
    expect(previewTime(3_723_004)).toBe("01:02:03,004")
  })

  it("เกิน 99 ชั่วโมงก็ไม่ตัดหลัก · ค่าติดลบหรือทศนิยมปัดเป็นมิลลิวินาทีเต็มที่ไม่ติดลบ", () => {
    expect(previewTime(360_000_005)).toBe("100:00:00,005")
    expect(previewTime(-5)).toBe("00:00:00,000")
    expect(previewTime(1_000.7)).toBe("00:00:01,000")
  })
})
