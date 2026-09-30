import { describe, expect, it, vi } from "vitest"

import { copyImage, imageToPng } from "./clipboard"

class FakeItem {
  readonly items: Record<string, Promise<Blob> | Blob>
  constructor(items: Record<string, Promise<Blob> | Blob>) {
    this.items = items
  }
}

/** clipboard.write ปลอม: รับ ClipboardItem จริงตามชนิด แต่ในเทสคือ FakeItem */
const fakeWrite = (impl: (items: FakeItem[]) => Promise<void> = async () => {}) =>
  vi.fn((items: ClipboardItems) => impl(items as unknown as FakeItem[]))

const pngBlob = new Blob(["png"], { type: "image/png" })

describe("copyImage", () => {
  it("เขียนคลิปบอร์ดทันทีด้วย ClipboardItem ชนิด image/png ที่เป็น Promise (ยังอยู่ในจังหวะที่ผู้ใช้กด)", async () => {
    const write = fakeWrite()
    let resolvePng: (blob: Blob) => void = () => {}
    const toPng = vi.fn(() => new Promise<Blob>((resolve) => (resolvePng = resolve)))
    const done = copyImage("/api/cache/x/storyboard/f_0001.jpg?v=1", {
      clipboard: { write },
      ClipboardItem: FakeItem as unknown as typeof ClipboardItem,
      toPng,
    })
    // write ถูกเรียกก่อนภาพแปลงเสร็จ
    expect(write).toHaveBeenCalledTimes(1)
    expect(toPng).toHaveBeenCalledWith("/api/cache/x/storyboard/f_0001.jpg?v=1")
    const [[items]] = write.mock.calls
    expect(items).toHaveLength(1)
    const item = items[0] as unknown as FakeItem
    expect(Object.keys(item.items)).toEqual(["image/png"])
    expect(item.items["image/png"]).toBeInstanceOf(Promise)
    resolvePng(pngBlob)
    await expect(item.items["image/png"]).resolves.toBe(pngBlob)
    await expect(done).resolves.toBeUndefined()
  })

  it("เบราว์เซอร์ไม่มี clipboard.write หรือ ClipboardItem → ล้มทันที (ผู้เรียกแจ้งให้ใช้ โหลดภาพนี้ แทน)", async () => {
    const toPng = vi.fn(async () => pngBlob)
    await expect(copyImage("/x.jpg", { clipboard: undefined, ClipboardItem: FakeItem as never, toPng })).rejects.toThrow()
    await expect(
      copyImage("/x.jpg", { clipboard: { write: vi.fn() }, ClipboardItem: undefined, toPng }),
    ).rejects.toThrow()
    expect(toPng).not.toHaveBeenCalled()
  })

  it("เขียนไม่สำเร็จ (ถูกปฏิเสธ) → โยนต่อ", async () => {
    const write = vi.fn(async () => {
      throw new Error("NotAllowedError")
    })
    await expect(
      copyImage("/x.jpg", { clipboard: { write }, ClipboardItem: FakeItem as never, toPng: async () => pngBlob }),
    ).rejects.toThrow("NotAllowedError")
  })

  // vitest ทำให้ทั้งชุดล้มเองถ้ามี unhandled rejection หลุดออกมา
  it("แปลงภาพไม่สำเร็จ → write ล้มตาม และไม่มี unhandled rejection หลุดออกไป", async () => {
    const write = fakeWrite(async (items) => {
      await items[0].items["image/png"]
    })
    await expect(
      copyImage("/x.jpg", {
        clipboard: { write },
        ClipboardItem: FakeItem as never,
        toPng: async () => {
          throw new Error("decode")
        },
      }),
    ).rejects.toThrow("decode")
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
})

describe("imageToPng", () => {
  function canvasStub() {
    const drawImage = vi.fn()
    const toPng = vi.fn(async () => pngBlob)
    const makeCanvas = vi.fn((width: number, height: number) => ({ width, height, drawImage, toPng }))
    return { drawImage, toPng, makeCanvas }
  }

  it("โหลดภาพ ถอดเป็น bitmap วาดลง canvas ขนาดเดิม แล้วได้ PNG · ปิด bitmap ทุกครั้ง", async () => {
    const jpeg = new Blob(["jpeg"], { type: "image/jpeg" })
    const fetch = vi.fn(async () => new Response(jpeg, { status: 200 }))
    const bitmap = { width: 320, height: 180, close: vi.fn() }
    const createImageBitmap = vi.fn(async () => bitmap)
    const { drawImage, makeCanvas } = canvasStub()
    const result = await imageToPng("/api/cache/a/f.jpg", {
      fetch: fetch as unknown as typeof globalThis.fetch,
      createImageBitmap: createImageBitmap as never,
      makeCanvas,
    })
    expect(result).toBe(pngBlob)
    expect(fetch).toHaveBeenCalledWith("/api/cache/a/f.jpg")
    expect(makeCanvas).toHaveBeenCalledWith(320, 180)
    expect(drawImage).toHaveBeenCalledWith(bitmap)
    expect(bitmap.close).toHaveBeenCalled()
  })

  it("เซิร์ฟเวอร์ตอบ error → โยน และไม่ถอดภาพ", async () => {
    const fetch = vi.fn(async () => new Response("{}", { status: 404 }))
    const createImageBitmap = vi.fn()
    await expect(
      imageToPng("/x.jpg", {
        fetch: fetch as unknown as typeof globalThis.fetch,
        createImageBitmap: createImageBitmap as never,
        makeCanvas: canvasStub().makeCanvas,
      }),
    ).rejects.toThrow()
    expect(createImageBitmap).not.toHaveBeenCalled()
  })

  it("วาดไม่สำเร็จก็ยังปิด bitmap", async () => {
    const bitmap = { width: 2, height: 2, close: vi.fn() }
    await expect(
      imageToPng("/x.jpg", {
        fetch: (async () => new Response("x")) as unknown as typeof globalThis.fetch,
        createImageBitmap: (async () => bitmap) as never,
        makeCanvas: () => ({
          drawImage: () => {
            throw new Error("draw")
          },
          toPng: async () => pngBlob,
        }),
      }),
    ).rejects.toThrow("draw")
    expect(bitmap.close).toHaveBeenCalled()
  })
})
