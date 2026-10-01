import { CircleX, Minus } from "lucide-react"

import { Checkbox } from "@/components/ui/checkbox"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { fill, th } from "@/i18n/th"
import { formatDuration } from "@/lib/format"
import { thumbnailUrl } from "@/pages/home/queries"
import { Thumbnail } from "@/pages/home/thumbnail"

import { headerState, selectableRows, type BatchRow } from "./rows"

const t = th.batch

// ตารางกำหนดความกว้างคอลัมน์เอง (table-fixed) คอลัมน์ชื่อรับพื้นที่ที่เหลือและตัดบรรทัดได้
// จอแคบ/ซูม 200% (640 px) จึงไม่เลื่อนข้าง · ui/table ตั้ง whitespace-nowrap ให้ทุกเซลล์ ต้องยกเลิกที่เซลล์ชื่อ
const HEAD = "text-muted-foreground"
const SELECT_COL = "w-11"
const THUMB_COL = "w-24"
const DURATION_COL = "w-20"

type Props = {
  rows: BatchRow[]
  /** รหัสคลิปที่ผู้ใช้เอาออกจากการเลือก (ค่าเริ่มต้น = เลือกทั้งหมด) */
  deselected: ReadonlySet<string>
  onToggle: (videoId: string) => void
  /** ติ๊กช่องเลือกทั้งหมด: true = เลือกทุกคลิป false = เอาออกทุกคลิป */
  onToggleAll: (selected: boolean) => void
}

function RowName({ row }: { row: BatchRow }) {
  // ชื่อเป็นข้อความ: รหัสคลิปแสดงเป็นตัวอักษรเว้นระยะคงที่ (mono) เฉพาะตอนไม่รู้ชื่อ
  return row.title ? (
    <span className="line-clamp-2 font-medium [overflow-wrap:anywhere]">{row.title}</span>
  ) : (
    <span className="font-mono text-sm [overflow-wrap:anywhere]">{row.videoId}</span>
  )
}

function ClipRow({
  row,
  selected,
  onToggle,
}: {
  row: BatchRow
  selected: boolean
  onToggle: (videoId: string) => void
}) {
  const name = row.title ?? row.videoId
  return (
    <TableRow data-state={selected ? "selected" : undefined}>
      <TableCell className={SELECT_COL}>
        <Checkbox
          checked={selected}
          onCheckedChange={() => onToggle(row.videoId)}
          aria-label={fill(t.selectRow, { title: name })}
        />
      </TableCell>
      <TableCell className="py-2">
        <Thumbnail src={thumbnailUrl(row.videoId)} className="w-20" />
      </TableCell>
      <TableCell className="min-w-0 whitespace-normal">
        <RowName row={row} />
      </TableCell>
      <TableCell className="font-mono text-xs text-muted-foreground">
        {row.durationS !== undefined ? formatDuration(row.durationS) : null}
      </TableCell>
    </TableRow>
  )
}

/** ลิงก์ที่อ่านไม่ออก: แถวแดง เลือกไม่ได้ (ไม่มีช่องติ๊ก) */
function InvalidRow({ input }: { input: string }) {
  return (
    <TableRow className="bg-destructive/5 hover:bg-destructive/5">
      <TableCell className={SELECT_COL}>
        <CircleX aria-hidden className="size-4 text-destructive" />
      </TableCell>
      <TableCell />
      <TableCell className="min-w-0 whitespace-normal">
        <span className="line-clamp-2 font-mono text-sm [overflow-wrap:anywhere]">{input}</span>
        <span className="block text-sm text-destructive">{t.invalidRow}</span>
      </TableCell>
      <TableCell />
    </TableRow>
  )
}

function Header({ rows, deselected, onToggleAll }: Omit<Props, "onToggle">) {
  const selectable = selectableRows(rows)
  const selected = selectable.filter((row) => !deselected.has(row.videoId)).length
  const state = headerState(selectable.length, selected)
  return (
    <TableHeader>
      <TableRow className="hover:bg-transparent">
        {/* ช่องเลือกทั้งหมดอยู่คอลัมน์แรก (ข้อความต่อท้ายกินสองคอลัมน์: ช่องติ๊ก + ปก) กดข้อความก็ติ๊กได้ */}
        <TableHead colSpan={2} className={HEAD}>
          <label className="flex min-h-8 w-fit items-center gap-3 text-foreground">
            {/* ติ๊กบางส่วน: ช่องขึ้นสีเต็มพร้อมขีด (ui/checkbox วาดแต่เครื่องหมายถูก จึงซ่อนแล้ววางขีดทับ) */}
            <span className="relative flex">
              <Checkbox
                checked={state === "all"}
                indeterminate={state === "some"}
                disabled={selectable.length === 0}
                onCheckedChange={(next) => onToggleAll(next)}
                aria-label={t.selectAll}
                className="data-indeterminate:border-primary data-indeterminate:bg-primary data-indeterminate:[&_svg]:invisible"
              />
              {state === "some" && (
                <Minus aria-hidden className="pointer-events-none absolute inset-0 m-auto size-3.5 text-primary-foreground" />
              )}
            </span>
            {t.selectAll}
          </label>
        </TableHead>
        <TableHead className={HEAD}>{t.columns.title}</TableHead>
        <TableHead className={`${DURATION_COL} ${HEAD}`}>{t.columns.duration}</TableHead>
      </TableRow>
    </TableHeader>
  )
}

function Columns() {
  return (
    <colgroup>
      <col className={SELECT_COL} />
      <col className={THUMB_COL} />
      <col />
      <col className={DURATION_COL} />
    </colgroup>
  )
}

/** ตารางเลือกคลิปของหน้า W3: ช่องติ๊ก · ปก · ชื่อคลิป · ความยาว (ไม่เกิน 200 แถว จึงไม่ต้องแบ่งหน้า) */
export function BatchTable({ rows, deselected, onToggle, onToggleAll }: Props) {
  return (
    <Table className="table-fixed" aria-label={t.crumb}>
      <Columns />
      <Header rows={rows} deselected={deselected} onToggleAll={onToggleAll} />
      <TableBody>
        {rows.map((row, index) =>
          row.invalid ? (
            <InvalidRow key={`invalid-${index}`} input={row.invalid.input} />
          ) : (
            <ClipRow key={row.videoId} row={row} selected={!deselected.has(row.videoId)} onToggle={onToggle} />
          )
        )}
      </TableBody>
    </Table>
  )
}

/** โครงรอระหว่างโหลดเพลย์ลิสต์: หัวตารางจริงกับแถวเปล่า */
export function BatchTableSkeleton() {
  return (
    <Table className="table-fixed" aria-hidden="true">
      <Columns />
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead colSpan={2} className={HEAD}>
            {t.selectAll}
          </TableHead>
          <TableHead className={HEAD}>{t.columns.title}</TableHead>
          <TableHead className={`${DURATION_COL} ${HEAD}`}>{t.columns.duration}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {Array.from({ length: 5 }, (_, index) => (
          <TableRow key={index} className="hover:bg-transparent">
            <TableCell>
              <Skeleton className="size-4 rounded-[4px]" />
            </TableCell>
            <TableCell className="py-2">
              <Skeleton className="aspect-video w-20" />
            </TableCell>
            <TableCell>
              <Skeleton className="h-4 w-48 max-w-full" />
            </TableCell>
            <TableCell>
              <Skeleton className="h-3.5 w-10" />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
