import { describe, expect, it } from "vitest"

import { prefsFromSettings, type DownloadPrefs } from "@/lib/download-prefs"
import type { AudioFormat, SubtitleTrack, VideoFormat, VideoInfo } from "@/lib/types"

import {
  audioPrefsPatch,
  embeddableTracks,
  formatSize,
  heightOf,
  languageLocked,
  languageOptions,
  qualityForHeight,
  resolveDownloadState,
  resolveEmbed,
  videoPrefsPatch,
  wavSourceTrack,
} from "./use-download-state"

const fmt = (formatId: string, height: number, fps: number, vcodec: string, sizeBytes?: number): VideoFormat => ({
  formatId,
  height,
  fps,
  vcodec,
  compat: vcodec.startsWith("avc1"),
  ...(sizeBytes === undefined ? {} : { sizeBytes }),
})

const VIDEO_FORMATS: VideoFormat[] = [
  fmt("315", 2160, 60, "vp9", 1_362_269_481),
  fmt("299", 1080, 60, "avc1.64002a", 257_619_653),
  fmt("303", 1080, 60, "vp9", 168_736_189),
  fmt("298", 720, 60, "avc1.4d4020", 150_524_867),
  fmt("134", 360, 30, "avc1.4d401e", 18_294_110),
]

const aac = (formatId: string, language: string | undefined, isOriginal: boolean, extra: Partial<AudioFormat> = {}): AudioFormat => ({
  formatId,
  ...(language ? { language } : {}),
  isOriginal,
  acodec: "mp4a.40.2",
  abrKbps: 128,
  ...extra,
})

function clip(patch: Partial<VideoInfo> = {}): VideoInfo {
  return {
    videoId: "aqz-KE-bpKQ",
    title: "Big Buck Bunny",
    channel: "Blender",
    durationS: 635,
    thumbnailUrl: "",
    chapters: [],
    video: VIDEO_FORMATS,
    audio: [aac("140", undefined, false)],
    hasStoryboard: true,
    isLive: false,
    ...patch,
  }
}

// คลิปที่มีเสียงต้นฉบับภาษาไทยและเสียงพากย์อังกฤษ (แบบ 8lpOfyoxcvU ในชุดทดสอบ)
const DUBBED = clip({ audio: [aac("140-1", "th", true), aac("140-0", "en-US", false)] })

const prefs = (patch: Partial<DownloadPrefs> = {}): DownloadPrefs => ({ ...prefsFromSettings(undefined), ...patch })

describe("qualityForHeight / heightOf", () => {
  it("ความสูงที่จำไว้ใช้ตัวเลือกแรกที่สูงเท่ากัน · ไม่มีความสูงนั้นหรือจำว่า auto = auto", () => {
    const compat = [
      { value: "299", height: 1080, fps: 60, codec: "H.264", compat: true },
      { value: "298", height: 720, fps: 60, codec: "H.264", compat: true },
    ]
    expect(qualityForHeight(compat, 720)).toBe("298")
    expect(qualityForHeight(compat, 480)).toBe("auto")
    expect(qualityForHeight(compat, "auto")).toBe("auto")
    expect(heightOf(compat, "298")).toBe(720)
    expect(heightOf(compat, "auto")).toBe("auto")
    expect(heightOf(compat, "999")).toBe("auto")
  })
})

