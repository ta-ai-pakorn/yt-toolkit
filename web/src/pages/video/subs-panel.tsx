import { SubtitleGate } from "./subtitle-gate"

/** แท็บซับ: ตอนนี้มีแค่ด่าน 4 สถานะ (ตัวเลือกแทร็ก ความยาวซับ และปุ่มโหลดมาทีหลัง) */
export function SubsPanel({ videoId, enabled }: { videoId: string; enabled: boolean }) {
  return (
    <SubtitleGate videoId={videoId} enabled={enabled}>
      {() => null}
    </SubtitleGate>
  )
}
