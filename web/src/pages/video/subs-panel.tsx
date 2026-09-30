import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useId } from "react"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { th } from "@/i18n/th"
import type { SubtitleTracks, VideoInfo } from "@/lib/types"

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
  // อ่านข้อมูลคลิปจาก cache เท่านั้น (หน้า W2 โหลดไว้แล้ว) ไม่สร้างคำขอใหม่ ซึ่งจะนับว่าเปิดคลิปซ้ำ
  const video = useQueryClient().getQueryData<VideoInfo>(videoQuery(videoId).queryKey)
  const originalLang = originalLanguage(data.tracks, video?.audio)
  const defaultTrackId = data.defaultTrackId
  // ยูทูปไม่ให้โหลดซับแปล: กลับไปแทร็กเริ่มต้นของคลิป (เปลี่ยนแค่แทร็กใน patch เดียว)
  const backToOriginal = defaultTrackId ? () => update({ trackId: defaultTrackId }) : null

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
          />
          <PresetControls options={settings.options} onPreset={settings.choosePreset} onCustom={settings.setCustom} />
          {track && (
            <>
              <Separator />
              <SubsPreview query={tokens} options={settings.options} onUseOriginal={backToOriginal} />
            </>
          )}
          <ExportButtons
            videoId={videoId}
            track={track}
            options={settings.options}
            tokens={tokens.data?.tokens}
            failed={tokens.isError}
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
