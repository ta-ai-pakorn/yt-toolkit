import { expect, test, type Page, type Route } from "@playwright/test"

// owner round 3: ซับแปลต้องรอเซสชันผู้ชมของยูทูปอายุถึง 75 วินาที backend ตอบ 503 E_SESSION_WARMING + retryAfterSeconds
// เทสนี้จำลองคำตอบนั้นด้วย page.route (backend ปลอมไม่มีเซสชัน) แล้วให้คำขอถัดไปผ่านไปถึง backend ปลอมจริง
// (88o5Sk8_m1Y มีไฟล์ซับแปล tlang-en ใน fixtures) หรือจำลอง E_TRANSLATION_BLOCKED
const THAI = "88o5Sk8_m1Y"
const TRACK = "t.en"
const URL = `/v/${THAI}?tab=subs&track=${TRACK}`
const BLOCKED = "ยูทูปยังไม่ให้โหลดซับแปลอัตโนมัติในตอนนี้ เลือกซับภาษาต้นฉบับแทน"
const USE_ORIGINAL = "ใช้ซับภาษาต้นฉบับ"
const EXPORT_BUTTONS = ["โหลด .srt", "โหลด .txt", "คัดลอกข้อความ"]
const NOTE_BUTTON = "บันทึกเป็นโน้ต (.md)"
const PREVIEW = "ตัวอย่าง 5 ซับแรก"

const tab = (page: Page, name: string) => page.getByRole("tab", { name, exact: true })
const panel = (page: Page, name: string) => page.getByRole("tabpanel", { name, exact: true })
const box = (page: Page, name = "ซับ") => panel(page, name).getByTestId("session-warming")
const countdown = (page: Page, name = "ซับ") => box(page, name).locator('[data-slot="warming-text"]')
const cues = (page: Page) => page.getByRole("region", { name: PREVIEW }).locator('[data-slot="cue"]')

function warmingBody(seconds: number) {
  return {
    error: {
      code: "E_SESSION_WARMING",
      message: "กำลังเตรียมซับแปลจากยูทูป รอสักครู่แล้วโหลดใหม่",
      detail: null,
      retryAfterSeconds: seconds,
    },
  }
}

type Next = "pass" | "blocked" | "warming"

/**
 * คำขอ token ของซับแปล: ครั้งแรกตอบ E_SESSION_WARMING (รอ `seconds` วินาที) ครั้งต่อไปทำตาม `next`
 * pass = ส่งต่อให้ backend ปลอม (ได้ซับแปลจริงจาก fixture) · blocked = E_TRANSLATION_BLOCKED
 */
async function warmTranslated(page: Page, seconds: number, next: Next = "pass") {
  const calls = { n: 0, at: [] as number[] }
  await page.route(`**/api/videos/${THAI}/subtitles/${TRACK}/tokens`, (route: Route) => {
    calls.n += 1
    calls.at.push(Date.now())
    if (calls.n === 1 || next === "warming") {
      return route.fulfill({ status: 503, headers: { "Retry-After": String(seconds) }, json: warmingBody(seconds) })
    }
    if (next === "blocked") {
      return route.fulfill({
        status: 503,
        json: { error: { code: "E_TRANSLATION_BLOCKED", message: BLOCKED, detail: null } },
      })
    }
    return route.continue()
  })
  return calls
}

async function secondsShown(page: Page, name = "ซับ"): Promise<number> {
  const text = (await countdown(page, name).textContent()) ?? ""
  const match = text.match(/รอ (\d+) วินาที/)
  if (!match) throw new Error(`no countdown in ${JSON.stringify(text)}`)
  return Number(match[1])
}

