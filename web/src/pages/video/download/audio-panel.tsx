import { Download } from "lucide-react"
import { useId } from "react"

import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Spinner } from "@/components/ui/spinner"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { fill, th } from "@/i18n/th"
import { scaleBytes } from "@/lib/advanced-options"
import { audioSizeEstimate, buildAudioParams, wavBytes } from "@/lib/download-options"
import { formatBytes } from "@/lib/format"
import { useEnqueue } from "@/lib/jobs"
import type { VideoInfo } from "@/lib/types"

import { AdvancedSection } from "../advanced/advanced-section"
import { revealRangeErrors, useAdvancedChoice } from "../advanced/use-advanced-choice"
import { AudioLanguageSelect, SELECT_CONTENT, SELECT_TRIGGER } from "./audio-language-select"
import {
  AUDIO_FORMATS,
  audioPrefsPatch,
  ENQUEUE_MESSAGES,
  MP3_BITRATES,
  useDownloadState,
  wavSourceTrack,
  type DownloadChoices,
} from "./use-download-state"
import { DownloadCard, DownloadSkeleton, NoFormats } from "./video-panel"

const t = th.download.audio

const kbpsLabel = (n: number) => fill(t.kbps, { n })

type Props = {
  video: VideoInfo
  choices: DownloadChoices
  choose: (patch: DownloadChoices) => void
}

function AudioForm({ video, choices, choose }: Props) {
  const formatLabelId = useId()
  const formatHintId = useId()
  const bitrateLabelId = useId()
  const { state, languages, remember, ready } = useDownloadState(video, choices)
  const { enqueue, pending } = useEnqueue(ENQUEUE_MESSAGES)
  // แยก chapter ถูกกันด้วยการฝังซับที่เลือกไว้ในแท็บวิดีโอ (ค่าชุดเดียวกันทุกแท็บ)
  const advanced = useAdvancedChoice(video, "audio", choices.embedSubs != null)

  const source = wavSourceTrack(video.audio)
  const hint = state.audioFormat === "m4a" ? t.m4aHint : state.audioFormat === "mp3" ? t.mp3Hint : t.wavHint
  const fullSize =
    state.audioFormat === "wav"
      ? wavBytes(video.durationS, source?.sampleRate, source?.channels)
      : audioSizeEstimate(video, state.audioFormat, state.mp3Kbps, state.audioLanguage)
  const size = scaleBytes(fullSize, video.durationS, advanced.keptS)

  async function submit() {
    if (pending || !ready) return
    if (advanced.invalid) {
      revealRangeErrors(advanced, video.videoId, "audio")
      return
    }
    const params = buildAudioParams({
      format: state.audioFormat,
      mp3Kbps: state.mp3Kbps,
      audioLanguage: state.audioLanguage,
      advanced: advanced.params,
    })
    const ok = await enqueue([{ videoId: video.videoId, kind: "audio", params, title: video.title }])
    if (ok) remember(audioPrefsPatch(state, languages))
  }

  return (
    <DownloadCard title={t.title}>
      <div className="flex flex-col gap-2">
        <div id={formatLabelId} className="text-sm font-medium">
          {t.format}
        </div>
        <ToggleGroup
          aria-labelledby={formatLabelId}
          aria-describedby={formatHintId}
          variant="outline"
          spacing={0}
          value={[state.audioFormat]}
          // กดปุ่มที่เลือกอยู่ซ้ำได้ค่าว่าง: ไม่ทำอะไร (ต้องมีรูปแบบไฟล์เสมอ)
          onValueChange={(value) => {
            const next = AUDIO_FORMATS.find((format) => format === value[0])
            if (next) choose({ audioFormat: next })
          }}
        >
          {AUDIO_FORMATS.map((format) => (
            <ToggleGroupItem key={format} value={format} className="px-4">
              {t.formats[format]}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <p id={formatHintId} className="text-sm text-muted-foreground">
          {hint}
        </p>
      </div>

      {state.audioFormat === "mp3" && (
        <div className="flex flex-col gap-2">
          <div id={bitrateLabelId} className="text-sm font-medium">
            {t.mp3Bitrate}
          </div>
          <Select<string>
            value={String(state.mp3Kbps)}
            onValueChange={(value) => {
              const next = MP3_BITRATES.find((kbps) => String(kbps) === value)
              if (next) choose({ mp3Kbps: next })
            }}
          >
            <SelectTrigger aria-labelledby={bitrateLabelId} className={SELECT_TRIGGER}>
              <SelectValue>{(value: string | null) => (value ? kbpsLabel(Number(value)) : "")}</SelectValue>
            </SelectTrigger>
            <SelectContent alignItemWithTrigger={false} align="start" className={SELECT_CONTENT}>
              {MP3_BITRATES.map((kbps) => (
                <SelectItem key={kbps} value={String(kbps)}>
                  {kbpsLabel(kbps)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      <AudioLanguageSelect options={languages} value={state.audioLanguage} onChange={(audioLanguage) => choose({ audioLanguage })} />

      <AdvancedSection video={video} tab="audio" choice={advanced} embedSubsOn={false} />

      {/* owner (M4 preview): ปุ่มหลักหน้าตาเดียวกับ "โหลด mp4" ในแท็บวิดีโอ พร้อมขนาดโดยประมาณ */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Button disabled={pending || !ready} focusableWhenDisabled onClick={() => void submit()}>
          {pending ? <Spinner aria-hidden /> : <Download aria-hidden />}
          {advanced.label(fill(t.download, { format: state.audioFormat }))}
        </Button>
        {size !== undefined && (
          <span className="text-sm text-muted-foreground">{fill(th.download.video.estimate, { size: formatBytes(size) })}</span>
        )}
      </div>
    </DownloadCard>
  )
}

/**
 * แท็บเสียง: m4a (แนะนำ) / mp3 (เลือกบิตเรต) / wav (บอกขนาดโดยประมาณ) และภาษาเสียง (ค่าเดียวกับแท็บวิดีโอ)
 * แล้วกด "โหลด m4a/mp3/wav" (ปุ่มหลัก) ส่งงานเข้าคิว · รอข้อมูลคลิป = Skeleton · คลิปไม่มีเสียงให้โหลด = Empty
 */
export function AudioPanel({ video, ...rest }: Omit<Props, "video"> & { video: VideoInfo | undefined }) {
  if (!video) return <DownloadSkeleton title={t.title} />
  if (video.audio.length === 0) return <NoFormats title={t.title} />
  return <AudioForm video={video} {...rest} />
}
