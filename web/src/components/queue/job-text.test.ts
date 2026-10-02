import { describe, expect, it } from "vitest"

import { mergeJobPatch } from "@/lib/jobs"
import { PRESETS } from "@/lib/sub-options"
import type { Job } from "@/lib/types"

import {
  formatEta,
  formatPercent,
  formatSpeed,
  jobChoice,
  jobTitle,
  pausedCountdown,
  pausedRemainingMs,
  progressLine,
  retryText,
  stageText,
} from "./job-text"

function job(over: Partial<Job> = {}): Job {
  return {
    id: "00000000-0000-0000-0000-000000000001",
    videoId: "aqz-KE-bpKQ",
    title: "คลิปทดสอบ",
    kind: "video",
    params: { maxQuality: false, splitChapters: false, noAudio: false, audioLanguage: "original" },
    status: "running",
    position: 1,
    createdAt: "2026-10-01T10:00:00Z",
    ...over,
  }
}

describe("jobTitle", () => {
  it("ใช้ชื่อคลิป ไม่มีชื่อใช้รหัสคลิป", () => {
    expect(jobTitle(job())).toBe("คลิปทดสอบ")
    expect(jobTitle(job({ title: "" }))).toBe("aqz-KE-bpKQ")
  })
})

describe("formatPercent", () => {
  it("ปัดลง และอยู่ในช่วง 0-100", () => {
    expect(formatPercent(0.429)).toBe("42%")
    expect(formatPercent(0.999)).toBe("99%")
    expect(formatPercent(1)).toBe("100%")
    expect(formatPercent(-0.2)).toBe("0%")
    expect(formatPercent(1.5)).toBe("100%")
    expect(formatPercent(Number.NaN)).toBe("0%")
  })
})

describe("formatSpeed", () => {
  it("MB ทศนิยมหนึ่งตำแหน่ง (หน่วยฐานสิบ)", () => {
    expect(formatSpeed(2_400_000)).toBe("2.4 MB/วินาที")
    expect(formatSpeed(1_000_000)).toBe("1.0 MB/วินาที")
  })
  it("ต่ำกว่า 1 MB เป็น KB จำนวนเต็ม ไม่ต่ำกว่า 1 KB", () => {
    expect(formatSpeed(512_000)).toBe("512 KB/วินาที")
    expect(formatSpeed(120)).toBe("1 KB/วินาที")
    expect(formatSpeed(-5)).toBe("1 KB/วินาที")
  })
})

describe("formatEta", () => {
  it("M:SS และ H:MM:SS", () => {
    expect(formatEta(65)).toBe("เหลือ 1:05")
    expect(formatEta(0)).toBe("เหลือ 0:00")
    expect(formatEta(3725)).toBe("เหลือ 1:02:05")
  })
})

describe("retryText", () => {
  it("บอกครั้งที่ลองใหม่จาก 3 ครั้ง", () => {
    expect(retryText(2)).toBe("เน็ตหลุด กำลังลองใหม่ (ครั้งที่ 2/3)")
  })
})

describe("pausedCountdown", () => {
  const now = Date.parse("2026-10-01T10:00:00Z")
  it("m:ss จากเวลาที่คิวจะเริ่มต่อ", () => {
    expect(pausedCountdown("2026-10-01T10:10:00Z", now)).toBe("10:00")
    expect(pausedCountdown("2026-10-01T10:00:05Z", now)).toBe("0:05")
    expect(pausedCountdown("2026-10-01T10:01:30+00:00", now)).toBe("1:30")
  })
  it("ปัดวินาทีขึ้น (เหลือ 0.4 วินาที = 0:01)", () => {
    expect(pausedCountdown("2026-10-01T10:00:00.400Z", now)).toBe("0:01")
  })
  it("เลยเวลาแล้วหรือเวลาอ่านไม่ได้ = 0:00", () => {
    expect(pausedCountdown("2026-10-01T09:59:00Z", now)).toBe("0:00")
    expect(pausedCountdown("ไม่ใช่เวลา", now)).toBe("0:00")
    expect(pausedRemainingMs("ไม่ใช่เวลา", now)).toBe(0)
    expect(pausedRemainingMs("2026-10-01T10:00:02Z", now)).toBe(2000)
  })
})

