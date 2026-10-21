import { QueryClient } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

import {
  ACCOUNT_CODES,
  ACCOUNT_KEY,
  applyAccountEvent,
  DELETE_TIME_STYLE,
  deleteTime,
  fileTooBig,
  INACTIVE,
  isAccountCode,
  localClock,
  MAX_COOKIE_FILE_BYTES,
  needsAccount,
  putAccountStatus,
  remainingClock,
  showAccountButton,
  syncAccountCache,
} from "./account"
import { ApiError } from "./api"
import type { AccountStatus } from "./types"

const NOW = Date.parse("2026-10-06T03:00:00Z")
const ACTIVE: AccountStatus = {
  active: true,
  importedAt: "2026-10-06T03:00:00+00:00",
  expiresAt: "2026-10-06T05:00:00+00:00",
  used: false,
}

describe("error → ปุ่ม", () => {
  it("เฉพาะรหัสจำกัดอายุ / ส่วนตัว และยังไม่ได้ถือบัญชี", () => {
    expect([...ACCOUNT_CODES].sort()).toEqual(["E_AGE_RESTRICTED", "E_VIDEO_PRIVATE"])
    expect(showAccountButton("E_AGE_RESTRICTED", false)).toBe(true)
    expect(showAccountButton("E_VIDEO_PRIVATE", false)).toBe(true)
    expect(showAccountButton("E_VIDEO_PRIVATE", true)).toBe(false) // ถืออยู่แล้ว = ข้อความ "ลองด้วยบัญชีแล้ว…"
    for (const code of ["E_BOT_CHECK", "E_NETWORK", "E_GEO_BLOCKED", "E_UNKNOWN", undefined, null]) {
      expect(showAccountButton(code, false)).toBe(false)
    }
    expect(isAccountCode("E_AGE_RESTRICTED")).toBe(true)
  })

  it("needsAccount ดูเฉพาะ ApiError", () => {
    expect(needsAccount(new ApiError(409, "E_AGE_RESTRICTED", "m", null, null))).toBe(true)
    expect(needsAccount(new ApiError(429, "E_BOT_CHECK", "m", null, null))).toBe(false)
    expect(needsAccount(new Error("E_AGE_RESTRICTED"))).toBe(false)
  })
})

describe("remainingClock (แถบบนหน้า: ลบอัตโนมัติภายใน …)", () => {
  it("เวลาที่เหลือเป็นคำ ปัดนาทีขึ้น", () => {
    expect(remainingClock("2026-10-06T05:00:00Z", NOW)).toBe("2 ชม.")
    expect(remainingClock("2026-10-06T04:59:59Z", NOW)).toBe("2 ชม.")
    expect(remainingClock("2026-10-06T04:59:00Z", NOW)).toBe("1 ชม. 59 นาที")
    expect(remainingClock("2026-10-06T03:09:01Z", NOW)).toBe("10 นาที")
    expect(remainingClock("2026-10-06T03:00:01Z", NOW)).toBe("1 นาที")
  })
  it("นาฬิกาของหน้าเว็บช้ากว่าเวลานำเข้า = นับจากเวลานำเข้า (ไม่โชว์ 2 ชม. 1 นาที)", () => {
    expect(remainingClock("2026-10-06T05:00:00Z", NOW - 14_000, "2026-10-06T03:00:00Z")).toBe("2 ชม.")
    expect(remainingClock("2026-10-06T03:10:00Z", NOW + 60_000, "2026-10-06T01:00:00Z")).toBe("9 นาที")
  })
  it("เลยเวลาแล้ว หรืออ่านไม่ได้ = 0 นาที", () => {
    expect(remainingClock("2026-10-06T02:00:00Z", NOW)).toBe("0 นาที")
    expect(remainingClock("nonsense", NOW)).toBe("0 นาที")
  })
})

describe("deleteTime (คำถามเปิด Q1: เวลาที่เหลือ หรือเวลาบนนาฬิกา)", () => {
  it("ค่าเริ่มต้นเป็นเวลาที่เหลือตามสเปก", () => {
    expect(DELETE_TIME_STYLE).toBe("remaining")
    expect(deleteTime({ expiresAt: "2026-10-06T05:00:00+00:00", importedAt: ACTIVE.importedAt }, NOW)).toBe("2 ชม.")
  })
  it("แบบ clock = เวลาตามนาฬิกาของเครื่องตอนที่จะลบ", () => {
    const at = new Date(2026, 9, 6, 17, 5)
    expect(deleteTime({ expiresAt: at.toISOString() }, NOW, "clock")).toBe("17:05")
  })
})

describe("localClock (หน้าตรวจสุขภาพ: นำเข้าเมื่อ HH:MM)", () => {
  it("นาฬิกาตามเครื่อง สองหลัก", () => {
    const at = new Date(2026, 9, 6, 9, 5)
    expect(localClock(at.toISOString())).toBe("09:05")
  })
  it("อ่านไม่ได้ = ว่าง", () => {
    expect(localClock("x")).toBe("")
  })
})

describe("fileTooBig", () => {
  it("เกิน 1 MB เท่านั้น", () => {
    expect(fileTooBig(MAX_COOKIE_FILE_BYTES)).toBe(false)
    expect(fileTooBig(MAX_COOKIE_FILE_BYTES + 1)).toBe(true)
  })
})

