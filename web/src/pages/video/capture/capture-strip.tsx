import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Download, ExternalLink, FolderOpen, ImageIcon, Play, Trash2 } from "lucide-react"
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react"
import { toast } from "sonner"

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { AspectRatio } from "@/components/ui/aspect-ratio"
import { Button } from "@/components/ui/button"
import { fill, th } from "@/i18n/th"
import { copyImage } from "@/lib/clipboard"
import { downloadFile } from "@/lib/download"
import { youtubeWatchUrl } from "@/lib/format"
import type { Capture } from "@/lib/types"
import { cn } from "cn"

import { errorMessage, hasCode } from "../errors"
import { Lightbox } from "../lightbox"
import { playerActions } from "../player/player-store"
import { capturesKey, capturesQuery, deleteCapture, revealCaptures, withoutCapture } from "./capture-api"
import {
  captureClock,
  captureDownloadUrl,
  captureFileName,
  focusAfterDelete,
  revealScrollLeft,
  stripKeyTarget,
} from "./capture-model"
import { captureStore, useCaptureUi } from "./capture-store"

/** wrap = ภาพตัดขึ้นบรรทัด (แบบปกติ จอแคบ แนวตั้ง) · row = แถวเดียวเลื่อนได้ (โรงภาพยนตร์แนวนอน) */
export type StripLayout = "wrap" | "row"

const TILE_BUTTON =
  "relative block w-full cursor-zoom-in overflow-hidden rounded-md bg-black outline-none hover:ring-2 hover:ring-ring/40 focus-visible:ring-3 focus-visible:ring-ring"

const reducedMotion = () =>
  typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches

/** ตำแหน่งที่โฟกัสได้เมื่อแถบหายไป (ลบภาพสุดท้ายแล้ว): ปุ่มถ่ายภาพ ไม่มีก็ชื่อคลิป */
function fallbackFocus(): HTMLElement | null {
  return document.querySelector<HTMLElement>('[data-slot="capture-button"]') ?? document.querySelector<HTMLElement>("h1")
}

async function copyCapture(url: string): Promise<void> {
  try {
    await copyImage(url)
    toast.success(th.frames.imageCopied)
  } catch {
    toast.error(th.frames.copyImageFailed)
  }
}

async function downloadCapture(capture: Capture): Promise<void> {
  const id = toast.loading(th.frames.preparing)
  try {
    await downloadFile(captureDownloadUrl(capture.url), captureFileName(capture.tMs))
    toast.dismiss(id)
  } catch (error) {
    toast.error(errorMessage(error, th.errors.downloadFailed), { id })
  }
}

/**
 * แถบ "ภาพที่ถ่ายไว้ ({n})" ใต้ตัวเล่น (M5 รอบ B2 spec 2.3): ภาพ 16:9 กว้างราว 96 px พร้อมป้ายเวลา เรียงตามเวลา
 * จุดหยุด Tab เดียว (ภาพที่โฟกัสล่าสุด) ลูกศร/Home/End เลื่อน Enter/Space เปิดภาพใหญ่ · ภาพแนวตั้งเว้นขอบในช่อง 16:9
 * ไม่มีภาพ / กำลังโหลด / โหลดไม่ได้ = ไม่แสดงอะไร (แถบเป็นของเสริม) · ภาพใหญ่มีปุ่ม คัดลอก โหลด เปิดในยูทูป เล่นจากตรงนี้ ลบ
 */
