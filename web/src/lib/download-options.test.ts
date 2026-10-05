import { describe, expect, it } from "vitest"

import {
  AUTO_QUALITY,
  audioLanguageOptions,
  audioSizeEstimate,
  batchMinutes,
  buildAudioParams,
  buildSubtitleParams,
  buildVideoParams,
  codecLabel,
  compatCap,
  DEFAULT_SPONSOR_CATEGORIES,
  keptVideoSize,
  NO_ADVANCED,
  paramsFromSettings,
  qualityOptions,
  resolution,
  resolveAudioLanguage,
  SPONSOR_CATEGORIES,
  sponsorCategories,
  videoSizeEstimate,
  wavBytes,
  wavMegabytes,
} from "./download-options"
import { scaleBytes } from "./advanced-options"
import { audioLanguageName } from "./languages"
import { PRESETS } from "./sub-options"
import type { AudioFormat, Settings, VideoFormat, VideoInfo } from "./types"

// รูปร่างเดียวกับ VideoInfo ของ fixture aqz-KE-bpKQ (Big Buck Bunny) จาก core/videos.to_video_info
const BBB_VIDEO: [string, number, number, string, number?][] = [
  ["315", 2160, 60, "vp9", 1362269481],
  ["401", 2160, 60, "av01.0.13M.08", 712445280],
  ["308", 1440, 60, "vp9", 473363704],
  ["400", 1440, 60, "av01.0.12M.08", 312554313],
  ["299", 1080, 60, "avc1.64002a", 257619653],
  ["303", 1080, 60, "vp9", 168736189],
  ["399", 1080, 60, "av01.0.09M.08", 124386876],
  ["298", 720, 60, "avc1.4d4020", 150524867],
  ["302", 720, 60, "vp9", 112676322],
  ["398", 720, 60, "av01.0.08M.08", 71283827],
  ["244", 480, 30, "vp9", 33138062],
  ["135", 480, 30, "avc1.4d401f", 28207144],
  ["397", 480, 30, "av01.0.04M.08", 25998574],
  ["243", 360, 30, "vp9", 24109536],
  ["134", 360, 30, "avc1.4d401e", 18294110],
  ["396", 360, 30, "av01.0.01M.08", 15298808],
  ["242", 240, 30, "vp9", 10198281],
  ["133", 240, 30, "avc1.4d4015", 9323483],
  ["395", 240, 30, "av01.0.00M.08", 7576787],
  ["278", 144, 30, "vp9", 5289812],
  ["394", 144, 30, "av01.0.00M.08", 4639733],
  ["160", 144, 30, "avc1.4d400c", 4323893],
  ["602", 144, 15, "vp09.00.10.08"],
]

const BBB_AUDIO: AudioFormat[] = [
  { formatId: "139", isOriginal: false, acodec: "mp4a.40.5", abrKbps: 49 },
  { formatId: "249", isOriginal: false, acodec: "opus", abrKbps: 50 },
  { formatId: "250", isOriginal: false, acodec: "opus", abrKbps: 65 },
  { formatId: "140", isOriginal: false, acodec: "mp4a.40.2", abrKbps: 129 },
  { formatId: "251", isOriginal: false, acodec: "opus", abrKbps: 129 },
]

// เสียงของ fixture 8lpOfyoxcvU: ไทยต้นฉบับ + พากย์อังกฤษ (en-US) ยูทูปส่ง en-US มาก่อน
const DUB_AUDIO: AudioFormat[] = [
  {
    formatId: "139-0",
    language: "en-US",
    isOriginal: false,
    acodec: "mp4a.40.5",
    abrKbps: 49,
  },
  {
    formatId: "139-1",
    language: "th",
    isOriginal: true,
    acodec: "mp4a.40.5",
    abrKbps: 49,
  },
  {
    formatId: "249-0",
    language: "en-US",
    isOriginal: false,
    acodec: "opus",
    abrKbps: 50,
  },
  {
    formatId: "140-0",
    language: "en-US",
    isOriginal: false,
    acodec: "mp4a.40.2",
    abrKbps: 129,
  },
  {
    formatId: "140-1",
    language: "th",
    isOriginal: true,
    acodec: "mp4a.40.2",
    abrKbps: 129,
  },
  {
    formatId: "251-1",
    language: "TH",
    isOriginal: true,
    acodec: "opus",
    abrKbps: 135,
  },
]

