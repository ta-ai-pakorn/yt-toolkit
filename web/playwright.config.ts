import os from "node:os"
import path from "node:path"

import { defineConfig, devices } from "@playwright/test"

// E2E_PORT ให้รันหลายชุดพร้อมกันได้ (แต่ละชุดมีพอร์ตและโฟลเดอร์ข้อมูลของตัวเอง)
const PORT = Number(process.env.E2E_PORT ?? 8799)
const dataRoot = path.join(os.tmpdir(), PORT === 8799 ? "yt-toolkit-e2e" : `yt-toolkit-e2e-${PORT}`)

export default defineConfig({
  testDir: "e2e",
  timeout: 30_000,
  use: { baseURL: `http://127.0.0.1:${PORT}` },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    // ล้างข้อมูลเก่าก่อนเปิด backend (ดูเหตุผลใน e2e/reset-data-root.mjs)
    command: `node web/e2e/reset-data-root.mjs && uv run python -m yttoolkit serve --port ${PORT}`,
    cwd: "..",
    url: `http://127.0.0.1:${PORT}/api/ping`,
    reuseExistingServer: false,
    timeout: 60_000,
    // FAKE=1: ข้อมูลคลิปมาจาก tests/fixtures ไม่ต่อยูทูปจริง (health ไม่ใช้ตัวดึงข้อมูล จึงไม่กระทบ)
    env: { YT_TOOLKIT_DATA_ROOT: dataRoot, YT_TOOLKIT_FFMPEG_PATH_LOOKUP: "0", YT_TOOLKIT_FAKE: "1" },
  },
})
