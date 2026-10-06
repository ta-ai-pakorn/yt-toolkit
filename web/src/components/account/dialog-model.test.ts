import { describe, expect, it } from "vitest"

import { accountDialog, openAccountDialog } from "./account-store"
import { canImport, dialogReducer, EMPTY_DIALOG, importLabel } from "./dialog-model"

describe("dialogReducer", () => {
  it("เลือกไฟล์แล้วกดนำเข้าได้ · กำลังส่งกดซ้ำไม่ได้", () => {
    expect(canImport(EMPTY_DIALOG)).toBe(false)
    const picked = dialogReducer(EMPTY_DIALOG, { type: "picked", fileName: "cookies.txt", text: "x" })
    expect(canImport(picked)).toBe(true)
    const sending = dialogReducer(picked, { type: "submitting" })
    expect(sending.pending).toBe(true)
    expect(canImport(sending)).toBe(false)
  })

  it("ไฟล์ใหญ่เกิน = ข้อความใต้ช่อง ไม่มีข้อความให้ส่ง", () => {
    const rejected = dialogReducer(EMPTY_DIALOG, { type: "rejected", fileName: "big.txt", message: "ใช้ไม่ได้" })
    expect(rejected).toEqual({ fileName: "big.txt", text: null, error: "ใช้ไม่ได้", pending: false })
    expect(canImport(rejected)).toBe(false)
    expect(dialogReducer(rejected, { type: "submitting" })).toBe(rejected)
  })

  it("backend ไม่รับ = ข้อความใต้ช่อง ยังเลือกไฟล์เดิมอยู่และลองใหม่ได้ · เลือกไฟล์ใหม่ล้างข้อความ", () => {
    const sending = dialogReducer(dialogReducer(EMPTY_DIALOG, { type: "picked", fileName: "a.txt", text: "x" }), {
      type: "submitting",
    })
    const failed = dialogReducer(sending, { type: "failed", message: "ไฟล์นี้ใช้ไม่ได้" })
    expect(failed.error).toBe("ไฟล์นี้ใช้ไม่ได้")
    expect(canImport(failed)).toBe(true)
    expect(dialogReducer(failed, { type: "picked", fileName: "b.txt", text: "y" }).error).toBeNull()
    expect(dialogReducer(failed, { type: "reset" })).toEqual(EMPTY_DIALOG)
  })
})

describe("importLabel และที่เก็บสถานะ dialog", () => {
  it("เปิดจาก error = นำเข้าแล้วลองใหม่ · จากหน้าตั้งค่า = นำเข้า", () => {
    expect(importLabel({ origin: "error" })).toBe("นำเข้าแล้วลองใหม่")
    expect(importLabel({ origin: "settings" })).toBe("นำเข้า")
    expect(importLabel(null)).toBe("นำเข้า")
  })

  it("openAccountDialog เปิดพร้อมคำขอ close ล้างคำขอ", () => {
    const onImported = () => undefined
    openAccountDialog({ origin: "error", onImported })
    expect(accountDialog.get()).toEqual({ open: true, request: { origin: "error", onImported } })
    accountDialog.close()
    expect(accountDialog.get()).toEqual({ open: false, request: null })
  })
})