describe("resolveDownloadState: ค่าที่จำไว้ → ค่าเริ่มต้นของแต่ละคลิป", () => {
  it("ค่าเริ่มต้นของโปรแกรม: อัตโนมัติ ไม่เอาความละเอียดสูงสุด มีเสียง ภาษาต้นฉบับ m4a 192 kbps", () => {
    expect(resolveDownloadState(prefs(), clip(), null, {})).toEqual({
      quality: "auto",
      maxQuality: false,
      noAudio: false,
      audioLanguage: "original",
      audioFormat: "m4a",
      mp3Kbps: 192,
    })
  })

  it("จำความสูง 720 ไว้ = คลิปที่มี 720p เริ่มที่ตัวนั้น · คลิปที่ไม่มี 720p เริ่มที่อัตโนมัติ", () => {
    expect(resolveDownloadState(prefs({ quality: 720 }), clip(), null, {}).quality).toBe("298")
    const small = clip({ video: [fmt("134", 360, 30, "avc1.4d401e")] })
    expect(resolveDownloadState(prefs({ quality: 720 }), small, null, {}).quality).toBe("auto")
  })

  it("จำความสูงของภาพ VP9 ไว้แต่ปิดความละเอียดสูงสุด = ใช้ H.264 ที่สูงเท่ากัน · 2160 ไม่มีในโหมดเปิดได้ทุกที่ = อัตโนมัติ", () => {
    expect(resolveDownloadState(prefs({ quality: 1080 }), clip(), null, {}).quality).toBe("299")
    expect(resolveDownloadState(prefs({ quality: 2160 }), clip(), null, {}).quality).toBe("auto")
    expect(resolveDownloadState(prefs({ quality: 2160, maxQuality: true }), clip(), null, {}).quality).toBe("315")
  })

  it("ค่าที่ผู้ใช้เลือกกับคลิปนี้ชนะค่าที่จำไว้", () => {
    const state = resolveDownloadState(prefs({ quality: 720 }), clip(), null, {
      quality: "134",
      noAudio: true,
      audioFormat: "wav",
      mp3Kbps: 320,
    })
    expect(state).toMatchObject({ quality: "134", noAudio: true, audioFormat: "wav", mp3Kbps: 320 })
  })

  it("เลือก 4K ไว้แล้วปิดความละเอียดสูงสุด = กลับไปใช้ความสูงที่จำไว้ (หรืออัตโนมัติ)", () => {
    const on = resolveDownloadState(prefs(), clip(), null, { maxQuality: true, quality: "315" })
    expect(on.quality).toBe("315")
    const off = resolveDownloadState(prefs(), clip(), null, { maxQuality: false, quality: "315" })
    expect(off.quality).toBe("auto")
    expect(resolveDownloadState(prefs({ quality: 720 }), clip(), null, { quality: "315" }).quality).toBe("298")
  })
})

describe("ภาษาเสียงใช้ร่วมกันระหว่างแท็บวิดีโอและเสียง", () => {
  it("คลิปเสียงภาษาเดียวไม่มีตัวเลือกภาษา (ซ่อนช่อง) · คลิปพากย์: ต้นฉบับ (ไทย) แล้วตามด้วยอังกฤษ (สหรัฐอเมริกา)", () => {
    expect(languageOptions(clip())).toBeNull()
    expect(languageOptions(DUBBED)).toEqual([
      { value: "original", label: "ต้นฉบับ (ไทย)" },
      { value: "en-US", label: "อังกฤษ (สหรัฐอเมริกา)" },
    ])
  })

  it("เลือกภาษาครั้งเดียว ทั้งสองแท็บได้ค่าเดียวกัน (สถานะคำนวณจาก choices ก้อนเดียว)", () => {
    const languages = languageOptions(DUBBED)
    const choices = { audioLanguage: "en-US", audioFormat: "mp3" as const }
    const forVideoTab = resolveDownloadState(prefs(), DUBBED, languages, choices)
    const forAudioTab = resolveDownloadState(prefs(), DUBBED, languages, choices)
    expect(forVideoTab.audioLanguage).toBe("en-US")
    expect(forAudioTab.audioLanguage).toBe(forVideoTab.audioLanguage)
  })

  it("ภาษาที่จำไว้ 'en' ใช้เสียง en-US ของคลิปนี้ · ภาษาที่คลิปไม่มี = ต้นฉบับ", () => {
    const languages = languageOptions(DUBBED)
    expect(resolveDownloadState(prefs({ audioLanguage: "en" }), DUBBED, languages, {}).audioLanguage).toBe("en-US")
    expect(resolveDownloadState(prefs({ audioLanguage: "ja" }), DUBBED, languages, {}).audioLanguage).toBe("original")
  })

  it("ภาษาที่เลือกไว้แต่คลิปไม่มี (ค่าค้าง) ไม่ถูกส่ง กลับไปใช้ค่าที่จำไว้", () => {
    const languages = languageOptions(DUBBED)
    expect(resolveDownloadState(prefs(), DUBBED, languages, { audioLanguage: "ko" }).audioLanguage).toBe("original")
  })

  it("คลิปไม่มีตัวเลือกภาษา = ส่งภาษาที่จำไว้ไปตามเดิม (backend ใช้ต้นฉบับแทนและแจ้งในคิว)", () => {
    expect(resolveDownloadState(prefs({ audioLanguage: "th" }), clip(), null, {}).audioLanguage).toBe("th")
  })

  it("'ไม่เอาเสียง' เปิด = ช่องภาษาเสียงกดไม่ได้", () => {
    expect(languageLocked({ noAudio: true })).toBe(true)
    expect(languageLocked({ noAudio: false })).toBe(false)
  })
})

