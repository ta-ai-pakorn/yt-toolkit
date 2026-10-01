import { useSyncExternalStore } from "react"

/**
 * ที่เก็บสถานะของตัวเล่นคลิป (M3.5) ใช้ร่วมกันทั้งหน้า W2
 *
 * ไฟล์นี้ไม่รู้จัก YouTube: ตัวเชื่อมกับ YouTube (adapter) ลงทะเบียนเข้ามาผ่าน attach()
 * ส่วนอื่นของหน้า (ภาพเฟรม ทรานสคริปต์ แท็บข้อมูลคลิป แถบไทม์ไลน์) เรียกแค่ playerActions และอ่านค่าผ่าน usePlayer*
 *
 * API นี้เป็นสัญญากลางระหว่างทีม: ห้ามเปลี่ยนชื่อหรือรูปร่างของที่มีอยู่ เพิ่มของใหม่ได้
 */

export type PlayerStatus = "idle" | "loading" | "playing" | "paused" | "ended" | "error"

/** embed_blocked = เจ้าของคลิปไม่ให้ฝัง (101/150) · unplayable = เล่นไม่ได้ด้วยเหตุอื่น · offline = โหลดสคริปต์ยูทูปไม่ได้ */
export type PlayerError = "embed_blocked" | "unplayable" | "offline"

export type PlayRange = { startMs: number; endMs: number }

export type PlayerState = {
  videoId: string | null
  status: PlayerStatus
  /** เคยขอเล่นแล้วในหน้านี้ (ใช้ตัดสินว่าลอยมุมจอได้) ปิดตัวเล่น (close) แล้วกลับเป็น false */
  started: boolean
  currentMs: number
  error: PlayerError | null
  /** เวลาที่ขอให้เล่นตอนผิดพลาด ใช้ทำลิงก์ "เปิดในยูทูป" ให้ตรงเวลา */
  errorAtMs: number | null
  /** กำลังเล่นช่วงไฮไลต์อยู่ (index = ช่วงที่กำลังเล่น เริ่มที่ 0) */
  reel: { ranges: PlayRange[]; index: number } | null
  /** เวลาที่ขอไว้ก่อน adapter พร้อม adapter อ่านแล้วล้างด้วย takePendingSeek() */
  pendingSeekMs: number | null
  /** (เพิ่มโดย lane P) นับครั้งที่มีคนขอเล่นระหว่างผิดพลาด: ช่องตัวเล่นใช้ค่านี้รู้ว่าต้องโฟกัสข้อความผิดพลาด */
  errorNudge: number
}

/** สิ่งที่ adapter ของ YouTube ต้องทำได้ */
export interface PlayerAdapter {
  play(): void
  pause(): void
  seekTo(ms: number): void
  /** หยุดและคืนทรัพยากร (destroy ตัวเล่น) */
  stop(): void
}

const INITIAL: PlayerState = {
  videoId: null,
  status: "idle",
  started: false,
  currentMs: 0,
  error: null,
  errorAtMs: null,
  reel: null,
  pendingSeekMs: null,
  errorNudge: 0,
}

let state: PlayerState = INITIAL
let adapter: PlayerAdapter | null = null
const listeners = new Set<() => void>()

