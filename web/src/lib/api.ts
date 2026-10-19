import { th } from "@/i18n/th"

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly detail: string | null
  readonly body: unknown

  constructor(status: number, code: string, message: string, detail: string | null, body: unknown) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.code = code
    this.detail = detail
    this.body = body
  }
}

export function readToken(doc: Document = document): string {
  return doc.querySelector<HTMLMetaElement>('meta[name="yt-token"]')?.content ?? ""
}

type Deps = { fetch?: typeof fetch; token?: string }

export async function api<T>(path: string, init: RequestInit = {}, deps: Deps = {}): Promise<T> {
  const doFetch = deps.fetch ?? fetch
  const method = (init.method ?? "GET").toUpperCase()
  const headers = new Headers(init.headers)
  if (method !== "GET" && method !== "HEAD") {
    headers.set("X-Toolkit-Token", deps.token ?? readToken())
    // ใส่เฉพาะ body ที่เป็นสตริง (JSON) และผู้เรียกยังไม่กำหนดเอง FormData ต้องให้เบราว์เซอร์ใส่ boundary เอง
    if (typeof init.body === "string" && !headers.has("Content-Type")) headers.set("Content-Type", "application/json")
  }
  let res: Response
  try {
    res = await doFetch(`/api${path}`, { ...init, method, headers })
  } catch (error) {
    // fetch ล้มเองเมื่อต่อ backend ไม่ได้ (เช่นปิดโปรแกรมไปแล้ว) ข้อความของเบราว์เซอร์เป็นภาษาอังกฤษ
    throw new ApiError(0, "E_OFFLINE", th.errors.offline, String(error), null)
  }
  // อ่านเนื้อหาไม่ได้ = null (เช่นคำตอบว่าง) ยกเว้นคำขอถูกยกเลิกระหว่างที่เนื้อหายังมาไม่ครบ: ต้องโยนต่อ
  // ไม่อย่างนั้นผู้เรียกได้ null เหมือนสำเร็จ (เช่นชื่อคลิปของ W1 ที่ถูกยกเลิกตอนกด "เปิดดู" เขียน null ลงข้อมูลคลิปของ W2 แล้วหน้าพัง)
  const body: unknown = await res.json().catch((error: unknown) => {
    if (init.signal?.aborted) throw error
    return null
  })
  if (!res.ok) {
    const err = (body as { error?: { code?: string; message?: string; detail?: string | null } } | null)?.error
    throw new ApiError(res.status, err?.code ?? "E_UNKNOWN", err?.message ?? th.errors.unknown, err?.detail ?? null, body)
  }
  return body as T
}
