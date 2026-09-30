import { SubtitleGate } from "./subtitle-gate"

/** แท็บทรานสคริปต์: ตอนนี้มีแค่ด่าน 4 สถานะ (รายการบรรทัดและการค้นหามาทีหลัง) */
export function TranscriptPanel({ videoId, enabled }: { videoId: string; enabled: boolean }) {
  return (
    <SubtitleGate videoId={videoId} enabled={enabled}>
      {() => null}
    </SubtitleGate>
  )
}
