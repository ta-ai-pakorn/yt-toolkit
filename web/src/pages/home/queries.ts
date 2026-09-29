import { queryOptions } from "@tanstack/react-query"

import { api } from "@/lib/api"
import { createLimiter } from "@/lib/limiter"
import type { PlaylistInfo, VideoInfo } from "@/lib/types"

// รายการผลอาจยาวหลายสิบแถว: ขอข้อมูลจากยูทูปครั้งละไม่เกิน 3 คลิป และ 3 เพลย์ลิสต์ ที่เหลือรอคิว
const MAX_IN_FLIGHT = 3
const titleLimit = createLimiter(MAX_IN_FLIGHT)
const playlistLimit = createLimiter(MAX_IN_FLIGHT)

// แถวที่ถูกถอดออกจากจอ (กดวิเคราะห์ใหม่) ระหว่างรอคิว ไม่ต้องยิงคำขอที่ไม่มีใครดูแล้ว
function guarded<T>(signal: AbortSignal, task: () => Promise<T>): () => Promise<T> {
  return () => {
    signal.throwIfAborted()
    return task()
  }
}

/**
 * ชื่อคลิปสำหรับแถวในรายการผล W1: key เดียวกับหน้า W2 เพื่อให้เปิดต่อได้ทันทีจาก cache
 * `peek=1` = ขอแค่ข้อมูล ไม่นับว่าเปิดคลิป จึงไม่ดันคลิปเข้า "ล่าสุด"
 */
export function videoTitleQuery(videoId: string) {
  return queryOptions({
    queryKey: ["video", videoId],
    queryFn: ({ signal }) =>
      titleLimit(guarded(signal, () => api<VideoInfo>(`/videos/${videoId}?peek=1`, { signal }))),
    retry: false,
    staleTime: 60_000,
  })
}

export function playlistQuery(playlistId: string) {
  return queryOptions({
    queryKey: ["playlist", playlistId],
    queryFn: ({ signal }) =>
      playlistLimit(guarded(signal, () => api<PlaylistInfo>(`/playlists/${playlistId}`, { signal }))),
    // retry ปิด: ความผิดพลาดจากยูทูปมักไม่หายเอง ให้ผู้ใช้กด "ลองใหม่" เองจะเห็นผลเร็วกว่ารอลองซ้ำเบื้องหลัง
    retry: false,
    staleTime: 5 * 60_000,
  })
}

export const AUTO_TITLE_ROWS = 10
export const thumbnailUrl = (videoId: string) => `https://i.ytimg.com/vi/${videoId}/mqdefault.jpg`
