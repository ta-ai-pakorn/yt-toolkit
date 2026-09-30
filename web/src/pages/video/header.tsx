import type { UseQueryResult } from "@tanstack/react-query"
import { useEffect, useRef, type ReactNode } from "react"

import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { fill, th } from "@/i18n/th"
import { formatDuration, formatPublished } from "@/lib/format"
import type { VideoInfo } from "@/lib/types"
import { Thumbnail } from "@/pages/home/thumbnail"

import { LoadError } from "./load-error"

const t = th.video

// ปกกับข้อมูลวางข้างกัน จอแคบวางซ้อน (ทั้งตอนโหลดและตอนมีข้อมูลใช้ขนาดเดียวกัน ภาพไม่กระโดด)
const LAYOUT = "flex flex-col gap-4 sm:flex-row"
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

function Meta({ video }: { video: VideoInfo }) {
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
  return <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">{parts}</p>
}

/** หัวคลิปของ W2: ปก ชื่อ ช่อง ความยาว จำนวนตอน วันที่เผยแพร่ (โหลดอยู่ = Skeleton รูปเดียวกัน, ผิดพลาด = Alert) */
export function VideoHeader({ video }: { video: UseQueryResult<VideoInfo, Error> }) {
  // มีข้อมูลอยู่แล้ว (เช่นจากรายการผลของ W1) แต่รีเฟรชเบื้องหลังล้มเหลว = ยังแสดงข้อมูลเดิม (หน้าแม่แจ้งด้วย toast)
  const data = video.data
  const headingRef = useRef<HTMLHeadingElement>(null)
  const videoId = data?.videoId
  // เปิดหน้านี้จากลิงก์ (กด Enter ที่ "เปิดดู") โฟกัสหลุดไปที่ body: ย้ายมาที่ชื่อคลิป
  // โปรแกรมอ่านหน้าจอจะอ่านชื่อคลิปให้ และกด Tab ต่อจากตรงนี้ได้เลย · ถ้าผู้ใช้โฟกัสที่อื่นอยู่แล้วไม่ยุ่ง
  useEffect(() => {
    if (videoId && (document.activeElement === null || document.activeElement === document.body)) {
      headingRef.current?.focus({ preventScroll: true })
    }
  }, [videoId])
  if (!data) {
    if (video.isError) {
      return <LoadError showHome title={t.loadError} error={video.error} onRetry={() => void video.refetch()} />
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
        <Meta video={data} />
      </div>
    </div>
  )
}
