import { useQuery } from "@tanstack/react-query"
import { useEffect } from "react"
import { useParams } from "react-router"
import { toast } from "sonner"

import { fill, th } from "@/i18n/th"

import { FramesSection } from "./video/frames"
import { errorMessage } from "./video/errors"
import { VideoHeader } from "./video/header"
import { videoQuery } from "./video/queries"

/** หน้า W2 (/v/:videoId): หัวคลิป + ภาพเฟรม · ส่วนไหนข้อมูลมาก่อนแสดงก่อน */
export function VideoPage() {
  const { videoId = "" } = useParams()
  const video = useQuery(videoQuery(videoId))
  const title = video.data?.title
  const hasData = video.data !== undefined

  useEffect(() => {
    if (!title) return
    const previous = document.title
    document.title = fill(th.video.pageTitle, { title, app: th.app.name })
    return () => {
      document.title = previous
    }
  }, [title])

  // รีเฟรชเบื้องหลังล้มเหลวทั้งที่มีข้อมูลเดิมอยู่: ไม่ล้มทั้งหน้า แจ้งด้วย toast
  useEffect(() => {
    if (video.isError && hasData) toast.error(errorMessage(video.error, th.errors.unknown))
  }, [video.isError, video.error, hasData])

  return (
    <div className="flex flex-col gap-6 pt-8">
      <VideoHeader video={video} />
      {/* คลิปเปิดไม่ได้ (ส่วนตัว/ไลฟ์/ถูกลบ) ก็ไม่มีภาพเฟรมให้ขอ ซ่อนทั้งส่วน */}
      {(hasData || !video.isError) && <FramesSection videoId={videoId} enabled={hasData} />}
    </div>
  )
}
