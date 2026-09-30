import { useQuery } from "@tanstack/react-query"
import { Check, ChevronDown, ChevronUp, CircleX, ListVideo, Trash2 } from "lucide-react"
import { useId, useState, type ReactNode } from "react"
import { Link } from "react-router"

import { Alert, AlertAction, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button, buttonVariants } from "@/components/ui/button"
import { Empty, EmptyHeader, EmptyTitle } from "@/components/ui/empty"
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemMedia,
  ItemTitle,
} from "@/components/ui/item"
import { Skeleton } from "@/components/ui/skeleton"
import { fill, th } from "@/i18n/th"
import { formatDuration } from "@/lib/format"
import type { PlaylistEntry, ResolveItem } from "@/lib/types"
import { cn } from "cn"

import {
  BotStopContext,
  createBotStop,
  useBotStop,
  useBotStopped,
  type BotStop,
} from "./bot-stop"
import {
  AUTO_TITLE_ROWS,
  playlistQuery,
  thumbnailUrl,
  videoTitleQuery,
} from "./queries"
import { homeStore, playlistKey, useHomeState } from "./state"
import { Thumbnail } from "./thumbnail"
import { fromListState, fromPlaylistState } from "./use-analyze"

const t = th.home.results

// ปุ่มในแถวใช้ aria-disabled แทน disabled เพื่อให้โฟกัสยังอยู่ที่ปุ่ม (ตัวจัดการคลิกกันการกดเองอยู่แล้ว
// และปุ่มจางลงเองจากสไตล์ของปุ่ม) · ไม่ใส่ pointer-events-none เพราะคลิกจะทะลุไปโดนลิงก์ "เปิดดู" ที่คลุมทั้งแถว

type VideoRowProps = {
  item: ResolveItem
  /** 10 แถวแรกดึงชื่อเอง แถวหลังจากนั้นรอให้ผู้ใช้กด "แสดงชื่อ" */
  autoTitle: boolean
  onPlaylist?: () => void
}

function VideoRow({ item, autoTitle, onPlaylist }: VideoRowProps) {
  const id = item.videoId ?? ""
  // คลิปที่เปิดหน้า W2 ไปแล้ว (ทางไหนก็ได้) มีป้ายเล็ก ๆ ให้รู้ว่าดูไปแล้ว
  const opened = useHomeState().opened.includes(id)
  const [requested, setRequested] = useState(false)
  const wantsTitle = autoTitle || requested
  const botStop = useBotStop() ?? undefined
  // ยูทูปขอให้ยืนยันว่าไม่ใช่บอท: ทั้งรายการหยุดดึงชื่อ (คำขอที่รออยู่ก็ไม่ออก)
  const stopped = useBotStopped()
  const video = useQuery({
    ...videoTitleQuery(id, botStop),
    enabled: wantsTitle && !stopped,
  })
  const title = video.data?.title

  let name: ReactNode
  let hint: ReactNode = null
  if (title) {
    name = <ItemTitle className="line-clamp-2 w-auto">{title}</ItemTitle>
    hint = <ItemDescription className="font-mono text-xs">{id}</ItemDescription>
  } else if (stopped) {
    name = <ItemTitle className="font-mono">{id}</ItemTitle>
    hint = <ItemDescription className="text-xs">{t.botStopped}</ItemDescription>
  } else if (video.isError) {
    name = <ItemTitle className="font-mono">{id}</ItemTitle>
    hint = (
      <ItemDescription className="text-xs text-destructive">
        {t.titleError} · {video.error.message}
      </ItemDescription>
    )
  } else if (wantsTitle) {
    // aria-busy ที่แถวบอกสถานะโหลดแล้ว จึงซ่อนโครงรอจากโปรแกรมอ่านหน้าจอ (ไม่ประกาศซ้ำทีละแถว)
    name = <Skeleton aria-hidden="true" className="h-4 w-56 max-w-full" />
    hint = <ItemDescription className="font-mono text-xs">{id}</ItemDescription>
  } else {
    name = <ItemTitle className="font-mono">{id}</ItemTitle>
  }

  return (
    // ทั้งแถวกดเปิดคลิปได้ (ลิงก์ "เปิดดู" ขยายพื้นที่กดคลุมทั้งแถว) แต่ยังเป็นจุด Tab เดียว
    // ปุ่มอื่นในแถวอยู่ชั้นบน (relative z-10) จึงกดแยกได้ตามปกติ
    <Item
      role="listitem"
      variant="outline"
      size="sm"
      className="relative has-[a[data-row-link]:hover]:bg-muted/50"
      aria-busy={wantsTitle && video.isFetching && !title && !stopped}
    >
      <ItemMedia>
        <Thumbnail src={thumbnailUrl(id)} className="w-24" />
      </ItemMedia>
      <ItemContent>
        {name}
        {hint}
        {opened && (
          <Badge variant="outline" className="mt-0.5 text-muted-foreground">
            <Check aria-hidden />
            {t.opened}
          </Badge>
        )}
      </ItemContent>
      <ItemActions>
        {!wantsTitle && !title && (
          <Button
            variant="ghost"
            size="sm"
            aria-disabled={stopped}
            className="relative z-10"
            onClick={() => {
              if (!stopped) setRequested(true)
            }}
          >
            {t.showTitle}
          </Button>
        )}
        {onPlaylist && (
          <Button
            variant="outline"
            size="sm"
            aria-disabled={stopped}
            className="relative z-10"
            onClick={() => {
              if (!stopped) onPlaylist()
            }}
          >
            {item.isMix ? t.wholeMix : t.wholePlaylist}
          </Button>
        )}
        <Link
          to={`/v/${id}`}
          state={fromListState}
          aria-label={`${t.open} ${title ?? id}`}
          data-row-link=""
          className={cn(
            buttonVariants({ variant: "outline", size: "sm" }),
            // ปุ่มปกติยุบลง 1px ตอนกด (translate) ซึ่งทำให้พื้นที่กดที่คลุมทั้งแถวหดเหลือแค่ปุ่มกลางคลิก
            // เมาส์ปล่อยนอกปุ่มจึงไม่นับเป็นคลิก: ปิดการยุบสำหรับลิงก์นี้
            "after:absolute after:inset-0 after:rounded-lg after:content-[''] active:translate-none!",
          )}
        >
          {t.open}
        </Link>
      </ItemActions>
    </Item>
  )
}

