import { fill } from "@/i18n/th"

import { audioLanguageName } from "./languages"

import type {
  AudioFormat,
  AudioJobParams,
  Settings,
  SubOptions,
  VideoFormat,
  VideoInfo,
  VideoJobParams,
} from "./types"

/** ค่าของตัวเลือก "อัตโนมัติ" ในรายการคุณภาพ (ให้ backend เลือกเอง) */
export const AUTO_QUALITY = "auto"

/** เพดานความละเอียดของโหมดเปิดได้ทุกที่ (H.264) นับที่ด้านสั้นของภาพ: 1080 (ค่าเริ่มต้น) หรือ 720 (การตั้งค่า compat-720) */
export type CompatCap = 720 | 1080

const DEFAULT_COMPAT_CAP: CompatCap = 1080

/** เพดานจากการตั้งค่า: คุณภาพเริ่มต้น "เปิดได้ทุกที่ 720p" = 720 · อย่างอื่นหรือยังไม่โหลดการตั้งค่า = 1080 */
export function compatCap(s: Pick<Settings, "videoDefault"> | undefined): CompatCap {
  return s?.videoDefault === "compat-720" ? 720 : DEFAULT_COMPAT_CAP
}

/**
 * ความละเอียดของ format = ด้านสั้นของภาพ min(width, height) แบบเดียวกับ backend (C8) และ "res" ของ yt-dlp
 * คลิปแนวตั้ง (Shorts) 1080x1920 จึงเป็น 1080p · ไม่รู้ width = ใช้ height
 */
export function resolution(f: Pick<VideoFormat, "width" | "height">): number {
  return f.width === undefined ? f.height : Math.min(f.width, f.height)
}

export type QualityOption = {
  value: string
  /** ความละเอียด (ด้านสั้นของภาพ) ที่ใช้ทำป้าย "{h}p" เรียงลำดับ และจำค่าที่เลือกไว้ */
  height: number
  fps: number
  codec: string
  compat: boolean
  sizeBytes?: number
}

/** ชื่อ codec ที่คนอ่านเข้าใจ: avc1 → H.264, vp09/vp9 → VP9, av01 → AV1, อื่น ๆ = ชื่อตระกูลตัวพิมพ์ใหญ่ */
export function codecLabel(vcodec: string): string {
  const family = vcodec.split(".")[0].toLowerCase()
  if (family === "avc1" || family === "avc") return "H.264"
  if (family === "vp09" || family === "vp9") return "VP9"
  if (family === "av01") return "AV1"
  return family.toUpperCase()
}

/**
 * ตัวเลือกคุณภาพของแท็บวิดีโอ (ไม่รวม "อัตโนมัติ"): ปกติ = เฉพาะ H.264 ไม่เกินเพดาน cap (1080p หรือ 720p ตามการตั้งค่า)
 * · ความละเอียดสูงสุด = ทุกแบบ · เรียงสูงไปต่ำ แล้ว fps มากไปน้อย · value = formatId
 * · ความละเอียดนับที่ด้านสั้น (resolution): Shorts 1080x1920 = 1080p ผ่านเพดาน 1080 (แต่ไม่ผ่านเพดาน 720)
 * · ความละเอียดสูงสุด = ไม่สนเพดาน
 */
export function qualityOptions(
  video: VideoInfo,
  maxQuality: boolean,
  cap: CompatCap = DEFAULT_COMPAT_CAP
): QualityOption[] {
  return video.video
    .filter((f) => maxQuality || (f.compat && resolution(f) <= cap))
    .map((f) => {
      const option: QualityOption = {
        value: f.formatId,
        height: resolution(f),
        fps: f.fps,
        codec: codecLabel(f.vcodec),
        compat: f.compat,
      }
      if (f.sizeBytes !== undefined) option.sizeBytes = f.sizeBytes
      return option
    })
    .sort((a, b) => b.height - a.height || b.fps - a.fps)
}

export type LanguageOption = { value: string; label: string }

