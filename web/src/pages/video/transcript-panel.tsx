import { useQuery } from "@tanstack/react-query"
import { CaptionsOff, Search, X } from "lucide-react"
import { useDeferredValue, useMemo, useRef, useState, type KeyboardEvent } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia } from "@/components/ui/empty"
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from "@/components/ui/input-group"
import { Skeleton } from "@/components/ui/skeleton"
import { fill, th } from "@/i18n/th"
import type { Cue, SubtitleTrack, SubtitleTracks } from "@/lib/types"

import { cueIndexAt } from "./frame-target"
import { LoadError } from "./load-error"
import { tokensQuery } from "./subs-queries"
import { useSubSettings } from "./subs-settings"
import { SubtitleGate } from "./subtitle-gate"
import { trackInEffect, trackLabel } from "./track-label"
import { LineList } from "./transcript/line-list"
import { prepareLines, searchNeedle, searchPrepared } from "./transcript/search"
import { useCues } from "./use-cues"
import { useVideoParams } from "./url-state"

const t = th.transcript

const SKELETON_ROWS = 6

function LinesSkeleton() {
  return (
    <div className="flex flex-col gap-2" aria-busy="true">
      <span className="sr-only" role="status">
        {th.subs.loading}
      </span>
      {Array.from({ length: SKELETON_ROWS }, (_, index) => (
        <Skeleton key={index} className="h-7 w-full" />
      ))}
    </div>
  )
}

function NoLines() {
  return (
    <Empty className="border">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <CaptionsOff aria-hidden />
        </EmptyMedia>
        <EmptyDescription>{th.subs.none}</EmptyDescription>
      </EmptyHeader>
    </Empty>
  )
}

/** ไม่มีแทร็กที่ใช้อยู่ (คลิปมีแต่ซับแปลอัตโนมัติ) ผู้ใช้ต้องเลือกแทร็กเองที่แท็บซับก่อน */
function NoTrack({ onGoToSubs }: { onGoToSubs: () => void }) {
  return (
    <div className="flex flex-col items-start gap-3">
      <p className="text-sm text-muted-foreground">{th.subs.pickHint}</p>
      <Button variant="secondary" onClick={onGoToSubs}>
        {t.goToSubs}
      </Button>
    </div>
  )
}

type SearchBoxProps = { query: string; onQueryChange: (query: string) => void }

/** ช่องค้นหาคำ: ปุ่มล้างคำค้นขึ้นเมื่อมีคำค้น · Esc ในช่องก็ล้างได้ */
function SearchBox({ query, onQueryChange }: SearchBoxProps) {
  const inputRef = useRef<HTMLInputElement>(null)

  function clear() {
    onQueryChange("")
    inputRef.current?.focus()
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape" && query !== "") {
      event.preventDefault()
      clear()
    }
  }

  return (
    <InputGroup className="h-10">
      <InputGroupAddon>
        <Search aria-hidden />
      </InputGroupAddon>
      <InputGroupInput
        ref={inputRef}
        type="text"
        value={query}
        onChange={(event) => onQueryChange(event.target.value)}
        onKeyDown={onKeyDown}
        aria-label={t.searchLabel}
        placeholder={t.searchPlaceholder}
        autoComplete="off"
      />
      {query !== "" && (
        <InputGroupAddon align="inline-end">
          <InputGroupButton size="icon-sm" aria-label={t.clearSearch} onClick={clear}>
            <X aria-hidden />
          </InputGroupButton>
        </InputGroupAddon>
      )}
    </InputGroup>
  )
}

type LinesProps = { cues: Cue[]; at: number | null; onPick: (cue: Cue) => void }

