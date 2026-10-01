import { Copy } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { ButtonGroup } from "@/components/ui/button-group"
import { Spinner } from "@/components/ui/spinner"
import { th } from "@/i18n/th"
import { useEnqueue } from "@/lib/jobs"
import { toTxt } from "@/lib/srt-builder"
import type { SubExportFormat, SubOptions, SubToken, SubtitleTrack } from "@/lib/types"

const t = th.subs

/** ข้อความ toast ตอนส่งเข้าคิว: "failed" ของคิวคือ "เพิ่มเข้าคิวไม่สำเร็จ" (addFailed) */
const ENQUEUE_MESSAGES = {
  added: th.queue.added,
  addedMany: th.queue.addedMany,
  failed: th.queue.addFailed,
  goHealth: th.queue.goHealth,
}

const FORMATS: readonly { format: SubExportFormat; label: string }[] = [
  { format: "srt", label: t.downloadSrt },
  { format: "txt", label: t.downloadTxt },
  { format: "md", label: t.downloadMd },
]

// จอแคบ (มือถือ) ปุ่มสูง 44 px ให้นิ้วกดได้ง่าย
const TOUCH = "max-sm:h-11"

/** ข้อความล้วนของทั้งแทร็กลงคลิปบอร์ด (ขึ้นบรรทัดแบบ \n ตามปกติของคลิปบอร์ด ไม่ใช่ CRLF ของไฟล์) */
async function copyTranscript(tokens: readonly SubToken[]): Promise<void> {
  try {
    await navigator.clipboard.writeText(toTxt(tokens).replace(/\r\n/g, "\n"))
    toast.success(t.textCopied)
  } catch {
    toast.error(t.copyFailed)
  }
}

type Props = {
  videoId: string
  /** แทร็กที่ใช้อยู่ null = ยังไม่ได้เลือก (ทุกปุ่มกดไม่ได้) */
  track: SubtitleTrack | null
  /** ตัวเลือกความยาวซับ (บีบช่วงแล้วจาก useSubSettings) ใช้กับไฟล์ .srt */
  options: SubOptions
  /** คำของแทร็กนี้ (ยังโหลดไม่เสร็จ = ปุ่มคัดลอกกดไม่ได้) */
  tokens: readonly SubToken[] | undefined
  /**
   * โหลดคำของแทร็กนี้ไม่สำเร็จ (error ใดก็ได้ เช่น ไม่มีข้อความ ยูทูปไม่ให้โหลดซับแปล หรือซับแปลกำลังรอเซสชันอยู่)
   * โหลดไฟล์ไปก็ได้ error เดิม จึงกดไม่ได้ทุกปุ่ม (ระหว่างนับถอยหลังของซับแปลก็กดไม่ได้)
   */
  failed: boolean
}

/**
 * ปุ่มโหลดไฟล์ซับ .srt / .txt / .md (ปุ่มรอง) และปุ่ม "คัดลอกข้อความ"
 * M4: ปุ่มโหลดส่งงานเข้าคิว (ไฟล์ลงโฟลเดอร์ปลายทาง ดูความคืบหน้าที่แถบคิว) ไม่ใช่โหลดผ่านเบราว์เซอร์แล้ว
 * ยังไม่มีแทร็ก หรือโหลดคำของแทร็กไม่สำเร็จ = กดไม่ได้ทุกปุ่ม · ระหว่างส่งงานปุ่มที่กดมีวงหมุน และทุกปุ่มโหลดกดซ้ำไม่ได้ (แต่ยังโฟกัสได้ ลำดับ Tab ไม่กระโดด)
 */
export function ExportButtons({ videoId, track, options, tokens, failed }: Props) {
  const [busy, setBusy] = useState<SubExportFormat | null>(null)
  const { enqueue } = useEnqueue(ENQUEUE_MESSAGES)

  const unavailable = !track || failed

  async function download(format: SubExportFormat) {
    if (!track || failed || busy !== null) return
    setBusy(format)
    try {
      await enqueue([{ videoId, kind: "subtitle", params: { trackId: track.id, format, options } }])
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <ButtonGroup aria-label={t.downloadGroup}>
        {FORMATS.map(({ format, label }) => (
          <Button
            key={format}
            variant="secondary"
            className={TOUCH}
            disabled={unavailable || busy !== null}
            focusableWhenDisabled
            onClick={() => void download(format)}
          >
            {busy === format && <Spinner aria-hidden />}
            {label}
          </Button>
        ))}
      </ButtonGroup>
      <Button
        variant="ghost"
        className={TOUCH}
        disabled={unavailable || !tokens}
        focusableWhenDisabled
        onClick={() => {
          if (tokens) void copyTranscript(tokens)
        }}
      >
        <Copy aria-hidden />
        {t.copyText}
      </Button>
    </div>
  )
}