function InvalidRow({ item }: { item: ResolveItem }) {
  return (
    <Item
      role="listitem"
      variant="outline"
      size="sm"
      className="border-destructive/40"
    >
      <ItemMedia variant="icon">
        <CircleX aria-hidden className="text-destructive" />
      </ItemMedia>
      <ItemContent>
        <ItemTitle className="line-clamp-2 font-mono break-all">
          {item.input}
        </ItemTitle>
        <ItemDescription className="text-destructive">
          {item.error?.message ?? th.errors.unknown}
        </ItemDescription>
      </ItemContent>
    </Item>
  )
}

/** รายชื่อคลิปที่กางใต้แถวเพลย์ลิสต์ แสดงทีละ 50 คลิป */
const CLIPS_PAGE = 50

type PlaylistClipsProps = {
  title: string
  entries: PlaylistEntry[]
  shown: number
  playlistId: string
  mixVideoId?: string
}

/**
 * คลิปในเพลย์ลิสต์/มิกซ์ (ข้อมูลเดียวกับแถว ไม่ขอใหม่): ภาพปกจากรหัสคลิป ชื่อ ความยาว
 * แต่ละคลิปเป็นลิงก์ไปหน้าคลิป (ยังไม่นับว่าเปิดจนกว่าจะกด เหมือนแถวในรายการผล) · ยาวก็แสดงเพิ่มทีละ 50
 */
function PlaylistClips({ title, entries, shown, playlistId, mixVideoId }: PlaylistClipsProps) {
  const opened = useHomeState().opened
  const state = fromPlaylistState(playlistId, mixVideoId)
  const key = playlistKey(playlistId, mixVideoId)
  return (
    <>
      <ol aria-label={fill(t.clipsLabel, { title })} className="flex flex-col gap-0.5 border-t pt-2">
        {entries.slice(0, shown).map((entry, index) => (
          <li key={`${index}-${entry.videoId}`}>
            <Link
              to={`/v/${entry.videoId}`}
              state={state}
              className="flex min-h-11 items-center gap-3 rounded-md p-1.5 outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
            >
              <Thumbnail src={thumbnailUrl(entry.videoId)} className="w-16" />
              <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                <span className="line-clamp-2">{entry.title || entry.videoId}</span>
                {entry.durationS !== undefined && (
                  <span className="font-mono text-xs text-muted-foreground">{formatDuration(entry.durationS)}</span>
                )}
              </span>
              {opened.includes(entry.videoId) && (
                <Badge variant="outline" className="text-muted-foreground">
                  <Check aria-hidden />
                  {t.opened}
                </Badge>
              )}
            </Link>
          </li>
        ))}
      </ol>
      {shown < entries.length && (
        <div className="flex items-center gap-3 pt-1">
          <Button variant="ghost" size="sm" onClick={() => homeStore.setExpanded(key, shown + CLIPS_PAGE)}>
            {t.showMore}
          </Button>
          <span className="text-xs text-muted-foreground">
            {fill(t.shownCount, { shown: Math.min(shown, entries.length), n: entries.length })}
          </span>
        </div>
      )}
    </>
  )
}

