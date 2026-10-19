import { queryOptions } from "@tanstack/react-query"

import { api } from "@/lib/api"
import { createLimiter } from "@/lib/limiter"
import type { PlaylistInfo, VideoInfo } from "@/lib/types"

import type { BotStop } from "./bot-stop"

// รายการผลอาจยาวหลายสิบแถว: ขอข้อมูลจากยูทูปครั้งละไม่เกิน 3 คลิป และ 3 เพลย์ลิสต์ ที่เหลือรอคิว
const MAX_IN_FLIGHT = 3
const titleLimit = createLimiter(MAX_IN_FLIGHT)
const playlistLimit = createLimiter(MAX_IN_FLIGHT)

// แถวที่ถูกถอดออกจากจอ (กดวิเคราะห์ใหม่) ระหว่างรอคิว ไม่ต้องยิงคำขอที่ไม่มีใครดูแล้ว
// และถ้ารายการผลนี้ถูกเบรกเพราะ E_BOT_CHECK (ดู bot-stop.ts) คำขอที่ยังไม่เริ่มก็ไม่ออกไป
function guarded<T>(signal: AbortSignal, botStop: BotStop | undefined, task: () => Promise<T>): () => Promise<T> {
  return () => {
    signal.throwIfAborted()
    return botStop ? botStop.run(task) : task()
  }
}

/**
 * ชื่อคลิปสำหรับแถวในรายการผล W1 (`peek=1` = ขอแค่ข้อมูล ไม่นับว่าเปิดคลิป จึงไม่ดันคลิปเข้า "ล่าสุด")
 *
 * ใช้ key แยกของตัวเอง เพราะถ้าใช้ key เดียวกับหน้า W2 แล้วผู้ใช้กด "เปิดดู" ตอน peek ยังไม่เสร็จ
 * TanStack จะรวมคำขอ ทำให้ไม่มีคำขอปกติออกไปเลย และคลิปไม่เข้า "ล่าสุด"
 * สำเร็จแล้วเติมผลลง key ของ W2 (เฉพาะที่ยังว่าง) ให้ W2 มีข้อมูลโชว์ทันที แล้ว W2 ยิงคำขอปกติของตัวเองอีกครั้ง
 */
export function videoTitleQuery(videoId: string, botStop?: BotStop) {
  return queryOptions({
    queryKey: ["video", videoId, "peek"],
    queryFn: async ({ client, signal }) => {
      const info = await titleLimit(
        guarded(signal, botStop, () => api<VideoInfo>(`/videos/${videoId}?peek=1`, { signal })),
      )
      // ถูกยกเลิกแล้ว (แถวหลุดจากจอ เช่นกด "เปิดดู") ไม่เขียนลงข้อมูลคลิปของ W2: ผลนี้ไม่มีใครรับแล้ว
      signal.throwIfAborted()
      client.setQueryData<VideoInfo>(["video", videoId], (existing) => existing ?? info)
      return info
    },
    retry: false,
    staleTime: 60_000,
  })
}

/**
 * ข้อมูลเพลย์ลิสต์สำหรับแถวในรายการผล W1
 * มิกซ์อัตโนมัติ (id ขึ้นต้น RD) ต้องส่งคลิปตั้งต้น (`videoId`) ไปด้วย เพราะยูทูปให้ดึงมิกซ์จากลิงก์คลิปเท่านั้น
 */
export function playlistQuery(playlistId: string, botStop?: BotStop, videoId?: string) {
  const id = encodeURIComponent(playlistId)
  const path = videoId ? `/playlists/${id}?v=${encodeURIComponent(videoId)}` : `/playlists/${id}`
  return queryOptions({
    queryKey: videoId ? ["playlist", playlistId, videoId] : ["playlist", playlistId],
    queryFn: ({ signal }) => playlistLimit(guarded(signal, botStop, () => api<PlaylistInfo>(path, { signal }))),
    // retry ปิด: ความผิดพลาดจากยูทูปมักไม่หายเอง ให้ผู้ใช้กด "ลองใหม่" เองจะเห็นผลเร็วกว่ารอลองซ้ำเบื้องหลัง
    retry: false,
    staleTime: 5 * 60_000,
  })
}

export const AUTO_TITLE_ROWS = 10
export const thumbnailUrl = (videoId: string) => `https://i.ytimg.com/vi/${videoId}/mqdefault.jpg`
