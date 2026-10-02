import { useQuery, type UseQueryResult } from "@tanstack/react-query"
import { ExternalLink, ImageIcon, NotebookPen } from "lucide-react"
import { useEffect, useRef, useState, type ReactNode } from "react"

import { Badge } from "@/components/ui/badge"
import { Button, buttonVariants } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { fill, th } from "@/i18n/th"
import { youtubeWatchUrl } from "@/lib/format"
import { useEnqueue } from "@/lib/jobs"
import type { SubtitleTrack, VideoInfo } from "@/lib/types"
import { useNarrowScreen } from "@/lib/use-narrow-screen"

import { Lightbox } from "./lightbox"
import { LoadError } from "./load-error"
import { PlayerControls, PlayerSlot } from "./player/player-slot"
import { ReelButton } from "./player/reel-button"
import { useSlotInView } from "./player/slot-visibility"
import { useTrackWarming } from "./session-warming"
import { StatTiles } from "./stats"
import { subtitlesQuery } from "./subs-queries"
import { trackInEffect, trackLabel } from "./track-label"
import { useVideoParams } from "./url-state"

const t = th.video

/** ข้อความ toast ตอนส่งเข้าคิว (ชุดเดียวกับปุ่มโหลดอื่นของหน้า W2) */
const ENQUEUE_MESSAGES = {
  added: th.queue.added,
  addedMany: th.queue.addedMany,
  failed: th.queue.addFailed,
  goHealth: th.queue.goHealth,
}

// จอกว้าง: ปก 288 px อยู่ซ้าย ข้อมูลทั้งหมดอยู่คอลัมน์ขวา (ทั้งตอนโหลดและตอนมีข้อมูลใช้ขนาดเดียวกัน ภาพไม่กระโดด)
// จอแคบ (มือถือ): ปกเล็ก 128 px อยู่ข้างชื่อคลิป ส่วนอื่นเต็มความกว้างใต้ลงมา (คอลัมน์ข้อมูลเป็น contents ลูก ๆ จึงวางในกริดเอง)
// ปกเต็มจอกินความสูงเกือบ 200 px จนแถบแท็บถูกดันพ้นจอแรก
// หัวคลิปสูงคงที่ (owner round 4): ไม่มีคำอธิบายหรือกล่องที่กางได้แล้ว (ย้ายไปแท็บข้อมูลคลิป) และแถวป้ายเป็นบรรทัดเดียวเสมอ
// ข้อมูลที่มาทีหลัง (ป้ายแทร็กซับ) จึงไม่ดันแถบแท็บลงหลังหน้าโผล่
const LAYOUT = "grid grid-cols-[8rem_minmax(0,1fr)] items-start gap-x-3 gap-y-2 sm:flex sm:flex-row sm:gap-4"
const COVER = "w-full sm:w-72"
/** คอลัมน์ซ้ายของจอกว้าง: ช่องตัวเล่น + แถวไทม์ไลน์ใต้ตัวเล่น (จอแคบ = contents ช่องตัวเล่นวางในกริดเอง) */
const PLAYER_COLUMN = "max-sm:contents sm:flex sm:w-72 sm:shrink-0 sm:flex-col sm:gap-2"
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
      {/* ช่องตัวเล่น (แถวไทม์ไลน์มีหลังกดเล่นเท่านั้น ไม่จองที่) */}
      <div className={PLAYER_COLUMN}>
        <Skeleton className={`aspect-video ${COVER}`} />
      </div>
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
        {/* แถวปุ่ม: โน้ต · เปิดในยูทูป · ดูภาพปก (จอแคบเหลือไอคอน) */}
        <div className={`flex flex-wrap items-center gap-2 ${FULL_ROW}`}>
          <Skeleton className="h-8 w-40 max-sm:h-11" />
          <Skeleton className="h-8 w-28 max-sm:h-11" />
          <Skeleton className="h-8 w-24 max-sm:h-11 max-sm:w-11" />
        </div>
      </div>
    </div>
  )
}

/**
 * แทร็กซับที่ใช้อยู่ (แทร็กใน URL หรือแทร็กเริ่มต้นของคลิป) สำหรับป้ายที่หัวคลิปและงานโน้ต .md
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
 * ปุ่ม "ดูภาพปก" ในแถวปุ่มของหัวคลิป: เปิดภาพปกขนาดใหญ่ในกล่องลอย (Lightbox เดียวกับภาพเฟรม) · Esc/คลิกปิด แล้วโฟกัสกลับที่ปุ่ม
 * (M3.5: ปกกลายเป็นช่องตัวเล่น กดปกแล้วเล่นคลิป ภาพปกใหญ่จึงย้ายมาเป็นปุ่มนี้ กดได้ทุกสถานะของตัวเล่น และไม่หยุดคลิปที่กำลังเล่น)
 * ไม่มีภาพปก = ไม่มีปุ่ม
 */
