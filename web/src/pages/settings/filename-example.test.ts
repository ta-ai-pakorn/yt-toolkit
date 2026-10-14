import { describe, expect, it } from "vitest"

import { exampleFileName, SAMPLE_CLIP_ID } from "./filename-example"

const DIR = "C:\\Users\\somchai\\Downloads\\YT-Toolkit"
const CLIP = { title: 'ทดสอบ: "A/B" <ภาค 1>?', channel: "ช่อง/ทดสอบ", videoId: "aqz-KE-bpKQ" }

describe("exampleFileName", () => {
  it("ยังไม่เคยเปิดคลิป: ใช้ชื่อตัวอย่างภาษาไทย ทั้งสามรูปแบบ", () => {
    expect(exampleFileName("title", undefined, DIR)).toBe("สอนทำกับข้าวง่าย ๆ ใน 10 นาที.mp4")
    expect(exampleFileName("title-channel", undefined, DIR)).toBe("สอนทำกับข้าวง่าย ๆ ใน 10 นาที - ครัวบ้านเรา.mp4")
    expect(exampleFileName("title-quality", undefined, DIR)).toBe("สอนทำกับข้าวง่าย ๆ ใน 10 นาที (1080p).mp4")
    expect(SAMPLE_CLIP_ID).toHaveLength(11)
  })

  it("มีคลิปที่เปิดล่าสุด: ใช้ชื่อและช่องของคลิปนั้นตามกฎชื่อไฟล์ของ backend", () => {
    expect(exampleFileName("title", CLIP, DIR)).toBe("ทดสอบ AB ภาค 1.mp4")
    expect(exampleFileName("title-channel", CLIP, DIR)).toBe("ทดสอบ AB ภาค 1 - ช่องทดสอบ.mp4")
    expect(exampleFileName("title-quality", CLIP, DIR)).toBe("ทดสอบ AB ภาค 1 (1080p).mp4")
  })

  it("คลิปไม่รู้ชื่อช่อง: แบบ title-channel ได้ชื่อคลิปอย่างเดียว (เหมือนไฟล์จริง)", () => {
    expect(exampleFileName("title-channel", { ...CLIP, channel: "" }, DIR)).toBe("ทดสอบ AB ภาค 1.mp4")
  })

  it("ชื่อยาว 300 ตัว: ตัดตามงบ path ส่วนคุณภาพและนามสกุลอยู่ครบ", () => {
    const long = { title: "ก".repeat(300), channel: "ครัวบ้านเรา", videoId: "aqz-KE-bpKQ" }
    const name = exampleFileName("title-quality", long, DIR)
    expect(name.endsWith(" (1080p).mp4")).toBe(true)
    expect(name.length).toBeLessThan(120)
  })

  it("โฟลเดอร์ผลลัพธ์ยาวจน path เกิน: ยังแสดงรูปแบบได้ (คิดเหมือนโฟลเดอร์สั้น)", () => {
    expect(exampleFileName("title-channel", undefined, "D:\\" + "x".repeat(250))).toBe(
      "สอนทำกับข้าวง่าย ๆ ใน 10 นาที - ครัวบ้านเรา.mp4"
    )
  })
})
