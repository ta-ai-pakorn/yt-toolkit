import { useQuery, type UseQueryResult } from "@tanstack/react-query"
import { Eye, MessageSquare, NotebookPen, ThumbsUp } from "lucide-react"
import { useEffect, useRef, useState, type ReactNode } from "react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { fill, th } from "@/i18n/th"
import { downloadFile } from "@/lib/download"
import { formatCompact, formatCount, formatDuration, formatPublished } from "@/lib/format"
import { notePath } from "@/lib/sub-options"
import type { SubtitleTrack, VideoInfo } from "@/lib/types"
import { Thumbnail } from "@/pages/home/thumbnail"

import { ClipDetails } from "./clip-details"
import { errorMessage } from "./errors"
import { LoadError } from "./load-error"
import { Stat } from "./stats"
import { subtitlesQuery } from "./subs-queries"
import { useSubSettings } from "./subs-settings"
import { trackInEffect, trackLabel } from "./track-label"
import { useVideoParams } from "./url-state"

const t = th.video

// จอกว้าง: ปก 288 px อยู่ซ้าย ข้อมูลทั้งหมดอยู่คอลัมน์ขวา (ทั้งตอนโหลดและตอนมีข้อมูลใช้ขนาดเดียวกัน ภาพไม่กระโดด)
// items-start: กางคำอธิบายแล้วฝั่งข้อมูลสูงขึ้น ปกยังเป็น 16:9 เท่าเดิม ไม่ถูกยืดตามความสูงของแถว
// จอแคบ (มือถือ): ปกเล็ก 128 px อยู่ข้างชื่อคลิป ส่วนอื่นเต็มความกว้างใต้ลงมา (คอลัมน์ข้อมูลเป็น contents ลูก ๆ จึงวางในกริดเอง)
// ปกเต็มจอกินความสูงเกือบ 200 px จนแถบแท็บถูกดันพ้นจอแรก
const LAYOUT = "grid grid-cols-[8rem_minmax(0,1fr)] items-start gap-x-3 gap-y-2 sm:flex sm:flex-row sm:gap-4"
const COVER = "w-full sm:w-72"
/** ส่วนของคอลัมน์ข้อมูลที่จอแคบต้องเต็มความกว้าง (ใต้ปกกับชื่อคลิป) */
const FULL_ROW = "max-sm:col-span-2"

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
 * แทร็กซับที่ใช้อยู่ (แทร็กใน URL หรือแทร็กเริ่มต้นของคลิป) สำหรับป้ายที่หัวคลิปและโน้ต .md
 * ยังโหลดรายการแทร็กไม่เสร็จ โหลดไม่สำเร็จ หรือไม่มีแทร็กที่ใช้อยู่ = null (ไม่แสดงป้าย โน้ตใช้แทร็กเริ่มต้นของ backend)
 */
function useTrack(videoId: string | undefined): SubtitleTrack | null {
  const { trackId } = useVideoParams()
  const subtitles = useQuery(subtitlesQuery(videoId ?? "", videoId !== undefined))
  if (!subtitles.isSuccess) return null
  return trackInEffect(subtitles.data, trackId)
}

/** ยอดดู ถูกใจ คอมเมนต์ แบบย่อ ("1.2 แสน ครั้ง") ตัวไหนยูทูปไม่บอกก็ไม่แสดง */
function statParts(video: VideoInfo): ReactNode[] {
  const { views, likes, comments } = video.stats ?? {}
  const parts: ReactNode[] = []
  if (views !== undefined) {
    parts.push(
      <Stat
        key="views"
        icon={Eye}
        text={fill(t.stats.views, { n: formatCompact(views) })}
        label={fill(t.stats.viewsLabel, { n: formatCount(views) })}
      />,
    )
  }
  if (likes !== undefined) {
    parts.push(
      <Stat
        key="likes"
        icon={ThumbsUp}
        text={formatCompact(likes)}
        label={fill(t.stats.likesLabel, { n: formatCount(likes) })}
      />,
    )
  }
  if (comments !== undefined) {
    parts.push(
      <Stat
        key="comments"
        icon={MessageSquare}
        text={formatCompact(comments)}
        label={fill(t.stats.commentsLabel, { n: formatCount(comments) })}
      />,
    )
  }
  return parts
}