/**
 * ตัวเลือกภาษาเสียง: คลิปที่มีเสียงไม่ถึง 2 ภาษา = null (หน้าเว็บซ่อนช่องเลือก)
 * ตัวแรกเสมอ = "original" ชื่อตามภาษาของเสียงต้นฉบับ (labels.original ใส่ {lang}; ไม่รู้ภาษา = labels.originalUnknown)
 * ตามด้วยภาษาอื่นตามลำดับที่พบครั้งแรก value = รหัสภาษาตามที่ยูทูปให้มา
 * languageName ไม่ส่ง (undefined) = audioLanguageName ("อังกฤษ (สหรัฐอเมริกา)")
 * ป้ายต้นฉบับใช้เฉพาะภาษาหลัก (en-US → อังกฤษ) วงเล็บจึงไม่ซ้อนกัน: "ต้นฉบับ (อังกฤษ)"
 */
export function audioLanguageOptions(
  video: VideoInfo,
  languageName: ((tag: string) => string) | undefined,
  labels: { original: string; originalUnknown: string }
): LanguageOption[] | null {
  const name = languageName ?? audioLanguageName
  const tags = distinctLanguages(video.audio)
  if (tags.length < 2) return null
  const originalTag = video.audio.find((a) => a.isOriginal)?.language
  const originalKey = originalTag?.toLowerCase()
  const original: LanguageOption = {
    value: "original",
    label: originalTag
      ? fill(labels.original, { lang: name(baseLanguage(originalTag)) })
      : labels.originalUnknown,
  }
  const others = tags
    .filter((tag) => tag.toLowerCase() !== originalKey)
    .map((tag) => ({ value: tag, label: name(tag) }))
  return [original, ...others]
}

/** ภาษาหลักของรหัส (en-US → en) รหัสรูปแบบผิดคืนรหัสเดิม */
function baseLanguage(tag: string): string {
  try {
    return new Intl.Locale(tag).language
  } catch {
    return tag
  }
}

/** ภาษาเสียงไม่ซ้ำกัน (เทียบแบบไม่สนตัวพิมพ์) ตามลำดับที่พบครั้งแรก */
function distinctLanguages(audio: AudioFormat[]): string[] {
  const seen = new Map<string, string>()
  for (const track of audio) {
    if (track.language && !seen.has(track.language.toLowerCase()))
      seen.set(track.language.toLowerCase(), track.language)
  }
  return [...seen.values()]
}

/**
 * ภาษาเสียงที่จะใช้กับคลิปนี้จากภาษาที่ชอบ (ค่าที่จำไว้/การตั้งค่า): ไม่มีตัวเลือก = ส่งตามที่ชอบไป (backend ใช้ต้นฉบับแทนและแจ้งในคิว)
 * · ตรงกับตัวเลือกเป๊ะ หรือเป็นภาษาหลักของตัวเลือก ("en" → "en-US") = ตัวเลือกนั้น · ไม่มี = ต้นฉบับ
 */
export function resolveAudioLanguage(
  options: LanguageOption[] | null,
  preferred: string
): string {
  if (options === null) return preferred
  const want = preferred.toLowerCase()
  const match = options.find((o) => {
    const value = o.value.toLowerCase()
    return value === want || value.startsWith(`${want}-`)
  })
  return match?.value ?? "original"
}

/** ขนาดไฟล์ wav (PCM 16 บิต) เป็นไบต์ */
export function wavBytes(
  durationS: number,
  sampleRate = 44100,
  channels = 2
): number {
  return durationS * sampleRate * channels * 2
}

/** ขนาดไฟล์ wav เป็น MB (1 MB = 1,000,000 ไบต์) ปัดเป็นจำนวนเต็ม */
export function wavMegabytes(
  durationS: number,
  sampleRate?: number,
  channels?: number
): number {
  return Math.round(wavBytes(durationS, sampleRate, channels) / 1e6)
}

/** เสียง AAC ที่ backend น่าจะเลือกให้ (ต้นฉบับ บิตเรตสูงสุด) ใช้ประมาณขนาดไฟล์ mp4 */
function likelyAudio(audio: AudioFormat[]): AudioFormat | undefined {
  const aac = audio.filter((a) => a.acodec.startsWith("mp4a"))
  const pool = aac.filter((a) => a.isOriginal)
  return (pool.length > 0 ? pool : aac).reduce<AudioFormat | undefined>(
    (best, a) =>
      best === undefined || (a.abrKbps ?? 0) > (best.abrKbps ?? 0) ? a : best,
    undefined
  )
}

