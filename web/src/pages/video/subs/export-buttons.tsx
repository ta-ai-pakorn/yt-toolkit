import { Copy } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { ButtonGroup } from "@/components/ui/button-group"
import { Spinner } from "@/components/ui/spinner"
import { th } from "@/i18n/th"
import { downloadFile } from "@/lib/download"
import { exportPath } from "@/lib/sub-options"
import { toTxt } from "@/lib/srt-builder"
import type { SubExportFormat, SubOptions, SubToken, SubtitleTrack } from "@/lib/types"

import { errorMessage } from "../errors"

const t = th.subs

const FORMATS: readonly { format: SubExportFormat; label: string }[] = [
  { format: "srt", label: t.downloadSrt },
  { format: "txt", label: t.downloadTxt },
  { format: "md", label: t.downloadMd },
]

// จอแคบ (มือถือ) ปุ่มสูง 44 px ให้นิ้วกดได้ง่าย
const TOUCH = "max-sm:h-11"

/** โหลดไฟล์ผ่านเบราว์เซอร์ พร้อม toast บอกสถานะ: error ขึ้นข้อความไทยจาก backend แทนที่จะได้ไฟล์ JSON */
async function downloadWithToast(url: string, fallbackName: string): Promise<void> {
  const id = toast.loading(t.preparing)
  try {
    await downloadFile(url, fallbackName)
    toast.dismiss(id)
  } catch (error) {
    toast.error(errorMessage(error, t.downloadFailed), { id })
  }
}

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
}

/**
 * ปุ่มโหลดไฟล์ซับ .srt / .txt / .md (ปุ่มรอง เบราว์เซอร์โหลดลงเครื่องทันที) และปุ่ม "คัดลอกข้อความ"
 * ระหว่างเตรียมไฟล์ปุ่มที่กดมีวงหมุน และทุกปุ่มโหลดกดซ้ำไม่ได้ (แต่ยังโฟกัสได้ ลำดับ Tab ไม่กระโดด)
 */
export function ExportButtons({ videoId, track, options, tokens }: Props) {
  const [busy, setBusy] = useState<SubExportFormat | null>(null)

  async function download(format: SubExportFormat) {
    if (!track || busy !== null) return
    setBusy(format)
    try {
      await downloadWithToast(exportPath(videoId, track.id, format, options), `subtitles.${track.lang}.${format}`)
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
            disabled={!track || busy !== null}
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
        disabled={!track || !tokens}
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
