import { QueryClient } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"

import type { VideoInfo } from "@/lib/types"

import { videoTitleQuery } from "./queries"

const info = (title: string): VideoInfo => ({
  videoId: "aqz-KE-bpKQ",
  title,
  channel: "c",
  durationS: 1,
  thumbnailUrl: "",
  chapters: [],
  video: [],
  audio: [],
  hasStoryboard: false,
  isLive: false,
})

function stubFetch(body: unknown) {
  const fetch = vi.fn(async () => new Response(JSON.stringify(body), { status: 200 }))
  vi.stubGlobal("fetch", fetch)
  return fetch
}

afterEach(() => vi.unstubAllGlobals())

describe("videoTitleQuery", () => {
  it("ใช้ key ของตัวเอง (peek) ไม่ชนกับ key ของหน้า W2 ที่ต้องยิงคำขอปกติเอง", () => {
    expect(videoTitleQuery("aqz-KE-bpKQ").queryKey).toEqual(["video", "aqz-KE-bpKQ", "peek"])
  })

  it("เรียก ?peek=1 แล้วเติมผลลงใน key ของหน้า W2 เมื่อยังไม่มีข้อมูล", async () => {
    const fetch = stubFetch(info("จาก peek"))
    const client = new QueryClient()
    await client.fetchQuery(videoTitleQuery("aqz-KE-bpKQ"))
    expect(fetch).toHaveBeenCalledWith("/api/videos/aqz-KE-bpKQ?peek=1", expect.anything())
    expect(client.getQueryData<VideoInfo>(["video", "aqz-KE-bpKQ"])?.title).toBe("จาก peek")
  })

  it("ไม่ทับข้อมูลที่ key ของหน้า W2 มีอยู่แล้ว", async () => {
    stubFetch(info("จาก peek"))
    const client = new QueryClient()
    client.setQueryData(["video", "aqz-KE-bpKQ"], info("ของจริงจาก W2"))
    await client.fetchQuery(videoTitleQuery("aqz-KE-bpKQ"))
    expect(client.getQueryData<VideoInfo>(["video", "aqz-KE-bpKQ"])?.title).toBe("ของจริงจาก W2")
  })
})
