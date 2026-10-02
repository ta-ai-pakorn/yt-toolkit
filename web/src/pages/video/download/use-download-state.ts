import { useQuery } from "@tanstack/react-query"
import { useCallback, useState } from "react"

import { th } from "@/i18n/th"
import {
  AUTO_QUALITY,
  audioLanguageOptions,
  compatCap,
  qualityOptions,
  resolveAudioLanguage,
  type CompatCap,
  type LanguageOption,
  type QualityOption,
} from "@/lib/download-options"
import { prefsFromSettings, useDownloadPrefs, type DownloadPrefs } from "@/lib/download-prefs"
import { settingsQuery } from "@/lib/settings-api"
import type { AudioFormat, SubtitleTrack, VideoInfo } from "@/lib/types"

import { buildTrackGroups } from "../subs/track-groups"

export type AudioFormatChoice = DownloadPrefs["audioFormat"]
export type Mp3Kbps = DownloadPrefs["mp3Kbps"]

/** ตัวเลือกของแท็บวิดีโอและเสียงที่ใช้กับคลิปที่เปิดอยู่ (ค่าที่จะส่งเข้าคิว) */
export type DownloadState = {
  /** formatId ของภาพ หรือ "auto" */
  quality: string
  maxQuality: boolean
  noAudio: boolean
  /** "original" หรือรหัสภาษาของเสียงพากย์ (ค่าเดียวกันทั้งแท็บวิดีโอและแท็บเสียง) */
  audioLanguage: string
  audioFormat: AudioFormatChoice
  mp3Kbps: Mp3Kbps
}

/** สิ่งที่ผู้ใช้เลือกเองกับคลิปนี้ (ยังไม่เลือก = ใช้ค่าที่จำไว้/ค่าจากการตั้งค่า) · embedSubs null = "ไม่ฝัง" */
export type DownloadChoices = Partial<DownloadState> & { embedSubs?: string | null }

/** ข้อความแจ้งผลการส่งเข้าคิวของแท็บวิดีโอ/เสียง (useEnqueue) */
export const ENQUEUE_MESSAGES = {
  added: th.queue.added,
  addedMany: th.queue.addedMany,
  failed: th.queue.addFailed,
  goHealth: th.queue.goHealth,
}

export const MP3_BITRATES: readonly Mp3Kbps[] = [128, 192, 320]
export const AUDIO_FORMATS: readonly AudioFormatChoice[] = ["m4a", "mp3", "wav"]

/**
 * คุณภาพเริ่มต้นจากค่าที่จำไว้ (จำเป็นความสูงของภาพ ไม่ใช่ formatId): ตัวเลือกที่สูงเท่ากัน โดยเลือกแบบเปิดได้ทุกที่ (H.264)
 * ก่อน แล้วค่อยตามลำดับของ qualityOptions (fps มากสุดก่อน) · ไม่มีความสูงนั้น หรือจำว่า "auto" = "auto"
 * cap (โหมดเปิดได้ทุกที่): ความสูงที่จำไว้เกินเพดาน = ใช้ความสูงที่เพดานแทน ไม่กลายเป็น "อัตโนมัติ" เงียบ ๆ (M4 follow-up)
 */
export function qualityForHeight(options: readonly QualityOption[], height: DownloadPrefs["quality"], cap?: number): string {
  if (height === AUTO_QUALITY) return AUTO_QUALITY
  const wanted = cap === undefined ? height : Math.min(height, cap)
  const same = options.filter((option) => option.height === wanted)
  return (same.find((option) => option.compat) ?? same[0])?.value ?? AUTO_QUALITY
}

/** ความสูงของคุณภาพที่เลือก สำหรับจำไว้ใช้กับคลิปอื่น ("auto" หรือ formatId ที่ไม่อยู่ในรายการ = "auto") */
export function heightOf(options: readonly QualityOption[], quality: string): DownloadPrefs["quality"] {
  return options.find((option) => option.value === quality)?.height ?? AUTO_QUALITY
}

/** ตัวเลือกภาษาเสียงของคลิป (เสียงภาษาเดียวหรือไม่บอกภาษา = null ซ่อนช่องเลือก) ชื่อภาษาแบบ "อังกฤษ (สหรัฐอเมริกา)" */
export function languageOptions(video: VideoInfo): LanguageOption[] | null {
  return audioLanguageOptions(video, undefined, { original: th.download.original, originalUnknown: th.download.originalUnknown })
}

