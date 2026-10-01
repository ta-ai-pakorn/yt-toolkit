import { useQuery } from "@tanstack/react-query"
import { Download, FileX } from "lucide-react"
import { useId, type ReactNode } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia } from "@/components/ui/empty"
import { Field, FieldContent, FieldDescription, FieldLabel } from "@/components/ui/field"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import { Switch } from "@/components/ui/switch"
import { fill, th } from "@/i18n/th"
import { AUTO_QUALITY, buildVideoParams, qualityOptions, videoSizeEstimate, type QualityOption } from "@/lib/download-options"
import { formatBytes } from "@/lib/format"
import { useEnqueue } from "@/lib/jobs"
import type { VideoInfo } from "@/lib/types"

import { originalLanguage } from "../subs/track-groups"
import { subtitlesQuery } from "../subs-queries"
import { useSubSettings } from "../subs-settings"
import { trackLabel } from "../track-label"
import { AudioLanguageSelect, DisabledReason, SELECT_CONTENT, SELECT_TRIGGER } from "./audio-language-select"
import {
  embeddableTracks,
  ENQUEUE_MESSAGES,
  languageLocked,
  resolveEmbed,
  useDownloadState,
  videoPrefsPatch,
  type DownloadChoices,
} from "./use-download-state"

const t = th.download.video

/** ค่าของตัวเลือก "ไม่ฝัง" ในช่องฝังซับ (ไม่มีทางชนกับรหัสแทร็ก o./a./t.) */
const EMBED_NONE = "none"

/** ป้ายของตัวเลือกคุณภาพ: "1080p · 60 fps · H.264" (+ " · ประมาณ 268 MB" เมื่อรู้ขนาด) */
function optionLabel(option: QualityOption, size: number | undefined): string {
  const values = { height: option.height, fps: option.fps, codec: option.codec }
  return size === undefined ? fill(t.option, values) : fill(t.optionSize, { ...values, size: formatBytes(size) })
}

/** กรอบของแท็บวิดีโอ/เสียง: Card หัวข้อ h2 (แบบเดียวกับแท็บซับ) */
export function DownloadCard({ title, children }: { title: string; children: ReactNode }) {
  const titleId = useId()
  return (
    <section aria-labelledby={titleId}>
      <Card>
        <CardHeader>
          <CardTitle>
            <h2 id={titleId} className="text-base font-medium">
              {title}
            </h2>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">{children}</CardContent>
      </Card>
    </section>
  )
}

/** ระหว่างรอข้อมูลคลิป: Skeleton รูปเดียวกับช่องเลือกและปุ่ม */
export function DownloadSkeleton({ title }: { title: string }) {
  return (
    <DownloadCard title={title}>
      <div className="flex flex-col gap-4" aria-busy="true">
        <span className="sr-only" role="status">
          {th.download.loading}
        </span>
        <Skeleton className="h-8 w-full sm:w-80" />
        <Skeleton className="h-5 w-48" />
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-9 w-32" />
      </div>
    </DownloadCard>
  )
}

/** คลิปนี้ไม่มีไฟล์ให้โหลด */
export function NoFormats({ title }: { title: string }) {
  return (
    <DownloadCard title={title}>
      <Empty className="border">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <FileX aria-hidden />
          </EmptyMedia>
          <EmptyDescription>{th.download.noFormats}</EmptyDescription>
        </EmptyHeader>
      </Empty>
    </DownloadCard>
  )
}

type SwitchRowProps = {
  label: string
  hint: string
  checked: boolean
  onChange: (checked: boolean) => void
  disabled?: boolean
}

