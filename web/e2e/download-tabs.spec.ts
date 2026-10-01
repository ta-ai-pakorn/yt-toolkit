/// <reference lib="dom" />
import fs from "node:fs"
import path from "node:path"

import AxeBuilder from "@axe-core/playwright"
import { expect, test, type Page } from "@playwright/test"

import type { AudioJobParams, VideoJobParams } from "../src/lib/types"

import { mockEnqueue } from "./queue-helpers"

/**
 * M4 T15: แท็บวิดีโอและเสียงของ W2 (โปรเจกต์ chromium: ทุกเทสที่กดปุ่มส่งเข้าคิวดัก POST /api/jobs ด้วย mockEnqueue
 * ไม่มีงานจริงเกิดขึ้น · งานจริงอยู่ใน queue-download.spec.ts)
 */

// Big Buck Bunny: เสียงไม่บอกภาษา (ไม่มีช่องภาษาเสียง) ไม่มีซับ ยาว 635 วินาที
const BBB = "aqz-KE-bpKQ"
// เสียงต้นฉบับภาษาไทย + เสียงพากย์อังกฤษ en-US (AC-VID-05/06/07)
const DUB = "8lpOfyoxcvU"
// คลิปภาษาไทยที่มีซับอัตโนมัติภาษาต้นฉบับ (a.th-orig)
const THAI = "88o5Sk8_m1Y"

const TAB_LIST = "เครื่องมือของคลิปนี้"
const TAB_NAMES = ["ภาพเฟรม", "วิดีโอ", "เสียง", "ซับ", "ทรานสคริปต์", "ข้อมูลคลิป"]
const DOWNLOAD_MP4 = "โหลด mp4"
const DOWNLOAD_AUDIO = "โหลดเสียง"
const LANGUAGE = "ภาษาเสียง"
const EMBED = "ฝังซับ (เปิด/ปิดได้)"
const ADDED = "เพิ่มเข้าคิวแล้ว"
// ค่าความยาวซับ "กลาง" (ค่าเริ่มต้นของแท็บซับ) ต้องตรงกับ PRESETS.medium
const MEDIUM = { maxChars: 25, lines: 1, minMs: 1200, maxMs: 5000, mode: "chars" }

/** ชื่อคลิปในชุดทดสอบ (ข้อมูลเดียวกับที่ backend โหมด fake ส่งให้หน้าเว็บ) */
function fixtureTitle(videoId: string): string {
  const file = path.join(import.meta.dirname, "../../tests/fixtures/probe", `${videoId}.json`)
  return (JSON.parse(fs.readFileSync(file, "utf8")) as { title: string }).title
}

const tab = (page: Page, name: string) => page.getByRole("tab", { name, exact: true })
const combobox = (page: Page, name: string) => page.getByRole("combobox", { name, exact: true })
// ค่าที่เลือกอยู่ของช่องเลือก: ปุ่ม combobox มีไอคอนลูกศรของ Base UI ที่มีอักษร "▼" ซ่อนอยู่ใน svg (aria-hidden)
// toHaveText ของทั้งปุ่มจึงได้ "…▼" อ่านจาก SelectValue แทน
const selectedValue = (page: Page, name: string) => combobox(page, name).locator('[data-slot="select-value"]')
const downloadMp4 = (page: Page) => page.getByRole("button", { name: DOWNLOAD_MP4, exact: true })
const downloadAudio = (page: Page) => page.getByRole("button", { name: DOWNLOAD_AUDIO, exact: true })
const tooltip = (page: Page) => page.locator('[data-slot="tooltip-content"]')
// ข้อความในแผงของแท็บ (Tooltip อยู่นอกแผง จึงไม่ปนกัน)
const panelText = (page: Page, text: string) => page.getByRole("tabpanel").getByText(text, { exact: true })

/** แก้ข้อมูลคลิปที่ backend ส่งมาบางช่อง ส่วนอื่นมาจากชุดทดสอบตามปกติ */
async function withVideo(page: Page, videoId: string, patch: Record<string, unknown>) {
  await page.route(
    (url) => url.pathname === `/api/videos/${videoId}`,
    async (route) => {
      const response = await route.fetch()
      await route.fulfill({ response, json: { ...((await response.json()) as object), ...patch } })
    },
  )
}

