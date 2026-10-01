import { ExternalLink, RotateCw, TriangleAlert, WifiOff } from "lucide-react"
import { useEffect, useRef } from "react"

import { Button, buttonVariants } from "@/components/ui/button"
import { th } from "@/i18n/th"
import { youtubeWatchUrl } from "@/lib/format"

import { playerActions, usePlayerValue, type PlayerError } from "./player-store"

const t = th.player

const MESSAGE: Record<PlayerError, string> = {
  embed_blocked: t.embedBlocked,
  unplayable: t.unplayable,
  offline: t.offline,
}

/**
 * ข้อความผิดพลาดในช่องตัวเล่น (แทนที่ตัวเล่น)
 * - เจ้าของไม่ให้ฝัง / เล่นไม่ได้: ลิงก์ "เปิดในยูทูป" ตรงเวลาที่ขอเล่น (&t=)
 * - โหลดสคริปต์ยูทูปไม่ได้ (ออฟไลน์): ปุ่ม "ลองอีกครั้ง"
 * ขึ้นมาครั้งแรก หรือมีคนกด "เล่นจากตรงนี้" ที่อื่นระหว่างผิดพลาด = โฟกัสข้อความนี้ (เลื่อนมาให้เห็น)
 */
export function PlayerErrorView({ videoId, error }: { videoId: string; error: PlayerError }) {
  const atMs = usePlayerValue((s) => s.errorAtMs)
  const nudge = usePlayerValue((s) => s.errorNudge)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const box = ref.current
    if (!box) return
    box.focus({ preventScroll: true })
    box.scrollIntoView({ block: "nearest" })
  }, [nudge])

  const Icon = error === "offline" ? WifiOff : TriangleAlert
  return (
    <div
      ref={ref}
      tabIndex={-1}
      role="alert"
      data-slot="player-error"
      data-error={error}
      className="flex size-full flex-col items-center justify-center gap-2 rounded-md border bg-muted p-3 text-center text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
    >
      <Icon aria-hidden className="size-5 text-muted-foreground" />
      <p className="text-balance">{MESSAGE[error]}</p>
      {error === "offline" ? (
        <Button variant="outline" size="sm" className="max-sm:h-11" onClick={() => playerActions.retry()}>
          <RotateCw aria-hidden />
          {t.retry}
        </Button>
      ) : (
        <a
          href={youtubeWatchUrl(videoId, atMs ?? undefined)}
          target="_blank"
          rel="noopener noreferrer"
          data-slot="button"
          className={buttonVariants({ variant: "outline", size: "sm", className: "max-sm:h-11" })}
        >
          <ExternalLink aria-hidden />
          {th.video.openYoutube}
          <span className="sr-only"> {th.video.newTab}</span>
        </a>
      )}
    </div>
  )
}
