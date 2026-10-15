import { useQuery } from "@tanstack/react-query"
import { useEffect } from "react"
import { Link } from "react-router"

import { useElapsed } from "@/components/use-elapsed"
import { Item, ItemContent, ItemDescription, ItemGroup, ItemMedia, ItemTitle } from "@/components/ui/item"
import { Skeleton } from "@/components/ui/skeleton"
import { th } from "@/i18n/th"
import { formatDuration, relativeTime } from "@/lib/format"

import { recentQuery } from "../history/queries"
import { Thumbnail } from "./thumbnail"

const SKELETON_DELAY_MS = 300

// ข้อมูลรอง: โหลดไม่ได้ก็ซ่อนเงียบ ๆ ไม่เด้ง toast ไม่ให้กวนงานหลักของหน้า
export function RecentSection() {
  // "ล่าสุด" = เฉพาะคลิปที่เคยเปิดดูในหน้า W2 · คีย์เดียวกับตัวอย่างชื่อไฟล์ในหน้าตั้งค่า (M6 รอบ A)
  const history = useQuery(recentQuery())

  // โหลดเร็ว (ปกติคือเสี้ยววินาที) ไม่ต้องขึ้นโครงรอให้หน้ากระตุก: ขึ้นเมื่อช้าเกิน 300 ms เท่านั้น
  const slow = useElapsed(SKELETON_DELAY_MS)

  useEffect(() => {
    if (history.isError) console.warn("[recent] failed to load history", history.error)
  }, [history.isError, history.error])

  if (history.isPending) {
    if (!slow) return null
    return (
      <section aria-label={th.home.recent.title} aria-busy="true" className="flex flex-col gap-2">
        <Skeleton className="h-5 w-16" />
        {Array.from({ length: 3 }, (_, i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </section>
    )
  }

  if (history.isError || history.data.items.length === 0) return null

  return (
    <section aria-labelledby="recent-title" className="flex flex-col gap-2 text-left">
      <h2 id="recent-title" className="text-sm font-medium text-muted-foreground">
        {th.home.recent.title}
      </h2>
      <ItemGroup className="gap-2">
        {history.data.items.map((video) => (
          // role=listitem อยู่ที่ตัวห่อ เพราะถ้าใส่ที่ลิงก์เอง ลิงก์จะเสียความหมายว่าเป็นลิงก์
          <div key={video.videoId} role="listitem">
            <Item variant="outline" size="sm" render={<Link to={`/v/${video.videoId}`} />}>
              <ItemMedia>
                <Thumbnail src={video.thumbnailUrl} className="w-24" />
              </ItemMedia>
              <ItemContent>
                <ItemTitle className="line-clamp-2 w-auto">{video.title}</ItemTitle>
                <ItemDescription className="text-xs">
                  <span className="font-mono">{formatDuration(video.durationS)}</span> · {relativeTime(video.lastAt)}
                </ItemDescription>
              </ItemContent>
            </Item>
          </div>
        ))}
      </ItemGroup>
    </section>
  )
}
