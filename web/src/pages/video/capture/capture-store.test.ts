import { QueryClient } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { accountDialog } from "@/components/account/account-store"
import { ACCOUNT_KEY } from "@/lib/account"
import { ApiError } from "@/lib/api"
import { QUEUE_KEY } from "@/lib/jobs"
import type { Capture } from "@/lib/types"

import { capturesKey } from "./capture-api"
import { __resetCaptureStoreForTests, captureStore, viewsOtherClip } from "./capture-store"
import { runCapture } from "./use-capture"

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))
vi.mock("sonner", () => ({ toast }))
const api = vi.hoisted(() => ({ postCapture: vi.fn() }))
vi.mock("./capture-api", async (importOriginal) => ({ ...(await importOriginal<object>()), postCapture: api.postCapture }))

const BBB = "aqz-KE-bpKQ"
const item = (tMs: number): Capture => ({ id: `c_${tMs}`, tMs, width: 1920, height: 1080, url: `/api/cache/${BBB}/captures/c_${tMs}.jpg?v=1` })

beforeEach(() => {
  __resetCaptureStoreForTests()
  toast.success.mockReset()
  toast.error.mockReset()
  api.postCapture.mockReset()
})
afterEach(() => __resetCaptureStoreForTests())

describe("captureStore", () => {
  it("tryBegin is single-flight: ครั้งที่สองระหว่างถ่าย = false จน end", () => {
    expect(captureStore.tryBegin()).toBe(true)
    expect(captureStore.tryBegin()).toBe(false)
    captureStore.end()
    expect(captureStore.tryBegin()).toBe(true)
  })

  it("view / closeView / flash (n เพิ่มทุกครั้ง)", () => {
    captureStore.view({ videoId: BBB, id: "c_1" })
    expect(captureStore.get().viewing).toEqual({ videoId: BBB, id: "c_1" })
    captureStore.closeView()
    expect(captureStore.get().viewing).toBeNull()
    captureStore.flash({ videoId: BBB, id: "c_1" })
    captureStore.flash({ videoId: BBB, id: "c_1" })
    expect(captureStore.get().flash).toEqual({ videoId: BBB, id: "c_1", n: 2 })
  })
})

describe("flash และ view ที่ค้างอยู่", () => {
  it("consumeFlash ใช้ครั้งเดียว · ภาพใหม่กว่า (n ไม่ตรง) ไม่ถูกลบ", () => {
    captureStore.flash({ videoId: BBB, id: "c_1" })
    captureStore.consumeFlash(1)
    expect(captureStore.get().flash).toBeNull()
    captureStore.flash({ videoId: BBB, id: "c_2" })
    captureStore.consumeFlash(1)
    expect(captureStore.get().flash).toMatchObject({ id: "c_2", n: 2 })
  })

  it("dropOtherClips ทิ้ง view/flash ของคลิปอื่น เก็บของคลิปนี้ · dropFlash ทิ้งเฉพาะของคลิปนั้น", () => {
    captureStore.view({ videoId: "OTHER000001", id: "c_9" })
    captureStore.flash({ videoId: "OTHER000001", id: "c_9" })
    captureStore.dropOtherClips(BBB)
    expect(captureStore.get().viewing).toBeNull()
    expect(captureStore.get().flash).toBeNull()
    captureStore.view({ videoId: BBB, id: "c_1" })
    captureStore.flash({ videoId: BBB, id: "c_1" })
    captureStore.dropOtherClips(BBB)
    expect(captureStore.get().viewing).toEqual({ videoId: BBB, id: "c_1" })
    expect(captureStore.get().flash).toMatchObject({ videoId: BBB })
    captureStore.dropFlash("OTHER000001")
    expect(captureStore.get().flash).not.toBeNull()
    captureStore.dropFlash(BBB)
    expect(captureStore.get().flash).toBeNull()
    expect(captureStore.get().viewing).not.toBeNull()
  })
})

describe("viewsOtherClip", () => {
  it("เปิดภาพของคลิปอื่น = true · คลิปนี้หรือไม่มีคำสั่ง = false", () => {
    expect(viewsOtherClip({ videoId: "OTHER000001", id: "c_1" }, BBB)).toBe(true)
    expect(viewsOtherClip({ videoId: BBB, id: "c_1" }, BBB)).toBe(false)
    expect(viewsOtherClip(null, BBB)).toBe(false)
  })
})

