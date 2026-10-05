import { queryOptions } from "@tanstack/react-query"

import { api, ApiError } from "@/lib/api"
import { sharpKey } from "@/lib/sharp-frames"
import type { PinnedCommentResult, SharpSet, Storyboard, VideoInfo } from "@/lib/types"

import { canRetry } from "./errors"

/**
 * ข้อมูลคลิปของหน้า W2: key ["video", id] ซึ่งรายการผลของ W1 เติมข้อมูลให้ (จากคำขอ peek) แต่หน้านี้ไม่ใส่ `peek=1`
 * จึงนับว่าเปิดคลิปจริงและขึ้นใน "ล่าสุด" (refetchOnMount: always = เปิดหน้านี้ทีไรก็ยิงหนึ่งครั้งแม้มี cache)
 */
export function videoQuery(videoId: string) {
  return queryOptions({
    queryKey: ["video", videoId],
    queryFn: ({ signal }) => api<VideoInfo>(`/videos/${videoId}`, { signal }),
    // มีข้อมูลเติมมาจาก peek ของ W1 ก็แสดงได้ทันที แต่ต้องยิงคำขอปกติหนึ่งครั้งเสมอ เพื่อนับว่าเปิดคลิปจริง
    refetchOnMount: "always",
    // error ของยูทูป (ส่วนตัว/ไลฟ์/ถูกลบ) ลองซ้ำเองไม่หาย ให้ผู้ใช้กด "ลองใหม่" เอง
    retry: false,
  })
}

/**
 * คอมเมนต์ปักหมุดจากเจ้าของช่อง (สัญญา C-A2): ยิงเมื่อผู้ใช้กางแถวนี้เท่านั้น (enabled) ไม่ยิงตอนเปิดหน้า
 * backend เก็บผลไว้ 24 ชั่วโมง จึงเก็บไว้ตลอดหน้า · error ที่ลองใหม่ไม่ช่วย (E_BOT_CHECK) ไม่ยิงซ้ำเมื่อกางใหม่หรือเน็ตกลับมา
 */
export function pinnedCommentQuery(videoId: string, enabled: boolean) {
  return queryOptions({
    queryKey: ["pinned-comment", videoId],
    queryFn: ({ signal }) => api<PinnedCommentResult>(`/videos/${videoId}/pinned-comment`, { signal }),
    enabled,
    retry: false,
    retryOnMount: (query) => canRetry(query.state.error),
    refetchOnReconnect: (query) => canRetry(query.state.error),
    staleTime: Infinity,
  })
}

export function storyboardQuery(videoId: string, enabled: boolean) {
  return queryOptions({
    queryKey: ["storyboard", videoId],
    queryFn: ({ signal }) => api<Storyboard>(`/videos/${videoId}/storyboard`, { signal }),
    enabled,
    retry: false,
    // URL ภาพมีตัวเลขเวอร์ชัน (?v=) อยู่แล้ว เก็บผลไว้สั้น ๆ พอ ไม่ต้องยิงใหม่ทุกครั้งที่สลับหน้า
    staleTime: 60_000,
  })
}

/**
 * ชุดภาพคมของคลิป (M5 รอบ B): 404 = ยังไม่มีชุด คืน null (ไม่ใช่ error) · ข่าว SSE ของงานภาพคม/วิดีโอที่เสร็จสั่งโหลดใหม่
 * URL ภาพมี ?v= อยู่แล้ว เก็บผลไว้สั้น ๆ เหมือน storyboard
 */
export function sharpQuery(videoId: string, enabled: boolean) {
  return queryOptions({
    queryKey: sharpKey(videoId),
    queryFn: async ({ signal }): Promise<SharpSet | null> => {
      try {
        return await api<SharpSet>(`/videos/${videoId}/sharp`, { signal })
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null
        throw error
      }
    },
    enabled,
    retry: false,
    staleTime: 60_000,
  })
}
