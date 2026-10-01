import type { UseQueryResult } from "@tanstack/react-query"
import { Hourglass } from "lucide-react"
import { useState } from "react"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import { fill, th } from "@/i18n/th"
import type { SubTokens } from "@/lib/types"

import { announcedSeconds, useSecondsLeft, warmingDeadline } from "../session-warming"

const t = th.subs

type Props = {
  query: UseQueryResult<SubTokens>
  /** ปุ่ม "ใช้ซับภาษาต้นฉบับ" (ใช้ได้ตลอดการนับ) null = คลิปไม่มีแทร็กเริ่มต้น (ไม่มีปุ่ม) */
  onUseOriginal: ((button: HTMLButtonElement) => void) | null
}

/**
 * กล่องแจ้งแบบสงบ (ไม่ใช่สีแดง) ระหว่างรอเซสชันของซับแปล ใช้ทั้งแท็บซับและทรานสคริปต์
 * ตัวเลขนับถอยหลังทุกวินาที (โปรแกรมอ่านหน้าจอได้ยินทุก 15 วินาทีและตอนครบ) ครบแล้ว useWarmingRefetch โหลดให้เอง
 * เวลานับจาก query ก้อนเดียวกันทั้งหน้า สลับแท็บไปมาจึงไม่เริ่มนับใหม่
 */
export function SessionWarming({ query, onUseOriginal }: Props) {
  const left = useSecondsLeft(warmingDeadline(query.error, query.errorUpdatedAt))
  const text = left > 0 ? fill(t.warming, { n: left }) : t.warmingLoading
  // เลขที่เห็นตอนกล่องขึ้น (คงไว้ตลอดอายุกล่อง) ใช้คิดว่าเมื่อไรต้องประกาศ
  const [initial] = useState(left)
  const spoken = announcedSeconds(left, initial)
  const announced = spoken > 0 ? fill(t.warming, { n: spoken }) : t.warmingLoading

  return (
    <Alert role={undefined} data-testid="session-warming">
      <Hourglass aria-hidden />
      <AlertDescription className="flex items-center gap-2 text-foreground">
        <Spinner role={undefined} aria-hidden className="shrink-0" />
        <span aria-hidden data-slot="warming-text">
          {text}
        </span>
      </AlertDescription>
      <span role="status" aria-live="polite" className="sr-only">
        {announced}
      </span>
      <p className="col-start-2 text-sm text-muted-foreground">{t.warmingHint}</p>
      {onUseOriginal && (
        <div className="col-start-2 mt-2">
          <Button variant="secondary" size="sm" className="max-sm:h-11" onClick={(event) => onUseOriginal(event.currentTarget)}>
            {t.useOriginal}
          </Button>
        </div>
      )}
    </Alert>
  )
}