function clip(over: Partial<VideoInfo> = {}): VideoInfo {
  return {
    videoId: "aqz-KE-bpKQ",
    title: "Big Buck Bunny",
    channel: "Blender",
    durationS: 635,
    thumbnailUrl: "",
    chapters: [],
    video: BBB_VIDEO.map(
      ([formatId, height, fps, vcodec, sizeBytes]): VideoFormat => {
        const f: VideoFormat = {
          formatId,
          height,
          fps,
          vcodec,
          compat: vcodec.startsWith("avc1"),
        }
        if (sizeBytes !== undefined) f.sizeBytes = sizeBytes
        return f
      }
    ),
    audio: BBB_AUDIO,
    hasStoryboard: true,
    isLive: false,
    ...over,
  }
}

// ชื่อภาษาแบบ "อังกฤษ (สหรัฐอเมริกา)" (Intl.DisplayNames แบบ standard) ตามที่หน้าเว็บแสดงในช่องภาษาเสียง
const languageName = audioLanguageName
const labels = { original: "ต้นฉบับ ({lang})", originalUnknown: "ต้นฉบับ" }

describe("codecLabel", () => {
  it("ชื่อ codec ที่คนอ่านเข้าใจ", () => {
    expect(codecLabel("avc1.64002a")).toBe("H.264")
    expect(codecLabel("vp9")).toBe("VP9")
    expect(codecLabel("vp09.00.10.08")).toBe("VP9")
    expect(codecLabel("av01.0.13M.08")).toBe("AV1")
    expect(codecLabel("hev1.1.6.L93")).toBe("HEV1")
  })
})

describe("qualityOptions", () => {
  it("ปกติ = เฉพาะ H.264 ไม่เกิน 1080p เรียงสูงไปต่ำ", () => {
    const options = qualityOptions(clip(), false)
    expect(options.map((o) => o.value)).toEqual([
      "299",
      "298",
      "135",
      "134",
      "133",
      "160",
    ])
    expect(options[0]).toEqual({
      value: "299",
      height: 1080,
      fps: 60,
      codec: "H.264",
      compat: true,
      sizeBytes: 257619653,
    })
    expect(options.every((o) => o.compat && o.height <= 1080)).toBe(true)
  })

  it("ความละเอียดสูงสุด = ทุกแบบ เรียงความสูงแล้ว fps", () => {
    const options = qualityOptions(clip(), true)
    expect(options).toHaveLength(BBB_VIDEO.length)
    expect(options[0]).toMatchObject({
      value: "315",
      height: 2160,
      codec: "VP9",
      compat: false,
    })
    expect(options[1]).toMatchObject({
      value: "401",
      height: 2160,
      codec: "AV1",
    })
    expect(options.at(-1)).toEqual({
      value: "602",
      height: 144,
      fps: 15,
      codec: "VP9",
      compat: false,
    })
    for (let i = 1; i < options.length; i++) {
      const [a, b] = [options[i - 1], options[i]]
      expect(
        a.height > b.height || (a.height === b.height && a.fps >= b.fps)
      ).toBe(true)
    }
  })

  it("เรียงใหม่แม้ข้อมูลมาไม่เรียง", () => {
    const video = clip().video
    const shuffled = clip({ video: [video[21], video[4], video[11], video[7]] })
    expect(qualityOptions(shuffled, false).map((o) => o.height)).toEqual([
      1080, 720, 480, 144,
    ])
  })
})

