import { describe, expect, it, vi } from "vitest"

import { resetStats, STATS_KEY, statsQuery } from "./stats-api"

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })
}

describe("stats-api", () => {
  it("statsQuery โหลดใหม่ทุกครั้งที่เปิดแท็บ และเรียกแค่ /api/stats", async () => {
    const body = { since: null, clips: 0, files: 0, totalBytes: 0, byKind: [], byMonth: [] }
    const fetch = vi.fn().mockResolvedValue(jsonResponse(200, body))
    const query = statsQuery({ fetch, token: "tok" })
    expect(query.queryKey).toEqual(STATS_KEY)
    expect(query.staleTime).toBe(0)
    expect(query.refetchOnMount).toBe("always")
    await expect(query.queryFn()).resolves.toEqual(body)
    const [url] = fetch.mock.calls[0]
    expect(url).toBe("/api/stats")
  })

  it("resetStats ส่ง POST พร้อม token", async () => {
    const fetch = vi.fn().mockResolvedValue(jsonResponse(200, { since: "2026-10-15T05:00:00+00:00" }))
    await expect(resetStats({ fetch, token: "tok" })).resolves.toEqual({ since: "2026-10-15T05:00:00+00:00" })
    const [url, init] = fetch.mock.calls[0]
    expect(url).toBe("/api/stats/reset")
    expect(init.method).toBe("POST")
    expect(new Headers(init.headers).get("X-Toolkit-Token")).toBe("tok")
  })
})
