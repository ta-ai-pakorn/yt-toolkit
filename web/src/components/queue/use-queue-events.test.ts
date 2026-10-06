import { QueryClient } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { accountDialog } from "@/components/account/account-store"
import { ACCOUNT_KEY } from "@/lib/account"
import { ApiError } from "@/lib/api"
import { JOBS_KEY } from "@/lib/jobs"
import type { Job } from "@/lib/types"

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), dismiss: vi.fn(), getToasts: vi.fn() }))
vi.mock("sonner", () => ({ toast }))
const api = vi.hoisted(() => ({ retryJob: vi.fn() }))
vi.mock("@/lib/jobs", async (importOriginal) => ({ ...(await importOriginal<object>()), retryJob: api.retryJob }))

import { runJobAction, serverEventHandlers } from "./use-queue"

const REMOVED = "ลบบัญชีออกจากแอพแล้ว · กลับไปกดออกจากระบบในหน้าต่างไม่ระบุตัวตน แล้วปิดหน้าต่าง"

function job(over: Partial<Job> = {}): Job {
  return {
    id: "j1",
    videoId: "ACCOUNTAGE1",
    title: "คลิปจำกัดอายุ",
    kind: "video",
    params: { maxQuality: false, splitChapters: false, noAudio: false, audioLanguage: "original" },
    status: "queued",
    position: 0,
    createdAt: "2026-10-06T10:00:00Z",
    ...over,
  }
}
const failed = (code: string) => job({ status: "failed", error: { code, message: "คลิปนี้จำกัดอายุ", detail: "x" } })

beforeEach(() => {
  for (const fn of [...Object.values(toast), api.retryJob]) fn.mockReset()
  toast.getToasts.mockReturnValue([])
})
afterEach(() => accountDialog.close())

describe("serverEventHandlers: toast ของงานที่พลาด (M5 รอบ C)", () => {
  it("จำกัดอายุ/ส่วนตัวและยังไม่ได้ใช้บัญชี = ปุ่มหลักคือ ใช้บัญชียูทูปชั่วคราว ปุ่มรองคือ ดูรายละเอียด · นำเข้าแล้วลองงานเดิมใหม่", async () => {
    const client = new QueryClient()
    const queued = job()
    client.setQueryData<Job[]>(JOBS_KEY, [failed("E_AGE_RESTRICTED")])
    api.retryJob.mockResolvedValueOnce({ ...queued, status: "queued" })
    serverEventHandlers(client).onJobChange?.(queued, failed("E_AGE_RESTRICTED"))
    const [, options] = toast.error.mock.lastCall as [string, { action: { label: string; onClick: () => void }; cancel: { label: string } }]
    expect(options.action.label).toBe("ใช้บัญชียูทูปชั่วคราว")
    expect(options.cancel.label).toBe("ดูรายละเอียด")
    options.action.onClick()
    const request = accountDialog.get().request
    expect(request?.origin).toBe("error")
    request?.onImported?.()
    await vi.waitFor(() => expect(api.retryJob).toHaveBeenCalledTimes(1))
    expect(api.retryJob).toHaveBeenCalledWith("j1")
    await vi.waitFor(() => expect(client.getQueryData<Job[]>(JOBS_KEY)?.[0].status).toBe("queued"))
  })

  it("ยูทูปขอตรวจสอบ (E_BOT_CHECK) = ไม่มีปุ่มบัญชี ปุ่มเดียวคือ ดูรายละเอียด", () => {
    serverEventHandlers(new QueryClient()).onJobChange?.(job(), failed("E_BOT_CHECK"))
    const [, options] = toast.error.mock.lastCall as [string, { action: { label: string }; cancel?: unknown }]
    expect(options.action.label).toBe("ดูรายละเอียด")
    expect(options.cancel).toBeUndefined()
  })

  it("ถือบัญชีอยู่แล้ว หรือรหัสอื่น = ปุ่มเดียว ดูรายละเอียด ไม่มีปุ่มรอง", () => {
    const client = new QueryClient()
    client.setQueryData(ACCOUNT_KEY, { active: true, used: true })
    serverEventHandlers(client).onJobChange?.(job(), failed("E_VIDEO_PRIVATE"))
    let [, options] = toast.error.mock.lastCall as [string, { action: { label: string }; cancel?: unknown }]
    expect(options.action.label).toBe("ดูรายละเอียด")
    expect(options.cancel).toBeUndefined()
    serverEventHandlers(new QueryClient()).onJobChange?.(job(), failed("E_NETWORK"))
    ;[, options] = toast.error.mock.lastCall as [string, { action: { label: string }; cancel?: unknown }]
    expect(options.action.label).toBe("ดูรายละเอียด")
    expect(options.cancel).toBeUndefined()
  })
})

