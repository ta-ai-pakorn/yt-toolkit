import { th } from "@/i18n/th"
import { PathTooLongError, planNames, type FilenameStyle, type NameInput } from "@/lib/filename"

/** รหัสคลิปของชื่อตัวอย่าง (เครื่องที่ยังไม่เคยเปิดคลิป) 11 ตัวเท่ารหัสยูทูป จึงกินความยาวเท่าคลิปจริง */
export const SAMPLE_CLIP_ID = "abcdefghijk"

export type ExampleClip = { title: string; channel: string; videoId: string }

/**
 * ชื่อไฟล์ตัวอย่างของบรรทัด "ตัวอย่าง: …" (M6 รอบ A spec 2.6, AC-OUT-10) คำนวณในหน้าเว็บ ไม่เรียก API
 * ใช้คลิปที่เปิดล่าสุด ไม่มี = ชื่อตัวอย่างภาษาไทย (Pete Q1 = B) · เป็นไฟล์วิดีโอ 1080p เสมอ (PRD: "<ชื่อไฟล์>.mp4")
 * โฟลเดอร์ผลลัพธ์ยาวจนชื่อไม่พอ = คิดเหมือนโฟลเดอร์สั้น (ตัวอย่างต้องอ่านรูปแบบออก ไม่ใช่ชื่อรหัสคลิป)
 */
export function exampleFileName(style: FilenameStyle, clip: ExampleClip | undefined, outputDir: string): string {
  const source = clip ?? { title: th.general.filenameSample, channel: th.general.filenameSampleChannel, videoId: SAMPLE_CLIP_ID }
  const input: Omit<NameInput, "baseLen"> = {
    title: source.title,
    clipId: source.videoId,
    uploader: source.channel,
    style,
    quality: "1080p",
    suffix: "",
    ext: "mp4",
  }
  try {
    return planNames({ ...input, baseLen: outputDir.length }).file
  } catch (error) {
    if (!(error instanceof PathTooLongError)) throw error
    return planNames({ ...input, baseLen: 0 }).file
  }
}
