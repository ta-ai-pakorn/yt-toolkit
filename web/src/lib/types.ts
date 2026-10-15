export type ToolState = "ok" | "warn" | "error"

export type ToolStatus = {
  status: ToolState
  name: string | null
  version: string | null
  message: string | null
  path: string | null
}

/** แถว "บัญชียูทูป" ของ /health (M5 รอบ C): สถานะอย่างเดียว ไม่ต่อเน็ต ไม่มีชื่อหรือค่าคุกกี้ */
export type AccountHealth = { status: "ok"; active: boolean; importedAt: string | null }

export type Health = {
  version: string
  commit: string | null
  // impersonation (owner round 3): yt-dlp ทำงานแบบเบราว์เซอร์ได้ไหม (curl_cffi) backend รุ่นก่อนไม่มีแถวนี้
  tools: { ffmpeg: ToolStatus; ytdlp: ToolStatus; jsRuntime: ToolStatus; impersonation?: ToolStatus }
  disk: ToolStatus
  output: ToolStatus
  network: ToolStatus
  account?: AccountHealth // M5 รอบ C · backend รุ่นก่อนไม่มีแถวนี้
  mode?: "fake" // มีเฉพาะตอน backend รันโหมดข้อมูลปลอม (serve + YT_TOOLKIT_FAKE=1)
}

/** บัญชียูทูปชั่วคราว (M5 รอบ C, GET /cookies) · expiresAt = เวลาที่จะลบเองเร็วที่สุด (ครบ 2 ชม. หรือคิวว่างครบ 10 นาที) */
export type AccountStatus = { active: boolean; importedAt?: string; expiresAt?: string; used: boolean }

export type VideoFormat = {
  formatId: string
  /** ไม่มี = ไม่รู้ (ข้อมูลคลิปที่เก็บไว้ก่อน M4 gate 2) ใช้ height แทน */
  width?: number
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
  /** อัตราสุ่มเสียง (Hz) ไม่มีคีย์นี้ = ยูทูปไม่บอก (หน้าเว็บประมาณขนาด wav ด้วย 44,100) */
  sampleRate?: number
  /** จำนวนช่องเสียง ไม่มีคีย์นี้ = ยูทูปไม่บอก (หน้าเว็บประมาณด้วย 2) */
  channels?: number
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
  /** สัญญาอนุญาตของคลิปตามที่ยูทูปบอก ไม่มีคีย์นี้เมื่อไม่รู้ */
  license?: string
}

/**
 * คอมเมนต์ที่ปักหมุดไว้ (สัญญา C-A2 v2): เจ้าของช่องปักหมุดคอมเมนต์ของใครก็ได้
 * byUploader = เจ้าของช่องเขียนเอง (true) หรือผู้ชมเขียน (false) · ไม่มีชื่อ รหัส หรือรูปผู้เขียน ตาม PDPA
 * backend รุ่นก่อน (v1) อาจไม่ส่ง byUploader: หน้าเว็บถือว่าไม่ใช่เจ้าของช่อง (แสดงป้าย "ผู้ชม") เมื่อไม่มีคีย์นี้ (เป็น true เท่านั้นจึงเป็นเจ้าของ)
 */
export type PinnedComment = { text: string; likes?: number; publishedText?: string; byUploader: boolean }

/** ผลของ GET /videos/{id}/pinned-comment · null = คลิปนี้ไม่มีคอมเมนต์ปักหมุด */
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

/** ชุดภาพคมของคลิป (GET /videos/{id}/sharp) intervalMs null = เวลาเดียวกับภาพเร็ว */
export type SharpSet = { origin: "manual" | "auto"; intervalMs: number | null; frames: StoryboardFrame[] }

/** ภาพคมที่ถ่ายตรงจุด (M5 รอบ B2) · id = "c_<tMs>" · url มี ?v= อยู่แล้ว (ภาพ immutable) */
export type Capture = { id: string; tMs: number; width: number; height: number; url: string }

export type CaptureList = { captures: Capture[] }

