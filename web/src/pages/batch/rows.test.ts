import { describe, expect, it } from "vitest"

import type { PlaylistEntry, ResolveItem, Settings } from "@/lib/types"
import { PRESETS } from "@/lib/sub-options"

import {
  batchPath,
  buildBatchJobs,
  canSubmit,
  clipRows,
  headerState,
  isExpired,
  MAX_BATCH_ROWS,
  parseBatchSource,
  playlistRows,
  selectedRows,
} from "./rows"

const video = (videoId: string): ResolveItem => ({ input: `https://youtu.be/${videoId}`, kind: "video", videoId })
const ambiguous = (videoId: string): ResolveItem => ({
  input: `https://www.youtube.com/watch?v=${videoId}&list=PLabcdefghij`,
  kind: "ambiguous",
  videoId,
  playlistId: "PLabcdefghij",
})
const playlist: ResolveItem = {
  input: "https://www.youtube.com/playlist?list=PLabcdefghij",
  kind: "playlist",
  playlistId: "PLabcdefghij",
}
const invalid: ResolveItem = {
  input: "https://example.com/x",
  kind: "invalid",
  error: { code: "E_INVALID_INPUT", message: "ลิงก์นี้ไม่ใช่ยูทูป" },
}

const settings = {
  videoDefault: "compat-720",
  audioDefault: "mp3",
  mp3Kbps: 192,
  audioLanguage: "original",
  concurrency: 2,
} as Settings

describe("clipRows", () => {
  it("เอาคลิปกับลิงก์กำกวม ไม่ซ้ำรหัส ตามลำดับที่เจอครั้งแรก", () => {
    const { rows } = clipRows([video("aaaaaaaaaaa"), ambiguous("bbbbbbbbbbb"), video("aaaaaaaaaaa"), video("ccccccccccc")], () => undefined)
    expect(rows.map((r) => r.videoId)).toEqual(["aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"])
  })

  it("ลิงก์อ่านไม่ออกเป็นแถวแดงที่ตำแหน่งเดิม และไม่นับซ้ำ", () => {
    const { rows } = clipRows([video("aaaaaaaaaaa"), invalid, video("bbbbbbbbbbb")], () => undefined)
    expect(rows).toEqual([
      { videoId: "aaaaaaaaaaa" },
      { videoId: "", invalid: { input: "https://example.com/x" } },
      { videoId: "bbbbbbbbbbb" },
    ])
  })

  it("แถวเพลย์ลิสต์ไม่เข้าตาราง แต่บอกว่ามี (hasPlaylists)", () => {
    const withPlaylist = clipRows([video("aaaaaaaaaaa"), playlist], () => undefined)
    expect(withPlaylist.rows).toHaveLength(1)
    expect(withPlaylist.hasPlaylists).toBe(true)
    expect(clipRows([video("aaaaaaaaaaa")], () => undefined).hasPlaylists).toBe(false)
  })

  it("แถวเพลย์ลิสต์ที่ไม่มีรหัสเพลย์ลิสต์ = แถวแดงเหมือนที่ W1", () => {
    const { rows, hasPlaylists } = clipRows([{ input: "x", kind: "playlist" }], () => undefined)
    expect(rows).toEqual([{ videoId: "", invalid: { input: "x" } }])
    expect(hasPlaylists).toBe(false)
  })

  it("ชื่อและความยาวมาจาก cache (infoOf) · ไม่รู้ = ไม่มีคีย์", () => {
    const { rows } = clipRows([video("aaaaaaaaaaa"), video("bbbbbbbbbbb")], (id) =>
      id === "aaaaaaaaaaa" ? { title: "ชื่อคลิป", durationS: 90 } : undefined
    )
    expect(rows[0]).toEqual({ videoId: "aaaaaaaaaaa", title: "ชื่อคลิป", durationS: 90 })
    expect(rows[1]).toEqual({ videoId: "bbbbbbbbbbb" })
    expect("title" in rows[1]).toBe(false)
    expect("durationS" in rows[1]).toBe(false)
  })

  it("คลิปไม่เกิน 200 แถว (วาง 260 ลิงก์) · แถวลิงก์เสียยังแสดงครบ", () => {
    const many = Array.from({ length: 260 }, (_, i) => video(`vid${String(i).padStart(8, "0")}`))
    const { rows } = clipRows([...many, invalid], () => undefined)
    expect(rows.filter((r) => !r.invalid)).toHaveLength(MAX_BATCH_ROWS)
    expect(rows.filter((r) => r.invalid)).toHaveLength(1)
    expect(rows[0].videoId).toBe("vid00000000")
  })
})