export function CaptureStrip({ videoId, layout, className }: { videoId: string; layout: StripLayout; className?: string }) {
  const client = useQueryClient()
  const captures = useQuery(capturesQuery(videoId, true))
  const list = captures.data ?? []
  const viewing = useCaptureUi((s) => (s.viewing?.videoId === videoId ? s.viewing.id : null))
  const flash = useCaptureUi((s) => (s.flash?.videoId === videoId ? s.flash : null))
  const [active, setActive] = useState(0)
  const [confirming, setConfirming] = useState<Capture | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [lastViewed, setLastViewed] = useState<Capture | null>(null)
  const buttons = useRef(new Map<string, HTMLButtonElement>())
  const listRef = useRef<HTMLUListElement>(null)
  const afterDelete = useRef<string | null>(null)
  const headingId = useId()

  const viewIndex = viewing === null ? -1 : list.findIndex((c) => c.id === viewing)
  const current = viewIndex >= 0 ? list[viewIndex] : null
  // จำภาพล่าสุดไว้ ให้ภาพยังอยู่ระหว่างแอนิเมชันปิด
  if (current !== null && current !== lastViewed) setLastViewed(current)
  const shown = current ?? lastViewed
  const tabStop = Math.min(active, Math.max(0, list.length - 1))

  // คำสั่งเปิดภาพ/กระพริบที่ค้างของคลิปอื่นไม่ใช่ของแถบนี้ · แถบหายไป = กระพริบที่ยังไม่ได้ใช้ของคลิปนี้ไม่ต้องรอ
  useEffect(() => {
    captureStore.dropOtherClips(videoId)
    return () => captureStore.dropFlash(videoId)
  }, [videoId])

  // ขอเปิดภาพที่ไม่มีในรายการแล้ว (โหลดรายการเสร็จแล้วยังไม่พบ เช่นถูกลบไปแล้ว) = เลิกค้างไว้ ไม่เปิดให้ตอนเข้ามาดูครั้งหลัง
  const settled = captures.data !== undefined && !captures.isFetching
  useEffect(() => {
    if (settled && viewing !== null && viewIndex < 0) captureStore.closeView()
  }, [settled, viewing, viewIndex])

  // ภาพที่เพิ่งถ่าย (หรือถ่ายซ้ำเวลาเดิม): เลื่อนเฉพาะแถวภาพนี้ให้เห็น (ไม่เลื่อนทั้งหน้า) แล้วกระพริบกรอบสั้น ๆ
  // (ลดการเคลื่อนไหว = ไม่กระพริบ) ใช้ครั้งเดียว: ยังไม่เห็นภาพในรายการ = รอรายการอัปเดตแล้วค่อยทำ
  useEffect(() => {
    if (flash === null) return
    const node = buttons.current.get(flash.id)
    if (!node) return
    captureStore.consumeFlash(flash.n)
    const row = listRef.current
    if (row && row.scrollWidth > row.clientWidth) {
      const box = node.getBoundingClientRect()
      const rowBox = row.getBoundingClientRect()
      const left = revealScrollLeft({
        itemLeft: box.left - rowBox.left + row.scrollLeft,
        itemWidth: box.width,
        viewLeft: row.scrollLeft,
        viewWidth: row.clientWidth,
      })
      if (left !== row.scrollLeft) row.scrollTo({ left, behavior: reducedMotion() ? "auto" : "smooth" })
    }
    if (reducedMotion() || typeof node.animate !== "function") return
    node.animate(
      [{ boxShadow: "0 0 0 3px var(--primary)" }, { boxShadow: "0 0 0 0 transparent" }],
      { duration: 1200, easing: "ease-out" },
    )
  }, [flash, captures.data])

  if (list.length === 0) return null

  function focusAt(index: number) {
    setActive(index)
    buttons.current.get(list[index].id)?.focus()
  }

  function onKeyDown(event: KeyboardEvent<HTMLUListElement>) {
    const index = list.findIndex((c) => buttons.current.get(c.id) === document.activeElement)
    if (index < 0) return
    const next = stripKeyTarget(event.key, index, list.length)
    if (next === null) return
    event.preventDefault()
    focusAt(next)
  }

  function onLightboxKey(event: KeyboardEvent<HTMLDivElement>) {
    if (viewIndex < 0) return
    const next = event.key === "ArrowRight" ? viewIndex + 1 : event.key === "ArrowLeft" ? viewIndex - 1 : -1
    if (next < 0 || next >= list.length) return
    event.preventDefault()
    setActive(next)
    captureStore.view({ videoId, id: list[next].id })
  }

  function returnFocus(): HTMLElement | null {
    const target = afterDelete.current ?? shown?.id ?? null
    afterDelete.current = null
    return (target !== null ? buttons.current.get(target) : undefined) ?? fallbackFocus()
  }

  async function confirmDelete() {
    if (confirming === null || deleting) return
    const removed = confirming
    setDeleting(true)
    try {
      try {
        await deleteCapture(videoId, removed.id)
      } catch (error) {
        // ภาพหายไปแล้ว (ถูกลบจากที่อื่น) = ถือว่าลบสำเร็จ · พลาดแบบอื่น = แจ้งแล้วโหลดรายการใหม่ให้ตรงกับของจริง
        if (!hasCode(error, "E_NOT_FOUND")) {
          toast.error(errorMessage(error, th.errors.unknown))
          void client.invalidateQueries({ queryKey: capturesKey(videoId) })
          return
        }
      }
      const next = focusAfterDelete(list.map((c) => c.id), removed.id)
      afterDelete.current = next
      client.setQueryData<Capture[]>(capturesKey(videoId), (old) => withoutCapture(old, removed.id))
      setConfirming(null)
      captureStore.closeView()
      toast.success(th.capture.deleted)
      // กล่องยืนยันกับภาพใหญ่ปิดพร้อมกัน: หลังแอนิเมชันปิดจบ โฟกัสภาพถัดไป (ไม่เหลือภาพ = ปุ่มถ่ายภาพ / ชื่อคลิป)
      window.setTimeout(() => ((next !== null ? buttons.current.get(next) : undefined) ?? fallbackFocus())?.focus(), 200)
    } finally {
      setDeleting(false)
    }
  }

  async function reveal() {
    try {
      await revealCaptures(videoId)
    } catch (error) {
      toast.error(errorMessage(error, th.errors.unknown))
    }
  }

  const time = shown ? captureClock(shown.tMs) : ""
  return (
    <section aria-labelledby={headingId} data-slot="capture-strip" className={cn("flex min-w-0 flex-col gap-1.5", className)}>
      <div className="flex items-center justify-between gap-2">
        <h2 id={headingId} className="text-sm font-medium">
          {fill(th.capture.stripTitle, { n: list.length })}
        </h2>
        <Button variant="link" size="sm" className="h-auto px-0 max-sm:h-11" onClick={() => void reveal()}>
          <FolderOpen aria-hidden />
          {th.capture.openFolder}
        </Button>
      </div>
      <ul
        ref={listRef}
        aria-labelledby={headingId}
        onKeyDown={onKeyDown}
        className={cn("flex gap-2 p-[3px]", layout === "row" ? "overflow-x-auto" : "flex-wrap")}
      >
        {list.map((capture, index) => {
          const clock = captureClock(capture.tMs)
          return (
            <li key={capture.id} className="w-24 shrink-0">
              <button
                ref={(node) => {
                  if (node) buttons.current.set(capture.id, node)
                  else buttons.current.delete(capture.id)
                }}
                type="button"
                tabIndex={index === tabStop ? 0 : -1}
                aria-haspopup="dialog"
                onFocus={() => setActive(index)}
                onClick={() => {
                  setActive(index)
                  captureStore.view({ videoId, id: capture.id })
                }}
                className={TILE_BUTTON}
              >
                <AspectRatio ratio={16 / 9}>
                  <img
                    src={capture.url}
                    alt={fill(th.frames.frameAlt, { time: clock })}
                    loading="lazy"
                    decoding="async"
                    className="size-full object-contain"
                  />
                  <span
                    aria-hidden
                    className="pointer-events-none absolute bottom-0.5 left-0.5 rounded-sm bg-background/85 px-1 font-mono text-[11px] text-foreground"
                  >
                    {clock}
                  </span>
                </AspectRatio>
              </button>
            </li>
          )
        })}
      </ul>
      {shown && (
        <Lightbox
          open={current !== null}
          src={shown.url}
          label={fill(th.frames.frameAlt, { time })}
          onClose={() => captureStore.closeView()}
          finalFocus={returnFocus}
          sizeKey={shown.url}
          onKeyDown={onLightboxKey}
        >
          <span className="sr-only" aria-live="polite">
            {time}
          </span>
          <div data-slot="capture-actions" className="mt-2 flex flex-wrap items-center justify-center gap-2">
            <Button variant="secondary" size="sm" onClick={() => void copyCapture(shown.url)}>
              <ImageIcon aria-hidden />
              {th.frames.copyImage}
            </Button>
            <Button variant="secondary" size="sm" onClick={() => void downloadCapture(shown)}>
              <Download aria-hidden />
              {th.frames.downloadFrame}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => window.open(youtubeWatchUrl(videoId, shown.tMs), "_blank", "noopener,noreferrer")}
            >
              <ExternalLink aria-hidden />
              {th.frames.openYoutubeAt}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                captureStore.closeView()
                playerActions.playFrom(shown.tMs)
              }}
            >
              <Play aria-hidden />
              {th.frames.playFrom}
            </Button>
            <Button variant="destructive" size="sm" onClick={() => setConfirming(shown)}>
              <Trash2 aria-hidden />
              {th.capture.delete}
            </Button>
          </div>
        </Lightbox>
      )}
      <AlertDialog open={confirming !== null} onOpenChange={(open) => !open && !deleting && setConfirming(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{th.capture.deleteConfirm}</AlertDialogTitle>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>{th.capture.cancel}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" disabled={deleting} onClick={() => void confirmDelete()}>
              <Trash2 aria-hidden />
              {th.capture.deleteAction}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  )
}