/**
 * ขนาดไฟล์ mp4 โดยประมาณ (ไบต์): ภาพของคุณภาพที่เลือก ("auto" = ตัวแรกของรายการตามโหมด) + เสียง AAC ต้นฉบับ
 * ไม่รู้ขนาดภาพ = undefined (หน้าเว็บไม่แสดงบรรทัดขนาด)
 */
export function videoSizeEstimate(
  video: VideoInfo,
  quality: string,
  noAudio: boolean,
  maxQuality = false,
  cap: CompatCap = DEFAULT_COMPAT_CAP
): number | undefined {
  const picked: Pick<VideoFormat, "sizeBytes"> | undefined =
    quality === AUTO_QUALITY
      ? qualityOptions(video, maxQuality, cap)[0]
      : video.video.find((f) => f.formatId === quality)
  if (picked?.sizeBytes === undefined) return undefined
  if (noAudio) return picked.sizeBytes
  const abr = likelyAudio(video.audio)?.abrKbps ?? 0
  return picked.sizeBytes + Math.round(((abr * 1000) / 8) * video.durationS)
}

/** เวลาโดยประมาณ (นาที) ของการโหลดหลายคลิป: คลิปละ ~35 วินาที แบ่งตามจำนวนงานพร้อมกัน อย่างน้อย 1 นาที */
export function batchMinutes(count: number, concurrency: number): number {
  return Math.max(1, Math.ceil((count * 35) / concurrency / 60))
}

/**
 * ค่าของงานวิดีโอจากตัวเลือกในแท็บวิดีโอ: "auto" = ไม่ส่ง formatId · ฝังซับ = ส่งรหัสแทร็กพร้อมค่าความยาวซับ
 * · เพดาน 720 (compatCap) และไม่เปิดความละเอียดสูงสุด = ส่ง maxHeight 720 ให้ backend (เพดาน 1080 = ไม่ส่ง เป็นค่าเริ่มต้นของ backend)
 */
export function buildVideoParams(input: {
  quality: string
  maxQuality: boolean
  compatCap?: CompatCap
  noAudio: boolean
  audioLanguage: string
  embedSubs: string | null
  subOptions: SubOptions
}): VideoJobParams {
  const params: VideoJobParams = {
    maxQuality: input.maxQuality,
    splitChapters: false,
    noAudio: input.noAudio,
    audioLanguage: input.audioLanguage,
  }
  if (input.compatCap === 720 && !input.maxQuality) params.maxHeight = 720
  if (input.quality !== AUTO_QUALITY) params.formatId = input.quality
  if (input.embedSubs !== null) {
    params.embedSubs = input.embedSubs
    params.subOptions = input.subOptions
  }
  return params
}

/** ค่าของงานเสียง: บิตเรตส่งเฉพาะ mp3 */
export function buildAudioParams(input: {
  format: "m4a" | "mp3" | "wav"
  mp3Kbps: 128 | 192 | 320
  audioLanguage: string
}): AudioJobParams {
  const params: AudioJobParams = {
    format: input.format,
    splitChapters: false,
    audioLanguage: input.audioLanguage,
  }
  if (input.format === "mp3") params.mp3Kbps = input.mp3Kbps
  return params
}

/** ค่าของงานจากการตั้งค่า (หน้าเลือกหลายคลิป W3 ใช้ค่าเริ่มต้นเหล่านี้กับทุกคลิป) */
export function paramsFromSettings(kind: "video", s: Settings): VideoJobParams
export function paramsFromSettings(kind: "audio", s: Settings): AudioJobParams
export function paramsFromSettings(
  kind: "video" | "audio",
  s: Settings
): VideoJobParams | AudioJobParams
export function paramsFromSettings(
  kind: "video" | "audio",
  s: Settings
): VideoJobParams | AudioJobParams {
  if (kind === "audio")
    return buildAudioParams({
      format: s.audioDefault,
      mp3Kbps: s.mp3Kbps,
      audioLanguage: s.audioLanguage,
    })
  const params: VideoJobParams = {
    maxQuality: s.videoDefault === "max",
    splitChapters: false,
    noAudio: false,
    audioLanguage: s.audioLanguage,
  }
  if (s.videoDefault === "compat-720") params.maxHeight = 720
  return params
}
