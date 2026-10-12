import { useQuery } from "@tanstack/react-query"
import { CaptionsOff } from "lucide-react"
import type { ReactNode } from "react"

import { Empty, EmptyDescription, EmptyHeader, EmptyMedia } from "@/components/ui/empty"
import { Skeleton } from "@/components/ui/skeleton"
import { th } from "@/i18n/th"
import type { SubtitleTracks } from "@/lib/types"

import { LoadError } from "./load-error"
import { subtitlesQuery } from "./subs-queries"

const t = th.subs

const SKELETON_ROWS = 3

function SubsSkeleton() {
  return (
    <div className="flex flex-col gap-3" aria-busy="true">
      <span className="sr-only" role="status">
        {t.loading}
      </span>
      {Array.from({ length: SKELETON_ROWS }, (_, index) => (
        <Skeleton key={index} className="h-10 w-full" />
      ))}
    </div>
  )
}

function NoSubtitles() {
  return (
    <Empty className="border">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <CaptionsOff aria-hidden />
        </EmptyMedia>
        <EmptyDescription>{t.none}</EmptyDescription>
      </EmptyHeader>
    </Empty>
  )
}

type Props = {
  videoId: string
  /** ยิงคำขอรายการแทร็กเมื่อข้อมูลคลิปมาแล้วเท่านั้น (ก่อนหน้านั้นแสดง Skeleton) */
  enabled: boolean
  /** เนื้อหาของแท็บเมื่อคลิปมีซับอย่างน้อย 1 แทร็ก */
  children: (data: SubtitleTracks) => ReactNode
}

/**
 * ด่านหน้าของแท็บซับและทรานสคริปต์: ครบ 4 สถานะ
 * กำลังโหลด = Skeleton 3 แถว · ผิดพลาด = Alert + ลองใหม่ · ไม่มีซับ = Empty "คลิปนี้ไม่มีซับ" · มีซับ = children(data)
 * ใช้ query เดียวกับป้ายแทร็กที่หัวคลิป (cache เดียวกัน ไม่ยิงซ้ำ)
 */
export function SubtitleGate({ videoId, enabled, children }: Props) {
  const subtitles = useQuery(subtitlesQuery(videoId, enabled))
  if (subtitles.isError) {
    return (
      <LoadError
        title={t.loadError}
        error={subtitles.error}
        onRetry={() => void subtitles.refetch()}
        context="video-subtitles"
        videoId={videoId}
      />
    )
  }
  if (!subtitles.isSuccess) return <SubsSkeleton />
  if (subtitles.data.tracks.length === 0) return <NoSubtitles />
  return <>{children(subtitles.data)}</>
}
