import { describe, expect, it, vi } from "vitest"

import { importWithReload, isChunkLoadError } from "./lazy-import"

function memoryStorage(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial))
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
    removeItem: (key: string) => void data.delete(key),
  }
}

const pending = (promise: Promise<unknown>) =>
  Promise.race([promise.then(() => "settled"), new Promise((resolve) => setTimeout(() => resolve("pending"), 20))])

describe("importWithReload", () => {
  it("โหลดสำเร็จ: คืนโมดูล และล้างธงเก่า", async () => {
    const storage = memoryStorage({ "chunk-reloaded": "1" })
    const reload = vi.fn()
    const module = await importWithReload(() => Promise.resolve({ ok: 1 }), { storage, reload })
    expect(module).toEqual({ ok: 1 })
    expect(storage.getItem("chunk-reloaded")).toBeNull()
    expect(reload).not.toHaveBeenCalled()
  })

  it("พังครั้งแรก: ตั้งธง สั่งโหลดหน้าใหม่ครั้งเดียว และไม่โยน error (รอจนหน้าเปลี่ยน)", async () => {
    const storage = memoryStorage()
    const reload = vi.fn()
    const result = importWithReload(() => Promise.reject(new Error("404")), { storage, reload })
    expect(await pending(result)).toBe("pending")
    expect(reload).toHaveBeenCalledTimes(1)
    expect(storage.getItem("chunk-reloaded")).toBe("1")
  })

  it("พังซ้ำหลังโหลดใหม่แล้ว: โยน error ให้หน้า error แสดง ไม่วนโหลดอีก", async () => {
    const storage = memoryStorage({ "chunk-reloaded": "1" })
    const reload = vi.fn()
    await expect(importWithReload(() => Promise.reject(new Error("404")), { storage, reload })).rejects.toThrow("404")
    expect(reload).not.toHaveBeenCalled()
  })

  it("เก็บธงไม่ได้ (เช่นโหมดส่วนตัว): ไม่กล้าโหลดใหม่เพราะกันวนไม่ได้ โยน error ทันที", async () => {
    const storage = {
      getItem: () => {
        throw new Error("blocked")
      },
      setItem: () => {
        throw new Error("blocked")
      },
      removeItem: () => {
        throw new Error("blocked")
      },
    }
    const reload = vi.fn()
    await expect(importWithReload(() => Promise.reject(new Error("404")), { storage, reload })).rejects.toThrow("404")
    expect(reload).not.toHaveBeenCalled()
  })
})

describe("isChunkLoadError", () => {
  it.each([
    "Failed to fetch dynamically imported module: http://x/assets/video-abc.js",
    "error loading dynamically imported module",
    "Importing a module script failed.",
  ])("รู้จัก %j", (message) => {
    expect(isChunkLoadError(new TypeError(message))).toBe(true)
  })

  it("error อื่นไม่ใช่", () => {
    expect(isChunkLoadError(new Error("Cannot read properties of undefined"))).toBe(false)
    expect(isChunkLoadError("string")).toBe(false)
    expect(isChunkLoadError(null)).toBe(false)
  })
})
