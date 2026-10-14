import { describe, expect, it, vi } from "vitest"

import { readClipboard } from "./paste-button"

const reader = (readText: () => Promise<string>) => ({ clipboard: { readText: vi.fn(readText) } })

describe("readClipboard (ปุ่ม วาง)", () => {
  it("ลิงก์ยูทูป = analyze พร้อมข้อความเดิมไม่ตัดช่องว่าง", async () => {
    await expect(readClipboard(reader(async () => "  https://youtu.be/aqz-KE-bpKQ\n"))).resolves.toEqual({
      kind: "analyze",
      text: "  https://youtu.be/aqz-KE-bpKQ\n",
    })
    await expect(readClipboard(reader(async () => "ดูคลิปนี้ youtu.be/aqz-KE-bpKQ นะ"))).resolves.toMatchObject({
      kind: "analyze",
    })
  })

  it("ข้อความอื่น = fill", async () => {
    await expect(readClipboard(reader(async () => "สูตรแกงเขียวหวาน"))).resolves.toEqual({
      kind: "fill",
      text: "สูตรแกงเขียวหวาน",
    })
  })

  it("ว่างหรือมีแต่ช่องว่าง (เช่นคัดลอกรูปภาพ) = empty", async () => {
    await expect(readClipboard(reader(async () => ""))).resolves.toEqual({ kind: "empty" })
    await expect(readClipboard(reader(async () => " \n\t"))).resolves.toEqual({ kind: "empty" })
  })

  it("ผู้ใช้ไม่อนุญาต (NotAllowedError) หรือ NotFoundError = denied ไม่โยนต่อ", async () => {
    const refuse = async () => {
      throw new DOMException("Read permission denied.", "NotAllowedError")
    }
    await expect(readClipboard(reader(refuse))).resolves.toEqual({ kind: "denied" })
    const missing = async () => {
      throw new DOMException("No valid data on clipboard.", "NotFoundError")
    }
    await expect(readClipboard(reader(missing))).resolves.toEqual({ kind: "denied" })
  })

  it("readText โยนแบบ sync = denied", async () => {
    const clipboard = {
      readText: () => {
        throw new TypeError("Illegal invocation")
      },
    }
    await expect(readClipboard({ clipboard })).resolves.toEqual({ kind: "denied" })
  })

  it("ไม่มีคลิปบอร์ด หรือไม่มี readText = denied", async () => {
    await expect(readClipboard({ clipboard: undefined })).resolves.toEqual({ kind: "denied" })
    await expect(readClipboard({ clipboard: {} as Pick<Clipboard, "readText"> })).resolves.toEqual({ kind: "denied" })
  })

  it("ไม่ส่ง deps = ใช้ navigator.clipboard (ใน node ไม่มี = denied)", async () => {
    vi.stubGlobal("navigator", { clipboard: { readText: async () => "youtu.be/aqz-KE-bpKQ" } })
    try {
      await expect(readClipboard()).resolves.toEqual({ kind: "analyze", text: "youtu.be/aqz-KE-bpKQ" })
      vi.stubGlobal("navigator", {})
      await expect(readClipboard()).resolves.toEqual({ kind: "denied" })
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it("อ่านคลิปบอร์ดครั้งเดียวต่อการกด", async () => {
    const deps = reader(async () => "x")
    await readClipboard(deps)
    expect(deps.clipboard.readText).toHaveBeenCalledTimes(1)
  })
})