describe("runJobAction: ตัวเดียวทั้งปุ่มในแถวและปุ่มใน toast", () => {
  it("ไม่สำเร็จ = toast แล้วโหลดรายการงานใหม่ ไม่โยน error", async () => {
    const client = new QueryClient()
    const invalidate = vi.spyOn(client, "invalidateQueries")
    api.retryJob.mockRejectedValueOnce(new ApiError(500, "E_UNKNOWN", "พัง", null, null))
    await runJobAction(client, "retry", "j1")
    expect(toast.error).toHaveBeenCalledWith("ทำรายการนี้ไม่สำเร็จ ลองรีเฟรชหน้าเว็บ")
    expect(invalidate).toHaveBeenCalledWith({ queryKey: JOBS_KEY })
  })
})

describe("serverEventHandlers: ปิดโปรแกรม", () => {
  it("บัญชีถูกลบเพราะปิดโปรแกรม: ล้าง toast อื่นทีละตัว แต่ toast ลบบัญชีที่ขึ้นอยู่แล้วยังอยู่ (ไม่สร้างใหม่)", () => {
    const handlers = serverEventHandlers(new QueryClient())
    handlers.onAccount?.({ active: false, reason: "shutdown" })
    expect(toast.info.mock.lastCall?.[0]).toBe(REMOVED)
    toast.info.mockClear()
    toast.getToasts.mockReturnValue([{ id: "job-j1" }, { id: "account-removed" }, { id: 7 }])
    handlers.onShutdown()
    expect(toast.dismiss.mock.calls).toEqual([["job-j1"], [7]])  // ไม่มี dismiss() แบบล้างทั้งหมด
    expect(toast.info).not.toHaveBeenCalled()
  })

  it("บัญชีถูกลบเพราะปิดโปรแกรมแต่ toast ลบบัญชีถูกปิดไปแล้ว = แสดงใหม่หลังล้าง toast อื่น", () => {
    const handlers = serverEventHandlers(new QueryClient())
    handlers.onAccount?.({ active: false, reason: "shutdown" })
    toast.info.mockClear()
    toast.getToasts.mockReturnValue([{ id: "job-j1" }])
    handlers.onShutdown()
    expect(toast.dismiss.mock.calls).toEqual([["job-j1"]])
    expect(toast.info).toHaveBeenCalledTimes(1)
    expect(toast.info.mock.lastCall?.[0]).toBe(REMOVED)
    expect(toast.info.mock.lastCall?.[1]).toMatchObject({ id: "account-removed", duration: Infinity })
  })

  it("บัญชีหมดเวลา (expired) แล้วปิดโปรแกรม = เก็บ toast ลบบัญชีไว้เหมือนกรณีปิดโปรแกรม", () => {
    const handlers = serverEventHandlers(new QueryClient())
    handlers.onAccount?.({ active: false, reason: "expired" })
    toast.info.mockClear()
    toast.getToasts.mockReturnValue([{ id: "job-j1" }, { id: "account-removed" }])
    handlers.onShutdown()
    expect(toast.dismiss.mock.calls).toEqual([["job-j1"]])
    expect(toast.info).not.toHaveBeenCalled()
  })

  it("ปิดโปรแกรมโดยไม่มีบัญชี หรือบัญชีถูกลบด้วยเหตุผลอื่น = แค่ล้าง toast", () => {
    const handlers = serverEventHandlers(new QueryClient())
    handlers.onShutdown()
    handlers.onAccount?.({ active: false, reason: "manual" })
    toast.info.mockClear()
    handlers.onShutdown()
    expect(toast.dismiss).toHaveBeenCalledTimes(2)
    expect(toast.info).not.toHaveBeenCalled()
  })
})
