import { useId, useMemo, useRef, useState } from "react"

import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { th } from "@/i18n/th"
import type { SubtitleTrack, SubtitleTracks } from "@/lib/types"

import { trackLabel } from "../track-label"
import { buildTrackGroups } from "./track-groups"
import { TranslatedDialog } from "./translated-dialog"

const t = th.subs

// แถวสุดท้ายของรายการ: ไม่ใช่แทร็ก แต่เปิดกล่องเลือกซับแปลอัตโนมัติ (รูปแบบนี้ไม่มีทางชนกับรหัสแทร็ก o./a./t.)
const OPEN_TRANSLATED = "open-translated"

type Props = {
  data: SubtitleTracks
  /** แทร็กที่ใช้อยู่ (URL ก่อน ไม่มีค่อยใช้แทร็กเริ่มต้น) null = ยังไม่ได้เลือก */
  track: SubtitleTrack | null
  /** ภาษาต้นฉบับของคลิป (รหัสหลัก) แทร็กภาษานี้ขึ้นก่อนในแต่ละกลุ่ม */
  originalLang: string | null
  onChoose: (trackId: string) => void
}

/**
 * ตัวเลือกแทร็กซับ: กลุ่มซับจากเจ้าของคลิป · ซับอัตโนมัติภาษาต้นฉบับ และแถวสุดท้าย "เลือกซับแปลอัตโนมัติ…"
 * ยังไม่มีแทร็ก = ช่องว่างพร้อมคำแนะนำใต้ช่อง · ซับแปลที่เลือกไว้แสดงในช่องเป็น "… (แปลอัตโนมัติ)"
 */
export function TrackSelect({ data, track, originalLang, onChoose }: Props) {
  const labelId = useId()
  const hintId = useId()
  const [dialogOpen, setDialogOpen] = useState(false)
  // เลือกแถว "ซับแปลอัตโนมัติ…" แล้วรอให้รายการปิดสนิท (คืนโฟกัสให้ช่องเลือกแล้ว) ค่อยเปิดกล่อง
  const openAfterClose = useRef(false)

  const groups = useMemo(() => buildTrackGroups(data.tracks, originalLang), [data.tracks, originalLang])
  const hasTranslated = data.tracks.some((item) => item.group === "translated")
  // ชื่อของทุกแทร็ก (รวมซับแปลที่ไม่อยู่ในรายการ) ให้ช่องเลือกแสดงชื่อของแทร็กที่เลือกได้เสมอ
  const labels = useMemo(() => new Map(data.tracks.map((item) => [item.id, trackLabel(item)])), [data.tracks])

  function onValueChange(value: string | null) {
    if (value === OPEN_TRANSLATED) {
      openAfterClose.current = true
      return
    }
    if (value && value !== track?.id) onChoose(value)
  }

  function onOpenChangeComplete(open: boolean) {
    if (!open && openAfterClose.current) {
      openAfterClose.current = false
      setDialogOpen(true)
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div id={labelId} className="text-sm font-medium">
        {t.trackLabel}
      </div>
      <Select<string>
        value={track?.id ?? null}
        onValueChange={onValueChange}
        onOpenChangeComplete={onOpenChangeComplete}
      >
        <SelectTrigger
          aria-labelledby={labelId}
          aria-describedby={track ? undefined : hintId}
          className="w-full min-w-0 sm:w-80 max-sm:h-11!"
        >
          <SelectValue>{(value: string | null) => (value ? (labels.get(value) ?? value) : t.trackPlaceholder)}</SelectValue>
        </SelectTrigger>
        <SelectContent alignItemWithTrigger={false} align="start">
          {groups.map(({ group, tracks }) => (
            <SelectGroup key={group}>
              <SelectLabel>{t.groups[group]}</SelectLabel>
              {tracks.map((item) => (
                <SelectItem key={item.id} value={item.id} className="max-sm:min-h-11">
                  {trackLabel(item)}
                </SelectItem>
              ))}
            </SelectGroup>
          ))}
          {hasTranslated && (
            <>
              {groups.length > 0 && <SelectSeparator />}
              <SelectGroup>
                <SelectItem value={OPEN_TRANSLATED} className="max-sm:min-h-11">
                  {t.openTranslated}
                </SelectItem>
              </SelectGroup>
            </>
          )}
        </SelectContent>
      </Select>
      {!track && (
        <p id={hintId} className="text-sm text-muted-foreground">
          {t.pickHint}
        </p>
      )}
      <TranslatedDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        tracks={data.tracks}
        selectedId={track?.id ?? null}
        onChoose={onChoose}
      />
    </div>
  )
}