describe("progressLine", () => {
  it("กำลังทำ: ขั้นตอน · % · ความเร็ว · เวลาที่เหลือ", () => {
    const line = progressLine(job({ stage: "downloading_video", progress: 0.42, speedBps: 2_400_000, etaS: 65 }))
    expect(line).toBe("โหลดภาพ · 42% · 2.4 MB/วินาที · เหลือ 1:05")
  })
  it("มีเท่าที่รู้ (ไม่มีความเร็ว ไม่มีเวลา)", () => {
    expect(progressLine(job({ stage: "merging", progress: 0.5 }))).toBe("รวมไฟล์ · 50%")
    expect(progressLine(job({ stage: "probing" }))).toBe("ดึงข้อมูล")
  })
  it("ยังไม่รู้ขั้นตอน = กำลังเริ่ม", () => {
    expect(progressLine(job())).toBe("กำลังเริ่ม")
  })
  it("ลองใหม่เพราะเน็ตหลุดมาก่อนขั้นตอน", () => {
    expect(progressLine(job({ stage: "downloading_video", progress: 0.1, attempt: 1 }))).toBe(
      "เน็ตหลุด กำลังลองใหม่ (ครั้งที่ 1/3)",
    )
  })
  it("backend ล้าง attempt (null) เมื่อโหลดต่อได้ = ข้อความลองใหม่หายไป", () => {
    const retrying = job({ stage: "downloading_video", progress: 0.1, attempt: 1 })
    const [next] = mergeJobPatch([retrying], { id: retrying.id, attempt: null, progress: 0.2 })
    expect(progressLine(next)).toBe("โหลดภาพ · 20%")
  })
  it("กำลังยกเลิกมาก่อนทุกอย่าง", () => {
    expect(progressLine(job({ cancelling: true, attempt: 2, stage: "merging" }))).toBe("กำลังยกเลิก")
  })
  it("รอคิว = รอคิว · จบแล้ว = ว่าง", () => {
    expect(progressLine(job({ status: "queued" }))).toBe("รอคิว")
    expect(progressLine(job({ status: "done" }))).toBe("")
    expect(progressLine(job({ status: "failed" }))).toBe("")
  })
})

describe("M5-A: ชื่องานต่อท้ายตัวเลือก (spec 3.5) และขั้นตอนใหม่", () => {
  it("ช่วงเวลา · แยก chapter · ตัดโฆษณา", () => {
    const range = { startMs: 90_000, endMs: 300_000 }
    expect(
      jobTitle(job({ params: { maxQuality: false, splitChapters: false, noAudio: false, audioLanguage: "original", range, sponsorblock: ["sponsor"] } })),
    ).toBe("คลิปทดสอบ · ช่วง 1:30-5:00 · ตัดโฆษณา")
    expect(jobTitle(job({ kind: "audio", params: { format: "m4a", splitChapters: true, audioLanguage: "original" } }))).toBe(
      "คลิปทดสอบ · แยก chapter",
    )
    expect(
      jobTitle(job({ kind: "subtitle", params: { trackId: "a.th-orig", format: "srt", options: PRESETS.medium, range: { startMs: 3_750_000, endMs: 3_900_000 } } })),
    ).toBe("คลิปทดสอบ · ช่วง 1:02:30-1:05:00")
    expect(jobChoice({ source: "fast" })).toBe("")
    expect(jobTitle({ title: "", videoId: "aqz-KE-bpKQ" })).toBe("aqz-KE-bpKQ")
  })

  it("ขั้นตอนตัดช่วง ตัดโฆษณา แยก chapter", () => {
    expect(stageText("cutting")).toBe("กำลังตัดช่วง")
    expect(stageText("cutting_ads")).toBe("กำลังตัดโฆษณา")
    expect(stageText("splitting:3/12")).toBe("กำลังแยก chapter 3/12")
    expect(stageText("writing")).toBe("บันทึกไฟล์")
    expect(progressLine(job({ stage: "splitting:2/5", progress: 0.5 }))).toBe("กำลังแยก chapter 2/5 · 50%")
  })
})