/** `mixVideoId` = คลิปตั้งต้นของมิกซ์อัตโนมัติ (ยูทูปให้ดึงมิกซ์จากลิงก์คลิปเท่านั้น) */
function PlaylistRow({ playlistId, mixVideoId }: { playlistId: string; mixVideoId?: string }) {
  const botStop = useBotStop() ?? undefined
  const stopped = useBotStopped()
  const panelId = useId()
  const key = playlistKey(playlistId, mixVideoId)
  // กาง/พับ และจำนวนที่แสดง อยู่ใน homeStore: เปิดคลิปแล้วกลับมา หรือโหลดหน้าใหม่ ก็ยังกางอยู่
  const shown = useHomeState().expanded[key] ?? 0
  const playlist = useQuery({
    ...playlistQuery(playlistId, botStop, mixVideoId),
    enabled: !stopped,
  })

  // ยังไม่มีข้อมูลเพลย์ลิสต์ตอนที่รายการถูกเบรก: แทนที่โครงรอ/ข้อความผิดพลาด (ไม่มีปุ่มลองใหม่ เพราะต้องรอ)
  if (stopped && !playlist.data) {
    return (
      <Item role="listitem" variant="outline" size="sm">
        <ItemMedia variant="icon">
          <ListVideo aria-hidden className="text-muted-foreground" />
        </ItemMedia>
        <ItemContent>
          <ItemTitle className="font-mono">{playlistId}</ItemTitle>
          <ItemDescription className="text-xs">{t.botStopped}</ItemDescription>
        </ItemContent>
      </Item>
    )
  }

  if (playlist.isPending) {
    return (
      <Item role="listitem" variant="outline" size="sm" aria-busy="true">
        <ItemMedia variant="icon">
          <ListVideo aria-hidden className="text-muted-foreground" />
        </ItemMedia>
        <ItemContent>
          <span className="sr-only" role="status">
            {t.playlistLoading}
          </span>
          <Skeleton className="h-4 w-48" />
          <Skeleton className="h-3.5 w-72 max-w-full" />
        </ItemContent>
      </Item>
    )
  }

  if (playlist.isError) {
    return (
      <div role="listitem">
        <Alert variant="destructive">
          <CircleX aria-hidden />
          <AlertDescription>
            {t.playlistError} · {playlist.error.message}
          </AlertDescription>
          <AlertAction>
            <Button
              variant="outline"
              size="sm"
              disabled={playlist.isFetching}
              onClick={() => void playlist.refetch()}
            >
              {th.common.retry}
            </Button>
          </AlertAction>
        </Alert>
      </div>
    )
  }

  const { title, total, truncated, entries, isMix } = playlist.data
  const expanded = shown > 0 && entries.length > 0
  return (
    <Item role="listitem" variant="outline" size="sm">
      <ItemMedia variant="icon">
        <ListVideo aria-hidden className="text-muted-foreground" />
      </ItemMedia>
      <ItemContent>
        <ItemTitle className="line-clamp-2 w-auto">
          {title || t.playlistUntitled}
        </ItemTitle>
        {entries.length === 0 ? (
          <ItemDescription>{t.playlistEmpty}</ItemDescription>
        ) : (
          <ItemDescription>
            <span className="font-mono">{fill(t.clips, { n: total })}</span> ·{" "}
            {t.playlistLater}
            {/* มิกซ์: จำนวนที่บอกคือ 25 คลิปแรกอยู่แล้ว (กล่องถามบอกไว้) ไม่ต้องบอกว่าตัด */}
            {isMix && (
              <>
                <br />
                {t.mixNote}
              </>
            )}
            {truncated && !isMix && (
              <>
                <br />
                {fill(t.truncated, { n: entries.length })}
              </>
            )}
          </ItemDescription>
        )}
      </ItemContent>
      {entries.length > 0 && (
        <ItemActions>
          <Button
            variant="ghost"
            size="sm"
            aria-expanded={expanded}
            aria-controls={panelId}
            className="relative z-10"
            onClick={() => homeStore.setExpanded(key, expanded ? 0 : CLIPS_PAGE)}
          >
            {expanded ? <ChevronUp aria-hidden /> : <ChevronDown aria-hidden />}
            {expanded ? t.hideClips : t.showClips}
          </Button>
        </ItemActions>
      )}
      {/* กล่องรายชื่ออยู่ในหน้าเสมอ (aria-controls ชี้ได้) แต่มีรายการเฉพาะตอนกาง */}
      <div id={panelId} hidden={!expanded} className="basis-full">
        {expanded && (
          <PlaylistClips
            title={title || t.playlistUntitled}
            entries={entries}
            shown={shown}
            playlistId={playlistId}
            mixVideoId={mixVideoId}
          />
        )}
      </div>
    </Item>
  )
}

