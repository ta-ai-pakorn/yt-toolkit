import { useEffect, useEffectEvent, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import { InputGroup, InputGroupAddon, InputGroupTextarea } from "@/components/ui/input-group"
import { Kbd } from "@/components/ui/kbd"
import { th } from "@/i18n/th"
import { pasteShortcut } from "@/lib/platform"

export function HomePage() {
  const [text, setText] = useState("")
  const [note, setNote] = useState<string | null>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  function analyze(value: string) {
    if (!value.trim()) {
      inputRef.current?.focus()
      return
    }
    setNote(th.home.notReady)
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
    <section className="mx-auto flex max-w-[560px] flex-col items-center gap-6 pt-16 text-center">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold leading-relaxed">{th.home.title}</h1>
        <p className="text-muted-foreground">
          {th.home.subtitle} · {before}
          <Kbd>{pasteShortcut()}</Kbd>
          {after}
        </p>
      </div>
      <form
        className="w-full text-left"
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
            className="min-h-24"
            value={text}
            onChange={(event) => {
              setText(event.target.value)
              setNote(null)
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                event.preventDefault()
                analyze(text)
              }
            }}
          />
          <InputGroupAddon align="block-end" className="justify-end">
            <Button type="submit">{th.home.analyze}</Button>
          </InputGroupAddon>
        </InputGroup>
        {note && (
          <p role="status" className="mt-2 text-sm text-muted-foreground">
            {note}
          </p>
        )}
      </form>
      <p className="text-sm text-muted-foreground">{th.home.usage}</p>
    </section>
  )
}
