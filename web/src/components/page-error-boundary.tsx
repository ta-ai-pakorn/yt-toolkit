import { Component, type ReactNode } from "react"

import { ErrorPanel } from "@/components/error-panel"

type State = { error: unknown; failed: boolean }

// ครอบหน้า lazy: โหลดไฟล์โค้ดไม่ได้หรือหน้าพัง แสดงข้อความไทยพร้อมปุ่มโหลดใหม่ โดยหัวแอพยังอยู่
export class PageErrorBoundary extends Component<
  { children: ReactNode },
  State
> {
  state: State = { error: null, failed: false }

  static getDerivedStateFromError(error: unknown): State {
    return { error, failed: true }
  }

  render() {
    return this.state.failed ? (
      <ErrorPanel error={this.state.error} />
    ) : (
      this.props.children
    )
  }
}
