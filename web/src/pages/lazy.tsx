import { Suspense, lazy } from "react"

import { PageSkeleton } from "@/components/page-skeleton"

// หน้าอื่นนอกจากหน้าแรกโหลดโค้ดตอนเปิดครั้งแรกเท่านั้น เพื่อให้หน้าแรกเบา
const SettingsPage = lazy(() => import("@/pages/settings").then((m) => ({ default: m.SettingsPage })))
const VideoPage = lazy(() => import("@/pages/video").then((m) => ({ default: m.VideoPage })))

export function LazySettingsPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <SettingsPage />
    </Suspense>
  )
}

export function LazyVideoPage() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <VideoPage />
    </Suspense>
  )
}
