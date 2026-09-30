import { describe, expect, it } from "vitest"

import { ID_LOOKS_RANDOM, looksLikeYoutube } from "./paste"

describe("looksLikeYoutube", () => {
  it.each([
    "https://www.youtube.com/watch?v=aqz-KE-bpKQ",
    "http://youtube.com/watch?v=aqz-KE-bpKQ",
    "youtube.com/watch?v=aqz-KE-bpKQ",
    "https://youtu.be/aqz-KE-bpKQ",
    "youtu.be/aqz-KE-bpKQ",
    "https://m.youtube.com/watch?v=aqz-KE-bpKQ",
    "https://music.youtube.com/watch?v=aqz-KE-bpKQ",
    "https://www.youtube-nocookie.com/embed/aqz-KE-bpKQ",
    "  https://youtu.be/aqz-KE-bpKQ  ",
    "<https://youtu.be/aqz-KE-bpKQ>",
    "aqz-KE-bpKQ",
    "jNQXAC9IVRw",
    "dQw4w9WgXcQ",
    "abcdefghij_",
    "abcdefghij-",
    "  aqz-KE-bpKQ\n",
  ])("รับ %j", (text) => {
    expect(looksLikeYoutube(text)).toBe(true)
  })

  it.each([
    "1. https://youtu.be/aqz-KE-bpKQ",
    "• https://youtu.be/aqz-KE-bpKQ",
    "ดูอันนี้https://youtu.be/aqz-KE-bpKQ",
    "ดูคลิปนี้ youtu.be/aqz-KE-bpKQ นะ",
    "สวัสดีครับ\n2. https://www.youtube.com/watch?v=jNQXAC9IVRw ขอบคุณครับ",
    "(https://www.youtube.com/playlist?list=PLfakeplaylist250)",
    "1.https://youtu.be/aqz-KE-bpKQ",
    "12.https://www.youtube.com/watch?v=aqz-KE-bpKQ",
    "ลิงก์:https://youtu.be/aqz-KE-bpKQ",
    "ลิงก์:youtu.be/aqz-KE-bpKQ",
    "-youtu.be/aqz-KE-bpKQ",
    "2.youtu.be/aqz-KE-bpKQ",
    "https://youtu.be/aqz-KE-bpKQ,https://youtu.be/jNQXAC9IVRw",
  ])("ลิงก์ในข้อความจากแชต: รับ %j", (text) => {
    expect(looksLikeYoutube(text)).toBe(true)
  })

  it("หลายบรรทัด: มีบรรทัดไหนเป็นลิงก์ยูทูปก็รับ", () => {
    expect(looksLikeYoutube("https://youtu.be/aqz-KE-bpKQ\r\nอะไรสักอย่าง\r\nhttps://youtu.be/jNQXAC9IVRw")).toBe(true)
    expect(looksLikeYoutube("รายชื่อคลิป\nhttps://youtu.be/aqz-KE-bpKQ")).toBe(true)
  })

  it.each([
    "",
    "   ",
    "ดูคลิปนี้ใน youtube นะ",
    "I love youtube videos",
    "youtube",
    "my youtube.com/watch link",
    "https://example.com/youtu.be/aqz-KE-bpKQ",
    "https://notyoutube.com/watch?v=aqz-KE-bpKQ",
    "https://youtube.com.evil.example/watch",
    "https://youtu.be",
    "hello world",
    "helloworld12x",
    "development",
    "information",
    "abc def ghij",
    "ดูคำว่า youtube.com/watch ในประโยค",
    "https://drive.google.com/youtube.com/watch?v=aqz-KE-bpKQ",
    "me@youtube.com/watch?v=aqz-KE-bpKQ",
    "Goodmorning",
    "abc.youtu.be/aqz-KE-bpKQ",
  ])("ไม่รับ %j", (text) => {
    expect(looksLikeYoutube(text)).toBe(false)
  })

  // ตารางเดียวกับ tests/unit/test_inputs.py::test_id_looks_random_rule (กฎต้องตรงกันทั้งสองฝั่ง)
  it.each([
    ["dQw4w9WgXcQ", true],
    ["aqz-KE-bpKQ", true],
    ["jNQXAC9IVRw", true],
    ["abcdefghij_", true],
    ["abcdefghij-", true],
    ["abcdEfghijk", true],
    ["Goodmorning", false],
    ["development", false],
    ["information", false],
  ] as const)("ID_LOOKS_RANDOM %s → %s", (word, expected) => {
    expect(ID_LOOKS_RANDOM.test(word)).toBe(expected)
  })
})
