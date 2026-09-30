/// <reference lib="dom" />
import AxeBuilder from "@axe-core/playwright"
import { expect, test, type Page } from "@playwright/test"

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
// ชื่อไฟล์ตาม Q2 = ก: <ชื่อคลิปที่ปลอดภัย>.<ภาษา>.<นามสกุล> (ตัด | ออกและยุบช่องว่าง) ตรงกับที่เทสต์ API ของ T11 ตรึงไว้
const SRT_NAME = "Thai Listening Practice EP.1 Beginner.th.srt"

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

  test("ปรับเอง: เลื่อนค่าแล้วขึ้นป้าย 'ใช้ค่าที่ปรับเอง' และไม่มีปุ่มสำเร็จรูปไหนถูกเลือก", async ({ page }) => {
    await openSubs(page, THAI)
    await page.getByRole("button", { name: "ปรับเอง" }).click()
    const slider = page.getByRole("slider", { name: MAX_CHARS })
    await slider.focus()
    await page.keyboard.press("ArrowRight")
    await expect(slider).toHaveAttribute("aria-valuenow", "26")
    await expect(page.getByText("ใช้ค่าที่ปรับเอง")).toBeVisible()
    for (const name of ["สั้น", "กลาง", "ยาว"]) {
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

  test("'โหลด .srt' ได้ไฟล์ชื่อตามคลิป .th.srt ที่ขึ้นต้นด้วย 1\\r\\n00:00:00,120", async ({ page }) => {
    await openSubs(page, THAI)
    const downloading = page.waitForEvent("download")
    await page.getByRole("group", { name: "โหลดซับ" }).getByRole("button", { name: "โหลด .srt" }).click()
    const download = await downloading
    expect(download.suggestedFilename()).toBe(SRT_NAME)
    const bytes = await download.createReadStream().then(async (stream) => {
      const chunks: Buffer[] = []
      for await (const chunk of stream) chunks.push(chunk as Buffer)
      return Buffer.concat(chunks)
    })
    expect(bytes.toString("utf8").startsWith("1\r\n00:00:00,120 --> ")).toBe(true)
  })

  test("โหลดไม่สำเร็จ → toast ข้อความไทย ไม่ได้ไฟล์", async ({ page }) => {
    await page.route((url) => url.pathname.endsWith("/export"), (route) => route.abort())
    await openSubs(page, THAI)
    let downloads = 0
    page.on("download", () => (downloads += 1))
    await page.getByRole("button", { name: "โหลด .txt" }).click()
    await expect(page.getByText(/เชื่อมต่อโปรแกรมไม่ได้/)).toBeVisible()
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
    for (const name of ["โหลด .srt", "โหลด .txt", "โหลด .md", "คัดลอกข้อความ"]) {
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
