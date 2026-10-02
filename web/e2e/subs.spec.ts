/// <reference lib="dom" />
import AxeBuilder from "@axe-core/playwright"
import { expect, test, type Page } from "@playwright/test"

import { mockEnqueue } from "./queue-helpers"

// คลิปภาษาไทย: ซับอัตโนมัติภาษาต้นฉบับ (th-orig) เป็นแทร็กเริ่มต้น + ซับแปลอัตโนมัติหลายภาษา
const THAI = "88o5Sk8_m1Y"
// ไม่มีซับเจ้าของคลิป ไม่มี -orig: มีแต่ yue (แปลไม่ได้) กับซับแปล en, th → ไม่มีแทร็กเริ่มต้น
const NO_ORIG = "NOORIGSUB01"
// json3 เสีย ระบบต้องถอยไปใช้ vtt ของคลิปภาษาไทย
const VTT_FALLBACK = "VTTFALLBAK1"
// คลิปยาว 1 ชั่วโมง (ข้อความภาษาไทยซ้ำ 10 รอบ) สำหรับวัดความเร็วตัวอย่างซับ
const LONG = "LONGTHAI1hr"
// Big Buck Bunny: ไม่มีซับเลย
const BBB = "aqz-KE-bpKQ"

const NO_SUBS = "คลิปนี้ไม่มีซับ"
const PREVIEW = "ตัวอย่าง 5 ซับแรก"
const OPEN_TRANSLATED = "เลือกซับแปลอัตโนมัติ…"
const WARNING = "ซับกลุ่มนี้ยูทูปแปลด้วยเครื่อง คุณภาพต่ำและอาจผิดความหมาย ใช้เมื่อไม่มีซับภาษาที่ต้องการเท่านั้น"
const PICK_HINT = "คลิปนี้ไม่มีซับจากเจ้าของคลิปหรือซับภาษาต้นฉบับ เลือกแทร็กที่ต้องการจากรายการ"
const MAX_CHARS = "ตัวอักษรสูงสุดต่อบรรทัด"

const trackSelect = (page: Page) => page.getByRole("combobox", { name: "แทร็กซับ" })
// ข้อความที่ช่องเลือกแสดง (ไอคอนลูกศรของช่องมีอักขระซ่อนอยู่ใน textContent จึงอ่านเฉพาะส่วนค่า)
const trackValue = (page: Page) => trackSelect(page).locator('[data-slot="select-value"]')
const preview = (page: Page) => page.getByRole("region", { name: PREVIEW })
const cues = (page: Page) => preview(page).locator('[data-slot="cue"]')
const firstCueLines = (page: Page) => cues(page).first().locator('[data-slot="cue-line"]')
const stats = (page: Page) => preview(page).locator('[data-slot="cue-stats"]')
const presetButton = (page: Page, name: string) => page.getByRole("button", { name, exact: true })
const translatedDialog = (page: Page) => page.getByRole("dialog", { name: "ซับแปลอัตโนมัติ" })

// สระบน สระล่าง ไม้หันอากาศ และวรรณยุกต์ของไทยไม่นับเป็นตัวอักษร (นับแบบที่ตาเห็น ตาม Q7 = ก)
const THAI_MARKS = /[ัิ-ฺ็-๎]/g
const visibleLength = (text: string) => [...text.replace(THAI_MARKS, "")].length

async function openSubs(page: Page, videoId: string) {
  await page.goto(`/v/${videoId}?tab=subs`)
  await expect(cues(page)).toHaveCount(5)
}

async function openTranslatedDialog(page: Page) {
  await trackSelect(page).click()
  await page.getByRole("option", { name: OPEN_TRANSLATED }).click()
  await expect(translatedDialog(page)).toBeVisible()
}

