export type ToolState = "ok" | "warn" | "error"

export type ToolStatus = {
  status: ToolState
  name: string | null
  version: string | null
  message: string | null
  path: string | null
}

export type Health = {
  version: string
  commit: string | null
  tools: { ffmpeg: ToolStatus; ytdlp: ToolStatus; jsRuntime: ToolStatus }
  disk: ToolStatus
  output: ToolStatus
  network: ToolStatus
  mode?: "fake" // มีเฉพาะตอน backend รันโหมดข้อมูลปลอม (serve + YT_TOOLKIT_FAKE=1)
}

export type VideoFormat = {
  formatId: string
  height: number
  fps: number
  vcodec: string
  compat: boolean
  sizeBytes?: number
}

export type AudioFormat = {
  formatId: string
  language?: string
  isOriginal: boolean
  acodec: string
  abrKbps?: number
}

export type Chapter = { startS: number; endS: number; title: string }

export type VideoInfo = {
  videoId: string
  title: string
  channel: string
  durationS: number
  publishedAt?: string
  thumbnailUrl: string
  chapters: Chapter[]
  video: VideoFormat[]
  audio: AudioFormat[]
  hasStoryboard: boolean
  isLive: boolean
}

export type ResolveKind = "video" | "playlist" | "ambiguous" | "invalid"

export type ResolveItem = {
  input: string
  kind: ResolveKind
  videoId?: string
  playlistId?: string
  /** ลิงก์คลิปที่มากับมิกซ์อัตโนมัติของยูทูป (list=RD...) มีเฉพาะตอนเป็น true */
  isMix?: boolean
  error?: { code: string; message: string }
}

export type ResolveResult = { resolveId: string; items: ResolveItem[] }

export type StoryboardFrame = { index: number; tMs: number; url: string }

export type Storyboard = { intervalMs: number; frames: StoryboardFrame[] }

export type PlaylistEntry = {
  videoId: string
  title: string
  durationS?: number
  thumbnailUrl: string
}

export type PlaylistInfo = {
  title: string
  total: number
  truncated: boolean
  entries: PlaylistEntry[]
  /** มิกซ์อัตโนมัติ: ได้ไม่เกิน 25 คลิปแรก และ total = จำนวนที่ได้มา */
  isMix?: true
}

export type HistoryItem = {
  videoId: string
  title: string
  thumbnailUrl: string
  durationS: number
  outputs: unknown[]
  lastAt: string
}

export type HistoryPage = { items: HistoryItem[]; total: number }
