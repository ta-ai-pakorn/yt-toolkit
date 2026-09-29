import { describe, expect, it } from "vitest"

import { looksLikeYoutube } from "./paste"

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
  ])("ไม่รับ %j", (text) => {
    expect(looksLikeYoutube(text)).toBe(false)
  })
})
