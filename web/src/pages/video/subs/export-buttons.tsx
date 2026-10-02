import { Copy } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { ButtonGroup } from "@/components/ui/button-group"
import { Spinner } from "@/components/ui/spinner"
import { th } from "@/i18n/th"
import type { ClipRange } from "@/lib/advanced-options"
import { buildSubtitleParams } from "@/lib/download-options"
import { useEnqueue } from "@/lib/jobs"
import { rangeTokens, toTxt } from "@/lib/srt-builder"
import type { SubExportFormat, SubOptions, SubToken, SubtitleTrack } from "@/lib/types"

const t = th.subs

/** ข้อความ toast ตอนส่งเข้าคิว: "failed" ของคิวคือ "เพิ่มเข้าคิวไม่สำเร็จ" (addFailed) */
const ENQUEUE_MESSAGES = {
  added: th.queue.added,
  addedMany: th.queue.addedMany,
  failed: th.queue.addFailed,
  goHealth: th.queue.goHealth,
}

// owner round 2: เอาปุ่ม "โหลด .md" ออก (โน้ต .md อยู่ที่ปุ่ม "บันทึกเป็นโน้ต (.md)" ของหัวคลิป) · .txt = เนื้อหาเดียวกับ .srt ต่างแค่นามสกุล
const FORMATS: readonly { format: SubExportFormat; text: string }[] = [
  { format: "srt", text: t.downloadSrt },
  { format: "txt", text: t.downloadTxt },
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
  /** ช่วงเวลาที่ตั้งไว้ (null = ทั้งคลิป) ไฟล์และข้อความที่คัดลอกเป็นของช่วงนั้น */
  range: ClipRange | null
  /** ช่องเวลามี error: กดโหลดแล้วแสดง error แทนการส่งงาน (AC-ADV-02) */
  invalid: boolean
  onInvalid: () => void
  /** ป้ายปุ่ม เช่น "โหลด .srt (1:30-5:00)" */
  label: (base: string) => string
}

/**
 * ปุ่มโหลดไฟล์ซับ .srt / .txt (ปุ่มรอง) และปุ่ม "คัดลอกข้อความ"
 * M4: ปุ่มโหลดส่งงานเข้าคิว (ไฟล์ลงโฟลเดอร์ปลายทาง ดูความคืบหน้าที่แถบคิว) ไม่ใช่โหลดผ่านเบราว์เซอร์แล้ว
 * ยังไม่มีแทร็ก หรือโหลดคำของแทร็กไม่สำเร็จ = กดไม่ได้ทุกปุ่ม · ระหว่างส่งงานปุ่มที่กดมีวงหมุน และทุกปุ่มโหลดกดซ้ำไม่ได้ (แต่ยังโฟกัสได้ ลำดับ Tab ไม่กระโดด)
 */
export function ExportButtons({ videoId, track, options, tokens, failed, range, invalid, onInvalid, label }: Props) {
  const [busy, setBusy] = useState<SubExportFormat | null>(null)
  const { enqueue } = useEnqueue(ENQUEUE_MESSAGES)

  const unavailable = !track || failed

  async function download(format: SubExportFormat) {
    if (!track || failed || busy !== null) return
    if (invalid) {
      onInvalid()
      return
    }
    setBusy(format)
    try {
      const params = buildSubtitleParams({ trackId: track.id, format, options, range })
      await enqueue([{ videoId, kind: "subtitle", params }])
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <ButtonGroup aria-label={t.downloadGroup}>
        {FORMATS.map(({ format, text }) => (
          <Button
            key={format}
            variant="secondary"
            className={TOUCH}
            disabled={unavailable || busy !== null}
            focusableWhenDisabled
            onClick={() => void download(format)}
          >
            {busy === format && <Spinner aria-hidden />}
            {label(text)}
          </Button>
        ))}
      </ButtonGroup>
      <Button
        variant="ghost"
        className={TOUCH}
        disabled={unavailable || !tokens}
        focusableWhenDisabled
        onClick={() => {
          if (tokens) void copyTranscript(range ? rangeTokens(tokens, range.startMs, range.endMs) : tokens)
        }}
      >
        <Copy aria-hidden />
        {t.copyText}
      </Button>
    </div>
  )
}
