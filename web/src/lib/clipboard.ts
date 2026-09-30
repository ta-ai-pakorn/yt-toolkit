/** ผืนวาดขั้นต่ำที่ใช้แปลงภาพ: วาด bitmap ลงไป แล้วส่งออกเป็น PNG */
type PngCanvas = {
  drawImage(bitmap: ImageBitmap): void
  toPng(): Promise<Blob>
}

type ImageBitmapLike = Pick<ImageBitmap, "width" | "height" | "close">

type PngDeps = {
  fetch?: typeof fetch
  createImageBitmap?: (blob: Blob) => Promise<ImageBitmapLike>
  makeCanvas?: (width: number, height: number) => PngCanvas
}

/** OffscreenCanvas ถ้ามี (ไม่ต้องแตะหน้าเว็บ) ไม่มีก็ใช้ <canvas> ธรรมดา */
function browserCanvas(width: number, height: number): PngCanvas {
  if (typeof OffscreenCanvas !== "undefined") {
    const canvas = new OffscreenCanvas(width, height)
    return {
      drawImage: (bitmap) => canvas.getContext("2d")?.drawImage(bitmap, 0, 0),
      toPng: () => canvas.convertToBlob({ type: "image/png" }),
    }
  }
  const canvas = document.createElement("canvas")
  canvas.width = width
  canvas.height = height
  return {
    drawImage: (bitmap) => canvas.getContext("2d")?.drawImage(bitmap, 0, 0),
    toPng: () =>
      new Promise((resolve, reject) =>
        canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("toBlob failed"))), "image/png"),
      ),
  }
}

/**
 * โหลดภาพ (เช่น ภาพเฟรม JPEG) แล้วแปลงเป็น PNG ขนาดเดิม
 * คลิปบอร์ดของเบราว์เซอร์รับภาพได้แค่ image/png จึงต้องแปลงก่อน
 */
export async function imageToPng(url: string, deps: PngDeps = {}): Promise<Blob> {
  const response = await (deps.fetch ?? fetch)(url)
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  const blob = await response.blob()
  const bitmap = await (deps.createImageBitmap ?? ((source: Blob) => createImageBitmap(source)))(blob)
  try {
    const canvas = (deps.makeCanvas ?? browserCanvas)(bitmap.width, bitmap.height)
    canvas.drawImage(bitmap as ImageBitmap)
    return await canvas.toPng()
  } finally {
    bitmap.close()
  }
}

type CopyDeps = {
  clipboard?: Pick<Clipboard, "write">
  ClipboardItem?: typeof ClipboardItem
  toPng?: (url: string) => Promise<Blob>
}

/**
 * คัดลอกภาพจาก url ลงคลิปบอร์ดเป็น PNG (วางใน LINE / Word / PowerPoint ได้)
 *
 * ส่ง Promise<Blob> ให้ ClipboardItem แล้วเรียก write ทันที: การเขียนจึงยังอยู่ในจังหวะที่ผู้ใช้กด
 * (Safari ไม่ยอมถ้ารอแปลงภาพเสร็จก่อนค่อยเรียก) · เบราว์เซอร์ไม่รองรับหรือเขียนไม่สำเร็จ = โยน error
 */
export function copyImage(url: string, deps: CopyDeps = {}): Promise<void> {
  const clipboard = "clipboard" in deps ? deps.clipboard : globalThis.navigator?.clipboard
  const Item = "ClipboardItem" in deps ? deps.ClipboardItem : globalThis.ClipboardItem
  if (!clipboard?.write || !Item) return Promise.reject(new Error("clipboard image unsupported"))
  const png = (deps.toPng ?? imageToPng)(url)
  // ถ้าแปลงไม่สำเร็จ write จะล้มเองอยู่แล้ว: กันไม่ให้ Promise ตัวนี้กลายเป็น unhandled rejection อีกทาง
  png.catch(() => {})
  return clipboard.write([new Item({ "image/png": png })])
}