describe("จำค่าหลังส่งเข้าคิว", () => {
  it("งานวิดีโอจำคุณภาพเป็นความสูง (auto = auto) พร้อมสวิตช์และภาษา", () => {
    const state = resolveDownloadState(prefs(), clip(), null, { quality: "298", noAudio: true })
    expect(videoPrefsPatch(state, clip())).toEqual({ quality: 720, maxQuality: false, noAudio: true, audioLanguage: "original" })
    const auto = resolveDownloadState(prefs(), clip(), null, {})
    expect(videoPrefsPatch(auto, clip()).quality).toBe("auto")
  })

  it("งานเสียงจำรูปแบบไฟล์ บิตเรต และภาษา", () => {
    const state = resolveDownloadState(prefs(), DUBBED, languageOptions(DUBBED), {
      audioFormat: "mp3",
      mp3Kbps: 320,
      audioLanguage: "en-US",
    })
    expect(audioPrefsPatch(state)).toEqual({ audioFormat: "mp3", mp3Kbps: 320, audioLanguage: "en-US" })
  })
})

describe("ฝังซับ", () => {
  const tracks: SubtitleTrack[] = [
    { id: "t.fr", lang: "fr", name: "French", group: "translated" },
    { id: "a.th-orig", lang: "th", name: "Thai", group: "original" },
    { id: "o.en", lang: "en", name: "English", group: "owner" },
  ]

  it("ฝังได้เฉพาะซับเจ้าของคลิปและซับอัตโนมัติภาษาต้นฉบับ (ไม่รวมซับแปล) เจ้าของคลิปก่อน", () => {
    expect(embeddableTracks(tracks, "th").map((track) => track.id)).toEqual(["o.en", "a.th-orig"])
    expect(embeddableTracks([], null)).toEqual([])
  })

  it("แทร็กที่เลือกไว้ต้องยังอยู่ในรายการ ไม่งั้นไม่ฝัง", () => {
    const listed = embeddableTracks(tracks, "th")
    expect(resolveEmbed("o.en", listed)).toBe("o.en")
    expect(resolveEmbed("t.fr", listed)).toBeNull()
    expect(resolveEmbed(null, listed)).toBeNull()
    expect(resolveEmbed(undefined, listed)).toBeNull()
  })
})

describe("ขนาด wav และขนาดไฟล์", () => {
  it("แทร็กที่ใช้ประมาณ wav: AAC ต้นฉบับก่อน · ไม่มีต้นฉบับใช้ AAC ตัวแรก", () => {
    const opus: AudioFormat = { formatId: "251", isOriginal: true, acodec: "opus" }
    const dub = aac("140-0", "en-US", false, { sampleRate: 48000 })
    const original = aac("140-1", "th", true, { sampleRate: 44100, channels: 2 })
    expect(wavSourceTrack([opus, dub, original])).toBe(original)
    expect(wavSourceTrack([opus, dub])).toBe(dub)
    expect(wavSourceTrack([opus])).toBe(opus)
    expect(wavSourceTrack([])).toBeUndefined()
  })

  it("ขนาดแบบฐานสิบ: MB จำนวนเต็ม · ต่ำกว่า 10 MB ทศนิยม 1 ตำแหน่ง · GB ทศนิยม 1 ตำแหน่ง", () => {
    expect(formatSize(268_000_000)).toBe("268 MB")
    expect(formatSize(4_240_000)).toBe("4.2 MB")
    expect(formatSize(1_362_269_481)).toBe("1.4 GB")
    expect(formatSize(1000)).toBe("0.1 MB")
    expect(formatSize(Number.NaN)).toBe("0 MB")
  })
})
