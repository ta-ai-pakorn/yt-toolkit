import { describe, expect, it } from "vitest"

import type { PlaylistEntry, ResolveItem, Settings } from "@/lib/types"
import { PRESETS } from "@/lib/sub-options"

import {
  batchPath,
  buildBatchJobs,
  canSubmit,
  clipRows,
  defaultFolder,
  folderStamp,
  folderValid,
  headerState,
  isExpired,
  MAX_BATCH_ROWS,
  parseBatchSource,
  playlistRows,
  selectedRows,
  type BatchChoice,
  type ExtraChoice,
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

const EXTRA_ALL: ExtraChoice[] = ["srt", "txt", "note", "contactSheet", "framesZip"]
const choice = (what: BatchChoice["what"], ...extras: ExtraChoice[]): BatchChoice => ({ what, extras: new Set(extras) })

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

  it("ส่งเข้าคิวได้เมื่อมีคลิป เลือกอย่างน้อยหนึ่งอย่าง และมีชื่อโฟลเดอร์", () => {
    expect(canSubmit(2, choice("video"), "งาน")).toBe(true)
    expect(canSubmit(2, choice("none", "srt"), "งาน")).toBe(true)
    expect(canSubmit(2, choice("none", "framesZip"), "งาน")).toBe(true)
    expect(canSubmit(0, choice("video", "srt"), "งาน")).toBe(false)
    expect(canSubmit(2, choice("none"), "งาน")).toBe(false)
  })

  it("ชื่อโฟลเดอร์ว่าง (หลังตัดช่องว่าง) หรือยาวเกิน 80 ตัวอักษร = ส่งไม่ได้", () => {
    expect(canSubmit(2, choice("video"), "")).toBe(false)
    expect(canSubmit(2, choice("video"), "   ")).toBe(false)
    expect(canSubmit(2, choice("video"), "ก".repeat(81))).toBe(false)
    expect(canSubmit(2, choice("video"), ` ${"ก".repeat(80)} `)).toBe(true)
  })
})

describe("ชื่อโฟลเดอร์", () => {
  // เวลาเครื่อง 2 ต.ค. 2026 09:05 (เดือนและนาทีหลักเดียวต้องเติม 0)
  const openedAt = new Date(2026, 9, 2, 9, 5, 42)

  it("เวลาท้ายชื่อเป็น YYYY-MM-DD HH.mm ตามเวลาเครื่อง (ไม่มี : ที่ Windows ห้ามใช้)", () => {
    expect(folderStamp(openedAt)).toBe("2026-10-02 09.05")
    expect(folderStamp(new Date(2026, 0, 31, 23, 59))).toBe("2026-01-31 23.59")
  })

  it("วางหลายลิงก์ = 'หลายคลิป <เวลาที่เปิดหน้า>'", () => {
    expect(defaultFolder(undefined, openedAt)).toBe("หลายคลิป 2026-10-02 09.05")
  })

  it("เพลย์ลิสต์ = ชื่อเพลย์ลิสต์ (ตัดช่องว่างหัวท้าย) · ไม่มีชื่อ = แบบหลายคลิป", () => {
    expect(defaultFolder("  รวมคลิปสอนทำอาหาร  ", openedAt)).toBe("รวมคลิปสอนทำอาหาร")
    expect(defaultFolder("", openedAt)).toBe("หลายคลิป 2026-10-02 09.05")
    expect(defaultFolder("   ", openedAt)).toBe("หลายคลิป 2026-10-02 09.05")
  })

  it("ชื่อเพลย์ลิสต์ยาวเกิน 80 ตัวอักษรตัดท้ายให้พอดี (นับแบบ backend ไม่ผ่าอีโมจิครึ่งตัว)", () => {
    const long = `${"😀".repeat(79)}ab`
    const folder = defaultFolder(long, openedAt)
    expect(Array.from(folder)).toHaveLength(80)
    expect(folder.endsWith("😀a")).toBe(true)
    expect(folderValid(folder)).toBe(true)
  })
})

