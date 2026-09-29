// ล้างโฟลเดอร์ข้อมูลของ e2e ก่อนเปิด backend ทุกครั้ง เพื่อไม่ให้ค่าค้างจากรอบก่อนทำให้ผลเทสเพี้ยน
// รันเป็นส่วนแรกของคำสั่ง webServer (ก่อน backend เริ่ม) ไม่ใช้ globalSetup เพราะ Playwright เปิด
// webServer ก่อน globalSetup ทำให้ backend ถือไฟล์ run/app.lock อยู่แล้ว ลบตอนนั้นจะลบไฟล์ของ server ที่กำลังรัน
import fs from "node:fs"
import os from "node:os"
import path from "node:path"

const target = process.env.YT_TOOLKIT_DATA_ROOT

// เทียบพาธแบบไม่สนตัวพิมพ์บน Windows (ไดรฟ์และโฟลเดอร์ไม่แยกตัวพิมพ์)
const norm = (p) => (process.platform === "win32" ? p.toLowerCase() : p)

// กันพลาด: ลบเฉพาะโฟลเดอร์ชื่อ yt-toolkit-e2e* ที่อยู่ติดใต้โฟลเดอร์ temp ของระบบเท่านั้น
const resolved = target ? path.resolve(target) : null
const safe =
  resolved !== null &&
  path.basename(resolved).startsWith("yt-toolkit-e2e") &&
  norm(path.dirname(resolved)) === norm(path.resolve(os.tmpdir()))
if (!safe) {
  console.error(`[e2e] ไม่ลบ ${target ?? "(ไม่ได้ตั้ง YT_TOOLKIT_DATA_ROOT)"} เพราะไม่ใช่โฟลเดอร์ของ e2e ใต้ temp`)
  process.exit(1)
}

try {
  fs.rmSync(resolved, { recursive: true, force: true })
  console.log(`[e2e] ล้าง ${resolved} แล้ว`)
} catch (error) {
  // บน Windows ไฟล์ที่ถูกล็อกอาจลบไม่ได้ ไม่ต้องล้มทั้งชุดเทส
  console.warn(`[e2e] ลบ ${resolved} ไม่สำเร็จ ใช้ข้อมูลเดิมต่อ:`, error)
}
