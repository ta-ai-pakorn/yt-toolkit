import { fill, th } from "@/i18n/th"

import { playerActions, usePlayerValue } from "./player-store"

/** หยุดเล่นช่วงไฮไลต์: เลิกต่อช่วง และหยุดคลิปไว้ตรงนั้น */
export function stopReel(): void {
  playerActions.stopReel()
  playerActions.pause()
}

/** "ช่วง {i} จาก {n}" ของช่วงไฮไลต์ที่กำลังเล่น · ไม่ได้เล่นช่วงไฮไลต์ = null */
export function useReelStatus(): string | null {
  const reel = usePlayerValue((s) => s.reel)
  return reel ? fill(th.player.reelStatus, { i: reel.index + 1, n: reel.ranges.length }) : null
}