// ลิงก์ที่เป็นทั้งคลิปและเพลย์ลิสต์ปนอยู่ในรายการหลายบรรทัด: เริ่มที่คลิป แล้วให้ผู้ใช้กดขอทั้งเพลย์ลิสต์ได้เอง
// กดแล้วแถวกลายเป็นแถวเพลย์ลิสต์ถาวร (บันทึกลงรายการผล กลับมาจากหน้าคลิปก็ยังเป็นเพลย์ลิสต์)
type RowProps = { item: ResolveItem; autoTitle: boolean; onWhole: () => void }

function Row({ item, autoTitle, onWhole }: RowProps) {
  switch (item.kind) {
    case "video":
      return <VideoRow item={item} autoTitle={autoTitle} />
    case "playlist":
      return item.playlistId ? (
        <PlaylistRow playlistId={item.playlistId} mixVideoId={item.isMix ? item.videoId : undefined} />
      ) : (
        <InvalidRow item={item} />
      )
    case "ambiguous":
      return <VideoRow item={item} autoTitle={autoTitle} onPlaylist={item.playlistId ? onWhole : undefined} />
    default:
      return <InvalidRow item={item} />
  }
}

// เบรก E_BOT_CHECK ผูกกับรายการผลชุดหนึ่ง (listId) ไม่ใช่กับการแสดงผล: ไปหน้าคลิปแล้วกลับมา
// รายการเดิมยังถูกเบรกอยู่ ไม่ยิงคำขอซ้ำ · วิเคราะห์ใหม่ = listId ใหม่ = เบรกใหม่
let currentGate: { listId: string; gate: BotStop } | null = null
function botStopFor(listId: string): BotStop {
  if (currentGate?.listId !== listId) currentGate = { listId, gate: createBotStop() }
  return currentGate.gate
}

const isClip = (item: ResolveItem) =>
  item.kind === "video" || item.kind === "ambiguous"

type ResultListProps = {
  items: ResolveItem[]
  listId: string
  /** แถว ambiguous ที่ผู้ใช้กด "ทั้งเพลย์ลิสต์" (ส่งตำแหน่งแถว) */
  onWhole: (index: number) => void
  onClear: () => void
  /** ตอนวิเคราะห์มีข้อความที่ไม่ใช่ลิงก์ถูกข้าม */
  skipped?: boolean
}

export function ResultList({ items, listId, onWhole, onClear, skipped = false }: ResultListProps) {
  const botStop = botStopFor(listId)
  // นับเฉพาะแถวที่เป็นคลิป: 10 แถวแรกของคลิปดึงชื่อเอง
  const autoTitle = items.map(
    (item, index) =>
      isClip(item) &&
      items.slice(0, index).filter(isClip).length < AUTO_TITLE_ROWS
  )
  return (
    <BotStopContext value={botStop}>
      <section
        aria-labelledby="results-title"
        className="flex flex-col gap-2 text-left"
      >
        <div className="flex items-center justify-between gap-2">
          <h2
            id="results-title"
            className="text-sm font-medium text-muted-foreground"
          >
            {t.title}
          </h2>
          <Button variant="ghost" size="sm" onClick={onClear}>
            <Trash2 aria-hidden />
            {t.clear}
          </Button>
        </div>
        {items.length === 0 ? (
          <Empty className="border">
            <EmptyHeader>
              <EmptyTitle>{t.none}</EmptyTitle>
            </EmptyHeader>
          </Empty>
        ) : (
          <ItemGroup className="gap-2">
            {items.map((item, index) => (
              <Row
                key={`${index}-${item.input}`}
                item={item}
                autoTitle={autoTitle[index]}
                onWhole={() => onWhole(index)}
              />
            ))}
          </ItemGroup>
        )}
        {/* ข้อความทักทาย/ขอบคุณที่วางมาพร้อมลิงก์ถูกข้าม: บอกเบา ๆ ไม่ใช่ error */}
        {skipped && items.length > 0 && <p className="text-xs text-muted-foreground">{t.skipped}</p>}
      </section>
    </BotStopContext>
  )
}
