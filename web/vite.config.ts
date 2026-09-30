import fs from "node:fs"
import path from "node:path"

import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig, type Plugin } from "vite"
import { configDefaults } from "vitest/config"

const RUN_FILE = path.resolve(import.meta.dirname, "../run/app.json")

function readRunInfo(): { port: number; token: string } | null {
  try {
    return JSON.parse(fs.readFileSync(RUN_FILE, "utf8"))
  } catch {
    return null
  }
}

// ตอน dev ใส่ token ของ backend ที่รันด้วย `serve --dev` ลงใน index.html (แทนที่ backend ทำตอน production)
function devToken(): Plugin {
  return {
    name: "yt-dev-token",
    apply: "serve",
    transformIndexHtml(html) {
      const info = readRunInfo()
      return info ? html.replace("</head>", `<meta name="yt-token" content="${info.token}"></head>`) : html
    },
  }
}

export default defineConfig({
  test: {
    // e2e/ เป็นของ Playwright ไม่ใช่ vitest
    exclude: [...configDefaults.exclude, "**/dist/**", "e2e/**"],
    // ปิดคำแนะนำ fsModuleCache ของ vitest (ไม่ใช่คำเตือนจากเทส แต่รกผลรัน)
    experimental: { diagnostics: false },
  },
  plugins: [react(), tailwindcss(), devToken()],
  resolve: {
    alias: { "@": path.resolve(import.meta.dirname, "./src") },
  },
  server: {
    // อ่านพอร์ตครั้งเดียวตอนเริ่ม vite: ต้องเปิด backend ก่อน และรีสตาร์ท vite ถ้าพอร์ต backend เปลี่ยน
    proxy: {
      "/api": { target: `http://127.0.0.1:${readRunInfo()?.port ?? 8787}`, changeOrigin: true },
    },
  },
})