describe("playlistRows", () => {
  const entry = (videoId: string, title = "ชื่อ", durationS?: number): PlaylistEntry => ({
    videoId,
    title,
    thumbnailUrl: "",
    ...(durationS === undefined ? {} : { durationS }),
  })

  it("ชื่อ ความยาว มาจากข้อมูลเพลย์ลิสต์ · ชื่อว่าง = ไม่รู้ชื่อ · ไม่ซ้ำรหัส", () => {
    const rows = playlistRows([entry("aaaaaaaaaaa", "หนึ่ง", 61), entry("bbbbbbbbbbb", ""), entry("aaaaaaaaaaa", "ซ้ำ")])
    expect(rows).toEqual([{ videoId: "aaaaaaaaaaa", title: "หนึ่ง", durationS: 61 }, { videoId: "bbbbbbbbbbb" }])
  })

  it("ไม่เกิน 200 แถว", () => {
    const many = Array.from({ length: 250 }, (_, i) => entry(`vid${String(i).padStart(8, "0")}`))
    expect(playlistRows(many)).toHaveLength(MAX_BATCH_ROWS)
  })
})

describe("parseBatchSource / batchPath / isExpired", () => {
  it("อ่าน src, playlist และ v (มิกซ์)", () => {
    expect(parseBatchSource(new URLSearchParams("src=abc"))).toEqual({ src: "abc" })
    expect(parseBatchSource(new URLSearchParams("src=abc&playlist=PLabcdefghij"))).toEqual({
      src: "abc",
      playlist: { id: "PLabcdefghij" },
    })
    expect(parseBatchSource(new URLSearchParams("src=abc&playlist=RDaqz-KE-bpKQ&v=aqz-KE-bpKQ"))).toEqual({
      src: "abc",
      playlist: { id: "RDaqz-KE-bpKQ", v: "aqz-KE-bpKQ" },
    })
  })

  it("ไม่มี src หรือรหัสผิดกฎ = null", () => {
    expect(parseBatchSource(new URLSearchParams(""))).toBeNull()
    expect(parseBatchSource(new URLSearchParams("src=abc&playlist=short"))).toBeNull()
    expect(parseBatchSource(new URLSearchParams("src=abc&playlist=PLabcdefghij&v=bad"))).toBeNull()
  })

  it("batchPath เขียนกลับเป็นที่อยู่ที่อ่านได้เหมือนเดิม", () => {
    expect(batchPath("abc")).toBe("/batch?src=abc")
    const path = batchPath("abc", { id: "RDaqz-KE-bpKQ", v: "aqz-KE-bpKQ" })
    expect(path).toBe("/batch?src=abc&playlist=RDaqz-KE-bpKQ&v=aqz-KE-bpKQ")
    expect(parseBatchSource(new URL(path, "http://x").searchParams)).toEqual({
      src: "abc",
      playlist: { id: "RDaqz-KE-bpKQ", v: "aqz-KE-bpKQ" },
    })
  })

  it("src ไม่ตรงกับ listId ที่เก็บไว้ หรือไม่มีรายการ = หมดอายุ", () => {
    const items = [video("aaaaaaaaaaa")]
    expect(isExpired({ src: "abc" }, "abc", items)).toBe(false)
    expect(isExpired({ src: "abc" }, "xyz", items)).toBe(true)
    expect(isExpired({ src: "abc" }, "", items)).toBe(true)
    expect(isExpired({ src: "abc" }, "abc", null)).toBe(true)
    expect(isExpired(null, "abc", items)).toBe(true)
  })
})

