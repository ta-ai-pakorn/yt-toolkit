// ที่อยู่ของหน้าเลือกคลิป (W3): แยกไฟล์เพราะหน้าแรกใช้สร้างลิงก์ทางเข้า ไม่ควรลากโค้ดของหน้าเลือกคลิปเข้าไปด้วย

// กฎรหัสเดียวกับ backend (core/inputs.py) และ use-analyze.tsx
const PLAYLIST_ID = /^[A-Za-z0-9_-]{10,64}$/
const VIDEO_ID = /^[A-Za-z0-9_-]{11}$/

/** ที่มาของรายการ: `src` = รหัสรายการผลของ W1 (listId) · มี `playlist` = เฉพาะเพลย์ลิสต์/มิกซ์นั้น (มิกซ์มี `v` คลิปตั้งต้น) */
export type BatchSource = { src: string; playlist?: { id: string; v?: string } }

/** ที่อยู่ของหน้าเลือกคลิป: `/batch?src=<listId>[&playlist=<id>[&v=<mixVideoId>]]` */
export function batchPath(listId: string, playlist?: { id: string; v?: string }): string {
  const params = new URLSearchParams({ src: listId })
  if (playlist) {
    params.set("playlist", playlist.id)
    if (playlist.v) params.set("v", playlist.v)
  }
  return `/batch?${params.toString()}`
}

/** อ่านที่มาจาก URL · ไม่มี src หรือรหัสเพลย์ลิสต์/คลิปตั้งต้นผิดกฎ = null (ถือว่ารายการไม่อยู่แล้ว) */
export function parseBatchSource(params: URLSearchParams): BatchSource | null {
  const src = params.get("src")
  if (!src) return null
  const id = params.get("playlist")
  if (id === null) return { src }
  if (!PLAYLIST_ID.test(id)) return null
  const v = params.get("v")
  if (v === null) return { src, playlist: { id } }
  if (!VIDEO_ID.test(v)) return null
  return { src, playlist: { id, v } }
}
