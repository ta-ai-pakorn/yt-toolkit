import { queryOptions } from "@tanstack/react-query"

import { api } from "@/lib/api"
import type { SubTokens, SubtitleTracks } from "@/lib/types"

import { canRetry } from "./errors"
import { isWarmingPending } from "./session-warming"

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
 * E_SESSION_WARMING (ซับแปลรอเซสชัน) ก็ไม่ยิงซ้ำตอนสลับแท็บ: useWarmingRefetch โหลดใหม่ให้เองเมื่อครบเวลา
 */
export function tokensQuery(videoId: string, trackId: string | null | undefined) {
  return queryOptions({
    queryKey: ["subtokens", videoId, trackId ?? null],
    queryFn: ({ signal }) => api<SubTokens>(`/videos/${videoId}/subtitles/${trackId}/tokens`, { signal }),
    // ระหว่างรอเซสชัน (E_SESSION_WARMING) observer ไม่ยิงเอง: เปลี่ยนแทร็กไปแล้วกลับมา (query เดิมที่ไม่มีข้อมูล
    // react-query ถือว่า stale และยิงใหม่ทันที แม้ retryOnMount จะปิด) ต้องไม่ยิงซ้ำ ให้ watchWarming โหลดเมื่อครบเวลา
    // ปิดเฉพาะก่อนถึง deadline: เลยแล้ว (error ค้างหลัง react-query ยกเลิกคำขอตอนครบเวลา) observer ต้องโหลดเองได้
    // ไม่งั้นค้าง "กำลังโหลด" ตลอด (I-2) · ถ้า watchWarming ยิงพร้อมกัน react-query รวมเป็นคำขอเดียว
    enabled: (query) => Boolean(trackId) && !isWarmingPending(query.state.error, query.state.errorUpdatedAt),
    retry: false,
    retryOnMount: (query) => canRetry(query.state.error) && !isWarmingPending(query.state.error, query.state.errorUpdatedAt),
    refetchOnReconnect: (query) => canRetry(query.state.error) && !isWarmingPending(query.state.error, query.state.errorUpdatedAt),
    staleTime: Infinity,
  })
}
