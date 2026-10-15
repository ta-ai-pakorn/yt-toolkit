import { api } from "./api"
import type { Stats } from "./types"

type ApiDeps = Parameters<typeof api>[2]

/** M6 รอบ C (spec §3.2): สถิติคำนวณใหม่ทุกครั้งที่เปิดแท็บ (FR-STAT-2) */
export const STATS_KEY = ["stats"] as const

export function statsQuery(deps?: ApiDeps) {
  return {
    queryKey: STATS_KEY,
    queryFn: () => api<Stats>("/stats", {}, deps),
    staleTime: 0,
    refetchOnMount: "always" as const,
  }
}

/** เริ่มนับใหม่ (บันทึกเวลาเริ่มนับ ไม่ลบอะไร) */
export function resetStats(deps?: ApiDeps): Promise<{ since: string }> {
  return api<{ since: string }>("/stats/reset", { method: "POST" }, deps)
}
