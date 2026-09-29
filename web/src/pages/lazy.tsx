import { Suspense, lazy } from "react"

import { PageErrorBoundary } from "@/components/page-error-boundary"
import { PageSkeleton } from "@/components/page-skeleton"
import { importWithReload } from "@/lib/lazy-import"

// หน้าอื่นนอกจากหน้าแรกโหลดโค้ดตอนเปิดครั้งแรกเท่านั้น เพื่อให้หน้าแรกเบา
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

export function LazySettingsPage() {
  return (
    <PageErrorBoundary>
      <Suspense fallback={<PageSkeleton />}>
        <SettingsPage />
      </Suspense>
    </PageErrorBoundary>
  )
}

export function LazyVideoPage() {
  return (
    <PageErrorBoundary>
      <Suspense fallback={<PageSkeleton />}>
        <VideoPage />
      </Suspense>
    </PageErrorBoundary>
  )
}
