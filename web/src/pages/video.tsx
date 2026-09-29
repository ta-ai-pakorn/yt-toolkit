import { useQuery } from "@tanstack/react-query"
import { useEffect } from "react"
import { useParams } from "react-router"

import { fill, th } from "@/i18n/th"

import { FramesSection } from "./video/frames"
import { VideoHeader } from "./video/header"
import { videoQuery } from "./video/queries"

/** หน้า W2 (/v/:videoId): หัวคลิป + ภาพเฟรม · ส่วนไหนข้อมูลมาก่อนแสดงก่อน */
export function VideoPage() {
  const { videoId = "" } = useParams()
  const video = useQuery(videoQuery(videoId))
  const title = video.data?.title

  useEffect(() => {
    if (!title) return
    const previous = document.title
    document.title = fill(th.video.pageTitle, { title, app: th.app.name })
    return () => {
      document.title = previous
    }
  }, [title])

  return (
    <div className="flex flex-col gap-6 pt-8">
      <VideoHeader video={video} />
      {/* คลิปเปิดไม่ได้ (ส่วนตัว/ไลฟ์/ถูกลบ) ก็ไม่มีภาพเฟรมให้ขอ ซ่อนทั้งส่วน */}
      {!video.isError && <FramesSection videoId={videoId} enabled={video.isSuccess} />}
    </div>
  )
}
