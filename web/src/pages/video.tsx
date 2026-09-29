import { useQuery } from "@tanstack/react-query"
import { CircleX } from "lucide-react"
import { Link, useParams } from "react-router"

import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { buttonVariants } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { th } from "@/i18n/th"
import { api } from "@/lib/api"
import { formatDuration } from "@/lib/format"
import type { VideoInfo } from "@/lib/types"

// หน้า W2 ฉบับชั่วคราว: แสดงแค่ชื่อคลิปให้ลิงก์จาก W1 ไปถึงได้ (งาน Task 9 มาแทนที่ทั้งไฟล์)
export function VideoPage() {
  const { videoId = "" } = useParams()
  const video = useQuery({
    queryKey: ["video", videoId],
    queryFn: () => api<VideoInfo>(`/videos/${videoId}`),
    retry: false,
  })

  if (video.isPending) {
    return (
      <section className="flex flex-col gap-3 pt-8" aria-busy="true">
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-5 w-40" />
      </section>
    )
  }

  if (video.isError) {
    return (
      <section className="flex flex-col gap-4 pt-8">
        <Alert variant="destructive">
          <CircleX aria-hidden />
          <AlertTitle>{th.video.loadError}</AlertTitle>
          <AlertDescription>{video.error.message}</AlertDescription>
          <AlertAction>
            <Link to="/" className={buttonVariants({ variant: "outline", size: "sm" })}>
              {th.common.backHome}
            </Link>
          </AlertAction>
        </Alert>
      </section>
    )
  }

  const { title, channel, durationS } = video.data
  return (
    <section className="flex flex-col gap-2 pt-8">
      <h1 className="text-xl leading-relaxed font-semibold">{title}</h1>
      <p className="text-sm text-muted-foreground">
        {th.video.channel} {channel} · {th.video.duration} <span className="font-mono">{formatDuration(durationS)}</span>
      </p>
    </section>
  )
}
