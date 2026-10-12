import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CircleX, FolderOpen } from "lucide-react"
import { useId, useRef, useState } from "react"
import { toast } from "sonner"

import { ErrorDetails } from "@/components/error-report/error-details"
import { showErrorToast } from "@/components/error-report/error-toast"
import { PLAIN_TOAST } from "@/components/error-report/model"
import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Field, FieldDescription, FieldError, FieldGroup, FieldTitle } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { th } from "@/i18n/th"
import { reportRequest } from "@/lib/report"
import { openOutputFolder, patchSettings, SETTINGS_KEY, settingsQuery } from "@/lib/settings-api"
import type { Settings } from "@/lib/types"
import { SwitchRow } from "@/pages/video/advanced/switch-row"

import {
  AUDIO_FORMATS,
  CAPTURE_QUALITIES,
  CONCURRENCY_CHOICES,
  VIDEO_DEFAULTS,
  choicePatch,
  displayed,
  languageOptions,
  outputDirPatch,
  serverMessage,
  type GeneralPatch,
} from "./general-form"

const t = th.general
const TOAST_ID = "settings-general"

export function GeneralPanel() {
  const queryClient = useQueryClient()
  const settings = useQuery(settingsQuery())

  // ข้อความใต้ช่องโฟลเดอร์เมื่อเซิร์ฟเวอร์ไม่รับ (ค่าที่บันทึกไว้ยังเป็นค่าเดิม)
  const [dirError, setDirError] = useState<string | null>(null)

  const save = useMutation({
    mutationFn: (patch: GeneralPatch) => patchSettings(patch),
    onSuccess: (next, patch) => {
      queryClient.setQueryData<Settings>(SETTINGS_KEY, next)
      // บันทึกช่องอื่นสำเร็จ ไม่ลบข้อความผิดของช่องโฟลเดอร์ที่ยังแก้ไม่เสร็จ
      if ("outputDir" in patch) setDirError(null)
      // ...PLAIN_TOAST: id เดียวกับ toast error ของการบันทึก ไม่ให้ปุ่มคัดลอก/เวลาค้างติดมากับ "บันทึกแล้ว" (P5)
      toast.success(t.saved, { ...PLAIN_TOAST, id: TOAST_ID })
    },
    onError: (error, patch) => {
      // ช่องโฟลเดอร์แสดงข้อความของเซิร์ฟเวอร์ใต้ช่อง ช่องอื่น (เลือกจากรายการ) แจ้งด้วย toast
      if ("outputDir" in patch) setDirError(serverMessage(error))
      else showErrorToast(serverMessage(error), { id: TOAST_ID, request: reportRequest(error, { context: "settings-general" }) })
    },
  })

  const open = useMutation({
    mutationFn: () => openOutputFolder(),
    onError: (error) =>
      showErrorToast(serverMessage(error), { id: "settings-open", request: reportRequest(error, { context: "settings-general" }) }),
  })

  // บันทึกล่าสุดที่ยังรออยู่: "เปิดโฟลเดอร์" รอให้บันทึกจบก่อน จะได้เปิดโฟลเดอร์ที่เพิ่งตั้ง (ไม่ปิดปุ่ม เพราะกดปุ่มทำให้ช่องเสียโฟกัสและบันทึกอัตโนมัติ)
  const lastSave = useRef<Promise<boolean>>(Promise.resolve(true))

  /** ส่งค่าไปบันทึก คืนผลว่าสำเร็จหรือไม่ (ข้อความผิดพลาดแสดงใน onError แล้ว) */
  function submit(patch: GeneralPatch): Promise<boolean> {
    const done = save.mutateAsync(patch).then(
      () => true,
      () => false
    )
    lastSave.current = done
    return done
  }

  if (settings.isPending) {
    return (
      <div className="flex max-w-xl flex-col gap-5" aria-busy="true">
        {Array.from({ length: 7 }, (_, i) => (
          <Skeleton key={i} className="h-14 w-full" />
        ))}
      </div>
    )
  }

  if (settings.isError) {
    return (
      <Alert variant="destructive">
        <CircleX aria-hidden />
        <AlertTitle>{t.loadError}</AlertTitle>
        <AlertDescription>{settings.error.message}</AlertDescription>
        <ErrorDetails key={settings.errorUpdatedAt} error={settings.error} context="settings-general" className="col-start-2" />
        <AlertAction>
          <Button variant="outline" size="sm" disabled={settings.isFetching} onClick={() => void settings.refetch()}>
            {th.common.retry}
          </Button>
        </AlertAction>
      </Alert>
    )
  }

  const shown = displayed(settings.data, save.isPending ? save.variables : null)

  function choose(patch: GeneralPatch | null) {
    if (patch) void submit(patch)
  }

  return (
    <FieldGroup className="max-w-xl">
      <OutputDirField
        saved={settings.data.outputDir}
        error={dirError}
        onClearError={() => setDirError(null)}
        onSave={submit}
        onOpen={() => void lastSave.current.then(() => open.mutate())}
        opening={open.isPending}
      />

      <Field>
        <FieldTitle id="general-concurrency">{t.concurrency}</FieldTitle>
        <ToggleGroup
          aria-labelledby="general-concurrency"
          aria-describedby="general-concurrency-hint"
          variant="outline"
          spacing={0}
          // กดปุ่มที่เลือกอยู่ซ้ำจะได้ค่าว่าง: ไม่ทำอะไร (ต้องมีค่าเสมอ)
          value={[String(shown.concurrency)]}
          onValueChange={(value) => {
            const next = CONCURRENCY_CHOICES.find((n) => String(n) === value[0])
            if (next) choose(choicePatch("concurrency", next, shown))
          }}
        >
          {CONCURRENCY_CHOICES.map((n) => (
            <ToggleGroupItem key={n} value={String(n)} className="px-4">
              {n}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <FieldDescription id="general-concurrency-hint">{t.concurrencyHint}</FieldDescription>
      </Field>

      <Field>
        <FieldTitle id="general-language">{t.audioLanguage}</FieldTitle>
        <ChoiceSelect
          labelId="general-language"
          hintId="general-language-hint"
          value={shown.audioLanguage}
          options={languageOptions(shown.audioLanguage)}
          onChange={(value) => choose(choicePatch("audioLanguage", value, shown))}
        />
        <FieldDescription id="general-language-hint">{t.audioLanguageHint}</FieldDescription>
      </Field>

      <Field>
        <FieldTitle id="general-video">{t.videoDefault}</FieldTitle>
        <ChoiceSelect
          labelId="general-video"
          value={shown.videoDefault}
          options={VIDEO_DEFAULTS.map((value) => ({ value, label: t.videoDefaults[value] }))}
          onChange={(value) => {
            const next = VIDEO_DEFAULTS.find((v) => v === value)
            if (next) choose(choicePatch("videoDefault", next, shown))
          }}
        />
      </Field>

      {/* M5 รอบ B2 spec 2.4: ความละเอียดของ "ถ่ายภาพคมตรงนี้" (เพดานนับที่ด้านสั้น) */}
      <Field>
        <FieldTitle id="general-capture">{t.captureQuality}</FieldTitle>
        <ChoiceSelect
          labelId="general-capture"
          hintId="general-capture-hint"
          value={shown.captureQuality}
          options={CAPTURE_QUALITIES.map((value) => ({ value, label: t.captureQualities[value] }))}
          onChange={(value) => {
            const next = CAPTURE_QUALITIES.find((q) => q === value)
            if (next) choose(choicePatch("captureQuality", next, shown))
          }}
        />
        <FieldDescription id="general-capture-hint">{t.captureQualityHint}</FieldDescription>
      </Field>

      <Field>
        <FieldTitle id="general-audio">{t.audioDefault}</FieldTitle>
        <ToggleGroup
          aria-labelledby="general-audio"
          variant="outline"
          spacing={0}
          value={[shown.audioDefault]}
          onValueChange={(value) => {
            const next = AUDIO_FORMATS.find((f) => f === value[0])
            if (next) choose(choicePatch("audioDefault", next, shown))
          }}
        >
          {AUDIO_FORMATS.map((format) => (
            <ToggleGroupItem key={format} value={format} className="px-4">
              {th.download.audio.formats[format]}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </Field>

      {/* M5 รอบ B (D6): ภาพคมจากไฟล์วิดีโอที่โหลดแล้ว เปิดไว้ตั้งต้น */}
      <SwitchRow
        label={t.autoSharpFrames}
        hint={t.autoSharpFramesHint}
        checked={shown.autoSharpFrames}
        onChange={(checked) => choose(choicePatch("autoSharpFrames", checked, shown))}
      />
    </FieldGroup>
  )
}

type ChoiceSelectProps = {
  labelId: string
  hintId?: string
  value: string
  options: { value: string; label: string }[]
  onChange: (value: string) => void
}

function ChoiceSelect({ labelId, hintId, value, options, onChange }: ChoiceSelectProps) {
  const labels = new Map(options.map((o) => [o.value, o.label]))
  return (
    <Select<string> value={value} onValueChange={(next) => next && onChange(next)}>
      <SelectTrigger aria-labelledby={labelId} aria-describedby={hintId} className="w-full min-w-0 sm:w-72">
        <SelectValue>{(current: string | null) => (current ? (labels.get(current) ?? current) : "")}</SelectValue>
      </SelectTrigger>
      <SelectContent alignItemWithTrigger={false} align="start">
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

type OutputDirFieldProps = {
  saved: string
  error: string | null
  onClearError: () => void
  onSave: (patch: GeneralPatch) => Promise<boolean>
  onOpen: () => void
  opening: boolean
}

/** ช่องโฟลเดอร์: พิมพ์แล้วบันทึกเมื่อกด Enter หรือออกจากช่อง (เมื่อค่าเปลี่ยน) · Esc คืนค่าที่บันทึกไว้ */
function OutputDirField({ saved, error, onClearError, onSave, onOpen, opening }: OutputDirFieldProps) {
  const inputId = useId()
  const hintId = useId()
  const errorId = useId()
  const [draft, setDraft] = useState<string | null>(null)
  // ค่าที่เพิ่งส่งไป: กด Enter แล้วออกจากช่องต่อ จะไม่ส่งซ้ำ (และค่าที่ถูกปฏิเสธไม่ถูกส่งซ้ำจนกว่าจะแก้)
  const attempted = useRef<string | null>(null)
  const text = draft ?? saved

  function commit() {
    if (draft === null || draft === attempted.current) return
    const patch = outputDirPatch(draft, saved)
    if (!patch) return
    const submitted = draft
    attempted.current = submitted
    // บันทึกสำเร็จ: คืนช่องให้แสดงค่าที่เซิร์ฟเวอร์เก็บจริง (อาจปรับรูปแบบที่อยู่แล้ว) ถ้าระหว่างรอยังไม่ได้พิมพ์ต่อ
    void onSave(patch).then((ok) => {
      if (ok) setDraft((current) => (current === submitted ? null : current))
    })
  }

  return (
    <Field data-invalid={error ? true : undefined}>
      <FieldTitle>
        <label htmlFor={inputId}>{t.outputDir}</label>
      </FieldTitle>
      <div className="flex flex-wrap items-start gap-2">
        <Input
          id={inputId}
          value={text}
          spellCheck={false}
          autoComplete="off"
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${hintId} ${errorId}` : hintId}
          className="min-w-0 flex-1 basis-64 font-mono"
          onChange={(event) => {
            attempted.current = null
            if (error) onClearError()
            setDraft(event.target.value)
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") commit()
            if (event.key === "Escape") {
              attempted.current = null
              onClearError()
              setDraft(null)
            }
          }}
          onBlur={() => {
            commit()
            // ค่าที่พิมพ์ถูกบันทึกแล้ว (เท่าค่าที่บันทึกไว้) กลับไปตามค่าที่บันทึก
            if (draft !== null && outputDirPatch(draft, saved) === null) setDraft(null)
          }}
        />
        <Button type="button" variant="secondary" disabled={opening} onClick={onOpen}>
          <FolderOpen data-icon="inline-start" aria-hidden />
          {t.openOutput}
        </Button>
      </div>
      <FieldDescription id={hintId}>{t.outputDirHint}</FieldDescription>
      {error && <FieldError id={errorId}>{error}</FieldError>}
    </Field>
  )
}
