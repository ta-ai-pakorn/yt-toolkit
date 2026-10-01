import { createBotStop, type BotStop } from "./bot-stop"

// เบรก E_BOT_CHECK ผูกกับรายการผลชุดหนึ่ง (listId) ไม่ใช่กับการแสดงผล: ไปหน้าคลิปแล้วกลับมา
// รายการเดิมยังถูกเบรกอยู่ ไม่ยิงคำขอซ้ำ · วิเคราะห์ใหม่ = listId ใหม่ = เบรกใหม่
// อยู่ไฟล์เดียวกันทุกหน้า (W1 และ W3 ใช้เบรกตัวเดียวกันของรายการเดียวกัน)
let currentGate: { listId: string; gate: BotStop } | null = null

export function botStopFor(listId: string): BotStop {
  if (currentGate?.listId !== listId) currentGate = { listId, gate: createBotStop() }
  return currentGate.gate
}