/** เปิดหน้าคลิปที่แท็บนั้นแล้วรอให้ตัวเลือกพร้อม (ปุ่มโหลดขึ้น = ข้อมูลคลิปมาแล้ว) */
async function openTab(page: Page, videoId: string, which: "video" | "audio") {
  await page.goto(`/v/${videoId}?tab=${which}`)
  await expect(which === "video" ? downloadMp4(page) : downloadAudio(page)).toBeVisible()
}

/** เลือกตัวเลือกในช่องเลือก (เปิดรายการแล้วคลิกตัวเลือก) */
async function choose(page: Page, name: string, option: string | RegExp) {
  await combobox(page, name).click()
  await page.getByRole("option", { name: option }).first().click()
  await expect(page.getByRole("listbox")).toBeHidden()
}

/** ชี้เมาส์ที่ช่องที่กดไม่ได้ (ตัวช่องไม่รับเมาส์ เมาส์ตกที่กรอบรอบช่อง) แล้วคืน Tooltip */
async function hoverDisabled(page: Page, name: string) {
  await combobox(page, name).locator("..").hover()
  return tooltip(page)
}

async function seriousViolations(page: Page) {
  const results = await new AxeBuilder({ page }).analyze()
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.map((n) => n.target.join(" ")).slice(0, 5) }))
}

test.describe("W2 แท็บวิดีโอและเสียง: แถบแท็บ", () => {
  test("มี 6 แท็บตามลำดับ · ?tab=video เปิดแท็บวิดีโอตรง ๆ · โหลดหน้าใหม่ยังอยู่ที่แท็บนี้", async ({ page }) => {
    await openTab(page, BBB, "video")
    await expect(page.getByRole("tablist", { name: TAB_LIST }).getByRole("tab")).toHaveText(TAB_NAMES)
    await expect(tab(page, "วิดีโอ")).toHaveAttribute("aria-selected", "true")
    await expect(page.getByRole("heading", { level: 2, name: "วิดีโอ" })).toBeVisible()
    await page.reload()
    await expect(tab(page, "วิดีโอ")).toHaveAttribute("aria-selected", "true")
    await expect(downloadMp4(page)).toBeVisible()
  })

  test("กดแท็บเสียง → URL ?tab=audio · หัวข้อ 'เสียง'", async ({ page }) => {
    await openTab(page, BBB, "video")
    await tab(page, "เสียง").click()
    await expect(page).toHaveURL(new RegExp(`/v/${BBB}\\?tab=audio$`))
    await expect(page.getByRole("heading", { level: 2, name: "เสียง" })).toBeVisible()
    await expect(downloadAudio(page)).toBeVisible()
  })

  test("หน้านี้มีปุ่มหลักสีเหลืองปุ่มเดียวคือ 'โหลด mp4' · แท็บเสียงไม่มีปุ่มหลัก ('โหลดเสียง' เป็นปุ่มรอง)", async ({ page }) => {
    await openTab(page, BBB, "video")
    const primary = page.locator("[data-slot=button].bg-primary")
    await expect(primary).toHaveCount(1)
    await expect(primary).toHaveText(DOWNLOAD_MP4)
    await tab(page, "เสียง").click()
    await expect(downloadAudio(page)).toHaveClass(/bg-secondary/)
    await expect(primary).toHaveCount(0)
  })

  test("คีย์บอร์ด: Tab จากแท็บวิดีโอไปช่อง 'คุณภาพ' ทันที (แผงไม่เป็นจุด Tab เพิ่ม)", async ({ page }) => {
    await openTab(page, BBB, "video")
    await tab(page, "วิดีโอ").focus()
    await page.keyboard.press("Tab")
    await expect(combobox(page, "คุณภาพ")).toBeFocused()
  })
})

