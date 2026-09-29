/// <reference types="vitest/config" />
import fs from "node:fs"
import path from "node:path"

import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig, type Plugin } from "vite"

const RUN_FILE = path.resolve(__dirname, "../run/app.json")

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
    exclude: ["**/node_modules/**", "**/dist/**", "e2e/**"],
  },
  plugins: [react(), tailwindcss(), devToken()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    proxy: {
      "/api": { target: `http://127.0.0.1:${readRunInfo()?.port ?? 8787}`, changeOrigin: true },
    },
  },
})
