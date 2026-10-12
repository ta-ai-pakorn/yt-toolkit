import { useQuery } from "@tanstack/react-query"
import { useId, useRef } from "react"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { th } from "@/i18n/th"
import type { SubtitleTracks } from "@/lib/types"

import { AdvancedSection } from "./advanced/advanced-section"
import { revealRangeErrors, useAdvancedChoice } from "./advanced/use-advanced-choice"
import { videoQuery } from "./queries"
import { ExportButtons } from "./subs/export-buttons"
import { PresetControls } from "./subs/preset-controls"
import { SubsPreview } from "./subs/preview"
import { originalLanguage } from "./subs/track-groups"
import { TrackSelect } from "./subs/track-select"
import { tokensQuery } from "./subs-queries"
import { useSubSettings } from "./subs-settings"
import { SubtitleGate } from "./subtitle-gate"
import { trackInEffect } from "./track-label"
import { useVideoParams } from "./url-state"

const t = th.subs

function SubsBody({ videoId, data }: { videoId: string; data: SubtitleTracks }) {
  const titleId = useId()
  const { trackId, update } = useVideoParams()
  const track = trackInEffect(data, trackId)
  const settings = useSubSettings()
  const tokens = useQuery(tokensQuery(videoId, track?.id))
  // ข้อมูลคลิปจาก cache เท่านั้น (หน้า W2 โหลดไว้แล้ว) ไม่ยิงคำขอใหม่ ซึ่งจะนับว่าเปิดคลิปซ้ำ
  const video = useQuery({ ...videoQuery(videoId), enabled: false }).data
  const advanced = useAdvancedChoice(video, "subs", false)
  const range = advanced.params.range ?? null
  const originalLang = originalLanguage(data.tracks, video?.audio)
  const defaultTrackId = data.defaultTrackId
  // ยูทูปไม่ให้โหลดซับแปล: กลับไปแทร็กเริ่มต้นของคลิป (เปลี่ยนแค่แทร็กใน patch เดียว)
  // โฟกัสไปที่ช่องเลือกแทร็กก่อน (ปุ่มที่กดจะหายไป) ช่องนี้อยู่ต่อและบอกแทร็กใหม่ให้โปรแกรมอ่านหน้าจอ
  const triggerRef = useRef<HTMLButtonElement>(null)
  const backToOriginal = defaultTrackId
    ? () => {
        triggerRef.current?.focus()
        update({ trackId: defaultTrackId })
      }
    : null

  return (
    <section aria-labelledby={titleId}>
      <Card>
        <CardHeader>
          <CardTitle>
            <h2 id={titleId} className="text-base font-medium">
              {t.title}
            </h2>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          <TrackSelect
            data={data}
            track={track}
            originalLang={originalLang}
            // เปลี่ยนแค่แทร็ก (ส่งคีย์เดียว คีย์อื่นใน URL คงเดิม)
            onChoose={(id) => update({ trackId: id })}
            triggerRef={triggerRef}
          />
          <PresetControls options={settings.options} onPreset={settings.choosePreset} onCustom={settings.setCustom} />
          {video && <AdvancedSection video={video} tab="subs" choice={advanced} embedSubsOn={false} />}
          {track && (
            <>
              <Separator />
              <SubsPreview
                videoId={videoId}
                query={tokens}
                options={settings.options}
                onUseOriginal={backToOriginal}
                range={range}
              />
            </>
          )}
          {advanced.values.sponsorblock && !advanced.split && (
            <p className="text-sm text-warning">{th.advanced.subsWarning}</p>
          )}
          <ExportButtons
            videoId={videoId}
            track={track}
            options={settings.options}
            tokens={tokens.data?.tokens}
            failed={tokens.isError}
            range={range}
            invalid={advanced.invalid}
            onInvalid={() => revealRangeErrors(advanced, videoId, "subs")}
            label={advanced.label}
          />
        </CardContent>
      </Card>
    </section>
  )
}

/**
 * แท็บซับ: เลือกแทร็ก → เลือกความยาวซับ (สำเร็จรูปหรือปรับเอง) → ดูตัวอย่างสดในเบราว์เซอร์ → โหลดไฟล์หรือคัดลอกข้อความ
 * ความยาวซับที่เลือกจำไว้ในเบราว์เซอร์ · แทร็กที่เลือกอยู่ใน URL (?track=…) แท็บทรานสคริปต์ใช้แทร็กเดียวกัน
 */
export function SubsPanel({ videoId, enabled }: { videoId: string; enabled: boolean }) {
  return (
    <SubtitleGate videoId={videoId} enabled={enabled}>
      {(data) => <SubsBody videoId={videoId} data={data} />}
    </SubtitleGate>
  )
}