describe("เพดานโหมดเปิดได้ทุกที่ตามการตั้งค่า (compat-720)", () => {
  it("compatCap: compat-720 = 720 · อย่างอื่นหรือยังไม่โหลดการตั้งค่า = 1080", () => {
    expect(compatCap({ videoDefault: "compat-720" })).toBe(720)
    expect(compatCap({ videoDefault: "compat-1080" })).toBe(1080)
    expect(compatCap({ videoDefault: "max" })).toBe(1080)
    expect(compatCap(undefined)).toBe(1080)
  })

  it("เพดาน 720 = ไม่มีตัวเลือกเกิน 720p ยังเรียงสูงไปต่ำ", () => {
    const options = qualityOptions(clip(), false, 720)
    expect(options.map((o) => o.value)).toEqual(["298", "135", "134", "133", "160"])
    expect(options.every((o) => o.compat && o.height <= 720)).toBe(true)
  })

  it("เพดาน 1080 (หรือไม่ส่ง) = เหมือนเดิม", () => {
    expect(qualityOptions(clip(), false, 1080)).toEqual(qualityOptions(clip(), false))
    expect(qualityOptions(clip(), false)[0].value).toBe("299")
  })

  it("ความละเอียดสูงสุดไม่สนเพดาน", () => {
    expect(qualityOptions(clip(), true, 720)).toEqual(qualityOptions(clip(), true))
    expect(qualityOptions(clip(), true, 720)[0].value).toBe("315")
  })

  it("อัตโนมัติประมาณขนาดจาก H.264 ที่ดีที่สุดไม่เกิน 720p", () => {
    expect(videoSizeEstimate(clip(), AUTO_QUALITY, true, false, 720)).toBe(150524867)
    expect(videoSizeEstimate(clip(), AUTO_QUALITY, true, false, 1080)).toBe(257619653)
    expect(videoSizeEstimate(clip(), AUTO_QUALITY, true, false)).toBe(257619653)
  })

  it("ความละเอียดสูงสุด: อัตโนมัติประมาณจากภาพที่ดีที่สุดแม้เพดาน 720", () => {
    expect(videoSizeEstimate(clip(), AUTO_QUALITY, true, true, 720)).toBe(1362269481)
  })

  it("เลือกแบบเองยังประมาณขนาดตามแบบนั้น", () => {
    expect(videoSizeEstimate(clip(), "298", true, false, 720)).toBe(150524867)
  })

  it("ขนาดในรายการคุณภาพย่อตามความยาวของช่วงที่ตั้ง เหมือนข้อความใต้ปุ่ม", () => {
    const full = videoSizeEstimate(clip(), "298", true, false, 720)
    expect(keptVideoSize(clip(), "298", true, false, 720, undefined)).toBe(full)
    expect(keptVideoSize(clip(), "298", true, false, 720, 127)).toBe(scaleBytes(full, 635, 127))
    expect(keptVideoSize(clip(), "298", true, false, 720, 127)).toBe(30104973)
    expect(keptVideoSize(clip(), AUTO_QUALITY, true, false, 720, 127)).toBe(30104973)
  })

  it("คลิปแนวตั้งนับด้านสั้น: เพดาน 720 ตัด 1080x1920 ทิ้ง แต่เก็บ 720x1280", () => {
    const shorts = clip({
      durationS: 30,
      video: [
        ["137", 1080, 1920, 12_000_000],
        ["136", 720, 1280, 6_000_000],
        ["135", 480, 854, 3_000_000],
      ].map(([formatId, width, height, sizeBytes]) => ({
        formatId: String(formatId),
        width: Number(width),
        height: Number(height),
        fps: 30,
        vcodec: "avc1.4d401f",
        compat: true,
        sizeBytes: Number(sizeBytes),
      })),
    })
    expect(qualityOptions(shorts, false, 720).map((o) => [o.value, o.height])).toEqual([
      ["136", 720],
      ["135", 480],
    ])
    expect(videoSizeEstimate(shorts, AUTO_QUALITY, true, false, 720)).toBe(6_000_000)
    expect(videoSizeEstimate(shorts, AUTO_QUALITY, true, false, 1080)).toBe(12_000_000)
  })
})