test.describe("W2 แท็บวิดีโอ", () => {
  test("ค่าเริ่มต้นของ BBB: ส่งงานวิดีโอแบบอัตโนมัติ มีเสียง ภาษาต้นฉบับ · toast 'เพิ่มเข้าคิวแล้ว'", async ({ page }) => {
    const { bodies } = await mockEnqueue(page)
    await openTab(page, BBB, "video")
    await expect(selectedValue(page, "คุณภาพ")).toHaveText("เปิดได้ทุกที่ สูงสุด 1080p (แนะนำ)")
    await expect(page.getByText(/^ขนาดประมาณ \d+(\.\d)? (MB|GB)$/)).toBeVisible()
    await downloadMp4(page).click()
    await expect(page.getByText(ADDED, { exact: true })).toBeVisible()
    expect(bodies).toEqual([
      [
        {
          videoId: BBB,
          kind: "video",
          params: { maxQuality: false, noAudio: false, audioLanguage: "original", splitChapters: false },
          title: fixtureTitle(BBB),
        },
      ],
    ])
  })

  test("BBB ไม่มีช่อง 'ภาษาเสียง' ทั้งแท็บวิดีโอและแท็บเสียง (เสียงภาษาเดียว)", async ({ page }) => {
    await openTab(page, BBB, "video")
    await expect(combobox(page, LANGUAGE)).toHaveCount(0)
    await tab(page, "เสียง").click()
    await expect(downloadAudio(page)).toBeVisible()
    await expect(combobox(page, LANGUAGE)).toHaveCount(0)
  })

  test("เปิด 'ไม่เอาเสียง' → ส่ง noAudio: true · ช่องภาษาเสียงกดไม่ได้ พร้อมเหตุผลใต้ช่องและใน Tooltip · ไม่จำข้ามการโหลดหน้าใหม่", async ({
    page,
  }) => {
    const reason = "ปิด 'ไม่เอาเสียง' ก่อนถึงจะเลือกภาษาเสียงได้"
    const { bodies } = await mockEnqueue(page)
    await openTab(page, DUB, "video")
    const noAudio = page.getByRole("switch", { name: "ไม่เอาเสียง" })
    await expect(combobox(page, LANGUAGE)).toBeEnabled()
    await expect(panelText(page, reason)).toHaveCount(0)
    await noAudio.click()
    await expect(noAudio).toBeChecked()
    await expect(combobox(page, LANGUAGE)).toBeDisabled()
    await expect(panelText(page, reason)).toBeVisible()
    await expect(await hoverDisabled(page, LANGUAGE)).toHaveText(reason)
    await downloadMp4(page).click()
    await expect(page.getByText(ADDED, { exact: true })).toBeVisible()
    expect((bodies[0][0].params as VideoJobParams).noAudio).toBe(true)
    // ไม่เอาเสียงไม่ถูกจำ: คลิปถัดไป (หรือโหลดหน้าใหม่) เริ่มที่มีเสียงเสมอ ผู้ใช้จะได้ไม่ได้ไฟล์เงียบโดยไม่รู้ตัว
    await page.reload()
    await expect(downloadMp4(page)).toBeVisible()
    await expect(noAudio).not.toBeChecked()
    await expect(combobox(page, LANGUAGE)).toBeEnabled()
  })

  test("คลิปไม่มีเสียงเลย → 'ไม่เอาเสียง' เปิดอยู่และกดไม่ได้ · ส่ง noAudio: true", async ({ page }) => {
    await withVideo(page, BBB, { audio: [] })
    const { bodies } = await mockEnqueue(page)
    await openTab(page, BBB, "video")
    const noAudio = page.getByRole("switch", { name: "ไม่เอาเสียง" })
    await expect(noAudio).toBeChecked()
    await expect(noAudio).toBeDisabled()
    await downloadMp4(page).click()
    await expect(page.getByText(ADDED, { exact: true })).toBeVisible()
    expect((bodies[0][0].params as VideoJobParams).noAudio).toBe(true)
  })

  test("AC-VID-07: คลิปพากย์มีช่องภาษาเสียง ตัวแรก 'ต้นฉบับ (ไทย)' และมีแค่อังกฤษ · เลือกอังกฤษ → ส่ง en-US และแท็บเสียงเห็นค่าเดียวกัน", async ({
    page,
  }) => {
    const { bodies } = await mockEnqueue(page)
    await openTab(page, DUB, "video")
    await expect(selectedValue(page, LANGUAGE)).toHaveText("ต้นฉบับ (ไทย)")
    await combobox(page, LANGUAGE).click()
    await expect(page.getByRole("option")).toHaveText(["ต้นฉบับ (ไทย)", "อังกฤษ (สหรัฐอเมริกา)"])
    await page.getByRole("option", { name: "อังกฤษ (สหรัฐอเมริกา)" }).click()
    await expect(selectedValue(page, LANGUAGE)).toHaveText("อังกฤษ (สหรัฐอเมริกา)")
    await downloadMp4(page).click()
    await expect(page.getByText(ADDED, { exact: true })).toBeVisible()
    expect((bodies[0][0].params as VideoJobParams).audioLanguage).toBe("en-US")

    await tab(page, "เสียง").click()
    await expect(selectedValue(page, LANGUAGE)).toHaveText("อังกฤษ (สหรัฐอเมริกา)")
    // เปลี่ยนที่แท็บเสียง แท็บวิดีโอก็เปลี่ยนตาม
    await choose(page, LANGUAGE, "ต้นฉบับ (ไทย)")
    await tab(page, "วิดีโอ").click()
    await expect(selectedValue(page, LANGUAGE)).toHaveText("ต้นฉบับ (ไทย)")
  })

  test("เปิด 'ความละเอียดสูงสุด' → ตัวเลือก VP9/AV1 มีป้าย 'บางโปรแกรมเปิดไม่ได้' · เลือก 2160p ส่ง formatId และ maxQuality", async ({
    page,
  }) => {
    const { bodies } = await mockEnqueue(page)
    await openTab(page, BBB, "video")
    await combobox(page, "คุณภาพ").click()
    await expect(page.getByRole("option", { name: /^2160p/ })).toHaveCount(0)
    await expect(page.getByRole("option", { name: /บางโปรแกรมเปิดไม่ได้/ })).toHaveCount(0)
    await page.keyboard.press("Escape")

    await page.getByRole("switch", { name: "ความละเอียดสูงสุด" }).click()
    // ตัวเลือกอัตโนมัติเปลี่ยนชื่อเป็นภาพดีที่สุดของคลิป (BBB = 2160p VP9 จึงมีป้ายเตือนด้วย)
    await expect(selectedValue(page, "คุณภาพ")).toHaveText("สูงสุดที่คลิปนี้มี")
    await combobox(page, "คุณภาพ").click()
    const auto = page.getByRole("option").first()
    await expect(auto).toContainText("สูงสุดที่คลิปนี้มี")
    await expect(auto).toContainText("บางโปรแกรมเปิดไม่ได้")
    const uhd = page.getByRole("option", { name: /^2160p · 60 fps · VP9/ })
    await expect(uhd).toContainText("บางโปรแกรมเปิดไม่ได้")
    // ตัวเลือก H.264 ไม่มีป้าย
    await expect(page.getByRole("option", { name: /^1080p · 60 fps · H\.264/ })).not.toContainText("บางโปรแกรมเปิดไม่ได้")
    await uhd.click()
    await downloadMp4(page).click()
    await expect(page.getByText(ADDED, { exact: true })).toBeVisible()
    expect(bodies[0][0].params).toMatchObject({ formatId: "315", maxQuality: true })
  })

  test("จำคุณภาพที่ส่งเข้าคิวไว้ (เป็นความสูง): โหลดหน้าใหม่แล้วยังเป็น 720p", async ({ page }) => {
    await mockEnqueue(page)
    await openTab(page, BBB, "video")
    await choose(page, "คุณภาพ", /^720p · 60 fps · H\.264/)
    await downloadMp4(page).click()
    await expect(page.getByText(ADDED, { exact: true })).toBeVisible()
    await page.reload()
    await expect(selectedValue(page, "คุณภาพ")).toHaveText(/^720p · 60 fps · H\.264/)
  })

  test("ตั้งค่า 'เปิดได้ทุกที่ 720p' → ไม่มีตัวเลือกเกิน 720p · เริ่มที่ 720p · อัตโนมัติส่ง maxHeight 720", async ({ page }) => {
    // แทนเฉพาะ GET /api/settings ด้วยค่าปลอมในหน้า (ไม่เขียนการตั้งค่าจริง) · ไม่มีงานจริง (mockEnqueue ดัก POST /api/jobs)
    await page.route("**/api/settings", async (route) => {
      if (route.request().method() !== "GET") return route.fallback()
      const response = await route.fetch()
      await route.fulfill({
        response,
        json: { ...((await response.json()) as object), videoDefault: "compat-720" },
      })
    })
    const { bodies } = await mockEnqueue(page)
    await openTab(page, BBB, "video")

    // ไม่เคยจำค่าไว้ = เริ่มที่ 720p ตามการตั้งค่า · ไม่มีตัวเลือกเกิน 720p
    await expect(selectedValue(page, "คุณภาพ")).toHaveText(/^720p · 60 fps · H\.264/)
    await combobox(page, "คุณภาพ").click()
    await expect(page.getByRole("option", { name: /^(1080|1440|2160)p/ })).toHaveCount(0)
    await expect(page.getByRole("option", { name: /^720p · 60 fps · H\.264/ })).toHaveCount(1)
    await page.keyboard.press("Escape")

    // เลือก "อัตโนมัติ" (ตัวแรกของรายการ) แล้วส่ง: คำขอมี maxHeight 720 และไม่มี formatId
    await choose(page, "คุณภาพ", /^เปิดได้ทุกที่ สูงสุด 1080p/)
    await downloadMp4(page).click()
    await expect(page.getByText(ADDED, { exact: true })).toBeVisible()
    expect(bodies).toHaveLength(1)
    const params = bodies[0][0].params as VideoJobParams
    expect(params).toMatchObject({ maxQuality: false, maxHeight: 720 })
    expect(params).not.toHaveProperty("formatId")
  })

  test("ฝังซับ: BBB ไม่มีซับ → กดไม่ได้ พร้อมเหตุผล 'คลิปนี้ไม่มีซับให้ฝัง' ใต้ช่องและใน Tooltip", async ({ page }) => {
    await openTab(page, BBB, "video")
    await expect(selectedValue(page, EMBED)).toHaveText("ไม่ฝัง")
    await expect(combobox(page, EMBED)).toBeDisabled()
    await expect(panelText(page, "คลิปนี้ไม่มีซับให้ฝัง")).toBeVisible()
    await expect(await hoverDisabled(page, EMBED)).toHaveText("คลิปนี้ไม่มีซับให้ฝัง")
  })

  test("ฝังซับ: คลิปภาษาไทยเลือกซับอัตโนมัติภาษาต้นฉบับได้ → ส่ง embedSubs พร้อมค่าความยาวซับของแท็บซับ", async ({ page }) => {
    const { bodies } = await mockEnqueue(page)
    await openTab(page, THAI, "video")
    await expect(combobox(page, EMBED)).toBeEnabled()
    await expect(selectedValue(page, EMBED)).toHaveText("ไม่ฝัง")
    await expect(panelText(page, "ผู้ชมเปิดหรือปิดซับได้จากโปรแกรมเล่น ความยาวซับตามที่ตั้งไว้ในแท็บซับ")).toBeVisible()
    await expect(panelText(page, "คลิปนี้ไม่มีซับให้ฝัง")).toHaveCount(0)
    await combobox(page, EMBED).click()
    await expect(page.getByRole("option").first()).toHaveText("ไม่ฝัง")
    // ซับแปลอัตโนมัติไม่อยู่ในรายการฝังซับ
    await expect(page.getByRole("option", { name: /แปลอัตโนมัติ/ })).toHaveCount(0)
    await page.getByRole("option", { name: "ไทย (อัตโนมัติ)" }).click()
    await expect(selectedValue(page, EMBED)).toHaveText("ไทย (อัตโนมัติ)")
    await downloadMp4(page).click()
    await expect(page.getByText(ADDED, { exact: true })).toBeVisible()
    expect(bodies[0][0].params).toMatchObject({ embedSubs: "a.th-orig", subOptions: MEDIUM })
  })

  test("ไม่มี ffmpeg (409 E_FFMPEG_MISSING) → toast ข้อความไทยพร้อมปุ่ม 'ไปหน้าตรวจสุขภาพ' ที่พาไปหน้าตรวจสุขภาพ", async ({ page }) => {
    const message = 'ยังไม่มีโปรแกรมแปลงไฟล์ (ffmpeg) กด "โหลดใหม่" ในหน้าตรวจสุขภาพ'
    await page.route("**/api/jobs", (route) => {
      if (route.request().method() !== "POST") return route.fallback()
      return route.fulfill({
        status: 409,
        json: { error: { code: "E_FFMPEG_MISSING", message, detail: null } },
      })
    })
    await openTab(page, BBB, "video")
    await downloadMp4(page).click()
    await expect(page.getByText(message, { exact: true })).toBeVisible()
    await page.getByRole("button", { name: "ไปหน้าตรวจสุขภาพ" }).click()
    await expect(page).toHaveURL(/\/settings\/health$/)
  })
})