test.describe("ซับแปลรอเซสชันของยูทูป (E_SESSION_WARMING)", () => {
  test("กล่องแจ้งแบบสงบนับถอยหลังทุกวินาที มีวงหมุน ปุ่มโหลด/คัดลอก/โน้ตกดไม่ได้ ปุ่มใช้ซับภาษาต้นฉบับกดได้", async ({ page }) => {
    const calls = await warmTranslated(page, 30)
    await page.goto(URL)
    await expect(countdown(page)).toHaveText(/^กำลังเตรียมซับแปลจากยูทูป รอ \d+ วินาที แล้วโหลดให้เอง$/)
    // ไม่ใช่กล่องแดง/error: ไม่มี role=alert และไม่ใช้สี destructive
    await expect(box(page)).not.toHaveAttribute("role", "alert")
    await expect(box(page)).not.toHaveClass(/text-destructive/)
    await expect(box(page).locator('[data-slot="spinner"]')).toBeVisible()
    const first = await secondsShown(page)
    expect(first).toBeLessThanOrEqual(30)
    expect(first).toBeGreaterThanOrEqual(28)
    await expect.poll(() => secondsShown(page), { timeout: 4_000 }).toBeLessThanOrEqual(first - 2)
    for (const name of EXPORT_BUTTONS) {
      await expect(panel(page, "ซับ").getByRole("button", { name })).toBeDisabled()
    }
    await expect(page.getByRole("button", { name: NOTE_BUTTON })).toBeDisabled()
    await expect(box(page).getByRole("button", { name: USE_ORIGINAL })).toBeEnabled()
    // ไม่มีปุ่มลองใหม่ และไม่มีข้อความ error สีแดง
    await expect(page.getByRole("button", { name: "ลองใหม่" })).toHaveCount(0)
    expect(calls.n).toBe(1)
  })

  test("โปรแกรมอ่านหน้าจอได้ยินตอนเริ่ม ทุก 15 วินาที และตอนครบ ไม่ใช่ทุกวินาที", async ({ page }) => {
    await warmTranslated(page, 20)
    await page.goto(URL)
    const live = box(page).getByRole("status")
    await expect(live).toHaveAttribute("aria-live", "polite")
    // review #4: region ขึ้นแบบว่างแล้วได้ข้อความในอีกหนึ่งจังหวะ (ข้อความที่มีอยู่ตั้งแต่แรกมักไม่ถูกอ่าน)
    await expect(live).toHaveText(/รอ (19|20) วินาที/)
    const firstSpoken = await live.textContent()
    // ตัวเลขบนจอเดินไปแล้ว 2 วินาที แต่ข้อความที่ประกาศยังเป็นค่าเดิม
    const shownAtStart = await secondsShown(page)
    await expect.poll(() => secondsShown(page), { timeout: 4_000 }).toBeLessThanOrEqual(shownAtStart - 2)
    await expect(live).toHaveText(firstSpoken ?? "")
    // ถึง 15 วินาทีแล้วจึงประกาศใหม่
    await expect(live).toHaveText("กำลังเตรียมซับแปลจากยูทูป รอ 15 วินาที แล้วโหลดให้เอง", { timeout: 8_000 })
    // ตัวเลขบนจอไม่ถูกอ่านซ้ำ (ซ่อนจากโปรแกรมอ่านหน้าจอ อ่านจาก live region แทน)
    await expect(countdown(page)).toHaveAttribute("aria-hidden", "true")
  })

  test("ครบเวลาแล้วโหลดใหม่ให้เองครั้งเดียว ได้ซับแปลมาแสดง ปุ่มโหลดกดได้", async ({ page }) => {
    const calls = await warmTranslated(page, 2)
    await page.goto(URL)
    await expect(box(page)).toBeVisible()
    await expect(cues(page)).toHaveCount(5, { timeout: 10_000 })
    await expect(box(page)).toHaveCount(0)
    expect(calls.n).toBe(2)
    expect(calls.at[1] - calls.at[0]).toBeGreaterThanOrEqual(1_500)
    for (const name of EXPORT_BUTTONS) {
      await expect(panel(page, "ซับ").getByRole("button", { name })).toBeEnabled()
    }
    await expect(page.getByRole("button", { name: NOTE_BUTTON })).toBeEnabled()
    await page.waitForTimeout(2_500)
    expect(calls.n).toBe(2)
  })

  test("สลับแท็บระหว่างนับ: นับต่อจากเดิม (ไม่เริ่มใหม่) และไม่ยิงคำขอซ้ำ", async ({ page }) => {
    const calls = await warmTranslated(page, 20)
    await page.goto(URL)
    await expect(countdown(page)).toBeVisible()
    await page.waitForTimeout(2_200)
    const onSubs = await secondsShown(page)
    expect(onSubs).toBeLessThanOrEqual(18)
    await tab(page, "ทรานสคริปต์").click()
    await expect(countdown(page, "ทรานสคริปต์")).toBeVisible()
    const onTranscript = await secondsShown(page, "ทรานสคริปต์")
    expect(onTranscript).toBeLessThanOrEqual(onSubs)
    expect(onTranscript).toBeGreaterThanOrEqual(onSubs - 2)
    await expect(panel(page, "ทรานสคริปต์").getByRole("button", { name: USE_ORIGINAL })).toBeVisible()
    await tab(page, "ซับ").click()
    await expect(countdown(page)).toBeVisible()
    expect(await secondsShown(page)).toBeLessThanOrEqual(onTranscript)
    expect(calls.n).toBe(1)
  })

  test("อยู่แท็บภาพเฟรมตอนครบเวลา: ยังโหลดให้เอง กลับมาแท็บซับก็เห็นซับเลย", async ({ page }) => {
    const calls = await warmTranslated(page, 2)
    await page.goto(URL)
    await expect(box(page)).toBeVisible()
    await tab(page, "ภาพเฟรม").click()
    await expect.poll(() => calls.n, { timeout: 8_000 }).toBe(2)
    await tab(page, "ซับ").click()
    await expect(cues(page)).toHaveCount(5)
    expect(calls.n).toBe(2)
  })

  test("ครบเวลาแล้วยูทูปยังไม่ให้ (E_TRANSLATION_BLOCKED): ขึ้นข้อความตรง ๆ เดิมพร้อมปุ่มใช้ซับภาษาต้นฉบับ", async ({ page }) => {
    const calls = await warmTranslated(page, 2, "blocked")
    await page.goto(URL)
    await expect(box(page)).toBeVisible()
    await expect(panel(page, "ซับ").getByText(BLOCKED)).toBeVisible({ timeout: 10_000 })
    await expect(box(page)).toHaveCount(0)
    await expect(panel(page, "ซับ").getByRole("button", { name: USE_ORIGINAL })).toBeVisible()
    await page.waitForTimeout(2_500)
    expect(calls.n).toBe(2)
  })

  test("กด 'ใช้ซับภาษาต้นฉบับ' ระหว่างนับ: ไปซับไทยทันที โฟกัสอยู่ที่ช่องเลือกแทร็ก", async ({ page }) => {
    await warmTranslated(page, 30)
    await page.goto(URL)
    await box(page).getByRole("button", { name: USE_ORIGINAL }).click()
    await expect(page).toHaveURL(/[?&]track=a\.th-orig(&|$)/)
    await expect(cues(page)).toHaveCount(5)
    await expect(page.getByRole("combobox", { name: "แทร็กซับ" })).toBeFocused()
    await expect(page.getByTestId("session-warming")).toHaveCount(0)
  })

  test("live region ขึ้นมาแบบว่างก่อน แล้วจึงได้ข้อความ (review #4)", async ({ page }) => {
    await warmTranslated(page, 30)
    await page.addInitScript(() => {
      const seen: string[] = []
      Object.defineProperty(window, "__liveFirst", { value: seen })
      new MutationObserver((records) => {
        for (const record of records) {
          for (const node of record.addedNodes) {
            if (node instanceof HTMLElement) {
              const region = node.matches('[data-slot="warming-live"]') ? node : node.querySelector('[data-slot="warming-live"]')
              if (region) seen.push(region.textContent ?? "")
            }
          }
        }
      }).observe(document, { childList: true, subtree: true })
    })
    await page.goto(URL)
    await expect(box(page).getByRole("status")).toHaveText(/รอ \d+ วินาที/)
    const first = await page.evaluate(() => (window as unknown as { __liveFirst: string[] }).__liveFirst)
    expect(first.length).toBeGreaterThan(0)
    expect(first[0]).toBe("")
  })

  test("เปลี่ยนแทร็กระหว่างนับ: แทร็กใหม่โหลดทันที ซับแปลยังนับต่อเบื้องหลังและโหลดเองเมื่อครบ กลับมาเห็นซับเลย (review #8)", async ({
    page,
  }) => {
    const calls = await warmTranslated(page, 3)
    await page.goto(URL)
    await expect(box(page)).toBeVisible()
    // เปลี่ยนไปซับไทยจากช่องเลือกแทร็ก (ไม่ใช่ปุ่มในกล่อง)
    await page.getByRole("combobox", { name: "แทร็กซับ" }).click()
    await page.getByRole("option", { name: "ไทย (อัตโนมัติ)" }).click()
    await expect(page).toHaveURL(/[?&]track=a\.th-orig(&|$)/)
    await expect(cues(page)).toHaveCount(5)
    await expect(page.getByTestId("session-warming")).toHaveCount(0)
    for (const name of EXPORT_BUTTONS) {
      await expect(panel(page, "ซับ").getByRole("button", { name })).toBeEnabled()
    }
    // ครบเวลาแล้ว ซับแปลที่ไม่ได้แสดงอยู่ก็ถูกโหลดเองหนึ่งครั้ง
    await expect.poll(() => calls.n, { timeout: 8_000 }).toBe(2)
    // กลับไปซับแปลอังกฤษ: เห็นซับทันที ไม่มีกล่องนับ และไม่ยิงคำขอเพิ่ม
    await page.getByRole("combobox", { name: "แทร็กซับ" }).click()
    await page.getByRole("option", { name: "เลือกซับแปลอัตโนมัติ…" }).click()
    const dialog = page.getByRole("dialog", { name: "ซับแปลอัตโนมัติ" })
    await dialog.getByRole("searchbox", { name: "ค้นหาภาษา" }).fill("อังกฤษ")
    await dialog.getByRole("button", { name: /^อังกฤษ/ }).first().click()
    await expect(page).toHaveURL(/[?&]track=t\.en(&|$)/)
    await expect(cues(page)).toHaveCount(5)
    await expect(page.getByTestId("session-warming")).toHaveCount(0)
    expect(calls.n).toBe(2)
  })

  test("เปลี่ยนแทร็กไปแล้วกลับมาระหว่างนับ: นับต่อจากเดิม (ราว 17 ไม่ใช่ 20) และไม่ยิงคำขอเพิ่ม (review #8)", async ({
    page,
  }) => {
    const calls = await warmTranslated(page, 20)
    await page.goto(URL)
    await expect(countdown(page)).toBeVisible()
    await page.getByRole("combobox", { name: "แทร็กซับ" }).click()
    await page.getByRole("option", { name: "ไทย (อัตโนมัติ)" }).click()
    await expect(cues(page)).toHaveCount(5)
    await page.waitForTimeout(3_000)
    await page.getByRole("combobox", { name: "แทร็กซับ" }).click()
    await page.getByRole("option", { name: "เลือกซับแปลอัตโนมัติ…" }).click()
    const dialog = page.getByRole("dialog", { name: "ซับแปลอัตโนมัติ" })
    await dialog.getByRole("searchbox", { name: "ค้นหาภาษา" }).fill("อังกฤษ")
    await dialog.getByRole("button", { name: /^อังกฤษ/ }).first().click()
    await expect(page).toHaveURL(/[?&]track=t\.en(&|$)/)
    await expect(countdown(page)).toBeVisible()
    const shown = await secondsShown(page)
    expect(shown).toBeLessThanOrEqual(17)
    expect(shown).toBeGreaterThanOrEqual(14)
    expect(calls.n).toBe(1)
  })

  test("เปลี่ยนแทร็กหนีระหว่างคำขอตอนครบเวลา (ช้า 3 วินาที) แล้วกลับมา: โหลดซับแปลได้ ไม่ค้าง 'กำลังโหลด' (I-2)", async ({
    page,
  }) => {
    // คำขอแรก = E_SESSION_WARMING 2 วินาที · คำขอตอนครบเวลาค้าง 3 วินาที (เหมือน backend รอ 429) · คำขอต่อไปผ่านทันที
    const calls = { n: 0 }
    await page.route(`**/api/videos/${THAI}/subtitles/${TRACK}/tokens`, async (route: Route) => {
      calls.n += 1
      if (calls.n === 1) return route.fulfill({ status: 503, json: warmingBody(2) })
      if (calls.n === 2) {
        await new Promise((resolve) => setTimeout(resolve, 3_000))
        // เบราว์เซอร์ยกเลิกคำขอนี้ไปแล้ว (ผู้ใช้เปลี่ยนแทร็ก) continue จึงอาจล้มเหลว
        return route.continue().catch(() => undefined)
      }
      return route.continue()
    })
    await page.goto(URL)
    await expect(box(page)).toBeVisible()
    await expect.poll(() => calls.n, { timeout: 8_000 }).toBe(2)
    // ระหว่างคำขอตอนครบเวลา (ยังไม่ตอบ) กล่องนับหายไปเป็นการโหลดปกติ แล้วผู้ใช้เปลี่ยนไปซับไทย
    await expect(box(page)).toHaveCount(0)
    await expect(cues(page)).toHaveCount(0)
    await page.getByRole("combobox", { name: "แทร็กซับ" }).click()
    await page.getByRole("option", { name: "ไทย (อัตโนมัติ)" }).click()
    await expect(page).toHaveURL(/[?&]track=a\.th-orig(&|$)/)
    await expect(cues(page)).toHaveCount(5)
    // กลับไปซับแปลอังกฤษ: ต้องได้ซับมาแสดง
    await page.getByRole("combobox", { name: "แทร็กซับ" }).click()
    await page.getByRole("option", { name: "เลือกซับแปลอัตโนมัติ…" }).click()
    const dialog = page.getByRole("dialog", { name: "ซับแปลอัตโนมัติ" })
    await dialog.getByRole("searchbox", { name: "ค้นหาภาษา" }).fill("อังกฤษ")
    await dialog.getByRole("button", { name: /^อังกฤษ/ }).first().click()
    await expect(page).toHaveURL(/[?&]track=t\.en(&|$)/)
    await expect(cues(page)).toHaveCount(5, { timeout: 10_000 })
    await expect(page.getByTestId("session-warming")).toHaveCount(0)
    // คำขอที่ถูกยกเลิก + โหลดใหม่หนึ่งครั้ง ไม่ยิงวน
    await page.waitForTimeout(2_000)
    expect(calls.n).toBe(3)
  })

  test("แท็บทรานสคริปต์ก็แสดงกล่องนับถอยหลังเดียวกัน และโหลดให้เองเมื่อครบ", async ({ page }) => {
    const calls = await warmTranslated(page, 2)
    await page.goto(`/v/${THAI}?tab=transcript&track=${TRACK}`)
    await expect(box(page, "ทรานสคริปต์")).toBeVisible()
    await expect(countdown(page, "ทรานสคริปต์")).toHaveText(/รอ \d วินาที/)
    await expect(page.getByRole("list", { name: "บรรทัดในทรานสคริปต์" }).getByRole("listitem").first()).toBeVisible({
      timeout: 10_000,
    })
    expect(calls.n).toBe(2)
  })
})
