import { describe, expect, it } from "vitest"

import { ApiError } from "@/lib/api"

import { detailsOpenByDefault, detailsRequest, errorToastSettings, PLAIN_TOAST } from "./model"

describe("detailsRequest", () => {
  it("จาก error ที่จับได้ + ที่ที่เกิด", () => {
    const error = new ApiError(502, "E_YT_REFUSED", "x", "HTTP Error 403", null)
    expect(detailsRequest({ error, context: "video-frames", videoId: "dQw4w9WgXcQ" })).toEqual({
      code: "E_YT_REFUSED",
      detail: "HTTP Error 403",
      context: "video-frames",
      videoId: "dQw4w9WgXcQ",
    })
  })

  it("จาก body ที่ประกอบไว้ (แถวงานในคิว) ผ่าน cleanRequest", () => {
    expect(detailsRequest({ request: { jobId: "j1", code: "E_NETWORK", detail: "d".repeat(5000), context: "queue" } })).toEqual({
      jobId: "j1",
      code: "E_NETWORK",
      detail: "d".repeat(4000),
      context: "queue",
    })
  })
})

describe("detailsOpenByDefault (planner ruling R1)", () => {
  it("E_UNKNOWN กางเอง รหัสอื่นพับไว้", () => {
    expect(detailsOpenByDefault("E_UNKNOWN")).toBe(true)
    expect(detailsOpenByDefault("E_NETWORK")).toBe(false)
    expect(detailsOpenByDefault(undefined)).toBe(false)
  })

  it("ผู้เรียกกำหนดเองได้", () => {
    expect(detailsOpenByDefault("E_UNKNOWN", false)).toBe(false)
    expect(detailsOpenByDefault("E_NETWORK", true)).toBe(true)
  })
})

describe("errorToastSettings", () => {
  it("ค้างจนกดปิด (D1) ส่ง id action cancel ต่อไปตรง ๆ", () => {
    const action = { label: "a", onClick: () => {} }
    const cancel = { label: "c", onClick: () => {} }
    expect(errorToastSettings({ id: "job-1", action, cancel })).toEqual({ id: "job-1", duration: Infinity, action, cancel })
    expect(errorToastSettings({})).toEqual({ id: undefined, duration: Infinity, action: undefined, cancel: undefined })
  })
})

describe("PLAIN_TOAST (planner ruling P5)", () => {
  it("ล้างทุกช่องที่ toast error ตั้งไว้ เมื่อ toast อื่นใช้ id เดียวกัน", () => {
    // แบบเดียวกับที่ sonner รวม toast ใหม่ทับ toast เดิมที่ id เดียวกัน: { ...เดิม, ...ใหม่ }
    const errorToast: Record<string, unknown> = { ...errorToastSettings({ id: "x", action: { label: "a", onClick: () => {} } }), description: "btn" }
    const merged = { ...errorToast, ...PLAIN_TOAST }
    expect(merged).toEqual({ id: "x", duration: undefined, action: undefined, cancel: undefined, description: undefined })
  })
})
