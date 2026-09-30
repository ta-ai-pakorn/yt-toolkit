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

/** state ของ router ที่ลิงก์ "เปิดดู" ในรายการผลส่งไปหน้า W2 (breadcrumb ใช้แสดง "รายการที่วาง") */
export type FromListState = { fromList: true }

export const fromListState: FromListState = { fromList: true }

export function isFromList(state: unknown): boolean {
  return typeof state === "object" && state !== null && (state as Partial<FromListState>).fromList === true
}

const newListId = () => (crypto.randomUUID?.() ?? String(Date.now())).replaceAll("-", "")

/**
 * ขั้นตอน "วิเคราะห์ลิงก์" ที่ใช้ร่วมกันทั้ง W1 และ W2 (วางลิงก์ที่หน้าคลิป):
 * คลิปเดียว → ไปหน้าคลิป · ลิงก์ที่เป็นทั้งคลิปและเพลย์ลิสต์/มิกซ์ → กล่องถาม · อย่างอื่น → รายการผลที่ W1
 *
 * ข้อความและรายการผลเก็บใน homeStore (อยู่รอดตอนสลับหน้าและโหลดหน้าใหม่)
 * คืน `dialog` ที่ผู้เรียกต้องวางไว้ในหน้า
 */
export function useAnalyze() {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const onHome = pathname === "/"
  // เก็บ item ไว้แยกจากสถานะเปิด/ปิด เพื่อให้เนื้อหากล่องไม่หายตอนกำลังเล่นแอนิเมชันปิด
  const [ambiguous, setAmbiguous] = useState<ResolveItem | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)

  function showList(items: ResolveItem[], listId: string) {
    homeStore.set({ results: items, listId })
    if (!onHome) void navigate("/")
  }

  const resolve = useMutation({
    mutationFn: (value: string) =>
      api<ResolveResult>("/resolve", { method: "POST", body: JSON.stringify({ text: value }) }),
    onMutate: () => {
      homeStore.set({ results: null })
      setDialogOpen(false)
    },
    onSuccess: ({ resolveId, items }) => {
      const only = items.length === 1 ? items[0] : null
      if (only?.kind === "video" && only.videoId) {
        void navigate(`/v/${only.videoId}`)
      } else if (only?.kind === "ambiguous" && only.videoId && only.playlistId) {
        setAmbiguous(only)
        setDialogOpen(true)
      } else {
        showList(items, resolveId)
      }
    },
    onError: (error) => {
      // W1 แสดงข้อความใต้ช่องเอง ส่วนหน้าอื่นไม่มีช่อง จึงแจ้งด้วย toast
      if (!onHome) toast.error(`${th.home.resolveFailed} · ${error.message}`)
    },
  })

  function analyze(value: string) {
    if (resolve.isPending) return
    homeStore.set({ text: value })
    resolve.mutate(value)
  }

  const dialog: ReactNode = (
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
        showList([{ ...item, kind: "playlist" }], newListId())
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
