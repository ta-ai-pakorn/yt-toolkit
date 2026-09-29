// ล้างโฟลเดอร์ข้อมูลของ e2e ก่อนเปิด backend ทุกครั้ง เพื่อไม่ให้ค่าค้างจากรอบก่อนทำให้ผลเทสเพี้ยน
// รันเป็นส่วนแรกของคำสั่ง webServer (ก่อน backend เริ่ม) ไม่ใช้ globalSetup เพราะ Playwright เปิด
// webServer ก่อน globalSetup ทำให้ backend ถือไฟล์ run/app.lock อยู่แล้ว ลบตอนนั้นจะลบไฟล์ของ server ที่กำลังรัน
import fs from "node:fs"
import path from "node:path"

const target = process.env.YT_TOOLKIT_DATA_ROOT

// กันพลาด: ลบเฉพาะโฟลเดอร์ที่ตั้งชื่อสำหรับ e2e เท่านั้น
if (!target || !path.basename(target).startsWith("yt-toolkit-e2e")) {
  console.error(`[e2e] ไม่ลบ ${target ?? "(ไม่ได้ตั้ง YT_TOOLKIT_DATA_ROOT)"} เพราะไม่ใช่โฟลเดอร์ของ e2e`)
  process.exit(1)
}

try {
  fs.rmSync(target, { recursive: true, force: true })
  console.log(`[e2e] ล้าง ${target} แล้ว`)
} catch (error) {
  // บน Windows ไฟล์ที่ถูกล็อกอาจลบไม่ได้ ไม่ต้องล้มทั้งชุดเทส
  console.warn(`[e2e] ลบ ${target} ไม่สำเร็จ ใช้ข้อมูลเดิมต่อ:`, error)
}
