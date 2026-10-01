import { describe, expect, it } from "vitest"

import {
  formatBytes,
  formatCompact,
  formatCount,
  formatDuration,
  formatPublished,
  formatTags,
  formatTimecode,
  relativeTime,
  youtubeLinkAt,
  youtubeWatchUrl,
} from "./format"

describe("formatDuration", () => {
  it("ต่ำกว่า 1 ชั่วโมงเป็น M:SS", () => {
    expect(formatDuration(0)).toBe("0:00")
    expect(formatDuration(5)).toBe("0:05")
    expect(formatDuration(19)).toBe("0:19")
    expect(formatDuration(635)).toBe("10:35")
    expect(formatDuration(3599)).toBe("59:59")
  })

  it("ตั้งแต่ 1 ชั่วโมงเป็น H:MM:SS", () => {
    expect(formatDuration(3600)).toBe("1:00:00")
    expect(formatDuration(3725)).toBe("1:02:05")
    expect(formatDuration(36000)).toBe("10:00:00")
  })

  it("ปัดเศษวินาทีลง และไม่พังกับค่าที่ผิดปกติ", () => {
    expect(formatDuration(59.9)).toBe("0:59")
    expect(formatDuration(-3)).toBe("0:00")
    expect(formatDuration(Number.NaN)).toBe("0:00")
  })
})

describe("formatTimecode", () => {
  it("เป็น HH:MM:SS เสมอ", () => {
    expect(formatTimecode(0)).toBe("00:00:00")
    expect(formatTimecode(4960)).toBe("00:00:04")
    expect(formatTimecode(61_000)).toBe("00:01:01")
    expect(formatTimecode(3_723_000)).toBe("01:02:03")
    expect(formatTimecode(100 * 3600 * 1000)).toBe("100:00:00")
  })

  it("ตัดมิลลิวินาทีทิ้ง ไม่ปัดขึ้น และกันค่าติดลบ", () => {
    expect(formatTimecode(999)).toBe("00:00:00")
    expect(formatTimecode(1999)).toBe("00:00:01")
    expect(formatTimecode(-50)).toBe("00:00:00")
  })
})

describe("relativeTime", () => {
  const now = new Date("2026-09-29T12:00:00Z")
  const ago = (seconds: number) => new Date(now.getTime() - seconds * 1000).toISOString()

  it("ไม่ถึงนาที = เมื่อสักครู่", () => {
    expect(relativeTime(ago(0), now)).toBe("เมื่อสักครู่")
    expect(relativeTime(ago(59), now)).toBe("เมื่อสักครู่")
  })

  it("นาทีและชั่วโมง", () => {
    expect(relativeTime(ago(5 * 60), now)).toBe("5 นาทีก่อน")
    expect(relativeTime(ago(59 * 60 + 59), now)).toBe("59 นาทีก่อน")
    expect(relativeTime(ago(3600), now)).toBe("1 ชั่วโมงก่อน")
    expect(relativeTime(ago(23 * 3600), now)).toBe("23 ชั่วโมงก่อน")
  })

  it("เมื่อวาน และกี่วันก่อน", () => {
    expect(relativeTime(ago(24 * 3600), now)).toBe("เมื่อวาน")
    expect(relativeTime(ago(47 * 3600), now)).toBe("เมื่อวาน")
    expect(relativeTime(ago(3 * 86400), now)).toBe("3 วันก่อน")
    expect(relativeTime(ago(6 * 86400), now)).toBe("6 วันก่อน")
  })

  it("สัปดาห์ เดือน ปี", () => {
    expect(relativeTime(ago(7 * 86400), now)).toBe("1 สัปดาห์ก่อน")
    expect(relativeTime(ago(29 * 86400), now)).toBe("4 สัปดาห์ก่อน")
    expect(relativeTime(ago(30 * 86400), now)).toBe("1 เดือนก่อน")
    expect(relativeTime(ago(364 * 86400), now)).toBe("12 เดือนก่อน")
    expect(relativeTime(ago(365 * 86400), now)).toBe("1 ปีก่อน")
  })

  it("เวลาในอนาคตหรืออ่านไม่ได้ ไม่แสดงค่าแปลก", () => {
    expect(relativeTime(ago(-600), now)).toBe("เมื่อสักครู่")
    expect(relativeTime("ไม่ใช่วันที่", now)).toBe("เมื่อสักครู่")
  })

  it("อ่านเวลาแบบมี offset ได้", () => {
    expect(relativeTime("2026-09-29T18:55:00+07:00", now)).toBe("5 นาทีก่อน")
  })
})

describe("formatPublished", () => {
  it("แสดงวันที่แบบไทย พ.ศ.", () => {
    expect(formatPublished("2008-05-30")).toBe("30 พฤษภาคม 2551")
    expect(formatPublished("2024-01-01")).toBe("1 มกราคม 2567")
  })

  it("วันที่ที่อ่านไม่ได้ให้ข้อความว่าง", () => {
    expect(formatPublished("")).toBe("")
    expect(formatPublished("ไม่ใช่วันที่")).toBe("")
  })
})

