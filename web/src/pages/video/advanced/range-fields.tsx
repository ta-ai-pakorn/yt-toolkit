import { Clock } from "lucide-react"
import { useId } from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { fill, th } from "@/i18n/th"
import type { RangeError } from "@/lib/advanced-options"
import { formatDuration } from "@/lib/format"
import type { VideoInfo } from "@/lib/types"

import { getPlayerState, usePlayerValue, type PlayerStatus } from "../player/player-store"
import { fieldId, type AdvancedChoice, type AdvancedTab } from "./use-advanced-choice"

const t = th.advanced

/** ตัวเล่นเริ่มเล่นคลิปนี้แล้ว (มีเวลาให้ใช้) */
const PLAYING: ReadonlySet<PlayerStatus> = new Set(["playing", "paused", "ended"])

function errorText(error: RangeError, durationS: number): string {
  return error === "beyond" ? fill(t.errors.beyond, { duration: formatDuration(durationS) }) : t.errors[error]
}

type FieldProps = {
  id: string
  label: string
  value: string
  error: RangeError | null
  durationS: number
  disabled: boolean
  playerReady: boolean
  onChange: (text: string) => void
  onBlur: () => void
}

/** ช่องเวลา + ปุ่มไอคอน "ใช้เวลาที่ตัวเล่นอยู่ตอนนี้" (D7) · error สีแดงใต้ช่อง ผูกด้วย aria-describedby */
function TimeField({ id, label, value, error, durationS, disabled, playerReady, onChange, onBlur }: FieldProps) {
  const errorId = `${id}-error`
  const message = error === null ? null : errorText(error, durationS)
  const fromPlayer = () => onChange(formatDuration(Math.floor(getPlayerState().currentMs / 1000)))
  return (
    <div role="group" aria-label={label} className="flex flex-col gap-1">
      <Label htmlFor={id}>{label}</Label>
      <div className="flex items-center gap-1">
        <Input
          id={id}
          value={value}
          inputMode="text"
          autoComplete="off"
          spellCheck={false}
          disabled={disabled}
          aria-invalid={message !== null || undefined}
          aria-describedby={message !== null ? errorId : undefined}
          className="w-28"
          onChange={(event) => onChange(event.target.value)}
          onBlur={onBlur}
        />
        <Tooltip>
          <TooltipTrigger render={<span className="inline-flex [&_button:disabled]:pointer-events-none" />}>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={t.usePlayerTime}
              disabled={disabled || !playerReady}
              focusableWhenDisabled
              onClick={fromPlayer}
            >
              <Clock aria-hidden />
            </Button>
          </TooltipTrigger>
          <TooltipContent>{playerReady ? t.usePlayerTime : t.playFirst}</TooltipContent>
        </Tooltip>
      </div>
      {message !== null && (
        <p id={errorId} className="text-sm text-destructive">
          {message}
        </p>
      )}
    </div>
  )
}

/**
 * "ช่วงเวลา": ช่อง "เริ่ม" / "จบ" (ss, m:ss, mm:ss, h:mm:ss) · คลิปสด/ไม่รู้ความยาว หรือแยก chapter เปิดอยู่ = กดไม่ได้พร้อมเหตุผล
 * error แสดงหลังออกจากช่อง กดตั้งจุด หรือกดโหลด (values.checked) · แท็บวิดีโอที่มีช่วงแล้ว = บอกว่าตัดเป๊ะแต่ใช้เวลาเพิ่ม
 */
export function RangeFields({ video, tab, choice }: { video: VideoInfo; tab: AdvancedTab; choice: AdvancedChoice }) {
  const noteId = useId()
  const { values, patch, check } = choice
  const playerReady = usePlayerValue((s) => s.videoId === video.videoId && s.started && PLAYING.has(s.status))
  const disabled = !choice.rangeOk || choice.split
  const note = !choice.rangeOk ? t.rangeUnavailable : choice.split ? t.blocked.chapters : null
  const shown = (error: RangeError | null) => (values.checked ? error : null)
  return (
    <fieldset aria-describedby={note !== null ? noteId : undefined} className="flex min-w-0 flex-col gap-2">
      <legend className="mb-2 text-sm font-medium">{t.range}</legend>
      <div className="flex flex-wrap gap-x-6 gap-y-3">
        <TimeField
          id={fieldId("start", tab)}
          label={t.start}
          value={values.startText}
          error={shown(check.startError)}
          durationS={video.durationS}
          disabled={disabled}
          playerReady={playerReady}
          onChange={(startText) => patch({ startText })}
          onBlur={() => patch({ checked: true })}
        />
        <TimeField
          id={fieldId("end", tab)}
          label={t.end}
          value={values.endText}
          error={shown(check.endError)}
          durationS={video.durationS}
          disabled={disabled}
          playerReady={playerReady}
          onChange={(endText) => patch({ endText })}
          onBlur={() => patch({ checked: true })}
        />
      </div>
      {note !== null && (
        <p id={noteId} className="text-sm text-muted-foreground">
          {note}
        </p>
      )}
      {tab === "video" && check.range !== null && <p className="text-sm text-muted-foreground">{t.exactHint}</p>}
    </fieldset>
  )
}
