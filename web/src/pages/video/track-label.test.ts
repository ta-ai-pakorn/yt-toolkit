import { describe, expect, it } from "vitest"

import type { SubtitleTrack } from "@/lib/types"

import { trackInEffect, trackLabel } from "./track-label"

const track = (id: string, lang: string, group: SubtitleTrack["group"]): SubtitleTrack => ({
  id,
  lang,
  name: lang,
  group,
})

describe("trackLabel", () => {
  it("ซับอัตโนมัติภาษาต้นฉบับ: ชื่อภาษาไทย + (อัตโนมัติ)", () => {
    expect(trackLabel({ id: "a.th-orig", lang: "th", name: "Thai (Original)", group: "original" })).toBe(
      "ไทย (อัตโนมัติ)",
    )
  })

  it("ซับจากเจ้าของคลิปเป็นชื่อภาษาอย่างเดียว ซับแปลอัตโนมัติมีวงเล็บบอก", () => {
    expect(trackLabel(track("o.th", "th", "owner"))).toBe("ไทย")
    expect(trackLabel(track("t.fr", "fr", "translated"))).toBe("ฝรั่งเศส (แปลอัตโนมัติ)")
  })
})

describe("trackInEffect", () => {
  const data = {
    tracks: [track("o.en", "en", "owner"), track("a.th-orig", "th", "original")],
    defaultTrackId: "a.th-orig",
  }

  it("ใช้แทร็กจาก URL ก่อน ไม่มีค่อยใช้แทร็กเริ่มต้น", () => {
    expect(trackInEffect(data, "o.en")?.id).toBe("o.en")
    expect(trackInEffect(data, null)?.id).toBe("a.th-orig")
  })

  it("รหัสใน URL ไม่อยู่ในรายการของคลิปนี้ (ลิงก์เก่า พิมพ์ผิด) = ใช้แทร็กเริ่มต้น", () => {
    expect(trackInEffect(data, "o.xx")?.id).toBe("a.th-orig")
    expect(trackInEffect(data, "t.nope")?.id).toBe("a.th-orig")
    expect(trackInEffect(data, "")?.id).toBe("a.th-orig")
  })

  it("ไม่มีแทร็กที่ใช้อยู่ และไม่มีแทร็กเริ่มต้น = null", () => {
    expect(trackInEffect({ tracks: data.tracks }, null)).toBeNull()
    expect(trackInEffect({ tracks: data.tracks }, "o.xx")).toBeNull()
    expect(trackInEffect({ tracks: [] }, null)).toBeNull()
    // แทร็กเริ่มต้นที่ไม่อยู่ในรายการก็ไม่นับ
    expect(trackInEffect({ tracks: data.tracks, defaultTrackId: "a.xx-orig" }, "o.xx")).toBeNull()
  })
})
