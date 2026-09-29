import { useElapsed } from "@/components/use-elapsed"
import { Skeleton } from "@/components/ui/skeleton"
import { th } from "@/i18n/th"

const DELAY_MS = 300

// ตัวแทนหน้าระหว่างรอโหลดโค้ดของหน้านั้น (React.lazy) · โหลดเร็วกว่า 300 ms ไม่ขึ้นเลย จะได้ไม่วูบ
export function PageSkeleton() {
  const show = useElapsed(DELAY_MS)
  if (!show) return null
  return (
    <div aria-busy="true" className="flex flex-col gap-3 pt-8">
      <span className="sr-only" role="status">
        {th.common.loading}
      </span>
      <Skeleton className="h-8 w-2/3" />
      <Skeleton className="h-5 w-40" />
    </div>
  )
}
