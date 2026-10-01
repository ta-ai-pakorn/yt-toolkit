import { cn } from "cn"
import type { LucideIcon } from "lucide-react"

import { th } from "@/i18n/th"
import type { VideoInfo } from "@/lib/types"

import { statTiles } from "./stat-tiles"

/**
 * ตัวเลขหนึ่งตัวแบบย่อพร้อมไอคอน เช่น 👍 "1.5 พัน" (ใช้กับยอดถูกใจของคอมเมนต์ปักหมุด)
 * ตาเห็นตัวเลขย่อ โปรแกรมอ่านหน้าจอได้ตัวเลขเต็ม (aria-label) และชี้เมาส์ก็เห็นตัวเลขเต็ม (title)
 * role="img": ไอคอนกับข้อความข้างในรวมเป็นภาพเดียวที่มีชื่อเดียว (aria-label บน span เปล่าใช้ไม่ได้)
 */
export function Stat({ icon: Icon, text, label }: { icon: LucideIcon; text: string; label: string }) {
  return (
    <span role="img" aria-label={label} title={label} className="inline-flex items-center gap-1">
      <Icon aria-hidden className="size-3.5 shrink-0" />
      <span className="tabular-nums">{text}</span>
    </span>
  )
}

/**
 * ช่องตัวเลขที่หัวคลิป: ป้ายเล็กสีจางด้านบน ค่าตัวใหญ่ด้านล่าง กวาดตาหาตัวเลขที่ต้องการได้ทันที
 * จอกว้าง 6 ช่องในแถวเดียว จอแคบ (< 640 px) แถวละ 3 ช่อง · ค่าไหนไม่มีไม่ขึ้นช่อง
 * แต่ละช่องเป็นภาพเดียวที่มีชื่อเต็ม (role="img" + aria-label) และชี้เมาส์ก็เห็นชื่อเต็ม (title)
 */
export function StatTiles({ video, className }: { video: VideoInfo; className?: string }) {
  const tiles = statTiles(video)
  if (tiles.length === 0) return null
  return (
    <ul aria-label={th.video.tiles.label} className={cn("grid grid-cols-3 gap-1.5 sm:grid-cols-6", className)}>
      {tiles.map((tile) => (
        <li key={tile.key} className="min-w-0">
          <div
            role="img"
            aria-label={tile.full}
            title={tile.full}
            data-tile={tile.key}
            className="flex h-full flex-col gap-0.5 rounded-md bg-muted px-2 py-1.5"
          >
            <span className="truncate text-xs text-muted-foreground">{tile.label}</span>
            <span className="truncate text-base leading-snug font-semibold tabular-nums">{tile.value}</span>
          </div>
        </li>
      ))}
    </ul>
  )
}
