import { describe, expect, it } from "vitest"

import { fromListState, fromPlaylistState, isFromList, readFromList } from "./use-analyze"

describe("readFromList (state ของ router จากประวัติเบราว์เซอร์)", () => {
  it("มาจากรายการผลของ W1", () => {
    expect(readFromList({ fromList: true })).toEqual(fromListState)
  })

  it("มาจากรายชื่อที่กางใต้แถวเพลย์ลิสต์/มิกซ์", () => {
    expect(readFromList({ fromList: true, playlist: { id: "PLfakeplaylist250" } })).toEqual(
      fromPlaylistState("PLfakeplaylist250")
    )
    expect(readFromList({ fromList: true, playlist: { id: "RDaqz-KE-bpKQ", v: "aqz-KE-bpKQ" } })).toEqual(
      fromPlaylistState("RDaqz-KE-bpKQ", "aqz-KE-bpKQ")
    )
  })

  it.each([null, undefined, 1, "x", {}, { fromList: "true" }, { fromList: false }])("ไม่ได้มาจากรายการ: %j", (state) => {
    expect(readFromList(state)).toBeNull()
    expect(isFromList(state)).toBe(false)
  })

  it.each([
    { id: "short" },
    { id: "PL/../../api/shutdown" },
    { id: "PLfakeplaylist250?v=x" },
    { id: "P".repeat(65) },
    { id: 42 },
    { id: "RDaqz-KE-bpKQ", v: "not-an-id" },
    { id: "RDaqz-KE-bpKQ", v: 7 },
    "PLfakeplaylist250",
    null,
  ])("playlist ที่รหัสผิดกฎ = ไม่เชื่อ state ทั้งก้อน: %j", (playlist) => {
    expect(readFromList({ fromList: true, playlist })).toBeNull()
  })
})
