import { describe, expect, it } from "vitest"

import { formatChapters } from "./chapters"

describe("formatChapters", () => {
  it("เรียงตามเวลาเริ่ม แต่ละบรรทัดเป็น HH:MM:SS ชื่อตอน คั่นด้วย LF", () => {
    const text = formatChapters([
      { startS: 3723, endS: 3800, title: "สรุป" },
      { startS: 0, endS: 65, title: "บทนำ" },
      { startS: 65, endS: 3723, title: "ส่วนกลาง" },
    ])
    expect(text).toBe("00:00:00 บทนำ\n00:01:05 ส่วนกลาง\n01:02:03 สรุป")
  })

  it("ไม่มี chapter ได้สตริงว่าง", () => {
    expect(formatChapters([])).toBe("")
  })

  it("ไม่แก้ลำดับของอาร์เรย์ที่ส่งเข้ามา", () => {
    const chapters = [
      { startS: 10, endS: 20, title: "ข" },
      { startS: 0, endS: 10, title: "ก" },
    ]
    formatChapters(chapters)
    expect(chapters[0]?.title).toBe("ข")
  })
})
