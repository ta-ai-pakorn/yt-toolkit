import { useQuery } from "@tanstack/react-query"
import { ChevronLeft, ChevronRight } from "lucide-react"
import { useNavigate } from "react-router"

import { Button } from "@/components/ui/button"
import { fill, th } from "@/i18n/th"
import type { ResolveItem } from "@/lib/types"
import { playlistQuery } from "@/pages/home/queries"
import { useHomeState } from "@/pages/home/state"
import type { FromListState } from "@/pages/home/use-analyze"

import { clipPathFrom } from "./url-state"

const t = th.video

/** รหัสคลิปไม่ซ้ำ ตามลำดับที่เจอครั้งแรก (คลิปเดียวกันซ้ำในรายการ ไม่ให้ก่อนหน้า/ถัดไปวนอยู่ที่เดิม) */
function unique(ids: string[]): string[] {
  return [...new Set(ids)]
}

// แถวในรายการผลของ W1 ที่เปิดเป็นคลิปได้ (ข้ามแถวลิงก์ผิด และแถวเพลย์ลิสต์/มิกซ์)
const clipId = (item: ResolveItem) =>
  (item.kind === "video" || item.kind === "ambiguous") && item.videoId ? [item.videoId] : []

/**
 * ลำดับคลิปที่ปุ่มก่อนหน้า/ถัดไปไล่ไป: คลิปในรายการผลของ W1 ตามลำดับ
 * หรือถ้าเปิดจากรายชื่อที่กางใต้แถวเพลย์ลิสต์ = คลิปในเพลย์ลิสต์นั้น (ข้อมูลจาก cache เดียวกับแถว)
 * ยังไม่มีข้อมูล = null
 */
function useClipSequence(from: FromListState | null): string[] | null {
  const { results } = useHomeState()
  const playlist = from?.playlist
  const query = useQuery({
    ...playlistQuery(playlist?.id ?? "", undefined, playlist?.v),
    enabled: playlist !== undefined,
  })
  if (!from) return null
  if (playlist) return query.data ? unique(query.data.entries.map((entry) => entry.videoId)) : null
  return results ? unique(results.flatMap(clipId)) : null
}

const STEP = "h-11 px-3"

/**
 * "‹ ก่อนหน้า · 3 จาก 5 · ถัดไป ›" ของ W2 เมื่อเปิดจากรายการ (ไม่ได้มาจากรายการ = ไม่แสดงเลย)
 * ไปคลิปอื่นแบบแทนที่ประวัติ: ปุ่ม back / "รายการที่วาง" ยังพากลับหน้ารายการในครั้งเดียว
 * สุดทางปุ่มจาง (aria-disabled โฟกัสได้) · ไปแล้วเลื่อนขึ้นบนสุด และโฟกัสย้ายไปชื่อคลิป (หัวคลิปทำเองเมื่อโฟกัสหลุด)
 * คลิปถัดไปเปิดที่แท็บเดิม (ภาพเฟรม / ซับ / ทรานสคริปต์)
 */
export function ClipSequence({ videoId, from }: { videoId: string; from: FromListState }) {
  const navigate = useNavigate()
  const ids = useClipSequence(from)
  const index = ids ? ids.indexOf(videoId) : -1
  if (!ids || index < 0 || ids.length < 2) return null

  const atStart = index === 0
  const atEnd = index === ids.length - 1
  function go(target: number) {
    if (!ids || target < 0 || target >= ids.length) return
    // ปล่อยโฟกัสจากปุ่ม: หัวคลิปย้ายโฟกัสไปชื่อคลิปใหม่ให้ (โปรแกรมอ่านหน้าจออ่านชื่อคลิปใหม่)
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur()
    // อ่านแท็บจาก URL ตอนกด ไม่ใช้ค่าที่จับไว้ตอน render: เครื่องช้าๆ หน้าจออาจยังไม่ render ตามแท็บที่เพิ่งเปลี่ยน
    void navigate(clipPathFrom(ids[target], window.location.search), { state: from, replace: true })
    window.scrollTo({ top: 0 })
  }

  return (
    <nav aria-label={t.sequence} className="flex shrink-0 items-center gap-1 text-sm">
      <Button variant="ghost" className={STEP} aria-disabled={atStart} onClick={() => !atStart && go(index - 1)}>
        <ChevronLeft aria-hidden />
        {t.prev}
      </Button>
      <span aria-hidden className="text-muted-foreground">
        ·
      </span>
      <span className="px-1 text-muted-foreground tabular-nums">
        <span aria-hidden>{fill(t.position, { i: index + 1, n: ids.length })}</span>
        <span className="sr-only">{fill(t.positionLabel, { i: index + 1, n: ids.length })}</span>
      </span>
      <span aria-hidden className="text-muted-foreground">
        ·
      </span>
      <Button variant="ghost" className={STEP} aria-disabled={atEnd} onClick={() => !atEnd && go(index + 1)}>
        {t.next}
        <ChevronRight aria-hidden />
      </Button>
    </nav>
  )
}
