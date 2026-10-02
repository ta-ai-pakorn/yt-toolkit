import { useInfiniteQuery } from "@tanstack/react-query"
import { Search, X } from "lucide-react"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Link, useSearchParams } from "react-router"

import { Button, buttonVariants } from "@/components/ui/button"
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty"
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from "@/components/ui/input-group"
import { Spinner } from "@/components/ui/spinner"
import { fill, th } from "@/i18n/th"
import type { HistoryItem } from "@/lib/types"
import { cn } from "cn"

import { HistoryTable, HistoryTableSkeleton } from "./history/history-table"
import { historyQuery } from "./history/queries"
import { LoadError } from "./video/load-error"

const SEARCH_DEBOUNCE_MS = 300

/** คลิปเดียวกันโผล่ในสองหน้า (ข้อมูลขยับระหว่างโหลดต่อ) แสดงครั้งเดียว */
function uniqueItems(pages: { items: HistoryItem[] }[]): HistoryItem[] {
  const seen = new Map<string, HistoryItem>()
  for (const page of pages) for (const item of page.items) if (!seen.has(item.videoId)) seen.set(item.videoId, item)
  return [...seen.values()]
}

/** หน้า W5 (/history): คลิปที่เคยเปิดดูหรือโหลดไฟล์ เรียงใหม่สุดก่อน · ค้นจากชื่อ (คำค้นอยู่ใน ?q=) · หน้าละ 50 คลิป */
export function HistoryPage() {
  const [params, setParams] = useSearchParams()
  const urlQ = (params.get("q") ?? "").trim()
  const [input, setInput] = useState(urlQ)
  const inputRef = useRef<HTMLInputElement>(null)
  const tableRef = useRef<HTMLDivElement>(null)
  // คำค้นล่าสุดที่หน้านี้เขียนลง URL เอง: URL เปลี่ยนเป็นค่าอื่น = มาจากข้างนอก (เช่นกดเมนู "ประวัติ" ตอนค้นอยู่)
  const lastWritten = useRef(urlQ)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  useEffect(() => {
    const previous = document.title
    document.title = fill(th.history.pageTitle, { app: th.app.name })
    return () => {
      document.title = previous
    }
  }, [])

  // คำค้นเข้า URL แบบ replace: พิมพ์ทีละตัวไม่เพิ่มรายการในประวัติเบราว์เซอร์ (ปุ่ม back ยังกลับหน้าก่อนหน้าได้ทันที)
  const writeQ = useCallback(
    (term: string) => {
      lastWritten.current = term
      setParams(
        (previous) => {
          const next = new URLSearchParams(previous)
          if (term) next.set("q", term)
          else next.delete("q")
          return next
        },
        { replace: true },
      )
    },
    [setParams],
  )

  // URL เปลี่ยนจากข้างนอก: ช่องค้นหาตามค่าใหม่ และยกเลิกคำค้นที่รอเขียนอยู่ ไม่ให้เขียนทับกลับ
  useEffect(() => {
    if (urlQ === lastWritten.current) return
    lastWritten.current = urlQ
    clearTimeout(timer.current)
    setInput(urlQ)
  }, [urlQ])

  useEffect(() => () => clearTimeout(timer.current), [])

  function onSearchChange(value: string) {
    setInput(value)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      const term = value.trim()
      if (term !== lastWritten.current) writeQ(term)
    }, SEARCH_DEBOUNCE_MS)
  }

  const history = useInfiniteQuery(historyQuery(urlQ))
  const items = useMemo(() => (history.data ? uniqueItems(history.data.pages) : []), [history.data])
  const total = history.data?.pages.at(-1)?.total ?? 0
  const firstTotal = history.data?.pages[0]?.total ?? 0
  const searching = urlQ !== "" || input.trim() !== ""
  // ไม่มีประวัติเลยก็ไม่มีอะไรให้ค้น: ซ่อนช่องค้นหาไว้จนกว่าจะมีคลิป
  const showSearch = searching || firstTotal > 0

  // ปุ่มล้าง: เขียน URL ทันที ไม่รอ 300 ms (กดแล้วรายการเต็มกลับมาเลย)
  function clearSearch() {
    clearTimeout(timer.current)
    setInput("")
    if (lastWritten.current !== "") writeQ("")
    inputRef.current?.focus()
  }

  // "แสดงเพิ่ม": ปุ่มไม่ถูก disable/ถอดออกขณะโหลด (โฟกัสจะหลุด) ใช้ aria-disabled แล้วเมื่อแถวใหม่มา ย้ายโฟกัสไปลิงก์แถวแรกที่เพิ่มมา
  const focusFrom = useRef<number | null>(null)
  function showMore() {
    if (history.isFetchingNextPage) return
    focusFrom.current = items.length
    void history.fetchNextPage()
  }
  useEffect(() => {
    const from = focusFrom.current
    if (from === null || items.length <= from) return
    focusFrom.current = null
    tableRef.current?.querySelectorAll<HTMLElement>("tbody tr")[from]?.querySelector<HTMLElement>("a")?.focus()
  }, [items.length])

  return (
    <section className="flex flex-col gap-4 pt-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-semibold">{th.history.title}</h1>
        {showSearch && (
          <InputGroup className="h-10 sm:max-w-xs">
            <InputGroupAddon>
              <Search aria-hidden />
            </InputGroupAddon>
            <InputGroupInput
              ref={inputRef}
              type="text"
              value={input}
              onChange={(event) => onSearchChange(event.target.value)}
              aria-label={th.history.search}
              placeholder={th.history.search}
              autoComplete="off"
              enterKeyHint="search"
            />
            {input !== "" && (
              <InputGroupAddon align="inline-end">
                <InputGroupButton size="icon-sm" aria-label={th.history.clearSearch} onClick={clearSearch}>
                  <X aria-hidden />
                </InputGroupButton>
              </InputGroupAddon>
            )}
          </InputGroup>
        )}
      </div>

      {history.isPending ? (
        <HistoryTableSkeleton />
      ) : history.isError && !history.data ? (
        <LoadError title={th.history.loadError} error={history.error} onRetry={() => void history.refetch()} />
      ) : items.length === 0 ? (
        urlQ ? (
          <p role="status" className="py-8 text-center text-muted-foreground [overflow-wrap:anywhere]">
            {fill(th.history.noMatch, { q: urlQ })}
          </p>
        ) : (
          <Empty className="border py-12">
            <EmptyHeader>
              <EmptyTitle>{th.history.empty}</EmptyTitle>
              <EmptyDescription>{th.history.emptyHint}</EmptyDescription>
            </EmptyHeader>
            <Link to="/" className={buttonVariants({ variant: "outline" })}>
              {th.common.backHome}
            </Link>
          </Empty>
        )
      ) : (
        <>
          <div ref={tableRef} className={cn("transition-opacity", history.isPlaceholderData && "opacity-60")}>
            <HistoryTable items={items} />
          </div>
          {history.isError && (
            <LoadError
              title={th.history.loadError}
              error={history.error}
              onRetry={() => void (history.isFetchNextPageError ? history.fetchNextPage() : history.refetch())}
            />
          )}
          <div className="flex flex-col items-center gap-3 pt-2">
            <p role="status" className="text-sm text-muted-foreground">
              {fill(th.history.shown, { n: items.length, total })}
            </p>
            {history.hasNextPage && (
              <Button variant="outline" aria-disabled={history.isFetchingNextPage} className="aria-disabled:opacity-50" onClick={showMore}>
                {history.isFetchingNextPage && <Spinner data-icon="inline-start" />}
                {th.history.more}
              </Button>
            )}
          </div>
        </>
      )}
    </section>
  )
}