describe("คลิปแนวตั้ง (Shorts): ความละเอียด = ด้านสั้นของภาพ", () => {
  // Shorts แบบสังเคราะห์: H.264 1080x1920, 720x1280, 480x854 และ VP9 1080x1920
  const portrait = (withWidth = true): VideoInfo =>
    clip({
      durationS: 30,
      video: (
        [
          ["137", 1080, 1920, "avc1.640028", 12_000_000],
          ["248", 1080, 1920, "vp09.00.40.08", 9_000_000],
          ["136", 720, 1280, "avc1.4d401f", 6_000_000],
          ["135", 480, 854, "avc1.4d401e", 3_000_000],
        ] as const
      ).map(([formatId, width, height, vcodec, sizeBytes]) => ({
        formatId,
        ...(withWidth ? { width } : {}),
        height,
        fps: 30,
        vcodec,
        compat: vcodec.startsWith("avc1"),
        sizeBytes,
      })),
    })

  it("resolution = min(width, height) · ไม่รู้ width = height", () => {
    expect(resolution({ width: 1080, height: 1920 })).toBe(1080)
    expect(resolution({ width: 1920, height: 1080 })).toBe(1080)
    expect(resolution({ width: 2560, height: 1080 })).toBe(1080)
    expect(resolution({ height: 1920 })).toBe(1920)
  })

  it("โหมดเปิดได้ทุกที่ไม่ตัด 1080x1920 ทิ้ง ป้ายเป็นด้านสั้น เรียงตามด้านสั้น", () => {
    expect(
      qualityOptions(portrait(), false).map((o) => [o.value, o.height])
    ).toEqual([
      ["137", 1080],
      ["136", 720],
      ["135", 480],
    ])
    expect(
      qualityOptions(portrait(), true).map((o) => [o.value, o.height, o.codec])
    ).toEqual([
      ["137", 1080, "H.264"],
      ["248", 1080, "VP9"],
      ["136", 720, "H.264"],
      ["135", 480, "H.264"],
    ])
  })

  it("อัตโนมัติประมาณขนาดจาก 1080x1920 ตรงกับที่ backend เลือก", () => {
    expect(videoSizeEstimate(portrait(), AUTO_QUALITY, true)).toBe(12_000_000)
  })

  it("ข้อมูลเก่าที่ไม่มี width = ใช้ height แบบเดิม", () => {
    expect(
      qualityOptions(portrait(false), false).map((o) => [o.value, o.height])
    ).toEqual([["135", 854]])
  })
})

describe("audioLanguageOptions", () => {
  it("คลิปพากย์: ต้นฉบับ (ไทย) ก่อน แล้วภาษาอื่นตามลำดับที่พบ ไม่ซ้ำแม้ตัวพิมพ์ต่างกัน", () => {
    expect(
      audioLanguageOptions(clip({ audio: DUB_AUDIO }), languageName, labels)
    ).toEqual([
      { value: "original", label: "ต้นฉบับ (ไทย)" },
      { value: "en-US", label: "อังกฤษ (สหรัฐอเมริกา)" },
    ])
  })

  it("คลิปภาษาเดียวหรือไม่รู้ภาษา = null", () => {
    expect(audioLanguageOptions(clip(), languageName, labels)).toBeNull()
    const single = DUB_AUDIO.filter((a) => a.language?.toLowerCase() === "th")
    expect(
      audioLanguageOptions(clip({ audio: single }), languageName, labels)
    ).toBeNull()
  })

  it("ไม่รู้ภาษาของเสียงต้นฉบับ = originalUnknown", () => {
    const audio = DUB_AUDIO.map((a) => ({ ...a, isOriginal: false }))
    expect(audioLanguageOptions(clip({ audio }), languageName, labels)).toEqual(
      [
        { value: "original", label: "ต้นฉบับ" },
        { value: "en-US", label: "อังกฤษ (สหรัฐอเมริกา)" },
        { value: "th", label: "ไทย" },
      ]
    )
  })

  it("ไม่ส่ง languageName = audioLanguageName · ต้นฉบับมีภูมิภาคใช้แค่ภาษาหลัก วงเล็บไม่ซ้อน", () => {
    const audio: AudioFormat[] = [
      {
        formatId: "140-0",
        language: "en-US",
        isOriginal: true,
        acodec: "mp4a.40.2",
      },
      {
        formatId: "140-1",
        language: "th",
        isOriginal: false,
        acodec: "mp4a.40.2",
      },
      {
        formatId: "140-2",
        language: "pt-BR",
        isOriginal: false,
        acodec: "mp4a.40.2",
      },
    ]
    expect(audioLanguageOptions(clip({ audio }), undefined, labels)).toEqual([
      { value: "original", label: "ต้นฉบับ (อังกฤษ)" },
      { value: "th", label: "ไทย" },
      { value: "pt-BR", label: audioLanguageName("pt-BR") },
    ])
    expect(audioLanguageName("pt-BR")).toMatch(/^โปรตุเกส \(.+\)$/)
  })

  it("รหัสต้นฉบับรูปแบบผิดไม่ทำให้พัง", () => {
    const audio: AudioFormat[] = [
      { formatId: "1", language: "x", isOriginal: true, acodec: "mp4a.40.2" },
      { formatId: "2", language: "th", isOriginal: false, acodec: "mp4a.40.2" },
    ]
    expect(
      audioLanguageOptions(clip({ audio }), undefined, labels)?.[0]
    ).toEqual({
      value: "original",
      label: "ต้นฉบับ (x)",
    })
  })
})