/**
 * ตัวเลือกที่ใช้จริงกับคลิปนี้ (ฟังก์ชันล้วน ทั้งสองแท็บเรียกด้วยค่าชุดเดียวกันจึงได้ภาษาเสียงตรงกันเสมอ):
 * ที่ผู้ใช้เลือกเองก่อน ไม่ได้เลือก = ค่าที่จำไว้ (prefs) ที่ปรับให้เข้ากับคลิปนี้
 * · คุณภาพที่เลือกไว้แต่ไม่อยู่ในรายการแล้ว (เช่น ปิดความละเอียดสูงสุดหลังเลือก 4K) = กลับไปใช้ความสูงที่จำไว้/อัตโนมัติ
 * · ภาษาเสียงที่จำไว้ = ภาษาที่ตรงในคลิปนี้ ("en" ใช้ "en-US" ได้) ไม่มี = ต้นฉบับ · คลิปไม่มีตัวเลือกภาษา = ต้นฉบับเสมอ
 * · "ไม่เอาเสียง" ไม่จำข้ามคลิป (เริ่มปิดทุกคลิป ผู้ใช้จะได้ไม่ได้ไฟล์เงียบโดยไม่รู้ตัว) · คลิปไม่มีเสียงเลย = เปิดเสมอ
 * · cap = เพดานความละเอียดของโหมดเปิดได้ทุกที่ตามการตั้งค่า (720 หรือ 1080) ตัวเลือกเกินเพดานไม่อยู่ในรายการ
 */
export function resolveDownloadState(
  prefs: DownloadPrefs,
  video: VideoInfo,
  languages: LanguageOption[] | null,
  choices: DownloadChoices,
  cap: CompatCap = 1080,
): DownloadState {
  const maxQuality = choices.maxQuality ?? prefs.maxQuality
  const options = qualityOptions(video, maxQuality, cap)
  const chosen = choices.quality
  const quality =
    chosen !== undefined && (chosen === AUTO_QUALITY || options.some((option) => option.value === chosen))
      ? chosen
      : qualityForHeight(options, prefs.quality, maxQuality ? undefined : cap)
  const chosenLanguage = choices.audioLanguage
  const audioLanguage =
    chosenLanguage !== undefined && languages?.some((option) => option.value === chosenLanguage)
      ? chosenLanguage
      : languages === null
        ? "original"
        : resolveAudioLanguage(languages, prefs.audioLanguage)
  return {
    quality,
    maxQuality,
    noAudio: video.audio.length === 0 || (choices.noAudio ?? false),
    audioLanguage,
    audioFormat: choices.audioFormat ?? prefs.audioFormat,
    mp3Kbps: choices.mp3Kbps ?? prefs.mp3Kbps,
  }
}

/** "ไม่เอาเสียง" เปิดอยู่ = ช่องภาษาเสียงของแท็บวิดีโอกดไม่ได้ (ไม่มีเสียงให้เลือกภาษา) */
export function languageLocked(state: Pick<DownloadState, "noAudio">): boolean {
  return state.noAudio
}

/** ภาษาเสียงที่จะจำ: คลิปที่ไม่มีตัวเลือกภาษาไม่ได้ให้ผู้ใช้เลือก จึงไม่ทับภาษาที่จำไว้ */
function languagePatch(state: DownloadState, languages: LanguageOption[] | null): Partial<DownloadPrefs> {
  return languages === null ? {} : { audioLanguage: state.audioLanguage }
}

/** ค่าที่จำไว้หลังส่งงานวิดีโอเข้าคิวสำเร็จ (คุณภาพเป็นความสูง · ไม่จำ "ไม่เอาเสียง") */
export function videoPrefsPatch(
  state: DownloadState,
  video: VideoInfo,
  languages: LanguageOption[] | null,
  cap: CompatCap = 1080,
): Partial<DownloadPrefs> {
  return {
    quality: heightOf(qualityOptions(video, state.maxQuality, cap), state.quality),
    maxQuality: state.maxQuality,
    ...languagePatch(state, languages),
  }
}

/** ค่าที่จำไว้หลังส่งงานเสียงเข้าคิวสำเร็จ */
export function audioPrefsPatch(state: DownloadState, languages: LanguageOption[] | null): Partial<DownloadPrefs> {
  return { audioFormat: state.audioFormat, mp3Kbps: state.mp3Kbps, ...languagePatch(state, languages) }
}

