import { describe, expect, it } from "vitest"

import { prefsFromSettings, type DownloadPrefs } from "@/lib/download-prefs"
import type { AudioFormat, SubtitleTrack, VideoFormat, VideoInfo } from "@/lib/types"

import {
  audioPanelHasControls,
  audioPrefsPatch,
  embeddableTracks,
  heightOf,
  languageLocked,
  languageOptions,
  qualityForHeight,
  resolveDownloadState,
  resolveEmbed,
  videoPanelHasControls,
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

  it("ความสูงเท่ากันหลายแบบ: เลือกแบบเปิดได้ทุกที่ (H.264) ก่อน แม้ VP9 อยู่ก่อนในรายการ", () => {
    const mixed = [
      { value: "303", height: 1080, fps: 60, codec: "VP9", compat: false },
      { value: "299", height: 1080, fps: 60, codec: "H.264", compat: true },
      { value: "302", height: 720, fps: 60, codec: "VP9", compat: false },
    ]
    expect(qualityForHeight(mixed, 1080)).toBe("299")
    // ไม่มี H.264 ที่ความสูงนั้น = ตัวแรกของความสูงนั้น
    expect(qualityForHeight(mixed, 720)).toBe("302")
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

  it("จำความสูงของภาพ VP9 ไว้แต่ปิดความละเอียดสูงสุด = ใช้ H.264 ที่สูงเท่ากัน · 2160 เกินเพดาน = ตัวเลือกที่เพดาน (1080p) ไม่ใช่อัตโนมัติ", () => {
    expect(resolveDownloadState(prefs({ quality: 1080 }), clip(), null, {}).quality).toBe("299")
    expect(resolveDownloadState(prefs({ quality: 2160 }), clip(), null, {}).quality).toBe("299")
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

describe("เพดาน compat-720 ในการเลือกคุณภาพของคลิป", () => {
  it("ความสูงที่จำไว้เกินเพดาน (1080) = ตัวเลือกที่เพดาน 720p (M4 follow-up) · 720 เริ่มที่ 720p", () => {
    expect(resolveDownloadState(prefs({ quality: 1080 }), clip(), null, {}, 720).quality).toBe("298")
    expect(resolveDownloadState(prefs({ quality: 720 }), clip(), null, {}, 720).quality).toBe("298")
  })

  it("เลือกตัวเลือกที่เกินเพดานค้างไว้ = ไม่ถูกส่ง กลับไปใช้ค่าที่จำไว้", () => {
    expect(resolveDownloadState(prefs({ quality: 720 }), clip(), null, { quality: "299" }, 720).quality).toBe("298")
    expect(resolveDownloadState(prefs(), clip(), null, { quality: "299" }, 720).quality).toBe("auto")
  })

  it("ความละเอียดสูงสุดเปิด = เพดานไม่มีผล", () => {
    expect(resolveDownloadState(prefs(), clip(), null, { maxQuality: true, quality: "299" }, 720).quality).toBe("299")
  })

  it("จำความสูงตามรายการที่ถูกเพดานตัดแล้ว", () => {
    const state = resolveDownloadState(prefs(), clip(), null, { quality: "298" }, 720)
    expect(videoPrefsPatch(state, clip(), null, 720).quality).toBe(720)
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

  it("คลิปไม่มีตัวเลือกภาษา = ส่ง 'original' เสมอ (ไม่ส่งภาษาที่จำไว้ ซึ่งผู้ใช้มองไม่เห็นในหน้านี้)", () => {
    expect(resolveDownloadState(prefs({ audioLanguage: "th" }), clip(), null, {}).audioLanguage).toBe("original")
    expect(resolveDownloadState(prefs({ audioLanguage: "en" }), clip(), null, { audioLanguage: "en" }).audioLanguage).toBe(
      "original",
    )
  })

  it("'ไม่เอาเสียง' เปิด = ช่องภาษาเสียงกดไม่ได้", () => {
    expect(languageLocked({ noAudio: true })).toBe(true)
    expect(languageLocked({ noAudio: false })).toBe(false)
  })
})

describe("ไม่เอาเสียง", () => {
  it("ไม่จำข้ามคลิป: แม้ค่าที่จำไว้ (รุ่นเก่า) เป็น true ทุกคลิปก็เริ่มที่ปิด", () => {
    expect(resolveDownloadState(prefs({ noAudio: true }), clip(), null, {}).noAudio).toBe(false)
    expect(resolveDownloadState(prefs(), clip(), null, { noAudio: true }).noAudio).toBe(true)
  })

  it("คลิปไม่มีเสียงเลย = เปิดเสมอ (ผู้ใช้ปิดไม่ได้)", () => {
    const silent = clip({ audio: [] })
    expect(resolveDownloadState(prefs(), silent, null, {}).noAudio).toBe(true)
    expect(resolveDownloadState(prefs(), silent, null, { noAudio: false }).noAudio).toBe(true)
  })
})

describe("จำค่าหลังส่งเข้าคิว", () => {
  it("งานวิดีโอจำคุณภาพเป็นความสูง (auto = auto) และความละเอียดสูงสุด แต่ไม่จำ 'ไม่เอาเสียง'", () => {
    const languages = languageOptions(DUBBED)
    const state = resolveDownloadState(prefs(), DUBBED, languages, { quality: "298", noAudio: true, audioLanguage: "en-US" })
    expect(videoPrefsPatch(state, DUBBED, languages)).toEqual({ quality: 720, maxQuality: false, audioLanguage: "en-US" })
    const auto = resolveDownloadState(prefs(), clip(), null, {})
    expect(videoPrefsPatch(auto, clip(), null).quality).toBe("auto")
  })

  it("คลิปที่ไม่มีตัวเลือกภาษาไม่ทับภาษาที่จำไว้", () => {
    const state = resolveDownloadState(prefs({ audioLanguage: "en" }), clip(), null, {})
    expect(videoPrefsPatch(state, clip(), null)).not.toHaveProperty("audioLanguage")
    expect(audioPrefsPatch(state, null)).toEqual({ audioFormat: "m4a", mp3Kbps: 192 })
  })

  it("งานเสียงจำรูปแบบไฟล์ บิตเรต และภาษา", () => {
    const languages = languageOptions(DUBBED)
    const state = resolveDownloadState(prefs(), DUBBED, languages, {
      audioFormat: "mp3",
      mp3Kbps: 320,
      audioLanguage: "en-US",
    })
    expect(audioPrefsPatch(state, languages)).toEqual({ audioFormat: "mp3", mp3Kbps: 320, audioLanguage: "en-US" })
  })
})

describe("แผงมีตัวเลือกให้กด (แผงไม่ต้องรับโฟกัสเอง)", () => {
  it("ยังโหลดอยู่ = ไม่มี · มีภาพ/เสียง = มี · ไม่มีภาพหรือเสียงของแผงนั้น = ไม่มี", () => {
    expect(videoPanelHasControls(undefined)).toBe(false)
    expect(audioPanelHasControls(undefined)).toBe(false)
    expect(videoPanelHasControls(clip())).toBe(true)
    expect(audioPanelHasControls(clip())).toBe(true)
    expect(videoPanelHasControls(clip({ video: [] }))).toBe(false)
    expect(audioPanelHasControls(clip({ audio: [] }))).toBe(false)
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

describe("ขนาด wav", () => {
  it("แทร็กที่ใช้ประมาณ wav: AAC ต้นฉบับก่อน · ไม่มีต้นฉบับใช้ AAC ตัวแรก", () => {
    const opus: AudioFormat = { formatId: "251", isOriginal: true, acodec: "opus" }
    const dub = aac("140-0", "en-US", false, { sampleRate: 48000 })
    const original = aac("140-1", "th", true, { sampleRate: 44100, channels: 2 })
    expect(wavSourceTrack([opus, dub, original])).toBe(original)
    expect(wavSourceTrack([opus, dub])).toBe(dub)
    expect(wavSourceTrack([opus])).toBe(opus)
    expect(wavSourceTrack([])).toBeUndefined()
  })
})

describe("qualityForHeight กับเพดาน (M4 follow-up 'หน้า W2 กับค่าตั้ง' ข้อ 2)", () => {
  const compat = [
    { value: "299", height: 1080, fps: 60, codec: "H.264", compat: true },
    { value: "298", height: 720, fps: 60, codec: "H.264", compat: true },
  ]
  it("ความสูงเกินเพดาน = ตัวเลือกที่เพดาน · ไม่ส่งเพดาน = กติกาเดิม", () => {
    expect(qualityForHeight(compat, 1080, 720)).toBe("298")
    expect(qualityForHeight(compat, 2160, 1080)).toBe("299")
    expect(qualityForHeight(compat, 720, 1080)).toBe("298")
    expect(qualityForHeight(compat, 480, 1080)).toBe("auto")
    expect(qualityForHeight(compat, 2160)).toBe("auto")
  })
  it("ความละเอียดสูงสุดเปิด = ไม่ใช้เพดาน", () => {
    expect(resolveDownloadState(prefs({ quality: 2160, maxQuality: true }), clip(), null, {}, 720).quality).toBe("315")
  })
})
