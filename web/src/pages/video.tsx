import { useQuery } from "@tanstack/react-query"
import { useEffect } from "react"
import { useLocation, useParams } from "react-router"
import { toast } from "sonner"

import { fill, th } from "@/i18n/th"

import { homeStore, useHomeState } from "./home/state"
import { readFromList, useAnalyze, useGlobalPaste } from "./home/use-analyze"
import { VideoCrumbs } from "./video/crumbs"
import { errorMessage } from "./video/errors"
import { VideoHeader } from "./video/header"
import { videoQuery } from "./video/queries"
import { ClipSequence } from "./video/sequence"
import { VideoTabs } from "./video/tabs"

/** หน้า W2 (/v/:videoId): breadcrumb + หัวคลิป + แถบแท็บ (ภาพเฟรม · ซับ · ทรานสคริปต์ · ข้อมูลคลิป) · ส่วนไหนข้อมูลมาก่อนแสดงก่อน */
export function VideoPage() {
  const { videoId = "" } = useParams()
  const location = useLocation()
  const video = useQuery(videoQuery(videoId))
  const title = video.data?.title
  const hasData = video.data !== undefined
  const { results } = useHomeState()
  // มาจากรายการผลของ W1 (กด "เปิดดู" หรือคลิปในเพลย์ลิสต์ที่กางไว้) และรายการนั้นยังอยู่
  // = breadcrumb มีขั้น "รายการที่วาง" และมีปุ่มคลิปก่อนหน้า/ถัดไป
  const from = results && results.length > 0 ? readFromList(location.state) : null
  const listCount = from && results ? results.length : undefined

  // วางลิงก์ยูทูปที่หน้านี้ก็วิเคราะห์ได้เหมือนหน้าแรก (คลิปเดียวมาหน้านี้ หลายลิงก์กลับไปแสดงรายการที่หน้าแรก)
  const { analyze, pending, dialog } = useAnalyze()
  useGlobalPaste(analyze, pending)

  // เปิดหน้านี้ = ดูคลิปนี้แล้ว (แถวในรายการผลของ W1 ขึ้นป้าย "เปิดดูแล้ว")
  useEffect(() => {
    if (videoId) homeStore.markOpened(videoId)
  }, [videoId])

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
    <div className="flex flex-col gap-6 pt-2">
      {/* breadcrumb กับปุ่มก่อนหน้า/ถัดไปอยู่แถวเดียวกัน (ปุ่มชิดขวา) · จอแคบปุ่มลงไปอยู่บรรทัดใต้ breadcrumb */}
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
        <VideoCrumbs
          className="min-w-0 sm:flex-1"
          title={title}
          fallback={video.isError && !hasData ? videoId : ""}
          listCount={listCount}
        />
        {from && <ClipSequence videoId={videoId} from={from} />}
      </div>
      <VideoHeader video={video} />
      {/* คลิปเปิดไม่ได้ (ส่วนตัว/ไลฟ์/ถูกลบ) ก็ไม่มีภาพเฟรมหรือซับให้ขอ ซ่อนแถบแท็บทั้งแถบ */}
      {(hasData || !video.isError) && <VideoTabs videoId={videoId} enabled={hasData} video={video.data} />}
      {dialog}
    </div>
  )
}