/** สวิตช์พร้อมคำอธิบายใต้ชื่อ (คำอธิบายผูกกับสวิตช์ผ่าน aria-describedby) */
function SwitchRow({ label, hint, checked, onChange, disabled = false }: SwitchRowProps) {
  const id = useId()
  const hintId = useId()
  return (
    <Field orientation="horizontal" className="items-start" data-disabled={disabled || undefined}>
      <Switch
        id={id}
        checked={checked}
        onCheckedChange={onChange}
        disabled={disabled}
        aria-describedby={hintId}
        className="mt-0.5"
      />
      <FieldContent>
        <FieldLabel htmlFor={id}>{label}</FieldLabel>
        <FieldDescription id={hintId}>{hint}</FieldDescription>
      </FieldContent>
    </Field>
  )
}

type Props = {
  video: VideoInfo
  /** ยิงคำขอรายการแทร็กซับ (ช่องฝังซับ) เมื่อข้อมูลคลิปมาแล้วเท่านั้น */
  enabled: boolean
  choices: DownloadChoices
  choose: (patch: DownloadChoices) => void
}

function VideoForm({ video, enabled, choices, choose }: Props) {
  const qualityLabelId = useId()
  const embedLabelId = useId()
  const embedHintId = useId()
  const { state, languages, remember, cap } = useDownloadState(video, choices)
  const subSettings = useSubSettings()
  const subtitles = useQuery(subtitlesQuery(video.videoId, enabled))
  const { enqueue, pending } = useEnqueue(ENQUEUE_MESSAGES)

  const options = qualityOptions(video, state.maxQuality, cap)
  // ความละเอียดสูงสุดเปิดอยู่: "อัตโนมัติ" = ภาพดีที่สุดของคลิป (อาจเป็น VP9/AV1) ไม่ใช่ "เปิดได้ทุกที่ 1080p"
  const autoLabel = state.maxQuality ? t.autoMax : t.auto
  const autoNotCompat = state.maxQuality && options.length > 0 && !options[0].compat
  const labels = new Map<string, string>([[AUTO_QUALITY, autoLabel]])
  for (const option of options) {
    labels.set(option.value, optionLabel(option, videoSizeEstimate(video, option.value, state.noAudio, state.maxQuality, cap)))
  }
  const size = videoSizeEstimate(video, state.quality, state.noAudio, state.maxQuality, cap)

  const tracks = subtitles.data ? embeddableTracks(subtitles.data.tracks, originalLanguage(subtitles.data.tracks, video.audio)) : []
  const embedSubs = resolveEmbed(choices.embedSubs, tracks)
  // รายการแทร็กยังไม่มา = ยังกดไม่ได้ (ไม่มีเหตุผลให้บอก) · มาแล้วไม่มีซับ หรือโหลดไม่สำเร็จ = กดไม่ได้พร้อมเหตุผล
  const embedReason = subtitles.isPending ? null : tracks.length === 0 ? t.embedNoSubs : null
  const embedDisabled = tracks.length === 0

  async function submit() {
    if (pending) return
    const params = buildVideoParams({
      quality: state.quality,
      maxQuality: state.maxQuality,
      compatCap: cap,
      noAudio: state.noAudio,
      audioLanguage: state.audioLanguage,
      embedSubs,
      subOptions: subSettings.options,
    })
    const ok = await enqueue([{ videoId: video.videoId, kind: "video", params, title: video.title }])
    if (ok) remember(videoPrefsPatch(state, video, languages, cap))
  }

  return (
    <DownloadCard title={t.title}>
      <div className="flex flex-col gap-2">
        <div id={qualityLabelId} className="text-sm font-medium">
          {t.quality}
        </div>
        <Select<string>
          value={state.quality}
          onValueChange={(value) => {
            if (value !== null && value !== state.quality) choose({ quality: value })
          }}
        >
          <SelectTrigger aria-labelledby={qualityLabelId} className={SELECT_TRIGGER}>
            <SelectValue>{(value: string | null) => (value ? (labels.get(value) ?? value) : "")}</SelectValue>
          </SelectTrigger>
          <SelectContent alignItemWithTrigger={false} align="start" className={SELECT_CONTENT}>
            <SelectItem value={AUTO_QUALITY}>
              {autoLabel}
              {autoNotCompat && <Badge variant="outline">{t.notCompat}</Badge>}
            </SelectItem>
            {options.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {labels.get(option.value)}
                {state.maxQuality && !option.compat && <Badge variant="outline">{t.notCompat}</Badge>}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <SwitchRow
        label={t.maxQuality}
        hint={t.maxQualityHint}
        checked={state.maxQuality}
        onChange={(maxQuality) => choose({ maxQuality })}
      />

      <AudioLanguageSelect
        options={languages}
        value={state.audioLanguage}
        onChange={(audioLanguage) => choose({ audioLanguage })}
        disabled={languageLocked(state)}
      />

      {/* คลิปไม่มีเสียงเลย: "ไม่เอาเสียง" เปิดไว้และกดไม่ได้ (ได้ไฟล์ภาพอย่างเดียวอยู่แล้ว) */}
      <SwitchRow
        label={t.noAudio}
        hint={t.noAudioHint}
        checked={state.noAudio}
        disabled={video.audio.length === 0}
        onChange={(noAudio) => choose({ noAudio })}
      />

      <div className="flex flex-col gap-2">
        <div id={embedLabelId} className="text-sm font-medium">
          {t.embedSubs}
        </div>
        <DisabledReason reason={embedReason}>
          <Select<string>
            value={embedSubs ?? EMBED_NONE}
            disabled={embedDisabled}
            onValueChange={(value) => {
              if (value !== null) choose({ embedSubs: value === EMBED_NONE ? null : value })
            }}
          >
            <SelectTrigger
              aria-labelledby={embedLabelId}
              aria-describedby={embedHintId}
              className={SELECT_TRIGGER}
            >
              <SelectValue>
                {(value: string | null) => {
                  const track = tracks.find((item) => item.id === value)
                  return track ? trackLabel(track) : t.embedNone
                }}
              </SelectValue>
            </SelectTrigger>
            <SelectContent alignItemWithTrigger={false} align="start" className={SELECT_CONTENT}>
              <SelectItem value={EMBED_NONE}>{t.embedNone}</SelectItem>
              {tracks.map((track) => (
                <SelectItem key={track.id} value={track.id}>
                  {trackLabel(track)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </DisabledReason>
        {/* ช่องคำอธิบาย: กดไม่ได้ = เหตุผล (เห็นได้โดยไม่ต้องชี้เมาส์) · กดได้หรือรอรายการซับ = วิธีใช้ */}
        <p id={embedHintId} className="text-sm text-muted-foreground">
          {embedReason ?? t.embedHint}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Button disabled={pending} focusableWhenDisabled onClick={() => void submit()}>
          {pending ? <Spinner aria-hidden /> : <Download aria-hidden />}
          {t.download}
        </Button>
        {size !== undefined && (
          <span className="text-sm text-muted-foreground">{fill(t.estimate, { size: formatBytes(size) })}</span>
        )}
      </div>
    </DownloadCard>
  )
}

/**
 * แท็บวิดีโอ: เลือกคุณภาพ (ค่าแนะนำ = เปิดได้ทุกที่ ไม่เกิน 1080p) ความละเอียดสูงสุด ภาษาเสียง ไม่เอาเสียง ฝังซับ
 * แล้วกด "โหลด mp4" (ปุ่มหลักปุ่มเดียวของหน้า) ส่งงานเข้าคิว · ส่งสำเร็จ = จำตัวเลือกไว้ใช้กับคลิปถัดไป
 * รอข้อมูลคลิป = Skeleton · คลิปไม่มีภาพให้โหลด = Empty
 */
export function VideoPanel({ video, ...rest }: Omit<Props, "video"> & { video: VideoInfo | undefined }) {
  if (!video) return <DownloadSkeleton title={t.title} />
  if (video.video.length === 0) return <NoFormats title={t.title} />
  return <VideoForm video={video} {...rest} />
}
