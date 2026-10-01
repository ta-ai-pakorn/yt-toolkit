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

/** ตัวเลขของคลิปตอนดึงข้อมูล (ไม่มีคีย์ไหน = ยูทูปไม่บอก) */
export type VideoStats = { views?: number; likes?: number; comments?: number; channelFollowers?: number }

/** ช่วงที่คนดูซ้ำมากที่สุด (มิลลิวินาที) จาก heatmap ของยูทูป */
export type ReplaySegment = { startMs: number; endMs: number }

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
  /** คำอธิบายคลิปตามที่ยูทูปให้มา (ข้อความดิบ) ไม่มีคีย์นี้เมื่อว่าง */
  description?: string
  /** ยอดดู ถูกใจ คอมเมนต์ (สัญญา C-A1) ไม่มีคีย์นี้เมื่อไม่รู้ */
  stats?: VideoStats
  /** แท็กของคลิป (ไม่เกิน 50) */
  tags?: string[]
  /** หมวดหมู่ของยูทูป เช่น "Education" */
  categories?: string[]
  /** ช่วงที่คนดูซ้ำมากที่สุด ไม่เกิน 3 ช่วง เรียงตามเวลา · คลิปที่ไม่มี heatmap ไม่มีคีย์นี้ */
  mostReplayed?: ReplaySegment[]
}

/** คอมเมนต์ปักหมุดที่เจ้าของช่องเขียนเอง (ไม่มีชื่อหรือรหัสผู้เขียน ตาม PDPA) */
export type PinnedComment = { text: string; likes?: number; publishedText?: string }

/** ผลของ GET /videos/{id}/pinned-comment · null = ไม่มีคอมเมนต์ปักหมุดจากเจ้าของช่อง */
export type PinnedCommentResult = { comment: PinnedComment | null }

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

export type ResolveResult = {
  resolveId: string
  items: ResolveItem[]
  /** มีข้อความที่ไม่ใช่ลิงก์ถูกข้ามไป (คำทักทายจากแชต ฯลฯ) มีเฉพาะตอนเป็น true */
  skippedText?: true
}

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

export type SubtitleGroup = "owner" | "original" | "translated"

export type SubtitleTrack = { id: string; lang: string; name: string; group: SubtitleGroup }

export type SubtitleTracks = { tracks: SubtitleTrack[]; defaultTrackId?: string }

/** คำหรือชิ้นข้อความหนึ่งชิ้นของซับ: t = ข้อความ, s/e = เวลาเริ่ม/จบ (มิลลิวินาที) */
export type SubToken = { t: string; s: number; e: number }

export type SubTokens = { hasWordTiming: boolean; tokens: SubToken[] }

export type SubMode = "chars" | "tokens"

export type SubOptions = {
  maxChars: number
  lines: 1 | 2
  minMs: number
  maxMs: number
  mode: SubMode
  tokensPerCue?: number
}

export type SubPreset = "short" | "medium" | "long" | "word"

export type Cue = { startMs: number; endMs: number; lines: string[] }

export type SubExportFormat = "srt" | "txt" | "md"