describe("resolveAudioLanguage", () => {
  const options = audioLanguageOptions(
    clip({ audio: DUB_AUDIO }),
    languageName,
    labels
  )

  it("ภาษาหลักตรงกับตัวเลือก = ตัวเลือกนั้น", () => {
    expect(resolveAudioLanguage(options, "en")).toBe("en-US")
    expect(resolveAudioLanguage(options, "en-US")).toBe("en-US")
    expect(resolveAudioLanguage(options, "EN-us")).toBe("en-US")
  })

  it("ไม่มีภาษานี้ = ต้นฉบับ", () => {
    expect(resolveAudioLanguage(options, "ja")).toBe("original")
    expect(resolveAudioLanguage(options, "e")).toBe("original")
    expect(resolveAudioLanguage(options, "original")).toBe("original")
  })

  it("คลิปไม่มีตัวเลือก = ส่งภาษาที่ชอบไปตามเดิม", () => {
    expect(resolveAudioLanguage(null, "ja")).toBe("ja")
    expect(resolveAudioLanguage(null, "original")).toBe("original")
  })
})

describe("ขนาดไฟล์และเวลา", () => {
  it("AC-AUD-04: ขนาด wav", () => {
    expect(wavBytes(60)).toBe(10_584_000)
    expect(wavMegabytes(635)).toBe(112)
    expect(wavBytes(10, 48000, 1)).toBe(960_000)
    expect(wavMegabytes(635, 48000, 2)).toBe(122)
  })

  it("ขนาดเสียง m4a/mp3 โดยประมาณ: m4a = บิตเรตสูงสุดของแทร็ก AAC ภาษาที่เลือก · mp3 = บิตเรตที่เลือก", () => {
    // BBB ไม่มีแทร็กที่บอกว่าต้นฉบับ: ใช้ AAC บิตเรตสูงสุด (140, 129 kbps) × 635 วินาที
    expect(audioSizeEstimate(clip(), "m4a", 192, "original")).toBe(Math.round(((129 * 1000) / 8) * 635))
    expect(audioSizeEstimate(clip(), "mp3", 128, "original")).toBe(Math.round(((128 * 1000) / 8) * 635))
    // คลิปพากย์: ต้นฉบับไทย = 140-1 (129 kbps ไม่ใช่ 139-1 49 kbps) · เลือก en-US = 140-0
    const dub = clip({ audio: DUB_AUDIO })
    expect(audioSizeEstimate(dub, "m4a", 192, "original")).toBe(Math.round(((129 * 1000) / 8) * 635))
    expect(audioSizeEstimate(dub, "m4a", 192, "en-US")).toBe(Math.round(((129 * 1000) / 8) * 635))
    // ไม่รู้บิตเรต = ไม่บอกขนาด
    expect(audioSizeEstimate(clip({ audio: [{ formatId: "140", isOriginal: true, acodec: "mp4a.40.2" }] }), "m4a", 192, "original")).toBeUndefined()
  })

  it("batchMinutes: คลิปละ ~35 วินาที แบ่งตามจำนวนงานพร้อมกัน อย่างน้อย 1 นาที", () => {
    expect(batchMinutes(21, 2)).toBe(7)
    expect(batchMinutes(1, 3)).toBe(1)
    expect(batchMinutes(200, 1)).toBe(117)
  })

  it("videoSizeEstimate: ภาพ + เสียง AAC ต้นฉบับ", () => {
    const audioBytes = Math.round(((129 * 1000) / 8) * 635)
    expect(videoSizeEstimate(clip(), AUTO_QUALITY, false)).toBe(
      257619653 + audioBytes
    )
    expect(videoSizeEstimate(clip(), AUTO_QUALITY, true)).toBe(257619653)
    expect(videoSizeEstimate(clip(), AUTO_QUALITY, true, true)).toBe(1362269481)
    expect(videoSizeEstimate(clip(), "298", false)).toBe(150524867 + audioBytes)
    expect(videoSizeEstimate(clip({ audio: DUB_AUDIO }), "298", false)).toBe(
      150524867 + audioBytes
    )
  })

  it("videoSizeEstimate: ไม่รู้ขนาดภาพหรือไม่มีตัวเลือกนี้ = undefined", () => {
    expect(videoSizeEstimate(clip(), "602", false)).toBeUndefined()
    expect(videoSizeEstimate(clip(), "nope", false)).toBeUndefined()
    expect(
      videoSizeEstimate(clip({ video: [] }), AUTO_QUALITY, false)
    ).toBeUndefined()
  })
})

