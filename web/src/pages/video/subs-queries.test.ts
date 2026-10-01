import { QueryClient, QueryObserver } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"

import { tokensQuery } from "./subs-queries"

afterEach(() => vi.unstubAllGlobals())

function stubFetch(status: number, code: string) {
  const body = { error: { code, message: "ข้อความ", detail: null } }
  const fetch = vi.fn(async () => new Response(JSON.stringify(body), { status }))
  vi.stubGlobal("fetch", fetch)
  return fetch
}

/** เปิดแท็บ (mount observer ใหม่) แล้วรอจนคำขอที่อาจยิงเสร็จ คืนสถานะที่แท็บเห็น */
async function mountTab(client: QueryClient, trackId: string) {
  const observer = new QueryObserver(client, tokensQuery("88o5Sk8_m1Y", trackId))
  const unsubscribe = observer.subscribe(() => undefined)
  await vi.waitFor(() => expect(observer.getCurrentResult().isFetching).toBe(false))
  const result = observer.getCurrentResult()
  unsubscribe()
  return result
}

describe("tokensQuery: สลับแท็บกลับมาหลัง error", () => {
  it.each([
    [503, "E_TRANSLATION_BLOCKED"],
    [404, "E_NO_SUBTITLES"],
    [429, "E_BOT_CHECK"],
  ])("%i %s ลองใหม่ไม่ช่วย: ไม่ยิงคำขอซ้ำ แท็บที่เปิดใหม่ยังเห็น error เดิม", async (status, code) => {
    const fetch = stubFetch(status, code)
    const client = new QueryClient()
    expect((await mountTab(client, "t.en")).error).toMatchObject({ code })
    const again = await mountTab(client, "t.en")
    expect(again.isError).toBe(true)
    expect(again.error).toMatchObject({ code })
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it("เน็ตหลุด (E_NETWORK) ยังยิงใหม่ให้เองเมื่อเปิดแท็บอีกครั้ง", async () => {
    const fetch = stubFetch(502, "E_NETWORK")
    const client = new QueryClient()
    await mountTab(client, "a.th-orig")
    await mountTab(client, "a.th-orig")
    expect(fetch).toHaveBeenCalledTimes(2)
  })
})
