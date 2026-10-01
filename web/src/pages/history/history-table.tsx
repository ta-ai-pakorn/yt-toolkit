import type { MouseEvent } from "react"
import { Link, useNavigate } from "react-router"

import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { th } from "@/i18n/th"
import { relativeTime } from "@/lib/format"
import type { HistoryItem } from "@/lib/types"
import { Thumbnail } from "@/pages/home/thumbnail"

import { outputLabels } from "./queries"

// ตารางกำหนดความกว้างคอลัมน์เอง (table-fixed) คอลัมน์ชื่อรับพื้นที่ที่เหลือและตัดบรรทัดได้
// จอแคบ/ซูม 200% (640 px) จึงไม่เลื่อนข้าง · ui/table ตั้ง whitespace-nowrap ให้ทุกเซลล์ ต้องยกเลิกที่เซลล์ชื่อ
const HEAD = "text-muted-foreground"

function Header() {
  return (
    <TableHeader>
      <TableRow className="hover:bg-transparent">
        <TableHead className={`w-28 ${HEAD}`}>{th.history.columns.thumb}</TableHead>
        <TableHead className={HEAD}>{th.history.columns.title}</TableHead>
        <TableHead className={`w-28 ${HEAD}`}>{th.history.columns.outputs}</TableHead>
        <TableHead className={`w-28 ${HEAD}`}>{th.history.columns.time}</TableHead>
      </TableRow>
    </TableHeader>
  )
}

function HistoryRow({ item }: { item: HistoryItem }) {
  const navigate = useNavigate()
  const href = `/v/${item.videoId}`
  const labels = outputLabels(item.outputs)

  // ทั้งแถวกดได้เหมือนรายการล่าสุดของ W1 · คีย์บอร์ดใช้ลิงก์ชื่อคลิป (จุดหยุด Tab เดียวต่อแถว)
  // คลิกที่ลิงก์เอง หรือกดร่วมกับ Ctrl/Shift/Alt/Cmd ปล่อยให้เบราว์เซอร์จัดการตามปกติ
  function openRow(event: MouseEvent<HTMLTableRowElement>) {
    if (event.defaultPrevented || event.button !== 0) return
    if (event.ctrlKey || event.shiftKey || event.altKey || event.metaKey) return
    if ((event.target as HTMLElement).closest("a")) return
    void navigate(href)
  }

  return (
    <TableRow onClick={openRow} className="cursor-pointer">
      <TableCell className="py-2">
        <Thumbnail src={item.thumbnailUrl} className="w-24" />
      </TableCell>
      <TableCell className="min-w-0 whitespace-normal">
        <Link
          to={href}
          className="line-clamp-2 rounded-sm font-medium [overflow-wrap:anywhere] outline-none hover:underline focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          {item.title}
        </Link>
      </TableCell>
      <TableCell className="whitespace-normal">
        {labels.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {labels.map((label) => (
              <Badge key={label} variant="secondary">
                {label}
              </Badge>
            ))}
          </div>
        )}
      </TableCell>
      <TableCell className="text-xs whitespace-normal text-muted-foreground">
        <time dateTime={item.lastAt}>{relativeTime(item.lastAt)}</time>
      </TableCell>
    </TableRow>
  )
}

/** ตารางประวัติ (หน้า W5): ปก · ชื่อคลิป · ไฟล์ที่ได้ · เวลา เรียงตามที่ backend ส่งมา (ใหม่สุดก่อน) */
export function HistoryTable({ items }: { items: HistoryItem[] }) {
  return (
    <Table className="table-fixed">
      <Header />
      <TableBody>
        {items.map((item) => (
          <HistoryRow key={item.videoId} item={item} />
        ))}
      </TableBody>
    </Table>
  )
}

/** โครงรอระหว่างโหลดครั้งแรก: หัวตารางจริงกับแถวเปล่า (ขนาดแถวใกล้เคียงของจริง หน้าจึงไม่กระโดด) */
export function HistoryTableSkeleton() {
  return (
    <div aria-busy="true">
      <span className="sr-only" role="status">
        {th.common.loading}
      </span>
      <Table className="table-fixed" aria-hidden>
        <Header />
        <TableBody>
          {Array.from({ length: 6 }, (_, i) => (
            <TableRow key={i} className="hover:bg-transparent">
              <TableCell>
                <Skeleton className="aspect-video w-24" />
              </TableCell>
              <TableCell>
                <Skeleton className="h-4 w-4/5" />
              </TableCell>
              <TableCell>
                <Skeleton className="h-5 w-12" />
              </TableCell>
              <TableCell>
                <Skeleton className="h-3 w-16" />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
