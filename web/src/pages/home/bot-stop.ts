import { createContext, useContext, useSyncExternalStore } from "react"

import { ApiError } from "@/lib/api"

/** โยนแทนการยิงคำขอที่ถูกระงับแล้ว (ไม่ได้ออกไปหายูทูป) */
export class BotStopped extends Error {
  constructor() {
    super("bot-check-stopped")
    this.name = "BotStopped"
  }
}

/**
 * เบรกของรายการผล W1 หนึ่งรายการ: พอคำขอดึงชื่อคลิปหรือเพลย์ลิสต์ได้ E_BOT_CHECK
 * คำขอที่ยังไม่เริ่มของรายการนี้จะไม่ออกไปอีก (M2 ยังไม่มีคิวพักให้ เบรกจึงอยู่ที่หน้าเว็บ)
 *
 * อยู่กับรายการผล ไม่ใช่ตัวแปรกลางของโมดูล: กดวิเคราะห์ใหม่ = รายการใหม่ = เบรกใหม่ จึงลองได้อีกครั้งเองโดยไม่ต้องมีตัวจับเวลา 10 นาที
 */
export type BotStop = {
  isStopped(): boolean
  subscribe(listener: () => void): () => void
  /** ใช้ห่อคำขอ: ถ้าเบรกอยู่ไม่เริ่มคำขอ · ถ้าคำขอได้ E_BOT_CHECK ก็เหยียบเบรก */
  run<T>(task: () => Promise<T>): Promise<T>
}

export function createBotStop(): BotStop {
  let stopped = false
  const listeners = new Set<() => void>()

  function trip() {
    if (stopped) return
    stopped = true
    listeners.forEach((listener) => listener())
  }

  return {
    isStopped: () => stopped,
    subscribe(listener) {
      listeners.add(listener)
      return () => void listeners.delete(listener)
    },
    async run(task) {
      if (stopped) throw new BotStopped()
      try {
        return await task()
      } catch (error) {
        if (error instanceof ApiError && error.code === "E_BOT_CHECK") trip()
        throw error
      }
    },
  }
}

export const BotStopContext = createContext<BotStop | null>(null)

export function useBotStop(): BotStop | null {
  return useContext(BotStopContext)
}

/** true เมื่อรายการผลนี้ถูกเบรกแล้ว (แถวใช้เพื่อเปลี่ยนเป็นข้อความหยุดชั่วคราว) */
export function useBotStopped(): boolean {
  const gate = useBotStop()
  return useSyncExternalStore(
    (listener) => (gate ? gate.subscribe(listener) : () => {}),
    () => gate?.isStopped() ?? false
  )
}
