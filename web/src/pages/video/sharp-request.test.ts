import { describe, expect, it } from "vitest"

import type { Job } from "@/lib/types"

import { sharpBlock, sharpJobBusy } from "./sharp-request"

const job = (over: Partial<Job>): Job => ({
  id: "j1",
  videoId: "aqz-KE-bpKQ",
  title: "",
  kind: "frames_sharp",
  params: {},
  status: "queued",
  position: 1,
  createdAt: "2026-10-05T03:00:00Z",
  ...over,
})

describe("sharpJobBusy", () => {
  it("a queued or running frames_sharp job of this clip", () => {
    expect(sharpJobBusy([job({})], "aqz-KE-bpKQ")).toBe(true)
    expect(sharpJobBusy([job({ status: "running" })], "aqz-KE-bpKQ")).toBe(true)
  })
  it("finished jobs, other clips, other kinds and no list are not busy", () => {
    expect(sharpJobBusy([job({ status: "done" }), job({ status: "failed" })], "aqz-KE-bpKQ")).toBe(false)
    expect(sharpJobBusy([job({ videoId: "jNQXAC9IVRw" })], "aqz-KE-bpKQ")).toBe(false)
    expect(sharpJobBusy([job({ kind: "frames_zip", params: { source: "sharp" } })], "aqz-KE-bpKQ")).toBe(false)
    expect(sharpJobBusy(undefined, "aqz-KE-bpKQ")).toBe(false)
  })
})

describe("sharpBlock", () => {
  it("loading, live, unknown duration, ok", () => {
    expect(sharpBlock(undefined)).toBe("loading")
    expect(sharpBlock({ isLive: true, durationS: 600 })).toBe("live")
    expect(sharpBlock({ isLive: false, durationS: 0 })).toBe("live")
    expect(sharpBlock({ isLive: false, durationS: 635 })).toBeNull()
  })
})
