import os from "node:os"
import path from "node:path"

import { defineConfig, devices } from "@playwright/test"

// E2E_PORT ให้รันหลายชุดพร้อมกันได้ (แต่ละชุดมีพอร์ตและโฟลเดอร์ข้อมูลของตัวเอง)
// ใช้สองพอร์ตติดกัน: PORT สำหรับ project chromium, QUEUE_PORT สำหรับ project queue
// ถ้ารันขนานหลายชุด ต้องตั้ง E2E_PORT ห่างกันอย่างน้อย 2
const PORT = Number(process.env.E2E_PORT ?? 8799)
const QUEUE_PORT = PORT + 1
const dataRoot = path.join(os.tmpdir(), PORT === 8799 ? "yt-toolkit-e2e" : `yt-toolkit-e2e-${PORT}`)
const queueDataRoot = path.join(os.tmpdir(), PORT === 8799 ? "yt-toolkit-e2e-queue" : `yt-toolkit-e2e-queue-${PORT}`)

// สองชุดใช้คำสั่งและ env เหมือนกัน ต่างกันที่พอร์ตกับโฟลเดอร์ข้อมูล
function backend(port: number, root: string) {
  return {
    // ล้างข้อมูลเก่าก่อนเปิด backend (ดูเหตุผลใน e2e/reset-data-root.mjs)
    command: `node web/e2e/reset-data-root.mjs && uv run python -m yttoolkit serve --port ${port}`,
    cwd: "..",
    url: `http://127.0.0.1:${port}/api/ping`,
    reuseExistingServer: false,
    timeout: 60_000,
    // FAKE=1: ข้อมูลคลิปมาจาก tests/fixtures ไม่ต่อยูทูปจริง (health ไม่ใช้ตัวดึงข้อมูล จึงไม่กระทบ)
    // ACCOUNT_GRACE_S (M5 รอบ C): ย่น grace 10 นาทีของบัญชีชั่วคราวเหลือ 5 วินาที (backend อ่านเฉพาะโหมดข้อมูลปลอม)
    env: {
      YT_TOOLKIT_DATA_ROOT: root,
      YT_TOOLKIT_FFMPEG_PATH_LOOKUP: "0",
      YT_TOOLKIT_FAKE: "1",
      YT_TOOLKIT_ACCOUNT_GRACE_S: "5",
    },
  }
}

export default defineConfig({
  testDir: "e2e",
  timeout: 30_000,
  // ค่าเริ่มต้นของ Playwright คือครึ่งหนึ่งของจำนวนคอร์ (8 บนเครื่อง 16 คอร์) ทำให้ CPU เต็ม 100% และ RAM 16 GB แทบหมด
  // เทสที่รอหน้าโหลดจึงหลุดเวลาแบบสุ่มทีละตัว (backend ตอบเร็ว ไม่ใช่คอขวด) จำกัดไว้ 4 พอ ส่ง --workers ทับได้
  workers: 4,
  projects: [
    {
      // spec ทั่วไป: ห้ามสร้างงานจริง (ต้อง mock POST /api/jobs) ดู mockEnqueue ใน e2e/queue-helpers.ts
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        baseURL: `http://127.0.0.1:${PORT}`,
        // M5 รอบ B2: spec เดิมกด ▶ แล้วตรวจหัวคลิปแบบปกติ จึงจำค่า "แบบปกติ" ไว้ก่อน
        // theater.spec.ts และ capture.spec.ts ตั้งค่าที่เก็บเอง (test.use storageState)
        storageState: {
          cookies: [],
          origins: [{ origin: `http://127.0.0.1:${PORT}`, localStorage: [{ name: "yt-toolkit:theater", value: "0" }] }],
        },
      },
      testIgnore: /queue-.*\.spec\.ts/,
    },
    {
      // spec ที่สร้างงานจริงในคิว (queue-*.spec.ts) แยก backend เพื่อไม่ให้คิวที่ค้างรบกวน spec อื่น
      name: "queue",
      use: { ...devices["Desktop Chrome"], baseURL: `http://127.0.0.1:${QUEUE_PORT}` },
      testMatch: /queue-.*\.spec\.ts/,
    },
  ],
  webServer: [backend(PORT, dataRoot), backend(QUEUE_PORT, queueDataRoot)],
})
