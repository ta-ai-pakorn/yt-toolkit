// ล้างโฟลเดอร์ข้อมูลชั่วคราวของชุดถ่ายรูปก่อนเปิด backend ทุกครั้ง ให้ทุกรอบเริ่มจากแอพที่ว่างเปล่า
// ลบเฉพาะ <temp>/yt-toolkit-shots เท่านั้น
import fs from "node:fs"
import os from "node:os"
import path from "node:path"

const target = path.join(os.tmpdir(), "yt-toolkit-shots")
if (process.env.YT_TOOLKIT_DATA_ROOT && path.resolve(process.env.YT_TOOLKIT_DATA_ROOT) !== path.resolve(target)) {
  console.error(`[shots] ไม่ลบ ${process.env.YT_TOOLKIT_DATA_ROOT} เพราะไม่ใช่โฟลเดอร์ของชุดถ่ายรูป`)
  process.exit(1)
}
fs.rmSync(target, { recursive: true, force: true })
console.log(`[shots] ล้าง ${target} แล้ว`)
