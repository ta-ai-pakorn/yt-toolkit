// ลิงก์ที่หน้าตาเป็นยูทูปจริง (โดเมนเดียวกับที่ backend รับ) ไม่ใช่แค่มีคำว่า youtube อยู่ในประโยค
const YOUTUBE_LINE = /^[<("'[]?(https?:\/\/)?(www\.|m\.|music\.)?(youtube\.com|youtu\.be|youtube-nocookie\.com)\/\S/i
const BARE_ID = /^[A-Za-z0-9_-]{11}$/

/** ข้อความที่วางนอกช่องกรอก ควรถูกวิเคราะห์ทันทีไหม: มีบรรทัดที่เป็นลิงก์ยูทูป หรือทั้งข้อความคือรหัสคลิป 11 ตัว */
export function looksLikeYoutube(text: string): boolean {
  const trimmed = text.trim()
  if (BARE_ID.test(trimmed)) return true
  return trimmed.split(/\r?\n/).some((line) => YOUTUBE_LINE.test(line.trim()))
}
