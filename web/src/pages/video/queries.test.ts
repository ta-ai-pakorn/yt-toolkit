import { QueryClient, QueryObserver } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"

import { pinnedCommentQuery, sharpQuery } from "./queries"

afterEach(() => vi.unstubAllGlobals())

function stubFetch(status: number, body: unknown) {
  const fetch = vi.fn(async () => new Response(JSON.stringify(body), { status }))
  vi.stubGlobal("fetch", fetch)
  return fetch
}

const envelope = (code: string) => ({ error: { code, message: "ข้อความ", detail: null } })

/** กางแถวคอมเมนต์ปักหมุด (mount observer ใหม่) แล้วรอจนคำขอที่อาจยิงเสร็จ คืนสถานะที่แถวเห็น */
async function open(client: QueryClient, enabled = true) {
  const observer = new QueryObserver(client, pinnedCommentQuery("88o5Sk8_m1Y", enabled))
  const unsubscribe = observer.subscribe(() => undefined)
  await vi.waitFor(() => expect(observer.getCurrentResult().isFetching).toBe(false))
  const result = observer.getCurrentResult()
  unsubscribe()
  return result
}

describe("pinnedCommentQuery", () => {
  it("ยังไม่กาง (enabled false) ไม่ยิงคำขอ", async () => {
    const fetch = stubFetch(200, { comment: null })
    await open(new QueryClient(), false)
    expect(fetch).not.toHaveBeenCalled()
  })

  it("ยิง /api/videos/<id>/pinned-comment ครั้งเดียว กางซ้ำใช้ผลเดิม", async () => {
    const fetch = stubFetch(200, { comment: { text: "สวัสดี\nบรรทัดสอง", likes: 12 } })
    const client = new QueryClient()
    expect((await open(client)).data).toEqual({ comment: { text: "สวัสดี\nบรรทัดสอง", likes: 12 } })
    await open(client)
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(fetch).toHaveBeenCalledWith("/api/videos/88o5Sk8_m1Y/pinned-comment", expect.anything())
  })

  it("E_BOT_CHECK ลองใหม่ไม่ช่วย: กางใหม่ไม่ยิงซ้ำ", async () => {
    const fetch = stubFetch(429, envelope("E_BOT_CHECK"))
    const client = new QueryClient()
    expect((await open(client)).error).toMatchObject({ code: "E_BOT_CHECK" })
    expect((await open(client)).error).toMatchObject({ code: "E_BOT_CHECK" })
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it("เน็ตหลุด (E_NETWORK) กางใหม่แล้วยิงใหม่ให้เอง", async () => {
    const fetch = stubFetch(502, envelope("E_NETWORK"))
    const client = new QueryClient()
    await open(client)
    await open(client)
    expect(fetch).toHaveBeenCalledTimes(2)
  })
})

async function observe<T>(client: QueryClient, options: ReturnType<typeof sharpQuery>) {
  const observer = new QueryObserver(client, options)
  const unsubscribe = observer.subscribe(() => undefined)
  await vi.waitFor(() => expect(observer.getCurrentResult().isFetching).toBe(false))
  const result = observer.getCurrentResult()
  unsubscribe()
  return result as { data: T | undefined; error: unknown }
}

describe("sharpQuery", () => {
  it("uses the shared key and the sharp route", async () => {
    const fetch = stubFetch(200, { origin: "manual", intervalMs: 60000, frames: [] })
    expect(sharpQuery("aqz-KE-bpKQ", true).queryKey).toEqual(["sharp", "aqz-KE-bpKQ"])
    await observe(new QueryClient(), sharpQuery("aqz-KE-bpKQ", true))
    expect(fetch).toHaveBeenCalledWith("/api/videos/aqz-KE-bpKQ/sharp", expect.anything())
  })

  it("404 = no sharp set yet (null), not an error", async () => {
    stubFetch(404, envelope("E_NO_SHARP_FRAMES"))
    const result = await observe(new QueryClient(), sharpQuery("aqz-KE-bpKQ", true))
    expect(result.data).toBeNull()
    expect(result.error).toBeNull()
  })

  it("other failures stay errors", async () => {
    stubFetch(502, envelope("E_NETWORK"))
    const result = await observe(new QueryClient(), sharpQuery("aqz-KE-bpKQ", true))
    expect(result.error).toMatchObject({ code: "E_NETWORK" })
  })
})
