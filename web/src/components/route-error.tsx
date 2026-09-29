import { useRouteError } from "react-router"

import { ErrorPanel } from "@/components/error-panel"

// ตาข่ายชั้นสุดท้ายของ router: ข้อผิดพลาดที่หลุดจากทุกหน้า ไม่ให้เห็นหน้า error ภาษาอังกฤษของ React Router
export function RouteError() {
  return (
    <main className="mx-auto max-w-[960px] px-4">
      <ErrorPanel error={useRouteError()} />
    </main>
  )
}