describe("buildBatchJobs", () => {
  const clips = [{ videoId: "aaaaaaaaaaa", title: "คลิป A" }, { videoId: "bbbbbbbbbbb" }]
  const options = PRESETS.long
  const FOLDER = "รวมคลิป"

  it("เสียง + .srt = งานเสียงตามด้วยงานซับ ทีละคลิป · ซับไม่ระบุแทร็ก", () => {
    const jobs = buildBatchJobs(clips, choice("audio", "srt"), FOLDER, settings, options)
    expect(jobs.map((j) => `${j.videoId}:${j.kind}`)).toEqual([
      "aaaaaaaaaaa:audio",
      "aaaaaaaaaaa:subtitle",
      "bbbbbbbbbbb:audio",
      "bbbbbbbbbbb:subtitle",
    ])
    expect(jobs[0].params).toEqual({
      format: "mp3",
      mp3Kbps: 192,
      splitChapters: false,
      audioLanguage: "original",
      folder: FOLDER,
    })
    expect(jobs[1].params).toEqual({ format: "srt", options, folder: FOLDER })
    expect("trackId" in jobs[1].params).toBe(false)
  })

  it("ลำดับต่อคลิป: หลัก → .srt → .txt → โน้ต → ภาพรวมเฟรม → ภาพเฟรมทั้งหมด ไม่ขึ้นกับลำดับที่ติ๊ก", () => {
    const all = choice("video", "framesZip", "note", "txt", "contactSheet", "srt")
    const jobs = buildBatchJobs(clips, all, FOLDER, settings, options)
    const perClip = ["video", "subtitle:srt", "subtitle:txt", "note", "contact_sheet", "frames_zip"]
    const label = (j: (typeof jobs)[number]) =>
      j.kind === "subtitle" && "format" in j.params ? `subtitle:${String(j.params.format)}` : j.kind
    expect(jobs.map((j) => `${j.videoId}:${label(j)}`)).toEqual([
      ...perClip.map((k) => `aaaaaaaaaaa:${k}`),
      ...perClip.map((k) => `bbbbbbbbbbb:${k}`),
    ])
  })

  it("ไฟล์เพิ่มเติมแต่ละอย่างได้ค่าของงานที่ถูก (ซับใช้ความยาวซับปัจจุบัน ไม่ระบุแทร็ก · ภาพใช้ค่าเริ่มต้น)", () => {
    const jobs = buildBatchJobs([clips[1]], choice("none", ...EXTRA_ALL), FOLDER, settings, options)
    expect(jobs).toEqual([
      { videoId: "bbbbbbbbbbb", kind: "subtitle", params: { format: "srt", options, folder: FOLDER } },
      { videoId: "bbbbbbbbbbb", kind: "subtitle", params: { format: "txt", options, folder: FOLDER } },
      { videoId: "bbbbbbbbbbb", kind: "note", params: { folder: FOLDER } },
      { videoId: "bbbbbbbbbbb", kind: "contact_sheet", params: { source: "fast", columns: 5, folder: FOLDER } },
      { videoId: "bbbbbbbbbbb", kind: "frames_zip", params: { source: "fast", folder: FOLDER } },
    ])
  })

  it("ทุกงานมี folder เดียวกัน (ตัดช่องว่างหัวท้ายแล้ว)", () => {
    const jobs = buildBatchJobs(clips, choice("video", ...EXTRA_ALL), "  งานลูกค้า A  ", settings, options)
    expect(jobs).toHaveLength(12)
    for (const job of jobs) expect(job.params).toMatchObject({ folder: "งานลูกค้า A" })
  })

  it("ชื่อที่รู้ส่งไปด้วย ที่ไม่รู้ไม่มีคีย์ title", () => {
    const jobs = buildBatchJobs(clips, choice("video", "note"), FOLDER, settings, options)
    expect(jobs.map((j) => j.title)).toEqual(["คลิป A", "คลิป A", undefined, undefined])
    expect("title" in jobs[2]).toBe(false)
  })

  it("วิดีโอใช้ค่าจากการตั้งค่า (compat-720 = maxHeight 720)", () => {
    const [job] = buildBatchJobs(clips, choice("video"), FOLDER, settings, options)
    expect(job.kind).toBe("video")
    expect(job.params).toMatchObject({ maxQuality: false, maxHeight: 720, noAudio: false, folder: FOLDER })
  })

  it("ไฟล์เพิ่มเติมอย่างเดียว = ไม่มีงานหลัก · ไม่เลือกอะไรเลย = ไม่มีงาน", () => {
    expect(buildBatchJobs(clips, choice("none", "txt"), FOLDER, settings, options).map((j) => j.kind)).toEqual([
      "subtitle",
      "subtitle",
    ])
    expect(buildBatchJobs(clips, choice("none"), FOLDER, settings, options)).toEqual([])
  })

  it("200 คลิป x 6 งาน = 1200 งาน ไม่เกินขีดต่อคำขอของ backend", () => {
    const many = Array.from({ length: 200 }, (_, i) => ({ videoId: `vid${String(i).padStart(8, "0")}` }))
    expect(buildBatchJobs(many, choice("video", ...EXTRA_ALL), FOLDER, settings, options)).toHaveLength(1200)
  })
})
