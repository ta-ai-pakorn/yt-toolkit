import { describe, expect, it } from "vitest"

import { createLimiter } from "./limiter"

function deferred<T = void>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

const tick = () => new Promise((resolve) => setTimeout(resolve, 0))

describe("createLimiter", () => {
  it("รันพร้อมกันไม่เกินจำนวนที่กำหนด ที่เหลือรอคิวตามลำดับ", async () => {
    const limit = createLimiter(3)
    const gates = Array.from({ length: 6 }, () => deferred())
    const started: number[] = []
    let running = 0
    let peak = 0
    const results = gates.map((gate, i) =>
      limit(async () => {
        started.push(i)
        running += 1
        peak = Math.max(peak, running)
        await gate.promise
        running -= 1
        return i
      }),
    )
    await tick()
    expect(started).toEqual([0, 1, 2])
    gates[0].resolve()
    await tick()
    expect(started).toEqual([0, 1, 2, 3])
    gates.slice(1).forEach((gate) => gate.resolve())
    expect(await Promise.all(results)).toEqual([0, 1, 2, 3, 4, 5])
    expect(peak).toBe(3)
  })

  it("งานที่ล้มเหลวคืนช่องให้งานถัดไป และส่ง error ต่อให้ผู้เรียก", async () => {
    const limit = createLimiter(1)
    const first = limit(() => Promise.reject(new Error("พัง")))
    const second = limit(() => Promise.resolve("ok"))
    await expect(first).rejects.toThrow("พัง")
    await expect(second).resolves.toBe("ok")
  })

  it("งานที่โยน error แบบ sync ก็คืนช่องและไม่ทำให้คิวค้าง", async () => {
    const limit = createLimiter(1)
    const first = limit(() => {
      throw new Error("พังทันที")
    })
    const second = limit(() => Promise.resolve(2))
    await expect(first).rejects.toThrow("พังทันที")
    await expect(second).resolves.toBe(2)
  })
})
