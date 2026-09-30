import { describe, expect, it, vi } from "vitest"

import type { ResolveItem } from "@/lib/types"

import { EMPTY_HOME, HOME_STORAGE_KEY, createHomeStore, parseHomeState } from "./state"

class MemoryStorage {
  data = new Map<string, string>()
  getItem(key: string) {
    return this.data.get(key) ?? null
  }
  setItem(key: string, value: string) {
    this.data.set(key, value)
  }
  removeItem(key: string) {
    this.data.delete(key)
  }
}

const clip: ResolveItem = { input: "https://youtu.be/aqz-KE-bpKQ", kind: "video", videoId: "aqz-KE-bpKQ" }
const mix: ResolveItem = {
  input: "https://www.youtube.com/watch?v=aqz-KE-bpKQ&list=RDaqz-KE-bpKQ",
  kind: "ambiguous",
  videoId: "aqz-KE-bpKQ",
  playlistId: "RDaqz-KE-bpKQ",
  isMix: true,
}
const bad: ResolveItem = {
  input: "ไม่ใช่ลิงก์",
  kind: "invalid",
  error: { code: "E_INVALID_INPUT", message: "ลิงก์นี้ไม่ใช่ลิงก์ยูทูป" },
}

describe("parseHomeState", () => {
  it("อ่านสถานะที่บันทึกไว้กลับมาครบ", () => {
    const state = { text: "a\nb", results: [clip, mix, bad], listId: "abc", opened: ["aqz-KE-bpKQ"] }
    expect(parseHomeState(JSON.stringify(state))).toEqual(state)
  })

  it.each([null, "", "{", "[]", "42", "null", '{"text": 5}'])("ข้อมูลว่างหรือเสีย (%s) ได้สถานะเริ่มต้น", (raw) => {
    expect(parseHomeState(raw)).toEqual(EMPTY_HOME)
  })

  it("ทิ้งแถวผลที่รูปร่างผิด แต่เก็บแถวที่ถูกไว้", () => {
    const raw = JSON.stringify({
      text: "x",
      results: [clip, { kind: "video" }, { input: "y", kind: "weird" }, "str", null, { ...clip, videoId: 7 }],
      listId: "l",
      opened: ["aqz-KE-bpKQ", 3, null],
    })
    const state = parseHomeState(raw)
    expect(state.results).toEqual([clip])
    expect(state.opened).toEqual(["aqz-KE-bpKQ"])
  })

  it("results ที่ไม่ใช่ array = ยังไม่ได้วิเคราะห์ (null)", () => {
    expect(parseHomeState(JSON.stringify({ text: "x", results: "nope" })).results).toBeNull()
    expect(parseHomeState(JSON.stringify({ text: "x", results: null })).results).toBeNull()
  })
})

describe("createHomeStore", () => {
  it("เริ่มจากสิ่งที่อยู่ใน sessionStorage (โหลดหน้าใหม่ในแท็บเดิม)", () => {
    const storage = new MemoryStorage()
    storage.setItem(HOME_STORAGE_KEY, JSON.stringify({ text: "เดิม", results: [clip], listId: "l1", opened: [] }))
    const store = createHomeStore(() => storage)
    expect(store.get().text).toBe("เดิม")
    expect(store.get().results).toEqual([clip])
  })

  it("set เขียนลง storage และแจ้งผู้ฟัง", () => {
    const storage = new MemoryStorage()
    const store = createHomeStore(() => storage)
    const listener = vi.fn()
    store.subscribe(listener)
    store.set({ text: "ลิงก์", results: [clip, bad], listId: "r1" })
    expect(listener).toHaveBeenCalledTimes(1)
    expect(parseHomeState(storage.getItem(HOME_STORAGE_KEY))).toMatchObject({ text: "ลิงก์", results: [clip, bad] })
  })

  it("markOpened จำคลิปที่เปิดแล้ว ไม่ซ้ำ และไม่แจ้งผู้ฟังถ้าไม่มีอะไรเปลี่ยน", () => {
    const store = createHomeStore(() => new MemoryStorage())
    const listener = vi.fn()
    store.subscribe(listener)
    store.markOpened("aqz-KE-bpKQ")
    store.markOpened("aqz-KE-bpKQ")
    expect(store.get().opened).toEqual(["aqz-KE-bpKQ"])
    expect(listener).toHaveBeenCalledTimes(1)
  })

  it("clear ล้างข้อความ ผล และคลิปที่เปิดแล้ว ทั้งในหน่วยความจำและใน storage", () => {
    const storage = new MemoryStorage()
    const store = createHomeStore(() => storage)
    store.set({ text: "x", results: [clip], listId: "r1" })
    store.markOpened("aqz-KE-bpKQ")
    store.clear()
    expect(store.get()).toEqual(EMPTY_HOME)
    expect(storage.getItem(HOME_STORAGE_KEY)).toBeNull()
  })

  it("storage ใช้ไม่ได้ (โยน error) ก็ยังจำในหน่วยความจำได้ ไม่ล้ม", () => {
    const store = createHomeStore(() => {
      throw new Error("SecurityError")
    })
    expect(store.get()).toEqual(EMPTY_HOME)
    store.set({ text: "ยังจำได้" })
    expect(store.get().text).toBe("ยังจำได้")
    expect(() => store.clear()).not.toThrow()
  })

  it("เขียน storage ไม่ได้ (เต็ม) ก็ยังจำในหน่วยความจำได้", () => {
    const storage = new MemoryStorage()
    storage.setItem = () => {
      throw new Error("QuotaExceededError")
    }
    const store = createHomeStore(() => storage)
    store.set({ text: "ยังจำได้" })
    expect(store.get().text).toBe("ยังจำได้")
  })

  it("ค่าที่ get คืนเป็นตัวเดิมจนกว่าจะเปลี่ยน (ใช้กับ useSyncExternalStore ได้)", () => {
    const store = createHomeStore(() => new MemoryStorage())
    const first = store.get()
    expect(store.get()).toBe(first)
    store.set({ text: "ใหม่" })
    expect(store.get()).not.toBe(first)
  })
})