/**
 * แถวข้อมูลใต้ชื่อคลิป: ช่อง ความยาว วันที่เผยแพร่ ยอดดู/ถูกใจ/คอมเมนต์ หมวดหมู่ และแทร็กซับที่ใช้อยู่
 * จำนวน chapter ไม่อยู่ในแถวนี้แล้ว (หัวข้อ "Chapter (N ตอน)" ในกล่องข้างล่างบอกอยู่)
 */
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
  if (published) parts.push(<span key="published">{fill(t.publishedOn, { date: published })}</span>)
  parts.push(...statParts(video))
  for (const [index, category] of (video.categories ?? []).entries()) {
    if (category.trim() === "") continue
    parts.push(
      <Badge key={`category-${index}`} variant="outline" className="text-muted-foreground">
        <span className="sr-only">{t.category} </span>
        {category}
      </Badge>,
    )
  }
  if (trackName) {
    parts.push(
      <Badge key="track" variant="secondary">
        {fill(t.trackBadge, { name: trackName })}
      </Badge>,
    )
  }
  return <p className={`flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground ${FULL_ROW}`}>{parts}</p>
}

/**
 * "บันทึกเป็นโน้ต (.md)": ไฟล์ Markdown ของคลิป (ข้อมูลคลิป คำอธิบาย chapter ทรานสคริปต์) สำหรับ Obsidian หรือแอปจดโน้ต
 * ใช้แทร็กและความยาวซับชุดเดียวกับไฟล์ซับในแท็บซับ · ปุ่มรอง (หน้านี้ไม่มีปุ่มหลักสีเหลือง)
 * ระหว่างเตรียมไฟล์มีวงหมุน กดซ้ำไม่ได้แต่ยังโฟกัสได้ · ผิดพลาด = toast ข้อความไทยจาก backend
 */
function NoteButton({ videoId, trackId }: { videoId: string; trackId: string | null }) {
  const { options } = useSubSettings()
  const [busy, setBusy] = useState(false)

  async function save() {
    if (busy) return
    setBusy(true)
    const id = toast.loading(t.note.preparing)
    try {
      await downloadFile(notePath(videoId, trackId, options), `${videoId}.note.md`)
      toast.dismiss(id)
    } catch (error) {
      toast.error(errorMessage(error, t.note.failed), { id })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            variant="secondary"
            size="sm"
            className={`w-fit max-sm:h-11 ${FULL_ROW}`}
            disabled={busy}
            focusableWhenDisabled
            onClick={() => void save()}
          />
        }
      >
        {busy ? <Spinner aria-hidden /> : <NotebookPen aria-hidden />}
        {t.note.button}
      </TooltipTrigger>
      <TooltipContent>{t.note.hint}</TooltipContent>
    </Tooltip>
  )
}

const focusLost = () => document.activeElement === null || document.activeElement === document.body

/**
 * หัวคลิปของ W2: ปก ชื่อ แถวข้อมูล (ช่อง ความยาว วันที่ ยอดดู หมวดหมู่ แทร็กซับ) ปุ่มบันทึกเป็นโน้ต
 * และกล่องคำอธิบาย/คอมเมนต์ปักหมุด/chapter/แท็ก พร้อมปุ่มคัดลอก
 * (โหลดอยู่ = Skeleton รูปเดียวกัน, ผิดพลาด = Alert)
 */
export function VideoHeader({ video }: { video: UseQueryResult<VideoInfo, Error> }) {
  // มีข้อมูลอยู่แล้ว (เช่นจากรายการผลของ W1) แต่รีเฟรชเบื้องหลังล้มเหลว = ยังแสดงข้อมูลเดิม (หน้าแม่แจ้งด้วย toast)
  const data = video.data
  const headingRef = useRef<HTMLHeadingElement>(null)
  const videoId = data?.videoId
  const track = useTrack(videoId)
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
      <div className="flex min-w-0 flex-1 flex-col gap-2 max-sm:contents">
        <h1
          ref={headingRef}
          tabIndex={-1}
          className="text-xl leading-relaxed font-semibold break-words outline-none max-sm:self-center max-sm:text-lg"
        >
          {data.title}
        </h1>
        <Meta video={data} trackName={track ? trackLabel(track) : null} />
        <NoteButton videoId={data.videoId} trackId={track?.id ?? null} />
        {/* key: เปิดคลิปถัดไปแล้วกล่องคำอธิบาย/chapter กลับมาพับเหมือนเดิม */}
        <ClipDetails key={data.videoId} video={data} className={FULL_ROW} />
      </div>
    </div>
  )
}
