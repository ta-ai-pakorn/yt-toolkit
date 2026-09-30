import { CircleX } from "lucide-react"
import { useRef, useState } from "react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { InputGroup, InputGroupAddon, InputGroupTextarea } from "@/components/ui/input-group"
import { Kbd } from "@/components/ui/kbd"
import { Spinner } from "@/components/ui/spinner"
import { fill, th } from "@/i18n/th"
import { looksLikeYoutube } from "@/lib/paste"
import { pasteShortcut } from "@/lib/platform"

import { RecentSection } from "./home/recent"
import { ResultList } from "./home/result-list"
import { homeStore, useHomeState } from "./home/state"
import { useAnalyze, useGlobalPaste } from "./home/use-analyze"

export function HomePage() {
  // ข้อความและรายการผลอยู่ใน homeStore: ไปหน้าคลิปแล้วกลับมา หรือโหลดหน้าใหม่ ก็ยังอยู่ครบ
  const { text, results, listId, skipped } = useHomeState()
  const { analyze: run, pending, error, dialog } = useAnalyze()
  const inputRef = useRef<HTMLTextAreaElement>(null)
  // กลับมาหน้านี้ (ปุ่ม back / โหลดหน้าใหม่) แล้วช่องยังมีข้อความเดิม: แตะช่องครั้งแรกเลือกข้อความทั้งหมด
  // วางลิงก์ใหม่จึงแทนที่ของเดิมและวิเคราะห์ทันที (ไม่กลายเป็นสองลิงก์ต่อกัน) · ครั้งต่อไปทำงานปกติ
  const selectOnFirstFocus = useRef(text.trim() !== "")
  // ข้อความทั้งหมดยังถูกเลือกจากการแตะครั้งแรก (วางตอนนี้ = แทนที่ของเดิม)
  const restoredSelected = useRef(false)
  // คลิกเมาส์: เบราว์เซอร์วางเคอร์เซอร์ตอนปล่อยปุ่ม ทับการเลือกทั้งหมด จึงกันไว้หนึ่งครั้ง
  // เฉพาะเมื่อโฟกัสครั้งแรกมาจากการคลิก (มาด้วย Tab ไม่มีการปล่อยปุ่มเมาส์ คลิกครั้งถัดไปต้องวางเคอร์เซอร์ตามปกติ)
  const keepSelectionOnMouseUp = useRef(false)
  const pointerDown = useRef(false)
  // ข้อความประกาศให้โปรแกรมอ่านหน้าจอหลังกด "ล้างรายการ"
  const [announce, setAnnounce] = useState("")

  function analyze(value: string) {
    if (pending) return
    if (!value.trim()) {
      inputRef.current?.focus()
      return
    }
    setAnnounce("")
    run(value)
  }

  useGlobalPaste(analyze, pending)

  function clearList() {
    homeStore.clear()
    setAnnounce(th.home.results.cleared)
    // ปุ่มที่กดหายไปพร้อมรายการ: ส่งโฟกัสกลับช่องวางลิงก์ พร้อมวางลิงก์ใหม่ได้เลย
    inputRef.current?.focus()
  }

  function wholePlaylist(index: number) {
    if (!results) return
    homeStore.set({ results: results.map((item, i) => (i === index ? { ...item, kind: "playlist" } : item)) })
  }

  const [before, after] = th.home.pasteHint.split("{key}")

  return (
    <section className="mx-auto flex max-w-[640px] flex-col gap-6 pt-16">
      <div className="flex flex-col items-center gap-2 text-center">
        <h1 className="text-2xl leading-relaxed font-semibold">{th.home.title}</h1>
        <p className="text-muted-foreground">
          {th.home.subtitle} · {before}
          <Kbd>{pasteShortcut()}</Kbd>
          {after}
        </p>
      </div>
      <form
        className="flex flex-col gap-3 text-left"
        onSubmit={(event) => {
          event.preventDefault()
          analyze(text)
        }}
      >
        <InputGroup>
          <InputGroupTextarea
            ref={inputRef}
            aria-label={th.home.inputLabel}
            placeholder={th.home.placeholder}
            className="max-h-[calc(8lh+1rem)] min-h-24 overflow-y-auto"
            value={text}
            onChange={(event) => {
              restoredSelected.current = false
              homeStore.set({ text: event.target.value })
            }}
            onMouseDown={() => {
              pointerDown.current = true
            }}
            onFocus={(event) => {
              const byPointer = pointerDown.current
              pointerDown.current = false
              if (!selectOnFirstFocus.current) return
              selectOnFirstFocus.current = false
              if (!event.currentTarget.value) return
              event.currentTarget.select()
              restoredSelected.current = true
              keepSelectionOnMouseUp.current = byPointer
            }}
            onMouseUp={(event) => {
              pointerDown.current = false
              if (!keepSelectionOnMouseUp.current) return
              keepSelectionOnMouseUp.current = false
              event.preventDefault()
            }}
            onBlur={() => {
              restoredSelected.current = false
              keepSelectionOnMouseUp.current = false
            }}
            onPaste={(event) => {
              const box = event.currentTarget
              const replacesAll =
                restoredSelected.current && box.selectionStart === 0 && box.selectionEnd === box.value.length
              restoredSelected.current = false
              const pasted = event.clipboardData.getData("text")
              if (!replacesAll || !looksLikeYoutube(pasted)) return
              event.preventDefault()
              analyze(pasted)
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                event.preventDefault()
                analyze(text)
              }
            }}
          />
          <InputGroupAddon align="block-end" className="justify-end">
            {/* aria-disabled แทน disabled เพื่อให้โฟกัสยังอยู่ที่ปุ่ม (analyze() กันการกดซ้ำอยู่แล้ว) */}
            <Button
              type="submit"
              aria-disabled={pending}
              className="aria-disabled:pointer-events-none aria-disabled:opacity-50"
            >
              {pending && <Spinner />}
              {th.home.analyze}
            </Button>
          </InputGroupAddon>
        </InputGroup>
        {error && (
          <Alert variant="destructive">
            <CircleX aria-hidden />
            <AlertTitle>{th.home.resolveFailed}</AlertTitle>
            <AlertDescription>{error.message}</AlertDescription>
          </Alert>
        )}
      </form>
      <p role="status" className="sr-only">
        {results ? fill(th.home.results.count, { n: results.length }) : announce}
      </p>
      {results && (
        <ResultList items={results} listId={listId} skipped={skipped} onWhole={wholePlaylist} onClear={clearList} />
      )}
      <RecentSection />
      <p className="text-center text-sm text-muted-foreground">{th.home.usage}</p>
      {dialog}
    </section>
  )
}