describe("การเลือก", () => {
  const rows = clipRows([video("aaaaaaaaaaa"), invalid, video("bbbbbbbbbbb"), video("ccccccccccc")], () => undefined).rows

  it("ค่าเริ่มต้นเลือกทุกคลิป ไม่รวมแถวแดง · เอาออกแล้วลำดับยังตามตาราง", () => {
    expect(selectedRows(rows, new Set()).map((r) => r.videoId)).toEqual(["aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"])
    expect(selectedRows(rows, new Set(["bbbbbbbbbbb"])).map((r) => r.videoId)).toEqual(["aaaaaaaaaaa", "ccccccccccc"])
  })

  it("ช่องเลือกทั้งหมด: ครบ / บางส่วน / ไม่มี", () => {
    expect(headerState(3, 3)).toBe("all")
    expect(headerState(3, 1)).toBe("some")
    expect(headerState(3, 0)).toBe("none")
    expect(headerState(0, 0)).toBe("none")
  })

  it("ส่งเข้าคิวได้เมื่อมีคลิปและเลือกอย่างน้อยหนึ่งอย่าง", () => {
    expect(canSubmit(2, { what: "video", sub: "none" })).toBe(true)
    expect(canSubmit(2, { what: "none", sub: "srt" })).toBe(true)
    expect(canSubmit(0, { what: "video", sub: "srt" })).toBe(false)
    expect(canSubmit(2, { what: "none", sub: "none" })).toBe(false)
  })
})

describe("buildBatchJobs", () => {
  const clips = [{ videoId: "aaaaaaaaaaa", title: "คลิป A" }, { videoId: "bbbbbbbbbbb" }]
  const options = PRESETS.long

  it("เสียง + .srt = งานเสียงตามด้วยงานซับ ทีละคลิป · ซับไม่ระบุแทร็ก", () => {
    const jobs = buildBatchJobs(clips, { what: "audio", sub: "srt" }, settings, options)
    expect(jobs.map((j) => `${j.videoId}:${j.kind}`)).toEqual([
      "aaaaaaaaaaa:audio",
      "aaaaaaaaaaa:subtitle",
      "bbbbbbbbbbb:audio",
      "bbbbbbbbbbb:subtitle",
    ])
    expect(jobs[0].params).toEqual({ format: "mp3", mp3Kbps: 192, splitChapters: false, audioLanguage: "original" })
    expect(jobs[1].params).toEqual({ format: "srt", options })
    expect("trackId" in jobs[1].params).toBe(false)
  })

  it("ชื่อที่รู้ส่งไปด้วย ที่ไม่รู้ไม่มีคีย์ title", () => {
    const jobs = buildBatchJobs(clips, { what: "video", sub: "none" }, settings, options)
    expect(jobs[0].title).toBe("คลิป A")
    expect("title" in jobs[1]).toBe(false)
  })

  it("วิดีโอใช้ค่าจากการตั้งค่า (compat-720 = maxHeight 720)", () => {
    const [job] = buildBatchJobs(clips, { what: "video", sub: "none" }, settings, options)
    expect(job.kind).toBe("video")
    expect(job.params).toMatchObject({ maxQuality: false, maxHeight: 720, noAudio: false })
  })

  it("ซับอย่างเดียว = งานซับอย่างเดียว · ไม่เอาทั้งคู่ = ไม่มีงาน", () => {
    expect(buildBatchJobs(clips, { what: "none", sub: "md" }, settings, options).map((j) => j.kind)).toEqual(["subtitle", "subtitle"])
    expect(buildBatchJobs(clips, { what: "none", sub: "none" }, settings, options)).toEqual([])
  })

  it("200 คลิป x 2 งาน ไม่เกินขีด 500 งานต่อคำขอ", () => {
    const many = Array.from({ length: 200 }, (_, i) => ({ videoId: `vid${String(i).padStart(8, "0")}` }))
    expect(buildBatchJobs(many, { what: "video", sub: "srt" }, settings, options)).toHaveLength(400)
  })
})
