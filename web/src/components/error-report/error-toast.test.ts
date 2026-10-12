import type { ReactElement, ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const toast = vi.hoisted(() => ({ error: vi.fn(() => "t1"), success: vi.fn() }))
vi.mock("sonner", () => ({ toast }))

import { CopyReportButton } from "./copy-report-button"
import { showErrorToast } from "./error-toast"

type Options = { id?: string; duration?: number; action?: unknown; cancel?: unknown; description: ReactElement<{ children: ReactNode[] }> }

beforeEach(() => toast.error.mockClear())

describe("showErrorToast", () => {
  it("ข้อความเดิม ค้างจนกดปิด id คงที่ ปุ่มคัดลอกอยู่ในแถว description (ไม่ใช่ action)", () => {
    const action = { label: "ไปหน้าตรวจสุขภาพ", onClick: () => {} }
    const request = { code: "E_FFMPEG_MISSING", context: "enqueue" }
    expect(showErrorToast("ยังไม่มีโปรแกรมแปลงไฟล์", { request, id: "enqueue-error", action })).toBe("t1")
    const [message, options] = toast.error.mock.lastCall as unknown as [string, Options]
    expect(message).toBe("ยังไม่มีโปรแกรมแปลงไฟล์")
    expect(options.id).toBe("enqueue-error")
    expect(options.duration).toBe(Infinity)
    expect(options.action).toBe(action)
    expect(options.cancel).toBeUndefined()
    const [extra, button] = options.description.props.children as [ReactNode, ReactElement<{ request: unknown }>]
    expect(extra).toBeUndefined()
    expect(button.type).toBe(CopyReportButton)
    expect(button.props.request).toBe(request)
  })

  it("description เดิม (ข้อความ error ของงาน) อยู่ก่อนปุ่ม", () => {
    showErrorToast("โหลดไม่สำเร็จ · คลิป", { request: { jobId: "j1" }, id: "job-j1", description: "เน็ตหลุด ลองใหม่อีกครั้ง" })
    const [, options] = toast.error.mock.lastCall as unknown as [string, Options]
    expect(options.description.props.children[0]).toBe("เน็ตหลุด ลองใหม่อีกครั้ง")
  })
})
