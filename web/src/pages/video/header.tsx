import { useQuery, type UseQueryResult } from "@tanstack/react-query"
import { ExternalLink, NotebookPen, ZoomIn } from "lucide-react"
import { useEffect, useRef, useState, type ReactNode } from "react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button, buttonVariants } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { fill, th } from "@/i18n/th"
import { downloadFile } from "@/lib/download"
import { youtubeWatchUrl } from "@/lib/format"
import { notePath } from "@/lib/sub-options"
import type { SubtitleTrack, VideoInfo } from "@/lib/types"
import { Thumbnail } from "@/pages/home/thumbnail"

import { errorMessage } from "./errors"
import { Lightbox } from "./lightbox"
import { LoadError } from "./load-error"
import { useTrackWarming } from "./session-warming"
import { StatTiles } from "./stats"
import { subtitlesQuery } from "./subs-queries"
import { useSubSettings } from "./subs-settings"
import { trackInEffect, trackLabel } from "./track-label"
import { useVideoParams } from "./url-state"

const t = th.video

// จอกว้าง: ปก 288 px อยู่ซ้าย ข้อมูลทั้งหมดอยู่คอลัมน์ขวา (ทั้งตอนโหลดและตอนมีข้อมูลใช้ขนาดเดียวกัน ภาพไม่กระโดด)
// จอแคบ (มือถือ): ปกเล็ก 128 px อยู่ข้างชื่อคลิป ส่วนอื่นเต็มความกว้างใต้ลงมา (คอลัมน์ข้อมูลเป็น contents ลูก ๆ จึงวางในกริดเอง)
// ปกเต็มจอกินความสูงเกือบ 200 px จนแถบแท็บถูกดันพ้นจอแรก
// หัวคลิปสูงคงที่ (owner round 4): ไม่มีคำอธิบายหรือกล่องที่กางได้แล้ว (ย้ายไปแท็บข้อมูลคลิป) และแถวป้ายเป็นบรรทัดเดียวเสมอ
// ข้อมูลที่มาทีหลัง (ป้ายแทร็กซับ) จึงไม่ดันแถบแท็บลงหลังหน้าโผล่
const LAYOUT = "grid grid-cols-[8rem_minmax(0,1fr)] items-start gap-x-3 gap-y-2 sm:flex sm:flex-row sm:gap-4"
const COVER = "w-full sm:w-72"
/** ส่วนของคอลัมน์ข้อมูลที่จอแคบต้องเต็มความกว้าง (ใต้ปกกับชื่อคลิป) */
const FULL_ROW = "max-sm:col-span-2"
// จอแคบ (มือถือ) ปุ่มสูง 44 px ให้นิ้วกดได้ง่าย
const TOUCH = "max-sm:h-11"