describe("applyAccountEvent", () => {
  it("ลบแล้ว = ไม่ได้ใช้บัญชี", () => {
    expect(applyAccountEvent(ACTIVE, { active: false, reason: "expired" })).toEqual(INACTIVE)
    expect(applyAccountEvent(undefined, { active: false, reason: "manual" })).toEqual(INACTIVE)
  })
  it("ยังถืออยู่ = เปลี่ยนเวลาลบ (grace เริ่ม/ยกเลิก)", () => {
    expect(applyAccountEvent(ACTIVE, { active: true, expiresAt: "2026-10-06T03:10:00+00:00" })).toEqual({
      ...ACTIVE,
      expiresAt: "2026-10-06T03:10:00+00:00",
    })
  })
  it("เพิ่งนำเข้าจากแท็บอื่น = ไม่รู้เวลานำเข้า ต้องโหลดใหม่", () => {
    expect(applyAccountEvent(INACTIVE, { active: true, expiresAt: "2026-10-06T05:00:00+00:00" })).toBeUndefined()
    expect(applyAccountEvent(undefined, { active: true })).toBeUndefined()
  })
})

describe("syncAccountCache", () => {
  function setup(prev: AccountStatus | undefined) {
    const client = new QueryClient()
    if (prev !== undefined) client.setQueryData(ACCOUNT_KEY, prev)
    const invalidate = vi.spyOn(client, "invalidateQueries")
    return { client, invalidate }
  }

  it("ยังถืออยู่ (นำเข้าซ้ำจากแท็บอื่น / grace): เปลี่ยนเวลาลบทันที แล้วโหลดสถานะเต็มใหม่ด้วย (เวลานำเข้าใหม่)", () => {
    const { client, invalidate } = setup(ACTIVE)
    syncAccountCache(client, { active: true, expiresAt: "2026-10-06T05:30:00+00:00" })
    expect(client.getQueryData(ACCOUNT_KEY)).toEqual({ ...ACTIVE, expiresAt: "2026-10-06T05:30:00+00:00" })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ACCOUNT_KEY })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["health"] })
  })

  it("เพิ่งนำเข้า (แคชไม่ถือบัญชี): โหลดสถานะเต็มใหม่ และหน้าตรวจสุขภาพใหม่", () => {
    const { client, invalidate } = setup(INACTIVE)
    syncAccountCache(client, { active: true, expiresAt: "2026-10-06T05:00:00+00:00" })
    expect(client.getQueryData(ACCOUNT_KEY)).toEqual(INACTIVE)
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ACCOUNT_KEY })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["health"] })
  })

  it("ลบแล้ว: แคชเป็นไม่ได้ใช้บัญชี และโหลดหน้าตรวจสุขภาพใหม่", () => {
    const { client, invalidate } = setup(ACTIVE)
    syncAccountCache(client, { active: false, reason: "expired" })
    expect(client.getQueryData(ACCOUNT_KEY)).toEqual(INACTIVE)
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["health"] })
  })
})

describe("putAccountStatus", () => {
  /** GET /api/cookies ที่ค้างอยู่ (คำตอบคำนวณก่อนการเปลี่ยนแปลง) แล้วมาถึงทีหลังค่าใหม่ */
  function staleRead(client: QueryClient) {
    let answer!: (status: AccountStatus) => void
    const pending = client
      .fetchQuery({ queryKey: ACCOUNT_KEY, queryFn: () => new Promise<AccountStatus>((resolve) => (answer = resolve)) })
      .catch(() => undefined)
    return { answer, pending }
  }

  it("ลบแล้วระหว่างที่ GET ยังค้าง: คำตอบเก่า (ยังถือบัญชี) ที่มาทีหลังไม่ทับ แถบบนหน้าไม่กลับมา", async () => {
    const client = new QueryClient()
    client.setQueryData(ACCOUNT_KEY, ACTIVE)
    const read = staleRead(client)
    putAccountStatus(client, INACTIVE)
    read.answer(ACTIVE)
    await read.pending
    expect(client.getQueryData(ACCOUNT_KEY)).toEqual(INACTIVE)
  })

  it("นำเข้าแล้วระหว่างที่ GET ยังค้าง: คำตอบเก่า (ไม่ถือบัญชี) ไม่ทับ", async () => {
    const client = new QueryClient()
    const read = staleRead(client)
    putAccountStatus(client, ACTIVE)
    read.answer(INACTIVE)
    await read.pending
    expect(client.getQueryData(ACCOUNT_KEY)).toEqual(ACTIVE)
  })

  it("เทียบ: setQueryData เฉย ๆ โดนคำตอบเก่าทับ (เหตุที่ต้องยกเลิกก่อน)", async () => {
    const client = new QueryClient()
    client.setQueryData(ACCOUNT_KEY, ACTIVE)
    const read = staleRead(client)
    client.setQueryData(ACCOUNT_KEY, INACTIVE)
    read.answer(ACTIVE)
    await read.pending
    expect(client.getQueryData(ACCOUNT_KEY)).toEqual(ACTIVE)
  })
})
