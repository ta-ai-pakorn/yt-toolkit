import { useRouteError } from "react-router"

import { ErrorPanel } from "@/components/error-panel"
import { Toaster } from "@/components/ui/sonner"

// ตาข่ายชั้นสุดท้ายของ router: ข้อผิดพลาดที่หลุดจากทุกหน้า ไม่ให้เห็นหน้า error ภาษาอังกฤษของ React Router
// หน้านี้แทน Layout ทั้งหน้า (Toaster อยู่ใน Layout) จึงมี Toaster ของตัวเอง ไม่งั้น toast "คัดลอกแล้ว" ไม่ขึ้น (M6 รอบ B)
export function RouteError() {
  return (
    <main className="mx-auto max-w-[960px] px-4">
      <ErrorPanel error={useRouteError()} />
      <Toaster position="bottom-right" />
    </main>
  )
}
