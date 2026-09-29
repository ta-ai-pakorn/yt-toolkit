import { describe, expect, it } from "vitest"

import { formatDuration, formatPublished, formatTimecode, relativeTime } from "./format"

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