/** ค้นหา + ผลค้นหา + รายการบรรทัด */
function TranscriptLines({ cues, at, onPick }: LinesProps) {
  const [query, setQuery] = useState("")
  // ช่องค้นหาตอบสนองทันที ส่วนการกรองรายการ (คลิปยาวเป็นพันบรรทัด) ตามมาทีหลังได้โดยไม่หน่วงการพิมพ์
  const deferredQuery = useDeferredValue(query)
  // เตรียมข้อความสำหรับค้นหาครั้งเดียวต่อชุดบรรทัด (เปลี่ยนแทร็กหรือความยาวซับ) ไม่ใช่ทุกครั้งที่พิมพ์
  const lines = useMemo(() => prepareLines(cues), [cues])
  const visible = useMemo(() => searchPrepared(lines, deferredQuery), [lines, deferredQuery])
  const needle = searchNeedle(deferredQuery)
  const searching = needle !== ""
  const current = at === null ? -1 : cueIndexAt(cues, at)

  return (
    <div className="flex flex-col gap-3">
      <SearchBox query={query} onQueryChange={setQuery} />
      {/* ประกาศจำนวนที่พบให้โปรแกรมอ่านหน้าจอ: กล่องนี้ต้องอยู่ตลอด ข้อความถึงจะถูกอ่านเมื่อเปลี่ยน */}
      <p aria-live="polite" className="min-h-5 text-sm text-muted-foreground">
        {searching && (visible.length > 0 ? fill(t.found, { n: visible.length }) : t.notFound)}
      </p>
      {visible.length > 0 && (
        <>
          <p className="text-sm text-muted-foreground">{t.hint}</p>
          <LineList
            cues={cues}
            lines={lines}
            visible={visible}
            needle={needle}
            current={current}
            revealKey={at}
            onPick={onPick}
          />
        </>
      )}
    </div>
  )
}

type TrackProps = { videoId: string; track: SubtitleTrack; at: number | null; onPick: (cue: Cue) => void }

/** ทรานสคริปต์ของแทร็กที่ใช้อยู่ แบ่งบรรทัดตามความยาวซับที่เลือกในแท็บซับ (เห็นอะไรที่นี่ ได้แบบนั้นในไฟล์ .srt) */
function TrackTranscript({ videoId, track, at, onPick }: TrackProps) {
  const tokens = useQuery(tokensQuery(videoId, track.id))
  const { options } = useSubSettings()
  const cues = useCues(tokens.data?.tokens, options)

  let body
  if (tokens.isError) {
    body = <LoadError title={th.subs.loadError} error={tokens.error} onRetry={() => void tokens.refetch()} />
  } else if (!tokens.isSuccess) body = <LinesSkeleton />
  else if (cues.length === 0) body = <NoLines />
  else body = <TranscriptLines cues={cues} at={at} onPick={onPick} />

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">{fill(t.source, { name: trackLabel(track) })}</p>
      {body}
    </div>
  )
}

function Transcript({ videoId, data }: { videoId: string; data: SubtitleTracks }) {
  const { trackId, at, update } = useVideoParams()
  const track = trackInEffect(data, trackId)
  // เปลี่ยนแท็บแล้วล้างเวลาที่ไฮไลต์ไว้ เหมือนกดแถบแท็บ
  if (!track) return <NoTrack onGoToSubs={() => update({ tab: "subs", at: null })} />
  return (
    <TrackTranscript
      videoId={videoId}
      track={track}
      at={at}
      // FR-SUB-8: กดบรรทัด → แท็บภาพเฟรม ไฮไลต์ภาพของเวลานั้น (patch เดียว: update อ่าน URL ตอนสร้าง)
      onPick={(cue) => update({ tab: "frames", at: cue.startMs })}
    />
  )
}

/**
 * แท็บทรานสคริปต์ (Q4 = ก): ข้อความจากแทร็กเดียวกับแท็บซับ แบ่งบรรทัดตามความยาวซับที่เลือก
 * ค้นหาคำได้ (คำที่ตรงถูกเน้น บรรทัดอื่นซ่อน) · กดบรรทัดไปภาพเฟรมของช่วงนั้น
 * มาจาก "ดูซับช่วงนี้" (?at=) = บรรทัดของเวลานั้นมีกรอบ เลื่อนมาให้เห็น และได้โฟกัส
 */
export function TranscriptPanel({ videoId, enabled }: { videoId: string; enabled: boolean }) {
  return (
    <section aria-labelledby="transcript-title">
      <Card>
        <CardHeader>
          <CardTitle>
            <h2 id="transcript-title" className="text-base font-medium">
              {t.title}
            </h2>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <SubtitleGate videoId={videoId} enabled={enabled}>
            {(data) => <Transcript videoId={videoId} data={data} />}
          </SubtitleGate>
        </CardContent>
      </Card>
    </section>
  )
}
