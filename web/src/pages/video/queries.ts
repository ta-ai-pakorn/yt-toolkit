import { queryOptions } from "@tanstack/react-query"

import { api } from "@/lib/api"
import type { Storyboard, VideoInfo } from "@/lib/types"

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