function HeaderSkeleton() {
  return (
    <div className={LAYOUT} aria-busy="true">
      <span className="sr-only" role="status">
        {t.loading}
      </span>
      <Skeleton className={`aspect-video ${COVER}`} />
      <div className="flex min-w-0 flex-1 flex-col gap-2 max-sm:contents">
        <div className="flex flex-col gap-2 max-sm:self-center">
          <Skeleton className="h-8 w-3/4 max-sm:h-7" />
          <Skeleton className="h-7 w-1/2 sm:hidden" />
        </div>
        <Skeleton className={`h-6 w-2/3 ${FULL_ROW}`} />
        <ul className={`grid grid-cols-3 gap-1.5 sm:grid-cols-6 ${FULL_ROW}`}>
          {Array.from({ length: 6 }, (_, index) => (
            <li key={index} className="min-w-0">
              <Skeleton className="h-[3.25rem] w-full" />
            </li>
          ))}
        </ul>
        <div className={`flex flex-wrap items-center gap-2 ${FULL_ROW}`}>
          <Skeleton className="h-8 w-40 max-sm:h-11" />
          <Skeleton className="h-8 w-32 max-sm:h-11" />
        </div>
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

// ของในแถวป้ายย่อได้ (ตัดท้ายด้วย …) แถวจึงไม่ขึ้นบรรทัดใหม่ ชื่อเต็มอยู่ใน title
const SHRINK = "min-w-0 shrink truncate"

/**
 * แถวใต้ชื่อคลิป บรรทัดเดียว: ช่อง · หมวดหมู่ · แทร็กซับที่ใช้อยู่ (ตัวเลข ความยาว วันที่ อยู่ในช่องตัวเลขข้างล่าง)
 * ป้ายแทร็กมาทีหลัง (รอรายการแทร็ก) แต่แถวสูงเท่าเดิมเสมอ: ของที่ยาวเกินถูกตัดท้าย ไม่ตัดขึ้นบรรทัดใหม่
 */
function Meta({ video, trackName }: { video: VideoInfo; trackName: string | null }) {
  const channel = `${t.channel} ${video.channel}`
  const parts: ReactNode[] = [
    <span key="channel" title={channel} className={SHRINK}>
      {channel}
    </span>,
  ]
  for (const [index, category] of (video.categories ?? []).entries()) {
    if (category.trim() === "") continue
    parts.push(
      <Badge key={`category-${index}`} variant="outline" title={category} className={`${SHRINK} text-muted-foreground`}>
        <span className="sr-only">{t.category} </span>
        {category}
      </Badge>,
    )
  }
  if (trackName) {
    const label = fill(t.trackBadge, { name: trackName })
    parts.push(
      <Badge key="track" variant="secondary" title={label} className={SHRINK}>
        {label}
      </Badge>,
    )
  }
  return (
    <p
      className={`flex h-6 min-w-0 flex-nowrap items-center gap-x-3 overflow-hidden text-sm whitespace-nowrap text-muted-foreground ${FULL_ROW}`}
    >
      {parts}
    </p>
  )
}

/**
 * ปกคลิป: กด (หรือ Enter/Space) แล้วเปิดภาพปกขนาดใหญ่ในกล่องลอย (Lightbox เดียวกับภาพเฟรม) · Esc/คลิกปิด แล้วโฟกัสกลับที่ปก
 * ชี้เมาส์หรือโฟกัสแล้วเห็นไอคอนขยายและเคอร์เซอร์แว่นขยาย · ภาพปกที่ backend ส่งมาเป็นขนาดใหญ่ที่สุดที่ยูทูปมีอยู่แล้ว
 * ไม่มีภาพปก = กรอบเทาเฉย ๆ (กดไม่ได้) · ขนาดปุ่มเท่ากรอบปกของ Skeleton ภาพจึงไม่กระโดดตอนโหลดเสร็จ
 */
function Cover({ src }: { src: string }) {
  const [open, setOpen] = useState(false)
  const buttonRef = useRef<HTMLButtonElement>(null)
  if (!src) return <Thumbnail src={src} className={COVER} />
  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        aria-haspopup="dialog"
        aria-label={t.cover.open}
        onClick={() => setOpen(true)}
        className={`group/cover relative block shrink-0 cursor-zoom-in rounded-md outline-none hover:ring-2 hover:ring-ring/40 focus-visible:ring-3 focus-visible:ring-ring ${COVER}`}
      >
        <Thumbnail src={src} className="w-full" />
        <span
          aria-hidden
          data-slot="cover-zoom"
          className="pointer-events-none absolute inset-0 flex items-center justify-center rounded-md bg-black/30 opacity-0 transition-opacity group-hover/cover:opacity-100 group-focus-visible/cover:opacity-100 motion-reduce:transition-none"
        >
          <span className="flex size-10 items-center justify-center rounded-full bg-black/60 text-white">
            <ZoomIn className="size-5" />
          </span>
        </span>
      </button>
      <Lightbox
        open={open}
        src={src}
        label={t.cover.dialog}
        onClose={() => setOpen(false)}
        finalFocus={() => buttonRef.current}
        sizeKey={src}
      />
    </>
  )
}

/**
 * "เปิดในยูทูป": ลิงก์จริง (<a>) หน้าตาเป็นปุ่มรอง เปิดหน้าคลิปบนยูทูปในแท็บใหม่ (noopener noreferrer)
 * ไม่ใช้ Button ของ Base UI ครอบ เพราะจะได้ role="button" ทั้งที่เป็นลิงก์ (โปรแกรมอ่านหน้าจอต้องรู้ว่าพาออกจากหน้า)
 */
function YoutubeLink({ videoId }: { videoId: string }) {
  return (
    <a
      href={youtubeWatchUrl(videoId)}
      target="_blank"
      rel="noopener noreferrer"
      data-slot="button"
      className={buttonVariants({ variant: "secondary", size: "sm", className: TOUCH })}
    >
      <ExternalLink aria-hidden />
      {t.openYoutube}
      <span className="sr-only"> {t.newTab}</span>
    </a>
  )
}

/**
 * "บันทึกเป็นโน้ต (.md)": ไฟล์ Markdown ของคลิป (ข้อมูลคลิป คำอธิบาย chapter คอมเมนต์ปักหมุด ทรานสคริปต์) สำหรับ Obsidian หรือแอปจดโน้ต
 * ใช้แทร็กและความยาวซับชุดเดียวกับไฟล์ซับในแท็บซับ · ปุ่มรอง (หน้านี้ไม่มีปุ่มหลักสีเหลือง)
 * ระหว่างเตรียมไฟล์มีวงหมุน กดซ้ำไม่ได้แต่ยังโฟกัสได้ · ผิดพลาด = toast ข้อความไทยจาก backend
 */
function NoteButton({ videoId, trackId }: { videoId: string; trackId: string | null }) {
  const { options } = useSubSettings()
  const [busy, setBusy] = useState(false)
  // ซับแปลของแทร็กนี้กำลังรอเซสชัน (นับถอยหลังอยู่): โน้ตจะได้ error เดียวกัน จึงกดไม่ได้จนโหลดซับเสร็จ
  const warming = useTrackWarming(videoId, trackId)

  async function save() {
    if (busy || warming) return
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
            className={TOUCH}
            disabled={busy || warming}
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
 * หัวคลิปของ W2 (สูงคงที่): ปก (กดดูภาพใหญ่) ชื่อ แถวป้าย (ช่อง หมวดหมู่ แทร็กซับ) ช่องตัวเลข
 * และปุ่ม "บันทึกเป็นโน้ต (.md)" กับ "เปิดในยูทูป" · คำอธิบาย chapter คอมเมนต์ปักหมุด แท็ก อยู่ในแท็บข้อมูลคลิป
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
      {/* key: เปิดคลิปถัดไปแล้วกล่องภาพปกปิดเสมอ */}
      <Cover key={data.videoId} src={data.thumbnailUrl} />
      <div className="flex min-w-0 flex-1 flex-col gap-2 max-sm:contents">
        {/* จอแคบ (< 640 px) ตัดชื่อที่ 3 บรรทัด ไม่ให้ชื่อยาวดันแถบแท็บพ้นจอแรก (review I-3: ชื่อไทย 100 ตัวดันไป 805 px)
            ชื่อเต็มยังอยู่ใน title (ชี้เมาส์) และโปรแกรมอ่านหน้าจออ่านครบ (ตัดแค่ที่ตาเห็น) */}
        <h1
          ref={headingRef}
          tabIndex={-1}
          title={data.title}
          className="text-xl leading-relaxed font-semibold break-words outline-none max-sm:line-clamp-3 max-sm:self-center max-sm:text-lg"
        >
          {data.title}
        </h1>
        <Meta video={data} trackName={track ? trackLabel(track) : null} />
        <StatTiles video={data} className={FULL_ROW} />
        <div className={`flex flex-wrap items-center gap-2 ${FULL_ROW}`}>
          <NoteButton videoId={data.videoId} trackId={track?.id ?? null} />
          <YoutubeLink videoId={data.videoId} />
        </div>
      </div>
    </div>
  )
}
