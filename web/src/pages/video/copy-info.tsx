import { FileText, ListVideo } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { ButtonGroup } from "@/components/ui/button-group"
import { th } from "@/i18n/th"
import { formatChapters } from "@/lib/chapters"
import type { VideoInfo } from "@/lib/types"

const t = th.video

/** เขียนข้อความลงคลิปบอร์ดตามตัวอักษรทุกตัว (ไม่ตัดช่องว่างหรือบรรทัดว่าง) แล้วแจ้งด้วย toast */
async function copyText(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text)
    toast.success(t.copied)
  } catch {
    toast.error(t.copyFailed)
  }
}

/**
 * ปุ่มคัดลอกใต้บรรทัดข้อมูลคลิป: "คัดลอก chapter" (มี chapter เท่านั้น) และ "คัดลอกคำอธิบาย" (มีคำอธิบายเท่านั้น)
 * ไม่มีทั้งคู่ = ไม่แสดงกลุ่มปุ่มเลย · ("คัดลอกเครดิต" มากับการโหลดไฟล์ในเวอร์ชันถัดไป)
 */
export function CopyInfo({ video }: { video: VideoInfo }) {
  const hasChapters = video.chapters.length > 0
  const description = video.description ?? ""
  const hasDescription = description !== ""
  if (!hasChapters && !hasDescription) return null

  return (
    <ButtonGroup aria-label={t.copyGroup} className="-ml-2.5 flex-wrap">
      {hasChapters && (
        <Button variant="ghost" onClick={() => void copyText(formatChapters(video.chapters))}>
          <ListVideo aria-hidden />
          {t.copyChapters}
        </Button>
      )}
      {hasDescription && (
        <Button variant="ghost" onClick={() => void copyText(description)}>
          <FileText aria-hidden />
          {t.copyDescription}
        </Button>
      )}
    </ButtonGroup>
  )
}
