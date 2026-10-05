import { QueryClient } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

import type { Capture } from "@/lib/types"

import { capturesKey, capturesQuery, deleteCapture, postCapture, revealCaptures, withCapture, withoutCapture } from "./capture-api"

const BBB = "aqz-KE-bpKQ"
const item = (tMs: number): Capture => ({ id: `c_${tMs}`, tMs, width: 1920, height: 1080, url: `/api/cache/${BBB}/captures/c_${tMs}.jpg?v=1` })

function stubFetch(status: number, body: unknown) {
  return vi.fn<typeof fetch>(async () =>
    status === 204 ? new Response(null, { status }) : new Response(JSON.stringify(body), { status }),
  )
}

describe("withCapture / withoutCapture", () => {
  it("เติมแล้วเรียงตามเวลา · id เดิมแทนที่ · ลบตาม id", () => {
    const list = withCapture(withCapture(undefined, item(3000)), item(1000))
    expect(list.map((c) => c.tMs)).toEqual([1000, 3000])
    expect(withCapture(list, { ...item(1000), width: 1280 }).map((c) => c.width)).toEqual([1280, 1920])
    expect(withoutCapture(list, "c_1000").map((c) => c.id)).toEqual(["c_3000"])
    expect(withoutCapture(undefined, "c_1")).toEqual([])
  })
})

describe("คำขอ", () => {
  it("GET รายการ คืน captures", async () => {
    const fetch = stubFetch(200, { captures: [item(1000)] })
    const client = new QueryClient()
    const data = await client.fetchQuery(capturesQuery(BBB, true, { fetch }))
    expect(data).toEqual([item(1000)])
    expect(fetch).toHaveBeenCalledWith(`/api/videos/${BBB}/captures`, expect.objectContaining({ method: "GET" }))
    expect(capturesKey(BBB)).toEqual(["captures", BBB])
  })

  it("POST ส่ง tMs พร้อม token · DELETE และ reveal ใช้ path ของภาพ", async () => {
    const post = stubFetch(201, item(125_400))
    expect(await postCapture(BBB, 125_400, { fetch: post, token: "t" })).toEqual(item(125_400))
    const [url, init] = post.mock.calls[0]
    expect(url).toBe(`/api/videos/${BBB}/captures`)
    expect(init?.method).toBe("POST")
    expect(init?.body).toBe(JSON.stringify({ tMs: 125_400 }))
    expect(new Headers(init?.headers).get("X-Toolkit-Token")).toBe("t")

    const del = stubFetch(204, null)
    await deleteCapture(BBB, "c_125400", { fetch: del, token: "t" })
    expect(del.mock.calls[0][0]).toBe(`/api/videos/${BBB}/captures/c_125400`)
    expect(del.mock.calls[0][1]?.method).toBe("DELETE")

    const reveal = stubFetch(200, { ok: true })
    await revealCaptures(BBB, { fetch: reveal, token: "t" })
    expect(reveal.mock.calls[0][0]).toBe(`/api/videos/${BBB}/captures/reveal`)
  })

  it("error ของ backend ส่งต่อเป็น ApiError พร้อมข้อความไทย", async () => {
    const fetch = stubFetch(422, { error: { code: "E_CAPTURE_UNSUPPORTED", message: "ข้อความ", detail: null } })
    await expect(postCapture(BBB, 0, { fetch, token: "t" })).rejects.toMatchObject({ code: "E_CAPTURE_UNSUPPORTED", message: "ข้อความ" })
  })
})
