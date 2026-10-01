import { Suspense, lazy } from "react"
import { useLocation } from "react-router"

import { PageErrorBoundary } from "@/components/page-error-boundary"
import { PageSkeleton } from "@/components/page-skeleton"
import { importWithReload } from "@/lib/lazy-import"

// หน้าอื่นนอกจากหน้าแรกโหลดโค้ดตอนเปิดครั้งแรกเท่านั้น เพื่อให้หน้าแรกเบา
const BatchPage = lazy(() =>
  importWithReload(() => import("@/pages/batch")).then((m) => ({
    default: m.BatchPage,
  }))
)
const HistoryPage = lazy(() =>
  importWithReload(() => import("@/pages/history")).then((m) => ({
    default: m.HistoryPage,
  }))
)
const SettingsPage = lazy(() =>
  importWithReload(() => import("@/pages/settings")).then((m) => ({
    default: m.SettingsPage,
  }))
)
const VideoPage = lazy(() =>
  importWithReload(() => import("@/pages/video")).then((m) => ({
    default: m.VideoPage,
  }))
)

// resetKey = เส้นทางปัจจุบัน: หน้าหนึ่งพังแล้วผู้ใช้ไปหน้า/คลิปอื่น กล่อง error ต้องถูกล้างด้วย
// (ไม่ใช้ key เพราะจะสร้างหน้าใหม่ทุกครั้งที่เปลี่ยนแท็บในตั้งค่า โฟกัสหลุด)
export function LazyBatchPage() {
  const { pathname } = useLocation()
  return (
    <PageErrorBoundary resetKey={pathname}>
      <Suspense fallback={<PageSkeleton />}>
        <BatchPage />
      </Suspense>
    </PageErrorBoundary>
  )
}

export function LazyHistoryPage() {
  const { pathname } = useLocation()
  return (
    <PageErrorBoundary resetKey={pathname}>
      <Suspense fallback={<PageSkeleton />}>
        <HistoryPage />
      </Suspense>
    </PageErrorBoundary>
  )
}

export function LazySettingsPage() {
  const { pathname } = useLocation()
  return (
    <PageErrorBoundary resetKey={pathname}>
      <Suspense fallback={<PageSkeleton />}>
        <SettingsPage />
      </Suspense>
    </PageErrorBoundary>
  )
}

export function LazyVideoPage() {
  const { pathname } = useLocation()
  return (
    <PageErrorBoundary resetKey={pathname}>
      <Suspense fallback={<PageSkeleton />}>
        <VideoPage />
      </Suspense>
    </PageErrorBoundary>
  )
}