test.describe("แท็บซับ", () => {
  test("AC-SUB-01: คลิปภาษาไทยเลือก 'ไทย (อัตโนมัติ)' ให้เอง · ตัวอย่าง 5 ซับเริ่มด้วย สวัสดี · มีสรุปจำนวนซับ", async ({
    page,
  }) => {
    await openSubs(page, THAI)
    await expect(trackValue(page)).toHaveText("ไทย (อัตโนมัติ)")
    await expect(firstCueLines(page).first()).toContainText("สวัสดี")
    await expect(stats(page)).toHaveText(/^\d+ ซับ/)
    // ยังไม่ได้เลือกเองใน URL: แทร็กที่ใช้มาจากแทร็กเริ่มต้นของคลิป
    await expect(page).toHaveURL(new RegExp(`/v/${THAI}\\?tab=subs$`))
  })

  test("กด 'สั้น' → ซับแรกสั้นลง (ไม่เกิน 15 ตัวอักษรที่ตาเห็น) · โหลดหน้าใหม่ยังเป็น 'สั้น'", async ({ page }) => {
    await openSubs(page, THAI)
    await expect(presetButton(page, "กลาง")).toHaveAttribute("aria-pressed", "true")
    const before = await firstCueLines(page).allTextContents()

    await presetButton(page, "สั้น").click()
    await expect(presetButton(page, "สั้น")).toHaveAttribute("aria-pressed", "true")
    await expect.poll(() => firstCueLines(page).allTextContents()).not.toEqual(before)
    const after = await firstCueLines(page).allTextContents()
    expect(after).toHaveLength(1)
    expect(visibleLength(after[0])).toBeLessThanOrEqual(15)

    await page.reload()
    await expect(cues(page)).toHaveCount(5)
    await expect(presetButton(page, "สั้น")).toHaveAttribute("aria-pressed", "true")
    expect(await firstCueLines(page).allTextContents()).toEqual(after)
  })

  test("กด 'ทีละคำ' → ทุกซับในตัวอย่างมีคำเดียว จำนวนซับเท่ากับจำนวนคำ · ปุ่ม .srt ส่งงานเข้าคิวด้วยค่าของ ทีละคำ", async ({
    page,
  }) => {
    const queue = await mockEnqueue(page)
    const tokensResponse = page.waitForResponse((r) => /\/subtitles\/[^/]+\/tokens$/.test(new URL(r.url()).pathname))
    await openSubs(page, THAI)
    const { tokens } = (await (await tokensResponse).json()) as { tokens: { t: string }[] }
    expect(tokens.length).toBeGreaterThan(5)

    await presetButton(page, "ทีละคำ").hover()
    await expect(page.getByText("ซับละ 1 คำ แบบซับคลิปสั้น")).toBeVisible()
    await presetButton(page, "ทีละคำ").click()
    await expect(presetButton(page, "ทีละคำ")).toHaveAttribute("aria-pressed", "true")
    // ซับทั้งแทร็กมีเท่าจำนวนคำ = ทุกซับมีคำเดียว (ไม่ใช่แค่ 5 ซับแรก)
    await expect(stats(page)).toHaveText(new RegExp(`^${tokens.length} ซับ`))
    await expect(cues(page)).toHaveCount(5)
    for (let i = 0; i < 5; i++) {
      const word = tokens[i].t.replace(/ {2,}/g, " ").replace(/^ +| +$/g, "")
      await expect(cues(page).nth(i).locator('[data-slot="cue-line"]')).toHaveText([word])
    }

    // M4: ปุ่มโหลดส่งงานเข้าคิว (ไม่โหลดผ่านเบราว์เซอร์) ค่าความยาวซับของ "ทีละคำ" ไปครบทุกช่อง
    // (ไฟล์จริงตรงกับ golden ทุกไบต์ ตรวจที่ pytest ฝั่ง backend)
    await page.getByRole("group", { name: "โหลดซับ" }).getByRole("button", { name: "โหลด .srt" }).click()
    await expect.poll(() => queue.bodies.length).toBe(1)
    expect(queue.bodies[0]).toEqual([
      {
        videoId: THAI,
        kind: "subtitle",
        params: {
          trackId: "a.th-orig",
          format: "srt",
          options: { maxChars: 15, lines: 1, minMs: 800, maxMs: 3000, mode: "tokens", tokensPerCue: 1 },
        },
      },
    ])

    await page.reload()
    await expect(cues(page)).toHaveCount(5)
    await expect(presetButton(page, "ทีละคำ")).toHaveAttribute("aria-pressed", "true")
  })

  test("ปรับเอง: เลื่อนค่าแล้วขึ้นป้าย 'ใช้ค่าที่ปรับเอง' และไม่มีปุ่มสำเร็จรูปไหนถูกเลือก", async ({ page }) => {
    await openSubs(page, THAI)
    await page.getByRole("button", { name: "ปรับเอง" }).click()
    const slider = page.getByRole("slider", { name: MAX_CHARS })
    await slider.focus()
    await page.keyboard.press("ArrowRight")
    await expect(slider).toHaveAttribute("aria-valuenow", "26")
    await expect(page.getByText("ใช้ค่าที่ปรับเอง")).toBeVisible()
    for (const name of ["สั้น", "กลาง", "ยาว", "ทีละคำ"]) {
      await expect(presetButton(page, name)).toHaveAttribute("aria-pressed", "false")
    }
  })

  test("AC-SUB-02: คลิปไม่มีแทร็กเริ่มต้น → ช่องว่าง + คำแนะนำ · รายการหลักมีแค่ yue · เลือกซับแปลจากกล่องค้นหา", async ({
    page,
  }) => {
    await page.goto(`/v/${NO_ORIG}?tab=subs`)
    await expect(trackValue(page)).toHaveText("เลือกแทร็กซับ")
    await expect(page.getByText(PICK_HINT)).toBeVisible()
    await expect(preview(page)).toHaveCount(0)
    await expect(page.getByRole("button", { name: "โหลด .srt" })).toBeDisabled()

    await trackSelect(page).click()
    const yue = await page.evaluate(() => new Intl.DisplayNames(["th"], { type: "language" }).of("yue"))
    const options = page.getByRole("option")
    await expect(options).toHaveText([`${yue} (อัตโนมัติ)`, OPEN_TRANSLATED])

    await page.getByRole("option", { name: OPEN_TRANSLATED }).click()
    const dialog = translatedDialog(page)
    await expect(dialog).toBeVisible()
    // คำเตือนมาก่อนรายการภาษา
    const text = await dialog.innerText()
    expect(text.indexOf(WARNING)).toBeGreaterThanOrEqual(0)
    expect(text.indexOf(WARNING)).toBeLessThan(text.indexOf("อังกฤษ"))

    await dialog.getByRole("button", { name: /^อังกฤษ/ }).click()
    await expect(dialog).toBeHidden()
    await expect(page).toHaveURL(/[?&]track=t\.en(&|$)/)
    await expect(trackValue(page)).toHaveText("อังกฤษ (แปลอัตโนมัติ)")
    await expect(page.getByText(PICK_HINT)).toHaveCount(0)
  })

  test("กล่องซับแปล: ค้นหาด้วยชื่อไทยหรือรหัสภาษา · ไม่พบขึ้น 'ไม่พบภาษานี้'", async ({ page }) => {
    await openSubs(page, THAI)
    await openTranslatedDialog(page)
    const dialog = translatedDialog(page)
    const search = dialog.getByRole("searchbox", { name: "ค้นหาภาษา" })
    await expect(search).toBeFocused()
    await search.fill("ฝรั่ง")
    await expect(dialog.getByRole("listitem")).toHaveCount(1)
    await expect(dialog.getByRole("button", { name: /^ฝรั่งเศส/ })).toBeVisible()
    await search.fill("JA")
    await expect(dialog.getByRole("button", { name: /^ญี่ปุ่น/ })).toBeVisible()
    await search.fill("ภาษาที่ไม่มี")
    await expect(dialog.getByText("ไม่พบภาษานี้")).toBeVisible()
    await page.keyboard.press("Escape")
    await expect(dialog).toBeHidden()
    await expect(trackValue(page)).toHaveText("ไทย (อัตโนมัติ)")
  })

  test("'โหลด .srt/.txt' ส่งงานเข้าคิว: payload ครบ (แทร็ก รูปแบบ ความยาวซับกลาง) + toast 'เพิ่มเข้าคิวแล้ว' · ไม่มีไฟล์โหลดผ่านเบราว์เซอร์ · ไม่มีปุ่ม 'โหลด .md' แล้ว", async ({
    page,
  }) => {
    const queue = await mockEnqueue(page)
    let downloads = 0
    page.on("download", () => (downloads += 1))
    await openSubs(page, THAI)
    const group = page.getByRole("group", { name: "โหลดซับ" })
    // owner round 2: เหลือสองปุ่ม (โน้ต .md อยู่ที่ปุ่ม "บันทึกเป็นโน้ต (.md)" ของหัวคลิป)
    await expect(group.getByRole("button")).toHaveText(["โหลด .srt", "โหลด .txt"])
    await expect(page.getByRole("button", { name: "โหลด .md" })).toHaveCount(0)
    for (const [index, format] of ["srt", "txt"].entries()) {
      await group.getByRole("button", { name: `โหลด .${format}` }).click()
      await expect.poll(() => queue.bodies.length).toBe(index + 1)
      await expect(page.getByText("เพิ่มเข้าคิวแล้ว").first()).toBeVisible()
      // กดซ้ำได้อีกครั้งเมื่อส่งเสร็จ (ปุ่มกลับมาใช้ได้)
      await expect(group.getByRole("button", { name: `โหลด .${format}` })).toBeEnabled()
    }
    expect(queue.bodies.map((items) => items[0].params)).toEqual(
      ["srt", "txt"].map((format) => ({
        trackId: "a.th-orig",
        format,
        options: { maxChars: 25, lines: 1, minMs: 1200, maxMs: 5000, mode: "chars" },
      })),
    )
    for (const items of queue.bodies) {
      expect(items).toHaveLength(1)
      expect(items[0]).toMatchObject({ videoId: THAI, kind: "subtitle" })
    }
    expect(downloads).toBe(0)
  })

  test("ส่งเข้าคิวไม่สำเร็จ → toast ข้อความไทยจาก backend · ปุ่มกลับมากดได้ ไม่มีไฟล์โหลด", async ({ page }) => {
    await page.route("**/api/jobs", (route) =>
      route.request().method() === "POST"
        ? route.fulfill({
            status: 500,
            json: { error: { code: "E_INTERNAL", message: "ส่งเข้าคิวไม่ได้ในตอนนี้", detail: null } },
          })
        : route.fallback(),
    )
    await openSubs(page, THAI)
    let downloads = 0
    page.on("download", () => (downloads += 1))
    await page.getByRole("button", { name: "โหลด .txt" }).click()
    await expect(page.getByText("ส่งเข้าคิวไม่ได้ในตอนนี้")).toBeVisible()
    await expect(page.getByRole("button", { name: "โหลด .txt" })).toBeEnabled()
    expect(downloads).toBe(0)
  })

  test("'คัดลอกข้อความ' → คลิปบอร์ดขึ้นต้นด้วย สวัสดีครับ และขึ้น toast", async ({ page, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"])
    await openSubs(page, THAI)
    await page.getByRole("button", { name: "คัดลอกข้อความ" }).click()
    await expect(page.getByText("คัดลอกข้อความแล้ว")).toBeVisible()
    const text = await page.evaluate(() => navigator.clipboard.readText())
    // ไม่ตรวจ \r: คลิปบอร์ดของ Windows แปลง \n เป็น \r\n เองตอนอ่านกลับ
    expect(text.startsWith("สวัสดีครับ")).toBe(true)
  })

  test("AC-SUB-11: json3 เสียแล้วถอยไปใช้ vtt · ตัวอย่างยังขึ้นต้นด้วย สวัสดี", async ({ page }) => {
    await openSubs(page, VTT_FALLBACK)
    await expect(firstCueLines(page).first()).toHaveText(/^สวัสดี/)
  })

  test("คลิปไม่มีซับ: 'คลิปนี้ไม่มีซับ' และไม่มีช่องเลือกแทร็ก", async ({ page }) => {
    await page.goto(`/v/${BBB}?tab=subs`)
    await expect(page.getByText(NO_SUBS)).toBeVisible()
    await expect(trackSelect(page)).toHaveCount(0)
  })

  test("แทร็กที่อ่านแล้วไม่มีข้อความ (E_NO_SUBTITLES) → 'คลิปนี้ไม่มีซับ' แต่ยังเลือกแทร็กอื่นได้", async ({ page }) => {
    await page.route(`**/api/videos/${THAI}/subtitles/*/tokens`, (route) =>
      route.fulfill({
        status: 404,
        json: { error: { code: "E_NO_SUBTITLES", message: NO_SUBS, detail: null } },
      }),
    )
    await page.goto(`/v/${THAI}?tab=subs`)
    await expect(page.getByText(NO_SUBS)).toBeVisible()
    await expect(trackSelect(page)).toBeVisible()
    // แทร็กที่ไม่มีข้อความ: โหลดไฟล์และคัดลอกไม่ได้
    for (const name of ["โหลด .srt", "โหลด .txt", "คัดลอกข้อความ"]) {
      await expect(page.getByRole("button", { name })).toBeDisabled()
    }
  })

  test("โหลดคำของแทร็กไม่สำเร็จ → กล่อง error พร้อมปุ่มลองใหม่ แล้วลองใหม่สำเร็จ", async ({ page }) => {
    let fail = true
    await page.route(`**/api/videos/${THAI}/subtitles/*/tokens`, (route) =>
      fail
        ? route.fulfill({ status: 500, json: { error: { code: "E_UNKNOWN", message: "ลองอีกครั้ง", detail: null } } })
        : route.continue(),
    )
    await page.goto(`/v/${THAI}?tab=subs`)
    await expect(page.getByText("โหลดซับไม่สำเร็จ")).toBeVisible()
    fail = false
    await page.getByRole("button", { name: "ลองใหม่" }).click()
    await expect(cues(page)).toHaveCount(5)
  })

  test("AC-SUB-07: คลิป 1 ชั่วโมง ปรับค่าตัวอักษรแล้วตัวอย่างอัปเดตภายใน 200 ms (มัธยฐาน 5 ครั้ง)", async ({
    page,
  }) => {
    await openSubs(page, LONG)
    // ตรวจว่าข้อมูลทดสอบยาวจริง: ซับของคลิป 88o5 (342 คำ ยาว 6 นาที) ต่อกัน 10 รอบ = 3420 คำ ยาวเกิน 1 ชั่วโมง
    const track = await page.evaluate(async (videoId) => {
      const list = (await (await fetch(`/api/videos/${videoId}/subtitles`)).json()) as { defaultTrackId?: string }
      const res = await fetch(`/api/videos/${videoId}/subtitles/${list.defaultTrackId}/tokens`)
      const { tokens } = (await res.json()) as { tokens: { e: number }[] }
      return { count: tokens.length, endMs: tokens.at(-1)?.e ?? 0 }
    }, LONG)
    expect(track.count).toBeGreaterThanOrEqual(3400)
    expect(track.endMs).toBeGreaterThanOrEqual(3_600_000)

    await page.getByRole("button", { name: "ปรับเอง" }).click()
    const slider = page.getByRole("slider", { name: MAX_CHARS })
    await slider.focus()

    // ArrowRight ทีละ 1 ตัวอักษร (25 → 26) บางครั้งไม่ทำให้ซับเปลี่ยนเลย (คลิปนี้ได้ 830 ซับ เฉลี่ย 14.9 ตัวเท่าเดิม)
    // บรรทัดสรุปจึงไม่ขยับ: สลับกด Home (10 ตัว) กับ End (60 ตัว) ที่ปุ่มเลื่อนเดิม ผลต่างกันทุกครั้งแน่นอน
    const keys = ["Home", "End", "Home", "End", "Home"]
    const times: number[] = []
    for (const key of keys) {
      const elapsed = await page.evaluate(
        (pressed) =>
          new Promise<number>((resolve, reject) => {
            const statsLine = document.querySelector('[data-slot="cue-stats"]')
            const thumb = document.activeElement
            if (!statsLine || !(thumb instanceof HTMLInputElement)) {
              reject(new Error("ไม่พบบรรทัดสรุปหรือสไลเดอร์ที่โฟกัสอยู่"))
              return
            }
            let t0 = 0
            const timer = window.setTimeout(() => reject(new Error("บรรทัดสรุปไม่เปลี่ยนภายใน 2 วินาที")), 2000)
            const observer = new MutationObserver(() => {
              observer.disconnect()
              window.clearTimeout(timer)
              resolve(performance.now() - t0)
            })
            observer.observe(statsLine, { characterData: true, childList: true, subtree: true })
            t0 = performance.now()
            thumb.dispatchEvent(new KeyboardEvent("keydown", { key: pressed, bubbles: true }))
          }),
        key,
      )
      times.push(elapsed)
    }
    await expect(slider).toHaveAttribute("aria-valuenow", "10")
    times.sort((a, b) => a - b)
    expect(times[2]).toBeLessThanOrEqual(200)
  })
})

const BLOCKED = "ยูทูปยังไม่ให้โหลดซับแปลอัตโนมัติในตอนนี้ เลือกซับภาษาต้นฉบับแทน"
const USE_ORIGINAL = "ใช้ซับภาษาต้นฉบับ"
const EXPORT_BUTTONS = ["โหลด .srt", "โหลด .txt", "คัดลอกข้อความ"]
const tab = (page: Page, name: string) => page.getByRole("tab", { name, exact: true })
const panel = (page: Page, name: string) => page.getByRole("tabpanel", { name, exact: true })

/** ข้อความของซับในตัวอย่าง: บรรทัดย่อยต่อด้วยช่องว่าง แบบเดียวกับที่ทรานสคริปต์แสดง */
const cueTexts = (page: Page) =>
  cues(page).evaluateAll((items) =>
    items.map((item) =>
      [...item.querySelectorAll('[data-slot="cue-line"]')]
        .map((line) => line.textContent ?? "")
        .join(" ")
        .replace(/\s+/g, " "),
    ),
  )

/** ยูทูปตอบ 429 กับซับแปล (backend แปลงเป็น 503 E_TRANSLATION_BLOCKED) คืนตัวนับคำขอ token ของแทร็กนั้น */
async function blockTranslated(page: Page, videoId: string, trackId: string) {
  const calls = { n: 0 }
  await page.route(`**/api/videos/${videoId}/subtitles/${trackId}/tokens`, (route) => {
    calls.n += 1
    return route.fulfill({
      status: 503,
      json: { error: { code: "E_TRANSLATION_BLOCKED", message: BLOCKED, detail: null } },
    })
  })
  return calls
}

test.describe("แท็บซับ: ซับแปลที่ยูทูปไม่ให้โหลด (E_TRANSLATION_BLOCKED)", () => {
  test("บอกตรง ๆ ว่าซับแปลโหลดไม่ได้ ไม่มีปุ่มลองใหม่ ปุ่มโหลด/คัดลอกกดไม่ได้ สลับแท็บไม่ยิงซ้ำ · กด 'ใช้ซับภาษาต้นฉบับ' ได้ซับไทย", async ({
    page,
  }) => {
    const calls = await blockTranslated(page, THAI, "t.en")
    await page.goto(`/v/${THAI}?tab=subs&track=t.en`)
    await expect(page.getByText(BLOCKED)).toBeVisible()
    await expect(page.getByText("ยูทูปขอให้ยืนยันว่าไม่ใช่บอท", { exact: false })).toHaveCount(0)
    await expect(page.getByRole("button", { name: "ลองใหม่" })).toHaveCount(0)
    for (const name of EXPORT_BUTTONS) {
      await expect(page.getByRole("button", { name })).toBeDisabled()
    }
    expect(calls.n).toBe(1)

    // สลับไปทรานสคริปต์แล้วกลับมา: เห็นข้อความเดิมทั้งสองแท็บ โดยไม่ยิงคำขอไปยูทูปซ้ำ
    // แผงที่กำลังปิดยังอยู่ครู่หนึ่ง (มีข้อความและปุ่มชื่อเดียวกัน) จึงเจาะจงแผงของแท็บที่เปิด
    await tab(page, "ทรานสคริปต์").click()
    await expect(panel(page, "ทรานสคริปต์").getByText(BLOCKED)).toBeVisible()
    await expect(panel(page, "ทรานสคริปต์").getByRole("button", { name: USE_ORIGINAL })).toBeVisible()
    await tab(page, "ซับ").click()
    await expect(panel(page, "ซับ").getByText(BLOCKED)).toBeVisible()
    expect(calls.n).toBe(1)

    // ใช้คีย์บอร์ด: ปุ่มหายไปหลังเปลี่ยนแทร็ก โฟกัสต้องไปอยู่ที่ช่องเลือกแทร็ก ไม่หลุดไป body
    await panel(page, "ซับ").getByRole("button", { name: USE_ORIGINAL }).focus()
    await page.keyboard.press("Enter")
    await expect(page).toHaveURL(/[?&]track=a\.th-orig(&|$)/)
    await expect(page).toHaveURL(/[?&]tab=subs(&|$)/)
    await expect(trackSelect(page)).toBeFocused()
    await expect(trackValue(page)).toHaveText("ไทย (อัตโนมัติ)")
    await expect(cues(page)).toHaveCount(5)
    await expect(firstCueLines(page).first()).toContainText("สวัสดี")
    await expect(page.getByText(BLOCKED)).toHaveCount(0)
    for (const name of EXPORT_BUTTONS) {
      await expect(page.getByRole("button", { name })).toBeEnabled()
    }
    await expect(trackSelect(page)).toBeFocused()
    expect(await page.evaluate(() => document.activeElement === document.body)).toBe(false)
  })

  test("คลิปไม่มีแทร็กเริ่มต้น: บอกข้อความเดียวกันแต่ไม่มีปุ่ม 'ใช้ซับภาษาต้นฉบับ'", async ({ page }) => {
    await blockTranslated(page, NO_ORIG, "t.en")
    await page.goto(`/v/${NO_ORIG}?tab=subs&track=t.en`)
    await expect(page.getByText(BLOCKED)).toBeVisible()
    await expect(page.getByRole("button", { name: USE_ORIGINAL })).toHaveCount(0)
    await expect(page.getByRole("button", { name: "ลองใหม่" })).toHaveCount(0)
    // ยังเลือกแทร็กอื่นเองได้
    await expect(trackSelect(page)).toBeVisible()
  })

  test("error อื่นของ token (เช่น เน็ตหลุด) ก็ทำให้ปุ่มโหลด/คัดลอกกดไม่ได้", async ({ page }) => {
    await page.route(`**/api/videos/${THAI}/subtitles/*/tokens`, (route) =>
      route.fulfill({ status: 502, json: { error: { code: "E_NETWORK", message: "เน็ตหลุด ลองใหม่อีกครั้ง", detail: null } } }),
    )
    await page.goto(`/v/${THAI}?tab=subs`)
    await expect(page.getByText("เน็ตหลุด ลองใหม่อีกครั้ง")).toBeVisible()
    await expect(page.getByRole("button", { name: "ลองใหม่" })).toBeVisible()
    for (const name of EXPORT_BUTTONS) {
      await expect(page.getByRole("button", { name })).toBeDisabled()
    }
  })
})

test.describe("แท็บซับ: track= ใน URL ที่คลิปนี้ไม่มี", () => {
  test("ใช้แทร็กเริ่มต้นแทน: ป้ายแทร็ก แท็บซับ และทรานสคริปต์ใช้ซับไทย (อัตโนมัติ)", async ({ page }) => {
    await page.goto(`/v/${THAI}?tab=subs&track=o.xx`)
    await expect(trackValue(page)).toHaveText("ไทย (อัตโนมัติ)")
    await expect(cues(page)).toHaveCount(5)
    await expect(page.getByText(PICK_HINT)).toHaveCount(0)
    await expect(page.getByText("ซับ: ไทย (อัตโนมัติ)")).toBeVisible()
    await tab(page, "ทรานสคริปต์").click()
    await expect(page.getByText("จากแทร็ก ไทย (อัตโนมัติ)", { exact: false })).toBeVisible()
    await expect(page.getByRole("list", { name: "บรรทัดในทรานสคริปต์" }).getByRole("listitem").first()).toBeVisible()
  })
})

test.describe("แท็บซับ + ทรานสคริปต์ใช้ค่าความยาวซับก้อนเดียวกัน (Q4)", () => {
  test("เบราว์เซอร์บล็อก localStorage และ sessionStorage: ปรับเองในแท็บซับ → ทรานสคริปต์แบ่งบรรทัดตรงกับตัวอย่างซับ และค่ายังอยู่เมื่อกลับมา", async ({
    page,
  }) => {
    const pageErrors: string[] = []
    page.on("pageerror", (error) => pageErrors.push(error.message))
    await page.addInitScript(() => {
      for (const name of ["localStorage", "sessionStorage"]) {
        Object.defineProperty(window, name, {
          get() {
            throw new DOMException("The operation is insecure.", "SecurityError")
          },
        })
      }
    })
    await openSubs(page, THAI)
    const medium = await firstCueLines(page).allTextContents()
    await page.getByRole("button", { name: "ปรับเอง" }).click()
    const slider = page.getByRole("slider", { name: MAX_CHARS })
    await slider.focus()
    for (let i = 0; i < 10; i++) await page.keyboard.press("ArrowLeft")
    await expect(slider).toHaveAttribute("aria-valuenow", "15")
    await expect(page.getByText("ใช้ค่าที่ปรับเอง")).toBeVisible()
    await expect.poll(() => firstCueLines(page).allTextContents()).not.toEqual(medium)

    // ข้อความของ 5 ซับแรกในตัวอย่าง (บรรทัดย่อยต่อด้วยช่องว่าง แบบที่ทรานสคริปต์แสดง)
    const previewTexts = await cueTexts(page)
    expect(previewTexts).toHaveLength(5)

    await tab(page, "ทรานสคริปต์").click()
    const lines = page.getByRole("list", { name: "บรรทัดในทรานสคริปต์" }).getByRole("listitem")
    await expect(lines.first()).toBeVisible()
    const transcriptTexts = await lines.evaluateAll((items) =>
      items.slice(0, 5).map((item) => item.querySelector("button > span:last-child")?.textContent ?? ""),
    )
    expect(transcriptTexts).toEqual(previewTexts)

    // กลับมาแท็บซับ: ค่าที่ปรับเองยังอยู่ (ไม่ถอยกลับเป็น 'กลาง')
    await tab(page, "ซับ").click()
    await expect(page.getByText("ใช้ค่าที่ปรับเอง")).toBeVisible()
    await expect(cues(page)).toHaveCount(5)
    expect(await cueTexts(page)).toEqual(previewTexts)
    expect(pageErrors).toEqual([])
  })
})

test.describe("แท็บซับ การเข้าถึง (axe)", () => {
  for (const scheme of ["dark", "light"] as const) {
    test(`แท็บซับ · กล่องปรับเองเปิด · กล่องซับแปลเปิด ไม่มีปัญหาระดับ serious/critical (${scheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme })
      await openSubs(page, THAI)
      await expect(page.locator("html")).toHaveClass(scheme === "dark" ? /dark/ : /light/)
      expect(await seriousViolations(page)).toEqual([])

      await page.getByRole("button", { name: "ปรับเอง" }).click()
      await expect(page.getByRole("slider", { name: MAX_CHARS })).toBeVisible()
      expect(await seriousViolations(page)).toEqual([])

      await openTranslatedDialog(page)
      expect(await seriousViolations(page)).toEqual([])
    })
  }
})

async function seriousViolations(page: Page) {
  const results = await new AxeBuilder({ page }).analyze()
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.map((n) => n.target.join(" ")).slice(0, 5) }))
}
