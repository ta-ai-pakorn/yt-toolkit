import { fill, th } from "@/i18n/th"
import { formatCompact, formatCount, formatDuration, formatPublished } from "@/lib/format"
import type { VideoInfo } from "@/lib/types"

const t = th.video.tiles

export type StatTile = {
  key: "views" | "likes" | "comments" | "followers" | "duration" | "published"
  /** ป้ายเล็กด้านบน เช่น "ยอดวิว" */
  label: string
  /** ค่าที่ตาเห็น (ตัวเลขย่อแบบไทย เช่น "5.8 แสน") */
  value: string
  /** ชื่อเต็มสำหรับโปรแกรมอ่านหน้าจอและ title เช่น "ยอดวิว 580,123 ครั้ง" */
  full: string
}

// วันที่ในช่องแบบสั้น ("23 เม.ย. 48") ให้พอดีช่องกว้างราว 100 px · ชื่อเต็มใช้แบบยาว ("23 เมษายน 2548")
const shortDate = new Intl.DateTimeFormat("th-TH", { day: "numeric", month: "short", year: "2-digit", timeZone: "UTC" })

/** ตัวเลขที่ใช้ได้ (ไม่ใช่ค่าว่างหรือ NaN) · 0 ยังนับว่ามีค่า */
const known = (n: number | undefined): n is number => typeof n === "number" && Number.isFinite(n)

/**
 * ช่องตัวเลขที่หัวคลิป ตามลำดับ: ยอดวิว · ไลก์ · คอมเมนต์ · ผู้ติดตาม · ความยาว · เผยแพร่
 * ค่าไหนยูทูปไม่บอก (หรือวันที่อ่านไม่ได้ ความยาว 0 เช่นไลฟ์) = ไม่มีช่องนั้น
 */
export function statTiles(video: VideoInfo): StatTile[] {
  const { views, likes, comments, channelFollowers } = video.stats ?? {}
  const tiles: StatTile[] = []
  const count = (key: "views" | "likes" | "comments" | "followers", n: number | undefined, fullText: string) => {
    if (!known(n)) return
    tiles.push({ key, label: t[key], value: formatCompact(n), full: fill(fullText, { n: formatCount(n) }) })
  }
  count("views", views, t.viewsLabel)
  count("likes", likes, t.likesLabel)
  count("comments", comments, t.commentsLabel)
  count("followers", channelFollowers, t.followersLabel)
  if (known(video.durationS) && video.durationS > 0) {
    const d = formatDuration(video.durationS)
    tiles.push({ key: "duration", label: t.duration, value: d, full: fill(t.durationLabel, { d }) })
  }
  const published = video.publishedAt ? formatPublished(video.publishedAt) : ""
  if (published && video.publishedAt) {
    const value = shortDate.format(Date.parse(video.publishedAt))
    tiles.push({ key: "published", label: t.published, value, full: fill(t.publishedLabel, { date: published }) })
  }
  return tiles
}
