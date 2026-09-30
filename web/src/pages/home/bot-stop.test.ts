import { QueryClient } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"

import { ApiError } from "@/lib/api"

import { BotStopped, createBotStop } from "./bot-stop"
import { playlistQuery, videoTitleQuery } from "./queries"

const botError = () => new ApiError(429, "E_BOT_CHECK", "ข้อความ", null, null)

afterEach(() => vi.unstubAllGlobals())

describe("createBotStop", () => {
  it("เริ่มต้นไม่เบรก และคำขอที่สำเร็จผ่านไปตามปกติ", async () => {
    const gate = createBotStop()
    await expect(gate.run(async () => 42)).resolves.toBe(42)
    expect(gate.isStopped()).toBe(false)
  })

  it("คำขอที่ได้ E_BOT_CHECK เหยียบเบรก แจ้งผู้ฟัง แล้วคำขอถัดไปไม่เริ่ม", async () => {
    const gate = createBotStop()
    const listener = vi.fn()
    gate.subscribe(listener)
    await expect(gate.run(() => Promise.reject(botError()))).rejects.toBeInstanceOf(ApiError)
    expect(gate.isStopped()).toBe(true)
    expect(listener).toHaveBeenCalledTimes(1)
    const next = vi.fn(async () => 1)
    await expect(gate.run(next)).rejects.toBeInstanceOf(BotStopped)
    expect(next).not.toHaveBeenCalled()
  })

  it("error อื่น (เน็ตหลุด, คลิปส่วนตัว) ไม่เหยียบเบรก", async () => {
    const gate = createBotStop()
    for (const code of ["E_NETWORK", "E_VIDEO_PRIVATE", "E_UNKNOWN"]) {
      await expect(gate.run(() => Promise.reject(new ApiError(502, code, "x", null, null)))).rejects.toBeDefined()
    }
    expect(gate.isStopped()).toBe(false)
  })

  it("เหยียบซ้ำไม่แจ้งผู้ฟังซ้ำ และถอนการติดตามได้", async () => {
    const gate = createBotStop()
    const listener = vi.fn()
    const off = gate.subscribe(listener)
    off()
    await gate.run(() => Promise.reject(botError())).catch(() => undefined)
    expect(listener).not.toHaveBeenCalled()
  })

  it("รายการใหม่ (กดวิเคราะห์ใหม่) ได้เบรกใหม่ ลองได้อีกครั้ง", async () => {
    const first = createBotStop()
    await first.run(() => Promise.reject(botError())).catch(() => undefined)
    const second = createBotStop()
    await expect(second.run(async () => "ok")).resolves.toBe("ok")
  })
})

describe("ดึงชื่อคลิปและเพลย์ลิสต์ผ่านเบรก", () => {
  function stubBotFetch() {
    const body = { error: { code: "E_BOT_CHECK", message: "ข้อความ", detail: null } }
    const fetch = vi.fn(async () => new Response(JSON.stringify(body), { status: 429 }))
    vi.stubGlobal("fetch", fetch)
    return fetch
  }

  it("peek ได้ E_BOT_CHECK แล้ว peek และเพลย์ลิสต์ถัดไปของรายการเดียวกันไม่ยิงคำขอ", async () => {
    const fetch = stubBotFetch()
    const gate = createBotStop()
    const client = new QueryClient()
    await expect(client.fetchQuery(videoTitleQuery("aaaaaaaaaaa", gate))).rejects.toMatchObject({ code: "E_BOT_CHECK" })
    expect(fetch).toHaveBeenCalledTimes(1)
    await expect(client.fetchQuery(videoTitleQuery("bbbbbbbbbbb", gate))).rejects.toBeInstanceOf(BotStopped)
    await expect(client.fetchQuery(playlistQuery("PLtest", gate))).rejects.toBeInstanceOf(BotStopped)
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it("เพลย์ลิสต์ได้ E_BOT_CHECK แล้ว peek ถัดไปก็ไม่ยิงคำขอ", async () => {
    const fetch = stubBotFetch()
    const gate = createBotStop()
    const client = new QueryClient()
    await expect(client.fetchQuery(playlistQuery("PLtest", gate))).rejects.toMatchObject({ code: "E_BOT_CHECK" })
    await expect(client.fetchQuery(videoTitleQuery("aaaaaaaaaaa", gate))).rejects.toBeInstanceOf(BotStopped)
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it("เบรกของรายการอื่นไม่เกี่ยวกัน", async () => {
    const fetch = stubBotFetch()
    const client = new QueryClient()
    await client.fetchQuery(videoTitleQuery("aaaaaaaaaaa", createBotStop())).catch(() => undefined)
    await client.fetchQuery(videoTitleQuery("bbbbbbbbbbb", createBotStop())).catch(() => undefined)
    expect(fetch).toHaveBeenCalledTimes(2)
  })
})
