import os from "node:os"
import path from "node:path"

import { defineConfig, devices } from "@playwright/test"

// รูปในคู่มือพนักงาน (README) ถ่ายจากแอพโหมดข้อมูลปลอมเท่านั้น: รันด้วยมือ `npm run shots` ไม่รันใน CI
// พอร์ตแยกจากพอร์ต 8787 ของแอพจริงและพอร์ตของ e2e ปกติ (SHOTS_PORT เปลี่ยนได้)
const PORT = Number(process.env.SHOTS_PORT ?? 8911)
const dataRoot = path.join(os.tmpdir(), "yt-toolkit-shots")

export default defineConfig({
  testDir: "e2e-shots",
  timeout: 60_000,
  workers: 1,
  projects: [
    {
      name: "shots",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1280, height: 800 },
        colorScheme: "dark",
        locale: "th-TH",
        baseURL: `http://127.0.0.1:${PORT}`,
      },
    },
  ],
  webServer: {
    // ล้างข้อมูลเก่าก่อนเปิด backend ทุกครั้ง
    command: `node web/e2e-shots/reset-shots-root.mjs && uv run python -m yttoolkit serve --port ${PORT}`,
    cwd: "..",
    url: `http://127.0.0.1:${PORT}/api/ping`,
    reuseExistingServer: false,
    timeout: 60_000,
    // โหมดข้อมูลปลอม: โฟลเดอร์ปลายทางอยู่ใต้โฟลเดอร์ข้อมูลชั่วคราว ไม่แตะ Downloads ของเครื่อง
    env: {
      YT_TOOLKIT_DATA_ROOT: dataRoot,
      YT_TOOLKIT_FFMPEG_PATH_LOOKUP: "0",
      YT_TOOLKIT_FAKE: "1",
    },
  },
})
