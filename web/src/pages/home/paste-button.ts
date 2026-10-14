import { isSupportedLink } from "@/lib/paste"

/**
 * ผลของปุ่ม "วาง" (M6 รอบ A spec 1.2, AC-IN-08 / AC-IN-09)
 * - analyze: ลิงก์ที่แอพวิเคราะห์ได้ → แทนข้อความในช่องแล้ววิเคราะห์ทันที (ส่งข้อความเดิมไม่ตัดช่องว่าง)
 * - fill: ข้อความอื่น → เติมลงช่องอย่างเดียว
 * - empty: คลิปบอร์ดว่างหรือมีแต่ช่องว่าง (เช่นคัดลอกรูปภาพ) → ไม่เปลี่ยนอะไร
 * - denied: เบราว์เซอร์ไม่มี readText หรือไม่อนุญาต → คำแนะนำใต้ช่อง (ไม่ใช่ error สีแดง)
 */
export type PasteOutcome =
  | { kind: "analyze"; text: string }
  | { kind: "fill"; text: string }
  | { kind: "empty" }
  | { kind: "denied" }

type ClipboardReader = Pick<Clipboard, "readText">

/**
 * อ่านคลิปบอร์ดเมื่อผู้ใช้กดปุ่มเท่านั้น (ไม่มีที่อื่นในแอพเรียก readText) · ไม่โยน error ทุกกรณี
 * deps.clipboard = ตัวแทนในเทส (ไม่ส่ง = navigator.clipboard ส่ง undefined = ไม่มีคลิปบอร์ด)
 */
export async function readClipboard(deps?: { clipboard?: ClipboardReader | undefined }): Promise<PasteOutcome> {
  const clipboard = deps && "clipboard" in deps ? deps.clipboard : globalThis.navigator?.clipboard
  if (!clipboard || typeof clipboard.readText !== "function") return { kind: "denied" }
  let text: string
  try {
    text = await clipboard.readText()
  } catch {
    // NotAllowedError (ผู้ใช้กดไม่อนุญาต) NotFoundError หรือ readText โยนเองแบบ sync
    return { kind: "denied" }
  }
  if (typeof text !== "string" || text.trim() === "") return { kind: "empty" }
  return isSupportedLink(text) ? { kind: "analyze", text } : { kind: "fill", text }
}
