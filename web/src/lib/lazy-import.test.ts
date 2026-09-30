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

describe("importWithReload เมื่อแตะ sessionStorage ไม่ได้เลย", () => {
  // โหมดที่ปิดการเก็บข้อมูล: แค่อ่านชื่อ sessionStorage ก็โยน SecurityError
  function blockSessionStorage() {
    const original = Object.getOwnPropertyDescriptor(globalThis, "sessionStorage")
    Object.defineProperty(globalThis, "sessionStorage", {
      configurable: true,
      get() {
        throw new Error("SecurityError")
      },
    })
    return () => {
      if (original) Object.defineProperty(globalThis, "sessionStorage", original)
      else delete (globalThis as { sessionStorage?: unknown }).sessionStorage
    }
  }

  it("โหลดโค้ดสำเร็จก็ได้หน้าตามปกติ ไม่ล้ม", async () => {
    const restore = blockSessionStorage()
    try {
      await expect(importWithReload(async () => "หน้า")).resolves.toBe("หน้า")
    } finally {
      restore()
    }
  })

  it("โหลดโค้ดไม่สำเร็จ: ไม่โหลดใหม่ (กันวนไม่ได้) แต่โยน error เดิมให้หน้าแจ้งผู้ใช้", async () => {
    const restore = blockSessionStorage()
    const reload = vi.fn()
    try {
      await expect(importWithReload(() => Promise.reject(new Error("404")), { reload })).rejects.toThrow("404")
      expect(reload).not.toHaveBeenCalled()
    } finally {
      restore()
    }
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