describe("buildVideoParams", () => {
  const base = {
    quality: AUTO_QUALITY,
    maxQuality: false,
    noAudio: false,
    audioLanguage: "original",
    embedSubs: null,
    subOptions: PRESETS.medium,
  }

  it("อัตโนมัติ = ไม่ส่ง formatId", () => {
    expect(buildVideoParams(base)).toEqual({
      maxQuality: false,
      noAudio: false,
      audioLanguage: "original",
      splitChapters: false,
    })
  })

  it("อัตโนมัติภายใต้เพดาน 720 = ส่ง maxHeight 720", () => {
    expect(buildVideoParams({ ...base, compatCap: 720 })).toEqual({
      maxQuality: false,
      maxHeight: 720,
      noAudio: false,
      audioLanguage: "original",
      splitChapters: false,
    })
  })

  it("เพดาน 1080 หรือไม่ส่งเพดาน = ไม่ส่ง maxHeight (ค่าเริ่มต้นของ backend)", () => {
    expect(buildVideoParams({ ...base, compatCap: 1080 })).not.toHaveProperty("maxHeight")
    expect(buildVideoParams(base)).not.toHaveProperty("maxHeight")
  })

  it("ความละเอียดสูงสุดไม่สนเพดาน = ไม่ส่ง maxHeight", () => {
    expect(buildVideoParams({ ...base, maxQuality: true, compatCap: 720 })).not.toHaveProperty("maxHeight")
  })

  it("เลือกคุณภาพเอง = ส่ง formatId", () => {
    expect(
      buildVideoParams({ ...base, quality: "298", maxQuality: true })
    ).toMatchObject({ formatId: "298", maxQuality: true })
  })

  it("ไม่เอาเสียง", () => {
    expect(buildVideoParams({ ...base, noAudio: true }).noAudio).toBe(true)
  })

  it("ฝังซับ = embedSubs พร้อม subOptions", () => {
    const params = buildVideoParams({
      ...base,
      embedSubs: "o.th",
      subOptions: PRESETS.short,
      audioLanguage: "en-US",
    })
    expect(params).toEqual({
      maxQuality: false,
      noAudio: false,
      audioLanguage: "en-US",
      splitChapters: false,
      embedSubs: "o.th",
      subOptions: PRESETS.short,
    })
  })
})

describe("buildAudioParams", () => {
  it("บิตเรตส่งเฉพาะ mp3", () => {
    expect(
      buildAudioParams({
        format: "mp3",
        mp3Kbps: 320,
        audioLanguage: "original",
      })
    ).toEqual({
      format: "mp3",
      mp3Kbps: 320,
      splitChapters: false,
      audioLanguage: "original",
    })
    expect(
      buildAudioParams({ format: "wav", mp3Kbps: 320, audioLanguage: "en" })
    ).toEqual({
      format: "wav",
      splitChapters: false,
      audioLanguage: "en",
    })
  })
})

describe("paramsFromSettings", () => {
  const settings: Settings = {
    outputDir: "C:\\Users\\u\\Downloads\\YT-Toolkit",
    videoDefault: "compat-1080",
    audioDefault: "m4a",
    audioLanguage: "original",
    mp3Kbps: 192,
    subPreset: "medium",
    subCustom: PRESETS.medium,
    concurrency: 2,
    sponsorblockDefault: ["sponsor", "selfpromo", "interaction"],
    autoSharpFrames: true,
    theme: "system",
    filenameStyle: "title",
    cookies: { enabled: false, source: null, warningAccepted: false },
    statsResetAt: null,
    lastUsed: {},
  }

  it("วิดีโอ compat-720 = maxHeight 720", () => {
    expect(
      paramsFromSettings("video", { ...settings, videoDefault: "compat-720" })
    ).toEqual({
      maxQuality: false,
      maxHeight: 720,
      noAudio: false,
      audioLanguage: "original",
      splitChapters: false,
    })
  })

  it("วิดีโอ compat-1080 = ค่าเริ่มต้นของ backend · max = ความละเอียดสูงสุด", () => {
    expect(paramsFromSettings("video", settings)).toEqual({
      maxQuality: false,
      noAudio: false,
      audioLanguage: "original",
      splitChapters: false,
    })
    expect(
      paramsFromSettings("video", {
        ...settings,
        videoDefault: "max",
        audioLanguage: "en",
      })
    ).toMatchObject({
      maxQuality: true,
      audioLanguage: "en",
    })
  })

  it("เสียงตามรูปแบบที่ตั้งไว้", () => {
    expect(paramsFromSettings("audio", settings)).toEqual({
      format: "m4a",
      splitChapters: false,
      audioLanguage: "original",
    })
    expect(
      paramsFromSettings("audio", {
        ...settings,
        audioDefault: "mp3",
        mp3Kbps: 128,
      })
    ).toEqual({
      format: "mp3",
      mp3Kbps: 128,
      splitChapters: false,
      audioLanguage: "original",
    })
  })
})

