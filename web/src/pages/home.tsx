import { useMutation } from "@tanstack/react-query"
import { CircleX } from "lucide-react"
import { useEffect, useEffectEvent, useRef, useState } from "react"
import { useNavigate } from "react-router"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { InputGroup, InputGroupAddon, InputGroupTextarea } from "@/components/ui/input-group"
import { Kbd } from "@/components/ui/kbd"
import { Spinner } from "@/components/ui/spinner"
import { th } from "@/i18n/th"
import { api } from "@/lib/api"
import { pasteShortcut } from "@/lib/platform"
import type { ResolveItem, ResolveResult } from "@/lib/types"

import { AmbiguousDialog } from "./home/ambiguous-dialog"
import { RecentSection } from "./home/recent"
import { ResultList } from "./home/result-list"

export function HomePage() {
  const navigate = useNavigate()
  const [text, setText] = useState("")
  const [results, setResults] = useState<ResolveItem[] | null>(null)
  // เก็บ item ไว้แยกจากสถานะเปิด/ปิด เพื่อให้เนื้อหากล่องไม่หายตอนกำลังเล่นแอนิเมชันปิด
  const [ambiguous, setAmbiguous] = useState<ResolveItem | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const resolve = useMutation({
    mutationFn: (value: string) =>
      api<ResolveResult>("/resolve", { method: "POST", body: JSON.stringify({ text: value }) }),
    onMutate: () => {
      setResults(null)
      setDialogOpen(false)
    },
    onSuccess: ({ items }) => {
      const only = items.length === 1 ? items[0] : null
      if (only?.kind === "video" && only.videoId) {
        void navigate(`/v/${only.videoId}`)
      } else if (only?.kind === "ambiguous" && only.videoId && only.playlistId) {
        setAmbiguous(only)
        setDialogOpen(true)
      } else {
        setResults(items)
      }
    },
  })

  function analyze(value: string) {
    if (resolve.isPending) return
    if (!value.trim()) {
      inputRef.current?.focus()
      return
    }
    resolve.mutate(value)
  }

  // ตัวฟัง paste ผูกครั้งเดียว แต่ต้องเรียก analyze เวอร์ชันล่าสุดเสมอ
  const analyzePasted = useEffectEvent((value: string) => analyze(value))

  useEffect(() => {
    function onPaste(event: ClipboardEvent) {
      const target = event.target as HTMLElement | null
      if (target && (target.tagName === "TEXTAREA" || target.tagName === "INPUT" || target.isContentEditable)) return
      const pasted = event.clipboardData?.getData("text") ?? ""
      if (!/youtu\.?be/.test(pasted)) return
      event.preventDefault()
      setText(pasted)
      analyzePasted(pasted)
    }
    window.addEventListener("paste", onPaste)
    return () => window.removeEventListener("paste", onPaste)
  }, [])

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
            aria-label={th.home.placeholder}
            placeholder={th.home.placeholder}
            className="max-h-[calc(8lh+1rem)] min-h-24 overflow-y-auto"
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                event.preventDefault()
                analyze(text)
              }
            }}
          />
          <InputGroupAddon align="block-end" className="justify-end">
            <Button type="submit" disabled={resolve.isPending}>
              {resolve.isPending && <Spinner />}
              {th.home.analyze}
            </Button>
          </InputGroupAddon>
        </InputGroup>
        {resolve.isError && (
          <Alert variant="destructive">
            <CircleX aria-hidden />
            <AlertTitle>{th.home.resolveFailed}</AlertTitle>
            <AlertDescription>{resolve.error.message}</AlertDescription>
          </Alert>
        )}
      </form>
      {results && <ResultList items={results} />}
      <RecentSection />
      <p className="text-center text-sm text-muted-foreground">{th.home.usage}</p>
      <AmbiguousDialog
        open={dialogOpen}
        item={ambiguous}
        onOpenChange={setDialogOpen}
        onClip={(item) => {
          setDialogOpen(false)
          void navigate(`/v/${item.videoId}`)
        }}
        onPlaylist={(item) => {
          setDialogOpen(false)
          setResults([{ ...item, kind: "playlist" }])
        }}
      />
    </section>
  )
}
