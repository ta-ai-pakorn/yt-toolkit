import { th } from "@/i18n/th"
import { ApiError } from "@/lib/api"

/** ถอดรหัสค่า filename* ตาม RFC 5987: charset'ภาษา'ข้อความที่เข้ารหัส % · ผิดรูปหรือ charset ไม่รู้จัก = null */
function decodeExtended(raw: string): string | null {
  const value = raw.trim().replace(/^"(.*)"$/, "$1")
  const match = /^([^']*)'[^']*'(.*)$/.exec(value)
  const charset = (match?.[1] || "UTF-8").trim()
  const encoded = match ? (match[2] ?? "") : value
  // % ที่ไม่ตามด้วยเลขฐานสิบหกสองหลักคือรูปแบบที่ผิด
  if (/%(?![0-9A-Fa-f]{2})/.test(encoded)) return null
  const bytes: number[] = []
  const chunks = encoded.split(/(%[0-9A-Fa-f]{2})/)
  for (const chunk of chunks) {
    if (/^%[0-9A-Fa-f]{2}$/.test(chunk)) bytes.push(parseInt(chunk.slice(1), 16))
    else bytes.push(...new TextEncoder().encode(chunk))
  }
  try {
    const name = new TextDecoder(charset, { fatal: true }).decode(new Uint8Array(bytes)).trim()
    return name || null
  } catch {
    // charset ที่เบราว์เซอร์ไม่รู้จัก หรือไบต์ไม่ตรงกับ charset
    return null
  }
}

/**
 * ชื่อไฟล์จากหัว Content-Disposition: ใช้ filename* (ตาม charset ที่ระบุ, RFC 5987) ก่อน
 * ถ้าไม่มีหรือถอดรหัสไม่ได้ใช้ filename · ไม่มีทั้งคู่ = null
 */
export function parseContentDisposition(header: string | null): string | null {
  if (!header) return null
  const extended = /filename\*\s*=\s*("[^"]*"|[^;]*)/i.exec(header)?.[1]
  if (extended) {
    const name = decodeExtended(extended)
    if (name) return name
  }
  const plain = /(?:^|[;\s])filename\s*=\s*("((?:[^"\\]|\\.)*)"|[^;]*)/i.exec(header)
  if (!plain) return null
  const name = (plain[2] !== undefined ? plain[2].replace(/\\(.)/g, "$1") : (plain[1] ?? "")).trim()
  return name || null
}

/** บันทึก blob ลงเครื่องด้วยลิงก์ชั่วคราวที่มี download (ทางเดียวที่ไฟล์ที่ได้จาก fetch ไปถึงโฟลเดอร์ดาวน์โหลดของเบราว์เซอร์) */
function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  // เบราว์เซอร์เริ่มบันทึกทันทีหลังคลิก ปล่อยหน่วยความจำหลังจากนั้นเล็กน้อย
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

type Deps = { fetch?: typeof fetch; save?: (blob: Blob, filename: string) => void }

/**
 * โหลดไฟล์จาก backend ผ่าน fetch แล้วบันทึกลงเครื่อง
 * (`<a download>` ตรง ๆ ใช้ไม่ได้: ถ้า backend ตอบ error จะบันทึก JSON ของ error เป็นไฟล์แทน)
 * ล้มเหลวจะโยน ApiError ที่มีข้อความไทยจาก envelope
 */
export async function downloadFile(url: string, fallbackName: string, deps: Deps = {}): Promise<string> {
  const doFetch = deps.fetch ?? fetch
  let res: Response
  try {
    res = await doFetch(url)
  } catch (error) {
    throw new ApiError(0, "E_OFFLINE", th.errors.offline, String(error), null)
  }
  if (!res.ok) {
    const body: unknown = await res.json().catch(() => null)
    const err = (body as { error?: { code?: string; message?: string; detail?: string | null } } | null)?.error
    throw new ApiError(res.status, err?.code ?? "E_UNKNOWN", err?.message ?? th.errors.downloadFailed, err?.detail ?? null, body)
  }
  const filename = parseContentDisposition(res.headers.get("Content-Disposition")) ?? fallbackName
  let blob: Blob
  try {
    blob = await res.blob()
  } catch (error) {
    throw new ApiError(0, "E_OFFLINE", th.errors.offline, String(error), null)
  }
  ;(deps.save ?? saveBlob)(blob, filename)
  return filename
}
