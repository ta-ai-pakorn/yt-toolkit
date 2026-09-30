import { useMutation } from "@tanstack/react-query"
import { useEffect, useEffectEvent, useState, type ReactNode } from "react"
import { useLocation, useNavigate } from "react-router"
import { toast } from "sonner"

import { th } from "@/i18n/th"
import { api } from "@/lib/api"
import { looksLikeYoutube } from "@/lib/paste"
import type { ResolveItem, ResolveResult } from "@/lib/types"

import { AmbiguousDialog } from "./ambiguous-dialog"
import { homeStore } from "./state"

/**
 * state ของ router ที่ลิงก์ในรายการผลส่งไปหน้า W2: breadcrumb แสดง "รายการที่วาง" และมีปุ่มคลิปก่อนหน้า/ถัดไป
 * `playlist` = เปิดจากรายชื่อคลิปที่กางใต้แถวเพลย์ลิสต์/มิกซ์ (ก่อนหน้า/ถัดไปไล่ตามคลิปในเพลย์ลิสต์นั้น)
 */
export type FromListState = { fromList: true; playlist?: { id: string; v?: string } }

export const fromListState: FromListState = { fromList: true }

export function fromPlaylistState(playlistId: string, mixVideoId?: string): FromListState {
  return { fromList: true, playlist: mixVideoId ? { id: playlistId, v: mixVideoId } : { id: playlistId } }
}

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null

/** อ่าน state ของ router อย่างระวัง (ค่ามาจากประวัติของเบราว์เซอร์ อาจเป็นอะไรก็ได้) · ไม่ได้มาจากรายการ = null */
export function readFromList(state: unknown): FromListState | null {
  if (!isRecord(state) || state.fromList !== true) return null
  const playlist = state.playlist
  if (isRecord(playlist) && typeof playlist.id === "string") {
    return fromPlaylistState(playlist.id, typeof playlist.v === "string" ? playlist.v : undefined)
  }
  return fromListState
}

export function isFromList(state: unknown): boolean {
  return readFromList(state) !== null
}

const newListId = () => (crypto.randomUUID?.() ?? String(Date.now())).replaceAll("-", "")

/**
 * ขั้นตอน "วิเคราะห์ลิงก์" ที่ใช้ร่วมกันทั้ง W1 และ W2 (วางลิงก์ที่หน้าคลิป):
 * คลิปเดียว → ไปหน้าคลิป · ลิงก์ที่เป็นทั้งคลิปและเพลย์ลิสต์/มิกซ์ → กล่องถาม · อย่างอื่น → รายการผลที่ W1
 *
 * ข้อความและรายการผลเก็บใน homeStore (อยู่รอดตอนสลับหน้าและโหลดหน้าใหม่)
 * ที่ W1 ข้อความในช่องคือสิ่งที่วิเคราะห์อยู่แล้ว ส่วนหน้าอื่น (วางที่ W2) ข้อความและรายการเดิมของ W1 ไม่ถูกแตะ
 * จนกว่าจะวิเคราะห์สำเร็จจริง (ไปหน้าคลิป หรือแสดงรายการ) — ปิดกล่องถามหรือวิเคราะห์ไม่สำเร็จ = รายการเดิมอยู่ครบ
 * คืน `dialog` ที่ผู้เรียกต้องวางไว้ในหน้า
 */
export function useAnalyze() {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const onHome = pathname === "/"
  // เก็บ item ไว้แยกจากสถานะเปิด/ปิด เพื่อให้เนื้อหากล่องไม่หายตอนกำลังเล่นแอนิเมชันปิด
  const [ambiguous, setAmbiguous] = useState<ResolveItem | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  // ข้อความที่วิเคราะห์ล่าสุด: บันทึกลงช่องของ W1 เมื่อสำเร็จ
  const [analyzed, setAnalyzed] = useState("")

  function openClip(videoId: string, value: string) {
    homeStore.set({ text: value, results: null, skipped: false, expanded: {} })
    void navigate(`/v/${videoId}`)
  }

  function showList(items: ResolveItem[], listId: string, value: string, skipped: boolean) {
    homeStore.set({ text: value, results: items, listId, skipped, expanded: {} })
    if (!onHome) void navigate("/")
  }

  const resolve = useMutation({
    mutationFn: (value: string) =>
      api<ResolveResult>("/resolve", { method: "POST", body: JSON.stringify({ text: value }) }),
    onMutate: () => {
      // W1: ซ่อนรายการเก่าระหว่างวิเคราะห์ (ข้อความใหม่อยู่ในช่องแล้ว) · หน้าอื่นไม่แตะรายการของ W1
      if (onHome) homeStore.set({ results: null, skipped: false, expanded: {} })
      setDialogOpen(false)
    },
    onSuccess: ({ resolveId, items, skippedText }, value) => {
      const only = items.length === 1 ? items[0] : null
      if (only?.kind === "video" && only.videoId) {
        openClip(only.videoId, value)
      } else if (only?.kind === "ambiguous" && only.videoId && only.playlistId) {
        setAnalyzed(value)
        setAmbiguous(only)
        setDialogOpen(true)
      } else {
        showList(items, resolveId, value, skippedText === true)
      }
    },
    onError: (error) => {
      // W1 แสดงข้อความใต้ช่องเอง ส่วนหน้าอื่นไม่มีช่อง จึงแจ้งด้วย toast
      if (!onHome) toast.error(`${th.home.resolveFailed} · ${error.message}`)
    },
  })

  function analyze(value: string) {
    if (resolve.isPending) return
    // W1: ช่องแสดงข้อความที่กำลังวิเคราะห์ทันที (เช่นกด Ctrl+V นอกช่อง)
    if (onHome) homeStore.set({ text: value })
    resolve.mutate(value)
  }

  const dialog: ReactNode = (
    <AmbiguousDialog
      open={dialogOpen}
      item={ambiguous}
      onOpenChange={setDialogOpen}
      onClip={(item) => {
        setDialogOpen(false)
        if (item.videoId) openClip(item.videoId, analyzed)
      }}
      onPlaylist={(item) => {
        setDialogOpen(false)
        showList([{ ...item, kind: "playlist" }], newListId(), analyzed, false)
      }}
    />
  )

  return {
    analyze,
    pending: resolve.isPending,
    error: resolve.isError ? resolve.error : null,
    dialog,
  }
}

/**
 * Ctrl/⌘+V ที่ไหนก็ได้นอกช่องกรอก และคลิปบอร์ดเป็นลิงก์ยูทูป → เรียก onPaste ทันที (AC-IN-06)
 * `busy` = กำลังวิเคราะห์อยู่: ปล่อยให้เบราว์เซอร์ทำตามปกติ ไม่กลืนลิงก์ที่วางมา
 */
export function useGlobalPaste(onPaste: (text: string) => void, busy: boolean) {
  // ตัวฟัง paste ผูกครั้งเดียว แต่ต้องอ่านสถานะล่าสุดเสมอ
  const handle = useEffectEvent((event: ClipboardEvent) => {
    if (busy) return
    const target = event.target as HTMLElement | null
    if (target && (target.tagName === "TEXTAREA" || target.tagName === "INPUT" || target.isContentEditable)) return
    const pasted = event.clipboardData?.getData("text") ?? ""
    if (!looksLikeYoutube(pasted)) return
    event.preventDefault()
    onPaste(pasted)
  })

  useEffect(() => {
    const listener = (event: ClipboardEvent) => handle(event)
    window.addEventListener("paste", listener)
    return () => window.removeEventListener("paste", listener)
  }, [])
}
