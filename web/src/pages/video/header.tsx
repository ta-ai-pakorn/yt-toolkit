import { useQuery, type UseQueryResult } from "@tanstack/react-query"
import { useEffect, useRef, type ReactNode } from "react"

import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { fill, th } from "@/i18n/th"
import { formatDuration, formatPublished } from "@/lib/format"
import type { VideoInfo } from "@/lib/types"
import { Thumbnail } from "@/pages/home/thumbnail"

import { ClipDetails } from "./clip-details"
import { LoadError } from "./load-error"
import { subtitlesQuery } from "./subs-queries"
import { trackInEffect, trackLabel } from "./track-label"
import { useVideoParams } from "./url-state"

const t = th.video

// ปกกับข้อมูลวางข้างกัน จอแคบวางซ้อน (ทั้งตอนโหลดและตอนมีข้อมูลใช้ขนาดเดียวกัน ภาพไม่กระโดด)
// items-start: กางคำอธิบายแล้วฝั่งข้อมูลสูงขึ้น ปกยังเป็น 16:9 เท่าเดิม ไม่ถูกยืดตามความสูงของแถว
const LAYOUT = "flex flex-col gap-4 sm:flex-row sm:items-start"
const COVER = "w-full sm:w-72"

function HeaderSkeleton() {
  return (
    <div className={LAYOUT} aria-busy="true">
      <span className="sr-only" role="status">
        {t.loading}
      </span>
      <Skeleton className={`aspect-video ${COVER}`} />
      <div className="flex flex-1 flex-col gap-3">
        <Skeleton className="h-7 w-3/4" />
        <Skeleton className="h-4 w-1/2" />
      </div>
    </div>
  )
}

/**
 * ชื่อแทร็กซับที่ใช้อยู่ (แทร็กใน URL หรือแทร็กเริ่มต้นของคลิป) สำหรับป้ายที่หัวคลิป
 * ยังโหลดรายการแทร็กไม่เสร็จ โหลดไม่สำเร็จ หรือไม่มีแทร็กที่ใช้อยู่ = null (ไม่แสดงป้าย)
 */
function useTrackName(videoId: string | undefined): string | null {
  const { trackId } = useVideoParams()
  const subtitles = useQuery(subtitlesQuery(videoId ?? "", videoId !== undefined))
  if (!subtitles.isSuccess) return null
  const track = trackInEffect(subtitles.data, trackId)
  return track ? trackLabel(track) : null
}

function Meta({ video, trackName }: { video: VideoInfo; trackName: string | null }) {
  const published = video.publishedAt ? formatPublished(video.publishedAt) : ""
  const parts: ReactNode[] = [
    <span key="channel">
      {t.channel} {video.channel}
    </span>,
    <span key="duration">
      {t.duration} <span className="font-mono">{formatDuration(video.durationS)}</span>
    </span>,
  ]
  if (video.chapters.length > 0) {
    parts.push(
      <Badge key="chapters" variant="secondary">
        {fill(t.chapters, { n: video.chapters.length })}
      </Badge>,
    )
  }
  if (published) parts.push(<span key="published">{fill(t.publishedOn, { date: published })}</span>)
  if (trackName) {
    parts.push(
      <Badge key="track" variant="secondary">
        {fill(t.trackBadge, { name: trackName })}
      </Badge>,
    )
  }
  return <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">{parts}</p>
}

const focusLost = () => document.activeElement === null || document.activeElement === document.body

/**
 * หัวคลิปของ W2: ปก ชื่อ ช่อง ความยาว จำนวนตอน วันที่เผยแพร่ แทร็กซับที่ใช้อยู่ และกล่องคำอธิบาย/chapter พร้อมปุ่มคัดลอก
 * (โหลดอยู่ = Skeleton รูปเดียวกัน, ผิดพลาด = Alert)
 */
export function VideoHeader({ video }: { video: UseQueryResult<VideoInfo, Error> }) {
  // มีข้อมูลอยู่แล้ว (เช่นจากรายการผลของ W1) แต่รีเฟรชเบื้องหลังล้มเหลว = ยังแสดงข้อมูลเดิม (หน้าแม่แจ้งด้วย toast)
  const data = video.data
  const headingRef = useRef<HTMLHeadingElement>(null)
  const videoId = data?.videoId
  const trackName = useTrackName(videoId)
  // เปิดหน้านี้จากลิงก์ (กด Enter ที่ "เปิดดู") โฟกัสหลุดไปที่ body: ย้ายมาที่ชื่อคลิป
  // โปรแกรมอ่านหน้าจอจะอ่านชื่อคลิปให้ และกด Tab ต่อจากตรงนี้ได้เลย · ถ้าผู้ใช้โฟกัสที่อื่นอยู่แล้วไม่ยุ่ง
  useEffect(() => {
    if (videoId && focusLost()) headingRef.current?.focus({ preventScroll: true })
  }, [videoId])
  // เปิดคลิปที่เปิดไม่ได้ (เช่นกด "ถัดไป" แล้วคลิปนั้นถูกลบ) ไม่มีชื่อคลิป: โฟกัสกล่อง error แทน ไม่ปล่อยไว้ที่ body
  const errorRef = useRef<HTMLDivElement>(null)
  const failed = !data && video.isError
  useEffect(() => {
    if (failed && focusLost()) errorRef.current?.focus({ preventScroll: true })
  }, [failed, video.error])
  if (!data) {
    if (video.isError) {
      return (
        <LoadError
          ref={errorRef}
          showHome
          title={t.loadError}
          error={video.error}
          onRetry={() => void video.refetch()}
        />
      )
    }
    return <HeaderSkeleton />
  }
  return (
    <div className={LAYOUT}>
      <Thumbnail src={data.thumbnailUrl} className={COVER} />
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <h1 ref={headingRef} tabIndex={-1} className="text-xl leading-relaxed font-semibold break-words outline-none">
          {data.title}
        </h1>
        <Meta video={data} trackName={trackName} />
        {/* key: เปิดคลิปถัดไปแล้วกล่องคำอธิบาย/chapter กลับมาพับเหมือนเดิม */}
        <ClipDetails key={data.videoId} video={data} />
      </div>
    </div>
  )
}
