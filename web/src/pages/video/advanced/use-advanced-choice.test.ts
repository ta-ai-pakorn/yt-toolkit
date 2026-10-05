import { MutationObserver, QueryClient } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { SETTINGS_KEY } from "@/lib/settings-api"
import { PRESETS } from "@/lib/sub-options"
import type { Settings, SponsorCategory } from "@/lib/types"

import { nextSponsorCategories, sponsorToggleMutation } from "./use-advanced-choice"

function settings(sponsorblockDefault: SponsorCategory[]): Settings {
  return {
    outputDir: "C:\\Users\\u\\Downloads\\YT-Toolkit",
    videoDefault: "compat-1080",
    audioDefault: "m4a",
    audioLanguage: "original",
    mp3Kbps: 192,
    subPreset: "medium",
    subCustom: PRESETS.medium,
    concurrency: 2,
    sponsorblockDefault,
    autoSharpFrames: true,
    theme: "system",
    filenameStyle: "title",
    cookies: { enabled: false, source: null, warningAccepted: false },
    statsResetAt: null,
    lastUsed: {},
  }
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

/** เซิร์ฟเวอร์ปลอม: จำคำขอที่ส่งมา แล้วตอบเมื่อเทสต์สั่ง */
function slowServer() {
  const sent: SponsorCategory[][] = []
  const answers: (() => void)[] = []
  const save = (next: SponsorCategory[]) => {
    sent.push(next)
    return new Promise<Settings>((resolve) => answers.push(() => resolve(settings(next))))
  }
  return { sent, answers, save }
}

describe("ติ๊กหมวด SponsorBlock หลายช่องเร็ว ๆ", () => {
  it("ส่งทีละคำขอ คำขอหลังคิดจากค่าล่าสุด และช่องไม่เด้งกลับระหว่างรอ", async () => {
    const client = new QueryClient()
    client.setQueryData(SETTINGS_KEY, settings(["sponsor"]))
    const server = slowServer()
    const tick = (category: SponsorCategory, on: boolean) =>
      new MutationObserver(client, sponsorToggleMutation(client, server.save)).mutate(nextSponsorCategories(client, category, on))
    const cached = () => client.getQueryData<Settings>(SETTINGS_KEY)?.sponsorblockDefault

    const first = tick("intro", true)
    await flush()
    const second = tick("outro", true)
    await flush()
    expect(cached()).toEqual(["sponsor", "intro", "outro"])
    expect(server.sent).toEqual([["sponsor", "intro"]])

    server.answers[0]()
    await first
    await flush()
    expect(cached()).toEqual(["sponsor", "intro", "outro"])
    expect(server.sent).toEqual([
      ["sponsor", "intro"],
      ["sponsor", "intro", "outro"],
    ])

    server.answers[1]()
    await second
    expect(cached()).toEqual(["sponsor", "intro", "outro"])
  })

  it("ยังไม่มีการตั้งค่าในแคช = คิดจากหมวดเริ่มต้น", () => {
    expect(nextSponsorCategories(new QueryClient(), "intro", true)).toEqual(["sponsor", "selfpromo", "interaction", "intro"])
  })
})
