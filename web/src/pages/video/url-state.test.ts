import { describe, expect, it } from "vitest"

import { patchSearch, readVideoParams } from "./url-state"

const params = (q: string) => new URLSearchParams(q)

describe("readVideoParams", () => {
  it("อ่านแท็บ แทร็ก และเวลาครบทั้งสามค่า", () => {
    expect(readVideoParams(params("tab=subs&track=a.th-orig&at=90500"))).toEqual({
      tab: "subs",
      trackId: "a.th-orig",
      at: 90500,
      replayed: false,
    })
  })

  it("ไม่มีพารามิเตอร์ = แท็บภาพเฟรม ไม่มีแทร็ก ไม่มีเวลา", () => {
    expect(readVideoParams(params(""))).toEqual({ tab: "frames", trackId: null, at: null, replayed: false })
  })

  it("แท็บที่ไม่รู้จักอ่านเป็นภาพเฟรม", () => {
    expect(readVideoParams(params("tab=weird")).tab).toBe("frames")
    expect(readVideoParams(params("tab=transcript")).tab).toBe("transcript")
    expect(readVideoParams(params("tab=info")).tab).toBe("info")
    expect(readVideoParams(params("tab=INFO")).tab).toBe("frames")
  })

  it("เวลาที่ติดลบ ไม่ใช่ตัวเลข หรือเป็นทศนิยมอ่านเป็น null", () => {
    for (const bad of ["-5", "abc", "1.5", "", "1e3", "0x10"]) {
      expect(readVideoParams(params(`at=${bad}`)).at).toBeNull()
    }
    expect(readVideoParams(params("at=0")).at).toBe(0)
  })

  it("รหัสแทร็กผิดรูปอ่านเป็น null", () => {
    expect(readVideoParams(params("track=x.th")).trackId).toBeNull()
    expect(readVideoParams(params("track=o.")).trackId).toBeNull()
    expect(readVideoParams(params("track=o.th/../x")).trackId).toBeNull()
    expect(readVideoParams(params("track=t.fr")).trackId).toBe("t.fr")
  })
})

describe("ตัวกรองดูซ้ำบ่อย (?replayed=1)", () => {
  it("อ่านเป็น true เฉพาะค่า 1", () => {
    expect(readVideoParams(params("replayed=1")).replayed).toBe(true)
    for (const bad of ["0", "true", "", "yes", "01"]) {
      expect(readVideoParams(params(`replayed=${bad}`)).replayed).toBe(false)
    }
  })

  it("เปิด/ปิดด้วย patch โดยเก็บค่าอื่นไว้ · ปิด = ลบคีย์ออก", () => {
    expect(patchSearch(params("track=o.th"), { replayed: true })).toBe("?track=o.th&replayed=1")
    expect(patchSearch(params("track=o.th&replayed=1"), { replayed: false })).toBe("?track=o.th")
    expect(patchSearch(params("replayed=1"), { tab: "subs", at: 5 })).toBe("?tab=subs&at=5&replayed=1")
  })

  it("ค่าที่ผิดรูปใน URL เดิมถูกล้างเมื่อ patch", () => {
    expect(patchSearch(params("replayed=yes"), { tab: "info" })).toBe("?tab=info")
  })
})

describe("patchSearch", () => {
  it("เปลี่ยนแท็บและเวลา โดยเก็บแทร็กเดิมไว้ ลำดับ tab, track, at", () => {
    const p = params("tab=subs&track=a.th-orig")
    expect(patchSearch(p, { tab: "transcript", at: 1000 })).toBe("?tab=transcript&track=a.th-orig&at=1000")
  })

  it("at: null ลบเวลาออก", () => {
    expect(patchSearch(params("tab=subs&track=a.th-orig&at=90500"), { at: null })).toBe("?tab=subs&track=a.th-orig")
  })

  it("tab: frames ลบ tab ออก (ค่าเริ่มต้นไม่ขึ้นใน URL)", () => {
    expect(patchSearch(params("tab=subs&track=a.th-orig"), { tab: "frames" })).toBe("?track=a.th-orig")
  })

  it("tab: info ขึ้นใน URL เป็น ?tab=info และไปภาพเฟรมพร้อมเวลาได้ในก้าวเดียว", () => {
    expect(patchSearch(params(""), { tab: "info" })).toBe("?tab=info")
    expect(patchSearch(params("tab=info"), { tab: "frames", at: 5000 })).toBe("?at=5000")
  })

  it("trackId: null ลบแทร็กออก และไม่เหลืออะไรคืนสตริงว่าง", () => {
    expect(patchSearch(params("track=o.th"), { trackId: null })).toBe("")
  })

  it("เก็บพารามิเตอร์อื่นที่ไม่เกี่ยวไว้", () => {
    expect(patchSearch(params("foo=1&tab=subs"), { tab: "transcript" })).toBe("?tab=transcript&foo=1")
  })

  it("ค่าใน patch ที่ผิดรูปไม่ถูกเขียนลง URL", () => {
    expect(patchSearch(params(""), { trackId: "bad", at: -1 })).toBe("")
    expect(patchSearch(params(""), { at: 1.5 })).toBe("")
  })

  it("ค่าที่ผิดรูปใน URL เดิมถูกล้างเมื่อ patch", () => {
    expect(patchSearch(params("tab=weird&at=abc"), { trackId: "o.th" })).toBe("?track=o.th")
  })
})
