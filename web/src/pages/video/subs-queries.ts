import { queryOptions } from "@tanstack/react-query"

import { api } from "@/lib/api"
import type { SubTokens, SubtitleTracks } from "@/lib/types"

import { canRetry } from "./errors"

/** รายการแทร็กซับของคลิป (คลิปไม่มีซับได้ { tracks: [] } ไม่ใช่ error) ยิงเมื่อ enabled เท่านั้น */
export function subtitlesQuery(videoId: string, enabled: boolean) {
  return queryOptions({
    queryKey: ["subtitles", videoId],
    queryFn: ({ signal }) => api<SubtitleTracks>(`/videos/${videoId}/subtitles`, { signal }),
    enabled,
    retry: false,
    staleTime: 60_000,
  })
}

/**
 * คำพร้อมเวลาของแทร็กหนึ่ง ยิงเมื่อมี trackId เท่านั้น
 * ผลของแทร็กเดิมไม่เปลี่ยนตามตัวเลือกความยาวซับ (ตัวเลือกใช้ตอนสร้างซับในเบราว์เซอร์) จึงเก็บไว้ตลอดหน้า
 * error ที่ลองใหม่ไม่ช่วย (เช่น E_TRANSLATION_BLOCKED, E_NO_SUBTITLES) ไม่ยิงซ้ำเมื่อสลับแท็บกลับมา (mount ใหม่)
 * หรือเน็ตกลับมา · เน็ตหลุดยังยิงใหม่ให้เองเหมือนเดิม
 */
export function tokensQuery(videoId: string, trackId: string | null | undefined) {
  return queryOptions({
    queryKey: ["subtokens", videoId, trackId ?? null],
    queryFn: ({ signal }) => api<SubTokens>(`/videos/${videoId}/subtitles/${trackId}/tokens`, { signal }),
    enabled: Boolean(trackId),
    retry: false,
    retryOnMount: (query) => canRetry(query.state.error),
    refetchOnReconnect: (query) => canRetry(query.state.error),
    staleTime: Infinity,
  })
}