function set(patch: Partial<PlayerState>): void {
  state = { ...state, ...patch }
  for (const listener of listeners) listener()
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function getPlayerState(): PlayerState {
  return state
}

/** ขอเล่น (จากเวลาที่ให้ หรือจากตำแหน่งปัจจุบัน) ตัวเล่นยังไม่โหลด = เริ่มโหลด แล้วเล่นเมื่อพร้อม */
function request(ms: number | undefined, reel: PlayerState["reel"]): void {
  if (state.status === "error" && state.error !== "offline") {
    set({ errorAtMs: ms ?? state.currentMs, errorNudge: state.errorNudge + 1 })
    return
  }
  if (adapter && state.status !== "loading") {
    set({ reel, started: true })
    if (ms !== undefined) {
      adapter.seekTo(ms)
      set({ currentMs: ms })
    }
    adapter.play()
    return
  }
  set({
    status: "loading",
    started: true,
    error: null,
    errorAtMs: null,
    reel,
    pendingSeekMs: ms ?? state.pendingSeekMs,
  })
}

export const playerActions = {
  /** หน้า W2 เปลี่ยนคลิป: ล้างสถานะทั้งหมด (adapter ของคลิปเก่าต้อง detach เอง) */
  reset(videoId: string | null): void {
    if (state.videoId === videoId) return
    adapter?.stop()
    adapter = null
    state = { ...INITIAL, videoId }
    for (const listener of listeners) listener()
  },
  /** เล่นจากเวลา ms (ไม่ส่ง = เล่นต่อจากตำแหน่งเดิม) ยกเลิกการเล่นช่วงไฮไลต์ */
  playFrom(ms?: number): void {
    request(ms === undefined ? undefined : Math.max(0, Math.round(ms)), null)
  },
  /** เล่นช่วงไฮไลต์ต่อกันตามลำดับ ranges ว่าง = ไม่ทำอะไร */
  playReel(ranges: PlayRange[]): void {
    const clean = ranges.filter((r) => r.endMs > r.startMs).sort((a, b) => a.startMs - b.startMs)
    if (clean.length === 0) return
    request(clean[0].startMs, { ranges: clean, index: 0 })
  },
  stopReel(): void {
    if (state.reel) set({ reel: null })
  },
  pause(): void {
    adapter?.pause()
  },
  /** ปิดตัวเล่น: หยุด คืนทรัพยากร กลับไปเป็นภาพปกในหัวคลิป */
  close(): void {
    adapter?.stop()
    adapter = null
    set({ status: "idle", started: false, currentMs: 0, reel: null, pendingSeekMs: null, error: null, errorAtMs: null })
  },
  /** หลังโหลดสคริปต์ไม่ได้ (offline) ลองใหม่ */
  retry(): void {
    if (state.status === "error") set({ status: "loading", error: null, started: true })
  },
}

/** สำหรับ adapter เท่านั้น */
export const playerAdapterHooks = {
  attach(next: PlayerAdapter): void {
    adapter = next
  },
  detach(previous: PlayerAdapter): void {
    if (adapter === previous) adapter = null
  },
  takePendingSeek(): number | null {
    const ms = state.pendingSeekMs
    if (ms !== null) set({ pendingSeekMs: null })
    return ms
  },
  onStatus(status: Exclude<PlayerStatus, "loading" | "error">): void {
    if (status === "ended") set({ status, reel: null })
    else set({ status })
  },
  /** เรียกราว ๆ ทุก 250 ms ระหว่างเล่น และหลัง seek */
  onTime(ms: number): void {
    const reel = state.reel
    if (reel && ms >= reel.ranges[reel.index].endMs) {
      const next = reel.index + 1
      if (next < reel.ranges.length) {
        set({ currentMs: ms, reel: { ranges: reel.ranges, index: next } })
        adapter?.seekTo(reel.ranges[next].startMs)
        return
      }
      set({ currentMs: ms, reel: null })
      adapter?.pause()
      return
    }
    if (ms !== state.currentMs) set({ currentMs: ms })
  },
  onError(error: PlayerError): void {
    adapter = null
    set({ status: "error", error, errorAtMs: state.pendingSeekMs ?? state.currentMs, reel: null, pendingSeekMs: null })
  },
}

/** สถานะทั้งก้อน (เรนเดอร์ใหม่ทุกครั้งที่เปลี่ยน รวม currentMs ราว 4 ครั้ง/วินาที ใช้กับคอมโพเนนต์เล็ก ๆ เท่านั้น) */
export function usePlayer(): PlayerState {
  return useSyncExternalStore(subscribe, getPlayerState, getPlayerState)
}

/** อ่านเฉพาะค่าที่เลือก (ต้องคืนค่า primitive หรืออ้างอิงเดิม) เรนเดอร์ใหม่เฉพาะเมื่อค่านั้นเปลี่ยน เช่น index ภาพที่กำลังเล่น */
export function usePlayerValue<T>(select: (s: PlayerState) => T): T {
  return useSyncExternalStore(
    subscribe,
    () => select(state),
    () => select(state),
  )
}

/** ทดสอบเท่านั้น */
export function __resetPlayerForTests(): void {
  adapter = null
  state = INITIAL
  for (const listener of listeners) listener()
}
