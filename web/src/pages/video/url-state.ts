import { useCallback } from "react"
import { useLocation, useNavigate, useSearchParams } from "react-router"

export type VideoTab = "frames" | "subs" | "transcript"

export type VideoParams = { tab: VideoTab; trackId: string | null; at: number | null }

export type VideoParamsPatch = { tab?: VideoTab; trackId?: string | null; at?: number | null }

const TABS: readonly VideoTab[] = ["frames", "subs", "transcript"]
const DEFAULT_TAB: VideoTab = "frames"
// รูปแบบรหัสแทร็กตามสัญญา C1 (o./a./t. นำหน้า)
const TRACK_ID = /^[oat]\.[A-Za-z0-9_-]{1,64}$/
const DIGITS = /^\d+$/

function validTab(value: string | null): VideoTab {
  return TABS.find((t) => t === value) ?? DEFAULT_TAB
}

function validTrack(value: string | null | undefined): string | null {
  return value != null && TRACK_ID.test(value) ? value : null
}

function validAt(value: number | string | null | undefined): number | null {
  if (typeof value === "string") {
    if (!DIGITS.test(value)) return null
    value = Number(value)
  }
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null
}

/** อ่านสถานะของหน้า W2 จาก URL ค่าที่ผิดรูปถูกมองเป็น "ไม่มี" (tab เริ่มที่ภาพเฟรม) */
export function readVideoParams(search: URLSearchParams): VideoParams {
  return {
    tab: validTab(search.get("tab")),
    trackId: validTrack(search.get("track")),
    at: validAt(search.get("at")),
  }
}

/**
 * คืนสตริง query ใหม่ ("?tab=…&track=…&at=…" หรือ "" เมื่อไม่เหลืออะไร) หลังใส่ patch
 * พารามิเตอร์อื่นที่ไม่เกี่ยวข้องถูกเก็บไว้ ค่าเริ่มต้น (tab=frames) ไม่ขึ้นใน URL และ null = ลบคีย์นั้น
 */
export function patchSearch(search: URLSearchParams, patch: VideoParamsPatch): string {
  const current = readVideoParams(search)
  const tab = patch.tab ?? current.tab
  const trackId = "trackId" in patch ? validTrack(patch.trackId) : current.trackId
  const at = "at" in patch ? validAt(patch.at) : current.at

  const next = new URLSearchParams()
  if (tab !== DEFAULT_TAB) next.set("tab", tab)
  if (trackId !== null) next.set("track", trackId)
  if (at !== null) next.set("at", String(at))
  for (const [key, value] of search) {
    if (key !== "tab" && key !== "track" && key !== "at") next.append(key, value)
  }
  const text = next.toString()
  return text === "" ? "" : `?${text}`
}

/**
 * สถานะของหน้าคลิป (แท็บ แทร็กซับ เวลา) ที่เก็บใน URL: update ใช้ replace เสมอ
 * ปุ่มย้อนกลับจากหน้าคลิปจึงกลับหน้า W1 ในก้าวเดียว ไม่ไล่ย้อนทีละแท็บ (กติกา breadcrumb ของ M2)
 */
export function useVideoParams() {
  const [search] = useSearchParams()
  const navigate = useNavigate()
  const location = useLocation()
  const params = readVideoParams(search)

  const update = useCallback(
    (patch: VideoParamsPatch) => {
      navigate(
        { search: patchSearch(search, patch) },
        { replace: true, preventScrollReset: true, state: location.state },
      )
    },
    [navigate, search, location.state],
  )

  return { ...params, update }
}
