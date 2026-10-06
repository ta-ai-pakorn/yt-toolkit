import { useSyncExternalStore } from "react"

/**
 * dialog "ใช้บัญชียูทูปชั่วคราว" มีตัวเดียวทั้งแอพ (วางไว้ที่ layout) ทุกทางเข้าเปิดผ่าน openAccountDialog
 * origin "error" = ปุ่มบน error (ปุ่มนำเข้า "นำเข้าแล้วลองใหม่") · "settings" = แท็บขั้นสูง ("นำเข้า")
 * onImported = สิ่งที่ทำต่อหลังนำเข้าสำเร็จ (โหลดข้อมูลคลิปใหม่ / ลองงานใหม่ / ถ่ายภาพเดิมใหม่)
 */
export type AccountDialogRequest = { origin: "error" | "settings"; onImported?: () => void }
export type AccountDialogState = { open: boolean; request: AccountDialogRequest | null }

const CLOSED: AccountDialogState = { open: false, request: null }

function createStore() {
  let state: AccountDialogState = CLOSED
  const listeners = new Set<() => void>()
  const set = (next: AccountDialogState) => {
    state = next
    listeners.forEach((listener) => listener())
  }
  return {
    get: () => state,
    open: (request: AccountDialogRequest) => set({ open: true, request }),
    close: () => set(CLOSED),
    subscribe(listener: () => void) {
      listeners.add(listener)
      return () => void listeners.delete(listener)
    },
  }
}

export const accountDialog = createStore()

export function openAccountDialog(request: AccountDialogRequest): void {
  accountDialog.open(request)
}

export function useAccountDialog(): AccountDialogState {
  return useSyncExternalStore(accountDialog.subscribe, accountDialog.get, accountDialog.get)
}
