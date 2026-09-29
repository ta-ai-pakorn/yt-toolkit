import { useQuery } from "@tanstack/react-query"
import { CircleX, ListVideo, Video } from "lucide-react"
import { useState } from "react"
import { Link } from "react-router"

import { Alert, AlertAction, AlertDescription } from "@/components/ui/alert"
import { Button, buttonVariants } from "@/components/ui/button"
import { Empty, EmptyHeader, EmptyTitle } from "@/components/ui/empty"
import { Item, ItemActions, ItemContent, ItemDescription, ItemGroup, ItemMedia, ItemTitle } from "@/components/ui/item"
import { Skeleton } from "@/components/ui/skeleton"
import { fill, th } from "@/i18n/th"
import { api } from "@/lib/api"
import type { PlaylistInfo, ResolveItem } from "@/lib/types"

const t = th.home.results

function VideoRow({ item, onPlaylist }: { item: ResolveItem; onPlaylist?: () => void }) {
  const id = item.videoId ?? ""
  return (
    <Item role="listitem" variant="outline" size="sm">
      <ItemMedia variant="icon">
        <Video aria-hidden className="text-muted-foreground" />
      </ItemMedia>
      <ItemContent>
        <ItemTitle className="font-mono">{id}</ItemTitle>
      </ItemContent>
      <ItemActions>
        {onPlaylist && (
          <Button variant="outline" size="sm" onClick={onPlaylist}>
            {t.wholePlaylist}
          </Button>
        )}
        <Link
          to={`/v/${id}`}
          aria-label={`${t.open} ${id}`}
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
    <Item role="listitem" variant="outline" size="sm" className="border-destructive/40">
      <ItemMedia variant="icon">
        <CircleX aria-hidden className="text-destructive" />
      </ItemMedia>
      <ItemContent>
        <ItemTitle className="line-clamp-2 break-all font-mono">{item.input}</ItemTitle>
        <ItemDescription className="text-destructive">{item.error?.message ?? th.errors.unknown}</ItemDescription>
      </ItemContent>
    </Item>
  )
}

function PlaylistRow({ playlistId }: { playlistId: string }) {
  // retry ปิด: ความผิดพลาดจากยูทูปมักไม่หายเอง ให้ผู้ใช้กด "ลองใหม่" เองจะเห็นผลเร็วกว่ารอลองซ้ำเบื้องหลัง
  const playlist = useQuery({
    queryKey: ["playlist", playlistId],
    queryFn: () => api<PlaylistInfo>(`/playlists/${playlistId}`),
    retry: false,
    staleTime: 5 * 60_000,
  })

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
            <Button variant="outline" size="sm" disabled={playlist.isFetching} onClick={() => void playlist.refetch()}>
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
        <ItemTitle className="line-clamp-2 w-auto">{title || t.playlistUntitled}</ItemTitle>
        {entries.length === 0 ? (
          <ItemDescription>{t.playlistEmpty}</ItemDescription>
        ) : (
          <ItemDescription>
            <span className="font-mono">{fill(t.clips, { n: total })}</span> · {t.playlistLater}
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
function AmbiguousRow({ item }: { item: ResolveItem }) {
  const [wholePlaylist, setWholePlaylist] = useState(false)
  if (wholePlaylist && item.playlistId) return <PlaylistRow playlistId={item.playlistId} />
  return <VideoRow item={item} onPlaylist={item.playlistId ? () => setWholePlaylist(true) : undefined} />
}

function Row({ item }: { item: ResolveItem }) {
  switch (item.kind) {
    case "video":
      return <VideoRow item={item} />
    case "playlist":
      return item.playlistId ? <PlaylistRow playlistId={item.playlistId} /> : <InvalidRow item={item} />
    case "ambiguous":
      return <AmbiguousRow item={item} />
    default:
      return <InvalidRow item={item} />
  }
}

export function ResultList({ items }: { items: ResolveItem[] }) {
  return (
    <section aria-labelledby="results-title" className="flex flex-col gap-2 text-left">
      <h2 id="results-title" className="text-sm font-medium text-muted-foreground">
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
            <Row key={`${index}-${item.input}`} item={item} />
          ))}
        </ItemGroup>
      )}
    </section>
  )
}
