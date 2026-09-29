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
}