function CoverButton({ src }: { src: string }) {
  const [open, setOpen] = useState(false)
  const buttonRef = useRef<HTMLButtonElement>(null)
  if (!src) return null
  return (
    <>
      <Button
        ref={buttonRef}
        variant="secondary"
        size="sm"
        // จอแคบเหลือแค่ไอคอน (ชื่อปุ่มยังอ่านได้) แถวปุ่มจึงไม่ขึ้นบรรทัดใหม่
        className={`${TOUCH} max-sm:w-11 max-sm:px-0`}
        title={th.player.viewCover}
        aria-haspopup="dialog"
        data-slot="cover-button"
        onClick={() => setOpen(true)}
      >
        <ImageIcon aria-hidden />
        <span className="max-sm:sr-only">{th.player.viewCover}</span>
      </Button>
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
 * "บันทึกเป็นโน้ต (.md)": ไฟล์ Markdown ของคลิป (ข้อมูลคลิป คำอธิบาย chapter คอมเมนต์ปักหมุด ทรานสคริปต์) สำหรับ Obsidian หรือแอพจดโน้ต
 * owner round 2: ส่งงาน "note" เข้าคิว (ไม่ได้โหลดผ่านเบราว์เซอร์แล้ว) ไฟล์ลงโฟลเดอร์ของคลิปเหมือนไฟล์อื่น และขึ้นในคิว/ประวัติ
 * ใช้แทร็กที่ใช้อยู่ (ไม่มี = backend ใช้แทร็กเริ่มต้นของคลิป) · ปุ่มรอง (หน้านี้ไม่มีปุ่มหลักสีเหลือง)
 * ระหว่างส่งมีวงหมุน กดซ้ำไม่ได้แต่ยังโฟกัสได้ · toast มาตรฐานของคิว (เพิ่มเข้าคิวแล้ว / เพิ่มเข้าคิวไม่สำเร็จ)
 */
function NoteButton({ videoId, trackId }: { videoId: string; trackId: string | null }) {
  const { enqueue } = useEnqueue(ENQUEUE_MESSAGES)
  // สถานะของปุ่มเอง (ไม่ใช้ pending ของ react-query ที่อัปเดตช้ากว่าหนึ่งจังหวะ): กดรัว ๆ ก็ส่งงานเดียว
  const [busy, setBusy] = useState(false)
  // ซับแปลของแทร็กนี้กำลังรอเซสชัน (นับถอยหลังอยู่): งานโน้ตจะได้ error เดียวกัน จึงกดไม่ได้จนโหลดซับเสร็จ
  const warming = useTrackWarming(videoId, trackId)

  async function save() {
    if (busy || warming) return
    setBusy(true)
    try {
      await enqueue([{ videoId, kind: "note", params: trackId ? { trackId } : {} }])
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
 * หัวคลิปของ W2 (สูงคงที่ก่อนเล่น): ช่องตัวเล่น (ปก + ▶) ชื่อ แถวป้าย (ช่อง หมวดหมู่ แทร็กซับ) ช่องตัวเลข
 * และปุ่ม "บันทึกเป็นโน้ต (.md)" "เปิดในยูทูป" "ดูภาพปก" "เล่นเฉพาะช่วงที่ดูซ้ำบ่อย" (ถ้ามี) · คำอธิบาย chapter คอมเมนต์ปักหมุด แท็ก อยู่ในแท็บข้อมูลคลิป
 * หลังกดเล่น มีแถวไทม์ไลน์ใต้ตัวเล่น (จอแคบ: ใต้ชื่อคลิป)
 * (โหลดอยู่ = Skeleton รูปเดียวกัน, ผิดพลาด = Alert)
 */
export function VideoHeader({ video }: { video: UseQueryResult<VideoInfo, Error> }) {
  // มีข้อมูลอยู่แล้ว (เช่นจากรายการผลของ W1) แต่รีเฟรชเบื้องหลังล้มเหลว = ยังแสดงข้อมูลเดิม (หน้าแม่แจ้งด้วย toast)
  const data = video.data
  const headingRef = useRef<HTMLHeadingElement>(null)
  const videoId = data?.videoId
  const track = useTrack(videoId)
  // ช่องตัวเล่นอยู่ในจอไหม (พ้นจอหลังเริ่มเล่น = ลอย แถวไทม์ไลน์ซ่อน) · จอแคบ: แถวไทม์ไลน์อยู่ใต้ชื่อคลิปใน DOM ด้วย
  const [slotBox, setSlotBox] = useState<HTMLDivElement | null>(null)
  const slotInView = useSlotInView(slotBox)
  const narrow = useNarrowScreen()
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
      {/* ช่องตัวเล่น (ปก + ▶ ก่อนเล่น) · key: เปิดคลิปถัดไปแล้วเริ่มใหม่
          แถวไทม์ไลน์ (หลังกดเล่น): จอกว้างอยู่ใต้ตัวเล่นในคอลัมน์ซ้าย · จอแคบอยู่ใต้ชื่อคลิปเต็มความกว้าง
          วางคนละที่ใน DOM (ไม่ใช้ CSS order) ลำดับ Tab และโปรแกรมอ่านหน้าจอจึงตรงกับที่ตาเห็นทั้งสองแบบ */}
      <div className={PLAYER_COLUMN}>
        <PlayerSlot key={data.videoId} video={data} inView={slotInView} onBox={setSlotBox} />
        {!narrow && <PlayerControls key={data.videoId} video={data} inView={slotInView} />}
      </div>
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
        {narrow && <PlayerControls key={data.videoId} video={data} inView={slotInView} className={FULL_ROW} />}
        <Meta video={data} trackName={track ? trackLabel(track) : null} />
        <StatTiles video={data} className={FULL_ROW} />
        <div className={`flex flex-wrap items-center gap-2 ${FULL_ROW}`}>
          <NoteButton videoId={data.videoId} trackId={track?.id ?? null} />
          <YoutubeLink videoId={data.videoId} />
          {/* key: เปิดคลิปถัดไปแล้วกล่องภาพปกปิดเสมอ */}
          <CoverButton key={data.videoId} src={data.thumbnailUrl} />
          {/* เฉพาะคลิปที่มีช่วงดูซ้ำบ่อย: อยู่ในแถวปุ่ม (ไม่ใช่ใต้ตัวเล่น) หัวคลิปก่อนเล่นจึงสูงไม่ขึ้นกับ mostReplayed */}
          <ReelButton ranges={data.mostReplayed} />
        </div>
      </div>
    </div>
  )
}
