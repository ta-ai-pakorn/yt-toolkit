import { useQuery } from "@tanstack/react-query"
import { CircleX, ListVideo } from "lucide-react"
import { useState, type ReactNode } from "react"
import { Link } from "react-router"

import { Alert, AlertAction, AlertDescription } from "@/components/ui/alert"
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
import type { ResolveItem } from "@/lib/types"

import {
  AUTO_TITLE_ROWS,
  playlistQuery,
  thumbnailUrl,
  videoTitleQuery,
} from "./queries"
import { Thumbnail } from "./thumbnail"

const t = th.home.results

type VideoRowProps = {
  item: ResolveItem
  /** 10 แถวแรกดึงชื่อเอง แถวหลังจากนั้นรอให้ผู้ใช้กด "แสดงชื่อ" */
  autoTitle: boolean
  onPlaylist?: () => void
}

function VideoRow({ item, autoTitle, onPlaylist }: VideoRowProps) {
  const id = item.videoId ?? ""
  const [requested, setRequested] = useState(false)
  const wantsTitle = autoTitle || requested
  const video = useQuery({ ...videoTitleQuery(id), enabled: wantsTitle })
  const title = video.data?.title

  let name: ReactNode
  let hint: ReactNode = null
  if (title) {
    name = <ItemTitle className="line-clamp-2 w-auto">{title}</ItemTitle>
    hint = <ItemDescription className="font-mono text-xs">{id}</ItemDescription>
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
    <Item
      role="listitem"
      variant="outline"
      size="sm"
      aria-busy={wantsTitle && video.isFetching && !title}
    >
      <ItemMedia>
        <Thumbnail src={thumbnailUrl(id)} className="w-24" />
      </ItemMedia>
      <ItemContent>
        {name}
        {hint}
      </ItemContent>
      <ItemActions>
        {!wantsTitle && !title && (
          <Button variant="ghost" size="sm" onClick={() => setRequested(true)}>
            {t.showTitle}
          </Button>
        )}
        {onPlaylist && (
          <Button variant="outline" size="sm" onClick={onPlaylist}>
            {t.wholePlaylist}
          </Button>
        )}
        <Link
          to={`/v/${id}`}
          aria-label={`${t.open} ${title ?? id}`}
          className={buttonVariants({ variant: "outline", size: "sm" })}
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

function PlaylistRow({ playlistId }: { playlistId: string }) {
  const playlist = useQuery(playlistQuery(playlistId))

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

  const { title, total, truncated, entries } = playlist.data
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
            {truncated && (
              <>
                <br />
                {fill(t.truncated, { n: entries.length })}
              </>
            )}
          </ItemDescription>
        )}
      </ItemContent>
    </Item>
  )
}

// ลิงก์ที่เป็นทั้งคลิปและเพลย์ลิสต์ปนอยู่ในรายการหลายบรรทัด: เริ่มที่คลิป แล้วให้ผู้ใช้กดขอทั้งเพลย์ลิสต์ได้เอง
function AmbiguousRow({
  item,
  autoTitle,
}: {
  item: ResolveItem
  autoTitle: boolean
}) {
  const [wholePlaylist, setWholePlaylist] = useState(false)
  if (wholePlaylist && item.playlistId)
    return <PlaylistRow playlistId={item.playlistId} />
  return (
    <VideoRow
      item={item}
      autoTitle={autoTitle}
      onPlaylist={item.playlistId ? () => setWholePlaylist(true) : undefined}
    />
  )
}

function Row({ item, autoTitle }: { item: ResolveItem; autoTitle: boolean }) {
  switch (item.kind) {
    case "video":
      return <VideoRow item={item} autoTitle={autoTitle} />
    case "playlist":
      return item.playlistId ? (
        <PlaylistRow playlistId={item.playlistId} />
      ) : (
        <InvalidRow item={item} />
      )
    case "ambiguous":
      return <AmbiguousRow item={item} autoTitle={autoTitle} />
    default:
      return <InvalidRow item={item} />
  }
}

const isClip = (item: ResolveItem) =>
  item.kind === "video" || item.kind === "ambiguous"

export function ResultList({ items }: { items: ResolveItem[] }) {
  // นับเฉพาะแถวที่เป็นคลิป: 10 แถวแรกของคลิปดึงชื่อเอง
  const autoTitle = items.map(
    (item, index) =>
      isClip(item) &&
      items.slice(0, index).filter(isClip).length < AUTO_TITLE_ROWS
  )
  return (
    <section
      aria-labelledby="results-title"
      className="flex flex-col gap-2 text-left"
    >
      <h2
        id="results-title"
        className="text-sm font-medium text-muted-foreground"
      >
        {t.title}
      </h2>
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
            />
          ))}
        </ItemGroup>
      )}
    </section>
  )
}