describe("runCapture", () => {
  it("ปัดเวลา ส่งครั้งเดียว เติมลงแถบตามเวลา กระพริบ และ toast มีปุ่ม ดูภาพ", async () => {
    const client = new QueryClient()
    client.setQueryData<Capture[]>(capturesKey(BBB), [item(200_000)])
    api.postCapture.mockResolvedValue(item(125_400))
    const first = runCapture(client, BBB, 125_449)
    await runCapture(client, BBB, 9_000) // ระหว่างถ่ายอยู่: ไม่ส่งซ้ำ
    await first
    expect(api.postCapture).toHaveBeenCalledTimes(1)
    expect(api.postCapture).toHaveBeenCalledWith(BBB, 125_400)
    expect(client.getQueryData<Capture[]>(capturesKey(BBB))?.map((c) => c.tMs)).toEqual([125_400, 200_000])
    expect(captureStore.get().flash).toMatchObject({ videoId: BBB, id: "c_125400" })
    expect(captureStore.get().busy).toBe(false)
    const [message, options] = toast.success.mock.calls[0]
    expect(message).toBe("ถ่ายภาพคมแล้ว · 2:05.4")
    expect(options.action.label).toBe("ดูภาพ")
    options.action.onClick()
    expect(captureStore.get().viewing).toEqual({ videoId: BBB, id: "c_125400" })
  })

  it("ดูจนจบคลิปแล้วกดถ่าย: ส่งเวลาไม่เกิน 100 ms ก่อนจบตามความยาวในข้อมูลคลิปที่โหลดไว้", async () => {
    const client = new QueryClient()
    client.setQueryData(["video", BBB], { videoId: BBB, durationS: 635, isLive: false })
    api.postCapture.mockResolvedValue(item(634_900))
    await runCapture(client, BBB, 635_000)
    expect(api.postCapture).toHaveBeenCalledWith(BBB, 634_900)
  })

  it("รายการที่กำลังโหลดค้างอยู่ตอนถ่ายเสร็จ (รายการก่อนถ่าย) ไม่ทับภาพใหม่", async () => {
    const client = new QueryClient()
    let release: (list: Capture[]) => void = () => undefined
    const stale = client
      .fetchQuery({ queryKey: capturesKey(BBB), queryFn: () => new Promise<Capture[]>((resolve) => (release = resolve)) })
      .catch(() => undefined)
    api.postCapture.mockResolvedValue(item(125_400))
    await runCapture(client, BBB, 125_400)
    release([item(200_000)])
    await stale
    expect(client.getQueryData<Capture[]>(capturesKey(BBB))?.map((c) => c.id)).toEqual(["c_125400"])
  })

  it("พลาด = toast ข้อความจาก backend ไม่เติมแถบ · ยูทูปขอตรวจสอบ = โหลดสถานะคิวใหม่", async () => {
    const client = new QueryClient()
    const invalidate = vi.spyOn(client, "invalidateQueries")
    api.postCapture.mockRejectedValueOnce(new ApiError(422, "E_CAPTURE_UNSUPPORTED", "ถ่ายไม่ได้", null, null))
    await runCapture(client, BBB, 0)
    expect(toast.error).toHaveBeenCalledWith("ถ่ายไม่ได้")
    expect(client.getQueryData(capturesKey(BBB))).toBeUndefined()
    expect(invalidate).not.toHaveBeenCalled()
    api.postCapture.mockRejectedValueOnce(new ApiError(429, "E_BOT_CHECK", "ยูทูปขอให้ยืนยัน", null, null))
    await runCapture(client, BBB, 0)
    expect(invalidate).toHaveBeenCalledWith({ queryKey: QUEUE_KEY })
    expect(captureStore.get().busy).toBe(false)
  })

  it("M5 รอบ C: จำกัดอายุ/ส่วนตัวและยังไม่ได้ใช้บัญชี = toast มีปุ่ม ใช้บัญชียูทูปชั่วคราว นำเข้าแล้วถ่ายเวลาเดิมใหม่", async () => {
    const client = new QueryClient()
    api.postCapture.mockRejectedValueOnce(new ApiError(409, "E_AGE_RESTRICTED", "คลิปนี้จำกัดอายุ", null, null))
    await runCapture(client, BBB, 2_000)
    const [message, options] = toast.error.mock.lastCall as [string, { action: { label: string; onClick: () => void } }]
    expect(message).toBe("คลิปนี้จำกัดอายุ")
    expect(options.action.label).toBe("ใช้บัญชียูทูปชั่วคราว")
    expect((options as { duration?: number }).duration).toBe(Infinity)
    options.action.onClick()
    const request = accountDialog.get().request
    expect(request?.origin).toBe("error")
    api.postCapture.mockResolvedValueOnce(item(2_000))
    request?.onImported?.()
    await vi.waitFor(() => expect(toast.success).toHaveBeenCalledTimes(1))
    expect(api.postCapture).toHaveBeenCalledTimes(2)
    expect(api.postCapture).toHaveBeenLastCalledWith(BBB, 2_000)
    expect(toast.success.mock.lastCall?.[0]).toBe("ถ่ายภาพคมแล้ว · 0:02")
    accountDialog.close()
  })

  it("M5 รอบ C: ยูทูปขอตรวจสอบ (E_BOT_CHECK) = ไม่มีปุ่มบัญชี ข้อความเดิม ไม่ค้างถาวร", async () => {
    const client = new QueryClient()
    api.postCapture.mockRejectedValueOnce(new ApiError(429, "E_BOT_CHECK", "ยูทูปขอให้ยืนยัน", null, null))
    await runCapture(client, BBB, 0)
    expect(toast.error).toHaveBeenLastCalledWith("ยูทูปขอให้ยืนยัน")
  })

  it("M5 รอบ C: ถือบัญชีอยู่แล้ว = ไม่มีปุ่ม (ข้อความ ลองด้วยบัญชีแล้ว… มาจาก backend)", async () => {
    const client = new QueryClient()
    client.setQueryData(ACCOUNT_KEY, { active: true, used: true })
    api.postCapture.mockRejectedValueOnce(new ApiError(404, "E_VIDEO_PRIVATE", "ลองด้วยบัญชีแล้วยังเปิดไม่ได้", null, null))
    await runCapture(client, BBB, 0)
    expect(toast.error).toHaveBeenLastCalledWith("ลองด้วยบัญชีแล้วยังเปิดไม่ได้")
  })
})
