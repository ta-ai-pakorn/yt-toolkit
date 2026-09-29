import { Skeleton } from "@/components/ui/skeleton"
import { th } from "@/i18n/th"

// ตัวแทนหน้าระหว่างรอโหลดโค้ดของหน้านั้น (React.lazy)
export function PageSkeleton() {
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
