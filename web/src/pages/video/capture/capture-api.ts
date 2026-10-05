import { queryOptions } from "@tanstack/react-query"

import { api } from "@/lib/api"
import type { Capture, CaptureList } from "@/lib/types"

/** ภาพคมที่ถ่ายตรงจุด (M5 รอบ B2 สัญญา C11): รายการ ถ่าย ลบ และเปิดโฟลเดอร์ */

type ApiDeps = Parameters<typeof api>[2]

export const capturesKey = (videoId: string) => ["captures", videoId] as const

/** รายการภาพของคลิป เรียงตามเวลา · URL ภาพมี ?v= อยู่แล้ว เก็บผลไว้สั้น ๆ แบบ storyboard */
export function capturesQuery(videoId: string, enabled: boolean, deps?: ApiDeps) {
  return queryOptions({
    queryKey: capturesKey(videoId),
    queryFn: ({ signal }) => api<CaptureList>(`/videos/${videoId}/captures`, { signal }, deps).then((body) => body.captures),
    enabled,
    retry: false,
    staleTime: 60_000,
  })
}

export function postCapture(videoId: string, tMs: number, deps?: ApiDeps): Promise<Capture> {
  return api<Capture>(`/videos/${videoId}/captures`, { method: "POST", body: JSON.stringify({ tMs }) }, deps)
}

export async function deleteCapture(videoId: string, id: string, deps?: ApiDeps): Promise<void> {
  await api<null>(`/videos/${videoId}/captures/${encodeURIComponent(id)}`, { method: "DELETE" }, deps)
}

export async function revealCaptures(videoId: string, deps?: ApiDeps): Promise<void> {
  await api<{ ok: boolean }>(`/videos/${videoId}/captures/reveal`, { method: "POST" }, deps)
}

/** ใส่ภาพใหม่ (id เดิม = แทนที่) แล้วเรียงตามเวลา */
export function withCapture(list: readonly Capture[] | undefined, item: Capture): Capture[] {
  return [...(list ?? []).filter((c) => c.id !== item.id), item].sort((a, b) => a.tMs - b.tMs)
}

export function withoutCapture(list: readonly Capture[] | undefined, id: string): Capture[] {
  return (list ?? []).filter((c) => c.id !== id)
}
