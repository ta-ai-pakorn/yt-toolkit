import { useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { toast } from "sonner"

import { fill, th } from "@/i18n/th"
import { QUEUE_KEY, queueQuery } from "@/lib/jobs"
import type { Capture, VideoInfo } from "@/lib/types"

import { errorMessage, hasCode } from "../errors"
import { capturesKey, postCapture, withCapture } from "./capture-api"
import { captureBlock, captureClock, captureTimeMs, type CaptureBlock } from "./capture-model"
import { captureStore, useCaptureUi } from "./capture-store"

/** คลิปสดไหม: อ่านจากข้อมูลคลิปที่หน้า W2 โหลดไว้แล้ว (["video", id]) ไม่ยิงคำขอเพิ่ม */
function cachedIsLive(client: QueryClient, videoId: string): boolean {
  return client.getQueryData<VideoInfo>(["video", videoId])?.isLive === true
}

/**
 * ถ่ายภาพคมหนึ่งภาพ (ทุกทางเข้าใช้ตัวนี้ spec 2.2): ถ่ายได้ครั้งละภาพทั้งแอพ (มีค้างอยู่ = ไม่ทำอะไร)
 * สำเร็จ = เติมลงแถบ (เวลาเดิม = แทนที่) + กระพริบ + toast "ถ่ายภาพคมแล้ว · {time}" มีปุ่ม "ดูภาพ"
 * พลาด = toast ข้อความจาก backend · ยูทูปขอตรวจสอบ/คิวพัก = โหลดสถานะคิวใหม่ ทุกปุ่มจะปิดพร้อมเหตุผล
 */
export async function runCapture(client: QueryClient, videoId: string, ms: number): Promise<void> {
  if (!captureStore.tryBegin()) return
  try {
    const capture = await postCapture(videoId, captureTimeMs(ms))
    client.setQueryData<Capture[]>(capturesKey(videoId), (list) => withCapture(list, capture))
    captureStore.flash({ videoId, id: capture.id })
    toast.success(fill(th.capture.done, { time: captureClock(capture.tMs) }), {
      action: { label: th.capture.view, onClick: () => captureStore.view({ videoId, id: capture.id }) },
    })
  } catch (error) {
    toast.error(errorMessage(error, th.errors.unknown))
    if (hasCode(error, "E_BOT_CHECK") || hasCode(error, "E_QUEUE_PAUSED")) {
      void client.invalidateQueries({ queryKey: QUEUE_KEY })
    }
  } finally {
    captureStore.end()
  }
}

/** เวลาปัจจุบันที่เดินทุกวินาทีเฉพาะตอน active (ปุ่มกลับมากดได้เองเมื่อคิวครบเวลาพัก) */
function useNowWhile(active: boolean): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [active])
  return now
}

/** สถานะของปุ่มถ่ายภาพ: กำลังถ่าย (ทั้งแอพ) · เหตุที่ถ่ายไม่ได้ · capture(ms) = ถ่ายที่เวลานั้น (กดไม่ได้อยู่ = ไม่ทำอะไร) */
export function useCapture(videoId: string): { busy: boolean; block: CaptureBlock; capture: (ms: number) => void } {
  const client = useQueryClient()
  const busy = useCaptureUi((s) => s.busy)
  const queue = useQuery(queueQuery())
  const pausedUntil = queue.data?.pausedUntil ?? null
  const now = useNowWhile(pausedUntil !== null)
  const block = captureBlock({ isLive: cachedIsLive(client, videoId), pausedUntil, now })
  const capture = (ms: number) => {
    if (busy || block !== null) return
    void runCapture(client, videoId, ms)
  }
  return { busy, block, capture }
}