test.describe("W2 แท็บเสียง", () => {
  test("ค่าเริ่มต้น m4a (แนะนำ) พร้อมคำอธิบาย · ส่งงานเสียง m4a ภาษาต้นฉบับ", async ({ page }) => {
    const { bodies } = await mockEnqueue(page)
    await openTab(page, BBB, "audio")
    await expect(page.getByRole("button", { name: "m4a (แนะนำ)" })).toHaveAttribute("aria-pressed", "true")
    await expect(page.getByText("เร็วกว่าและเสียงดีกว่า", { exact: true })).toBeVisible()
    await expect(combobox(page, "คุณภาพ mp3")).toHaveCount(0)
    await downloadAudio(page).click()
    await expect(page.getByText(ADDED, { exact: true })).toBeVisible()
    expect(bodies).toEqual([
      [
        {
          videoId: BBB,
          kind: "audio",
          params: { format: "m4a", splitChapters: false, audioLanguage: "original" },
          title: fixtureTitle(BBB),
        },
      ],
    ])
  })

  test("AC-AUD-04: BBB เลือก wav → 'ไฟล์ไม่บีบอัด ขนาดประมาณ 112 MB'", async ({ page }) => {
    await openTab(page, BBB, "audio")
    await page.getByRole("button", { name: "wav", exact: true }).click()
    await expect(page.getByText("ไฟล์ไม่บีบอัด ขนาดประมาณ 112 MB", { exact: true })).toBeVisible()
    await expect(combobox(page, "คุณภาพ mp3")).toHaveCount(0)
  })

  test("mp3 → มีช่อง 'คุณภาพ mp3' (128/192/320 ค่าเริ่มต้น 192) และส่ง mp3Kbps: 192", async ({ page }) => {
    const { bodies } = await mockEnqueue(page)
    await openTab(page, BBB, "audio")
    await page.getByRole("button", { name: "mp3", exact: true }).click()
    await expect(page.getByText("เปิดได้ทุกเครื่อง แต่ต้องแปลงไฟล์จึงช้ากว่า m4a", { exact: true })).toBeVisible()
    await expect(selectedValue(page, "คุณภาพ mp3")).toHaveText("192 kbps")
    await combobox(page, "คุณภาพ mp3").click()
    await expect(page.getByRole("option")).toHaveText(["128 kbps", "192 kbps", "320 kbps"])
    await page.keyboard.press("Escape")
    await downloadAudio(page).click()
    await expect(page.getByText(ADDED, { exact: true })).toBeVisible()
    const params = bodies[0][0].params as AudioJobParams
    expect(bodies[0][0].kind).toBe("audio")
    expect(params).toEqual({ format: "mp3", mp3Kbps: 192, splitChapters: false, audioLanguage: "original" })
  })
})