describe("youtubeLinkAt", () => {
  it("ลิงก์ youtu.be พร้อมวินาทีที่ตัดเศษทิ้ง (ไม่ปัดขึ้น)", () => {
    expect(youtubeLinkAt("aqz-KE-bpKQ", 4961)).toBe("https://youtu.be/aqz-KE-bpKQ?t=4")
    expect(youtubeLinkAt("aqz-KE-bpKQ", 90_500)).toBe("https://youtu.be/aqz-KE-bpKQ?t=90")
    expect(youtubeLinkAt("abc", 0)).toBe("https://youtu.be/abc?t=0")
  })

  it("ค่าที่ผิดปกติได้ t=0", () => {
    expect(youtubeLinkAt("abc", -5)).toBe("https://youtu.be/abc?t=0")
    expect(youtubeLinkAt("abc", Number.NaN)).toBe("https://youtu.be/abc?t=0")
  })
})

describe("youtubeWatchUrl", () => {
  it("ไม่ใส่เวลา = ลิงก์หน้าคลิป", () => {
    expect(youtubeWatchUrl("aqz-KE-bpKQ")).toBe("https://www.youtube.com/watch?v=aqz-KE-bpKQ")
  })

  it("ใส่เวลา = &t=วินาทีs ตัดเศษทิ้ง · ค่าผิดปกติได้ t=0s", () => {
    expect(youtubeWatchUrl("aqz-KE-bpKQ", 4961)).toBe("https://www.youtube.com/watch?v=aqz-KE-bpKQ&t=4s")
    expect(youtubeWatchUrl("abc", 90_999)).toBe("https://www.youtube.com/watch?v=abc&t=90s")
    expect(youtubeWatchUrl("abc", 0)).toBe("https://www.youtube.com/watch?v=abc&t=0s")
    expect(youtubeWatchUrl("abc", -5)).toBe("https://www.youtube.com/watch?v=abc&t=0s")
    expect(youtubeWatchUrl("abc", Number.NaN)).toBe("https://www.youtube.com/watch?v=abc&t=0s")
  })
})

describe("formatCompact", () => {
  it("ย่อเป็นหน่วยไทย (พัน หมื่น แสน ล้าน) ทศนิยมไม่เกิน 1 ตำแหน่ง", () => {
    expect(formatCompact(0)).toBe("0")
    expect(formatCompact(7)).toBe("7")
    expect(formatCompact(999)).toBe("999")
    expect(formatCompact(1000)).toBe("1 พัน")
    expect(formatCompact(1234)).toBe("1.2 พัน")
    expect(formatCompact(12_345)).toBe("1.2 หมื่น")
    expect(formatCompact(123_456)).toBe("1.2 แสน")
    expect(formatCompact(1_234_567)).toBe("1.2 ล้าน")
    expect(formatCompact(301_000_000)).toBe("301 ล้าน")
    expect(formatCompact(1_234_567_890)).toBe("1.2 พันล้าน")
  })

  it("ค่าที่ผิดปกติได้ 0 และตัดเศษทิ้ง", () => {
    expect(formatCompact(-5)).toBe("0")
    expect(formatCompact(Number.NaN)).toBe("0")
    expect(formatCompact(Number.POSITIVE_INFINITY)).toBe("0")
    expect(formatCompact(999.9)).toBe("999")
  })
})

describe("formatCount", () => {
  it("ตัวเลขเต็มมีจุลภาค", () => {
    expect(formatCount(0)).toBe("0")
    expect(formatCount(999)).toBe("999")
    expect(formatCount(123_456)).toBe("123,456")
    expect(formatCount(1_234_567_890)).toBe("1,234,567,890")
  })

  it("ค่าที่ผิดปกติได้ 0", () => {
    expect(formatCount(-1)).toBe("0")
    expect(formatCount(Number.NaN)).toBe("0")
  })
})

describe("formatTags", () => {
  it("คั่นด้วย จุลภาค + เว้นวรรค ตามลำดับเดิม", () => {
    expect(formatTags(["ยูทูป", "AI", "การตลาด"])).toBe("ยูทูป, AI, การตลาด")
  })

  it("ตัดช่องว่างหัวท้ายและข้ามแท็กว่าง · ไม่มีแท็ก = ข้อความว่าง", () => {
    expect(formatTags(["  a ", "", "   ", "b"])).toBe("a, b")
    expect(formatTags([])).toBe("")
  })
})

describe("formatBytes", () => {
  it("ฐานสิบ: MB จำนวนเต็ม · ต่ำกว่า 10 MB ทศนิยม 1 ตำแหน่ง · ตั้งแต่ 1 GB เป็น GB", () => {
    expect(formatBytes(268_000_000)).toBe("268 MB")
    expect(formatBytes(10_000_000)).toBe("10 MB")
    expect(formatBytes(4_240_000)).toBe("4.2 MB")
    expect(formatBytes(1_000_000_000)).toBe("1.0 GB")
    expect(formatBytes(1_362_269_481)).toBe("1.4 GB")
  })

  it("ไฟล์เล็กมากอย่างน้อย 0.1 MB · 0 ติดลบ หรือไม่ใช่ตัวเลข = 0 MB", () => {
    expect(formatBytes(1000)).toBe("0.1 MB")
    expect(formatBytes(0)).toBe("0 MB")
    expect(formatBytes(-5)).toBe("0 MB")
    expect(formatBytes(Number.NaN)).toBe("0 MB")
    expect(formatBytes(Number.POSITIVE_INFINITY)).toBe("0 MB")
  })
})
