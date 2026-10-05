import type { Job, VideoInfo } from "@/lib/types"

/** งานภาพคมของคลิปนี้ที่ยังรอคิวหรือกำลังทำ: ปุ่มเป็น "กำลังดึงภาพคม…" (spec 1.2 กันขอซ้ำ) */
export function sharpJobBusy(jobs: readonly Job[] | undefined, videoId: string): boolean {
  return (jobs ?? []).some(
    (job) => job.videoId === videoId && job.kind === "frames_sharp" && (job.status === "queued" || job.status === "running")
  )
}

export type SharpBlock = "loading" | "live" | null

/** ขอภาพคมไม่ได้เพราะ: ข้อมูลคลิปยังไม่มา (loading) · คลิปสด/ไม่รู้ความยาว (live: tooltip "คลิปสดยังขอภาพคมไม่ได้") */
export function sharpBlock(video: Pick<VideoInfo, "isLive" | "durationS"> | undefined): SharpBlock {
  if (video === undefined) return "loading"
  return video.isLive || !(video.durationS > 0) ? "live" : null
}