/** ความละเอียดภาพที่ถ่าย (เพดานนับที่ด้านสั้น) "max" = สูงสุดที่มี */
export type CaptureQuality = "max" | "1080" | "720"

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
  /** ชื่อช่อง ("" = ไม่รู้) ใช้ทำตัวอย่างชื่อไฟล์แบบ title-channel ในหน้าตั้งค่า (M6 รอบ A) */
  channel: string
  thumbnailUrl: string
  durationS: number
  /** ชนิดไฟล์ที่เคยโหลดของคลิปนี้ (ป้ายในหน้าประวัติ) ว่าง = เปิดดูอย่างเดียว */
  outputs: JobKind[]
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

// ---------- M4 งานในคิว (สัญญา C2) ----------

export type JobKind = "video" | "audio" | "subtitle" | "frames_sharp" | "contact_sheet" | "frames_zip" | "note"

export type JobStatus = "queued" | "running" | "done" | "failed" | "cancelled" | "interrupted"

export type JobStage =
  | "probing"
  | "downloading_video"
  | "downloading_audio"
  | "merging"
  | "converting"
  | "writing"
  | "cutting"
  | "cutting_ads"
  | `splitting:${number}/${number}`
  | `extracting_frames:${number}/${number}`
  | `sharp_frames:${number}/${number}`

export type JobError = { code: string; message: string; detail?: string | null }

/** หมายเหตุสีเทาในแถวงาน เช่น ไม่มีเสียงภาษาที่เลือกจึงใช้เสียงต้นฉบับแทน */
export type JobNote = { code: string; message: string }

/** ไฟล์ที่งานสร้าง: name = ชื่อไฟล์อย่างเดียว · files = งานภาพคม ผลเป็นโฟลเดอร์ (จำนวนภาพ) ไม่มีปุ่มดาวน์โหลด */
export type JobOutput = { index: number; name: string; sizeBytes: number; files?: number }

export type Job = {
  id: string
  videoId: string
  title: string
  kind: JobKind
  params: JobParams
  status: JobStatus
  stage?: JobStage
  progress?: number
  speedBps?: number
  etaS?: number
  /** มีเมื่อ > 0: "เน็ตหลุด กำลังลองใหม่ (ครั้งที่ n/3)" */
  attempt?: number
  /** true ระหว่างที่งานที่กำลังทำถูกสั่งยกเลิก (สถานะสุดท้าย cancelled มาทาง SSE) */
  cancelling?: boolean
  position: number
  error?: JobError
  notes?: JobNote[]
  outputs?: JobOutput[]
  createdAt: string
  startedAt?: string
  finishedAt?: string
}

/** ส่วนที่เปลี่ยนของงาน (SSE job.updated) · ค่า null = ลบคีย์นั้นออก */
export type JobPatch = { id: string } & { [K in keyof Omit<Job, "id">]?: Job[K] | null }

// ---------- ค่าของงานแต่ละชนิด (สัญญา C3) ----------

/**
 * โฟลเดอร์กลุ่ม (owner round 2): ทุกชนิดงานส่ง `folder` ได้ = ไฟล์ไปอยู่ใน <โฟลเดอร์ผลลัพธ์>/<folder>/<คลิป [id]>/
 * หน้า W3 ส่งทุกงาน · หน้า W2 (คลิปเดียว) ไม่ส่ง · backend ตัดช่องว่างหัวท้าย ยาว 1..80 ตัว และทำให้เป็นชื่อโฟลเดอร์ที่ปลอดภัยเอง
 */
export type GroupFolder = { folder?: string }

/** ช่วงเวลาของงาน (M5 รอบ A): มิลลิวินาที เต็มวินาที เริ่มก่อนจบอย่างน้อย 1 วินาที */
export type TimeRange = { startMs: number; endMs: number }

/** หมวด SponsorBlock ที่ตัดได้ (ตรงกับ core/jobs.SPONSORBLOCK_CATEGORIES) */
export type SponsorCategory =
  | "sponsor"
  | "selfpromo"
  | "interaction"
  | "intro"
  | "outro"
  | "preview"
  | "filler"
  | "music_offtopic"