/** แท็บวิดีโอมีตัวเลือกให้กด (มีภาพให้โหลด) · ไม่มี = Skeleton หรือ Empty แผงต้องรับโฟกัสเอง */
export function videoPanelHasControls(video: VideoInfo | undefined): boolean {
  return video !== undefined && video.video.length > 0
}

/** แท็บเสียงมีตัวเลือกให้กด (มีเสียงให้โหลด) · ไม่มี = Skeleton หรือ Empty แผงต้องรับโฟกัสเอง */
export function audioPanelHasControls(video: VideoInfo | undefined): boolean {
  return video !== undefined && video.audio.length > 0
}

/**
 * แทร็กซับที่ฝังในไฟล์ mp4 ได้: ซับจากเจ้าของคลิปและซับอัตโนมัติภาษาต้นฉบับ (ไม่รวมซับแปลอัตโนมัติ)
 * เรียงแบบเดียวกับรายการในแท็บซับ (ภาษาต้นฉบับของคลิปขึ้นก่อน)
 */
export function embeddableTracks(tracks: readonly SubtitleTrack[], originalLang: string | null): SubtitleTrack[] {
  return buildTrackGroups(tracks, originalLang).flatMap((group) => group.tracks)
}

/** ซับที่จะฝัง: ที่เลือกไว้ต้องยังอยู่ในรายการ ไม่งั้น = ไม่ฝัง (null) */
export function resolveEmbed(choice: string | null | undefined, tracks: readonly SubtitleTrack[]): string | null {
  return choice != null && tracks.some((track) => track.id === choice) ? choice : null
}

/**
 * แทร็กเสียงต้นฉบับที่ใช้ประมาณขนาด wav (backend แปลงจากเสียง AAC): AAC ต้นฉบับก่อน ไม่มีค่อยใช้ AAC ตัวแรก
 * ไม่มี AAC เลย = แทร็กต้นฉบับใด ๆ หรือแทร็กแรก
 */
export function wavSourceTrack(audio: readonly AudioFormat[]): AudioFormat | undefined {
  const aac = audio.filter((track) => track.acodec.startsWith("mp4a"))
  return aac.find((track) => track.isOriginal) ?? aac[0] ?? audio.find((track) => track.isOriginal) ?? audio[0]
}

/**
 * ตัวเลือกที่ผู้ใช้เลือกเองของคลิปที่เปิดอยู่ (ก้อนเดียวของหน้า W2 แท็บวิดีโอและเสียงใช้ร่วมกัน เปลี่ยนที่หนึ่งอีกที่ตาม)
 * เปลี่ยนคลิป = เริ่มใหม่จากค่าที่จำไว้ · แท็บที่ไม่ได้เปิดไม่ถูกเรนเดอร์ จึงเก็บไว้ที่แถบแท็บ ไม่ใช่ในแผง
 */
export function useDownloadChoices(videoId: string): [DownloadChoices, (patch: DownloadChoices) => void] {
  const [held, setHeld] = useState<{ videoId: string; choices: DownloadChoices }>({ videoId, choices: {} })
  const choices = held.videoId === videoId ? held.choices : {}
  const choose = useCallback(
    (patch: DownloadChoices) =>
      setHeld((current) => ({
        videoId,
        choices: { ...(current.videoId === videoId ? current.choices : {}), ...patch },
      })),
    [videoId],
  )
  return [choices, choose]
}

/**
 * ตัวเลือกที่ใช้จริงของแผงวิดีโอ/เสียง: ค่าที่จำไว้ในเบราว์เซอร์ (ยังไม่เคยจำ = ค่าเริ่มต้นจากการตั้งค่า)
 * รวมกับที่ผู้ใช้เลือกเองกับคลิปนี้ · remember = จำค่าหลังส่งเข้าคิวสำเร็จ
 */
export function useDownloadState(video: VideoInfo, choices: DownloadChoices) {
  const settings = useQuery(settingsQuery())
  const [prefs, remember] = useDownloadPrefs(prefsFromSettings(settings.data))
  const languages = languageOptions(video)
  // ยังไม่โหลดการตั้งค่า = เพดาน 1080
  const cap = compatCap(settings.data)
  const state = resolveDownloadState(prefs, video, languages, choices, cap)
  // M4 follow-up: กดโหลดก่อนค่าตั้งมาถึงเคยใช้เพดาน 1080 · ปุ่มโหลดรอจนค่าตั้งโหลดเสร็จ (หรือโหลดไม่สำเร็จ = ใช้ค่าเริ่มต้น)
  const ready = !settings.isPending
  return { state, languages, remember, cap, ready }
}