describe("M5-A: ตัวเลือกขั้นสูงใน params", () => {
  const base = {
    quality: AUTO_QUALITY,
    maxQuality: false,
    noAudio: false,
    audioLanguage: "original",
    embedSubs: null,
    subOptions: PRESETS.medium,
  }
  const range = { startMs: 90_000, endMs: 300_000 }

  it("ไม่มีตัวเลือกขั้นสูง = params เหมือน M4 ทุกคีย์", () => {
    expect(buildVideoParams({ ...base, advanced: NO_ADVANCED })).toEqual(buildVideoParams(base))
  })

  it("ช่วงเวลาและตัดโฆษณาไปกับงานวิดีโอ", () => {
    expect(buildVideoParams({ ...base, advanced: { splitChapters: false, range, sponsorblock: ["sponsor", "filler"] } })).toEqual({
      maxQuality: false,
      noAudio: false,
      audioLanguage: "original",
      splitChapters: false,
      range,
      sponsorblock: ["sponsor", "filler"],
    })
  })

  it("แยก chapter = ไม่ส่งฝังซับ (ใช้คู่กันไม่ได้ AC-VID-10 ส่วนที่ 2)", () => {
    expect(buildVideoParams({ ...base, embedSubs: "o.th", advanced: { splitChapters: true } })).toEqual({
      maxQuality: false,
      noAudio: false,
      audioLanguage: "original",
      splitChapters: true,
    })
  })

  it("งานเสียงรับตัวเลือกเดียวกัน · ตัดโฆษณาที่ไม่มีหมวด = ไม่ส่ง", () => {
    expect(buildAudioParams({ format: "mp3", mp3Kbps: 192, audioLanguage: "original", advanced: { splitChapters: true } })).toEqual({
      format: "mp3",
      mp3Kbps: 192,
      splitChapters: true,
      audioLanguage: "original",
    })
    expect(buildAudioParams({ format: "m4a", mp3Kbps: 192, audioLanguage: "th", advanced: { splitChapters: false, range, sponsorblock: [] } })).toEqual({
      format: "m4a",
      splitChapters: false,
      audioLanguage: "th",
      range,
    })
  })

  it("งานซับส่งเฉพาะช่วงเวลา", () => {
    expect(buildSubtitleParams({ trackId: "a.th-orig", format: "srt", options: PRESETS.medium, range })).toEqual({
      trackId: "a.th-orig",
      format: "srt",
      options: PRESETS.medium,
      range,
    })
    expect(buildSubtitleParams({ trackId: "a.th-orig", format: "txt", options: PRESETS.medium, range: null })).not.toHaveProperty("range")
  })

  it("หมวด SponsorBlock จากการตั้งค่า: เฉพาะหมวดที่รู้จักตามลำดับหน้าเว็บ · ว่างหรือยังไม่โหลด = 3 หมวดเริ่มต้น", () => {
    expect(SPONSOR_CATEGORIES).toEqual(["sponsor", "selfpromo", "interaction", "intro", "outro", "preview", "filler", "music_offtopic"])
    expect(sponsorCategories(undefined)).toEqual([...DEFAULT_SPONSOR_CATEGORIES])
    expect(sponsorCategories({ sponsorblockDefault: ["filler", "sponsor", "bogus"] })).toEqual(["sponsor", "filler"])
    expect(sponsorCategories({ sponsorblockDefault: [] })).toEqual(["sponsor", "selfpromo", "interaction"])
  })
})