export type VideoJobParams = GroupFolder & {
  /** ไม่มีคีย์ = เลือกให้อัตโนมัติ */
  formatId?: string
  maxQuality: boolean
  /** เพดานความละเอียดของโหมดเปิดได้ทุกที่ (ค่าเริ่มต้น 1080) */
  maxHeight?: 720 | 1080
  /** แยกไฟล์ตาม chapter (M5 รอบ A) ใช้คู่กับ range, sponsorblock และ embedSubs ไม่ได้ */
  splitChapters: boolean
  /** โหลดเฉพาะช่วง (M5 รอบ A) */
  range?: TimeRange
  /** หมวดโฆษณาที่ตัด (M5 รอบ A) ไม่มีคีย์ = ไม่ตัด */
  sponsorblock?: SponsorCategory[]
  noAudio: boolean
  /** "original" หรือรหัสภาษา เช่น "en-US" */
  audioLanguage: string
  /** รหัสแทร็กซับที่ฝังในไฟล์ ต้องมี subOptions ด้วย */
  embedSubs?: string
  subOptions?: SubOptions
}

export type AudioJobParams = GroupFolder & {
  format: "m4a" | "mp3" | "wav"
  mp3Kbps?: 128 | 192 | 320
  /** แยกไฟล์ตาม chapter (M5 รอบ A) ใช้คู่กับ range และ sponsorblock ไม่ได้ */
  splitChapters: boolean
  /** โหลดเฉพาะช่วง (M5 รอบ A) */
  range?: TimeRange
  /** หมวดโฆษณาที่ตัด (M5 รอบ A) ไม่มีคีย์ = ไม่ตัด */
  sponsorblock?: SponsorCategory[]
  audioLanguage: string
}

export type SubtitleJobParams = GroupFolder & { trackId?: string; format: SubExportFormat; options: SubOptions; range?: TimeRange }

export type FrameSource = "fast" | "sharp"

export type ContactSheetJobParams = GroupFolder & { source: FrameSource; columns: 5 }

export type FramesZipJobParams = GroupFolder & { source: FrameSource }

/** ภาพคม (M5 รอบ B): ไม่มี intervalS = เวลาเดียวกับภาพเร็ว */
export type FramesSharpJobParams = GroupFolder & { intervalS?: number }

/** โน้ต .md ของคลิป (ข้อมูลคลิป คำอธิบาย chapter คอมเมนต์ปักหมุด ทรานสคริปต์) · ไม่มี trackId = backend ใช้แทร็กเริ่มต้นของคลิป */
export type NoteJobParams = GroupFolder & { trackId?: string }

export type JobParams =
  | VideoJobParams
  | AudioJobParams
  | SubtitleJobParams
  | ContactSheetJobParams
  | FramesZipJobParams
  | FramesSharpJobParams
  | NoteJobParams

export type NewJob = { videoId: string; kind: JobKind; params: JobParams; title?: string }

// ---------- คิวและการตั้งค่า (สัญญา C12) ----------

export type QueueState = { pausedUntil: string | null; reason: string | null; concurrency: 1 | 2 | 3 }

export type Settings = {
  outputDir: string
  videoDefault: "compat-1080" | "compat-720" | "max"
  audioDefault: "m4a" | "mp3" | "wav"
  audioLanguage: string
  mp3Kbps: 128 | 192 | 320
  subPreset: SubPreset | "custom"
  subCustom: SubOptions
  concurrency: 1 | 2 | 3
  sponsorblockDefault: string[]
  autoSharpFrames: boolean
  captureQuality: CaptureQuality
  theme: "system" | "dark" | "light"
  filenameStyle: "title" | "title-channel" | "title-quality"
  statsResetAt: string | null
  lastUsed: Record<string, unknown>
}

/** M6 รอบ C (spec §1.5): GET /api/stats · 4 กลุ่มของ BRD */
export type StatsKind = "video" | "audio" | "subtitle" | "image"
export type Stats = {
  since: string | null
  clips: number
  files: number
  totalBytes: number
  byKind: { kind: StatsKind; files: number; bytes: number }[]
  byMonth: { month: string; clips: number; files: number; bytes: number }[]
}