test.describe("W2 แท็บวิดีโอและเสียง: การเข้าถึงและจอแคบ", () => {
  for (const which of ["video", "audio"] as const) {
    for (const scheme of ["dark", "light"] as const) {
      test(`แท็บ ${which} ไม่มีปัญหาระดับ serious/critical (${scheme})`, async ({ page }) => {
        await page.emulateMedia({ colorScheme: scheme })
        await openTab(page, DUB, which)
        await expect(page.locator("html")).toHaveClass(scheme === "dark" ? /dark/ : /light/)
        expect(await seriousViolations(page)).toEqual([])
      })
    }
  }

  test("แท็บวิดีโอที่ช่องภาษาและฝังซับกดไม่ได้ ไม่มีปัญหาระดับ serious/critical", async ({ page }) => {
    await openTab(page, DUB, "video")
    await page.getByRole("switch", { name: "ไม่เอาเสียง" }).click()
    await expect(combobox(page, LANGUAGE)).toBeDisabled()
    expect(await seriousViolations(page)).toEqual([])
  })

  for (const which of ["video", "audio"] as const) {
    test(`จอ 640 × 800: แท็บ ${which} ไม่ล้นแนวนอน (BBB, คลิปพากย์, คลิปที่มีซับให้ฝัง)`, async ({ page }) => {
      await page.setViewportSize({ width: 640, height: 800 })
      for (const videoId of [BBB, DUB, THAI]) {
        await openTab(page, videoId, which)
        if (which === "audio") await page.getByRole("button", { name: "mp3", exact: true }).click()
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(640)
      }
    })
  }
})
