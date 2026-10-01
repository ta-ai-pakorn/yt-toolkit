import { useQuery, useQueryClient, type Query, type QueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"

import { ApiError } from "@/lib/api"

import { tokensQuery } from "./subs-queries"

/** ประกาศให้โปรแกรมอ่านหน้าจอทุกกี่วินาทีระหว่างนับถอยหลัง (และตอนครบ) ไม่ประกาศทุกวินาทีให้รำคาญ */
export const ANNOUNCE_EVERY_S = 15

/**
 * E_SESSION_WARMING (owner round 3): เซสชันผู้ชมของยูทูปยังอายุไม่ถึง 75 วินาที ซับแปลยังโหลดไม่ได้
 * คืนจำนวนวินาทีที่ต้องรอจาก envelope (`error.retryAfterSeconds`) error อื่นหรือค่าผิดรูปแบบ = null
 */
export function warmingSeconds(error: unknown): number | null {
  if (!(error instanceof ApiError) || error.code !== "E_SESSION_WARMING") return null
  const raw = (error.body as { error?: { retryAfterSeconds?: unknown } } | null)?.error?.retryAfterSeconds
  return typeof raw === "number" && Number.isFinite(raw) && raw >= 0 ? Math.ceil(raw) : 1
}

export function isWarming(error: unknown): boolean {
  return warmingSeconds(error) !== null
}

/** เวลา (ms ของเครื่อง) ที่นับถอยหลังครบ: คิดจากเวลาที่ได้ error มา จึงเท่ากันทุกแท็บที่ใช้ query เดียวกัน */
export function warmingDeadline(error: unknown, errorUpdatedAt: number): number | null {
  const seconds = warmingSeconds(error)
  return seconds === null ? null : errorUpdatedAt + seconds * 1000
}

/**
 * ยังอยู่ระหว่างนับถอยหลังไหม (error เป็น E_SESSION_WARMING และยังไม่ถึง deadline)
 * เลย deadline แล้ว = error ค้าง (เช่น react-query คืนสถานะเดิมหลังยกเลิกคำขอตอนครบเวลาเพราะผู้ใช้เปลี่ยนแทร็กหนี)
 * ให้ถือเป็น error ธรรมดาที่ observer โหลดใหม่เองได้ (I-2)
 */
export function isWarmingPending(error: unknown, errorUpdatedAt: number, now: number = Date.now()): boolean {
  const deadline = warmingDeadline(error, errorUpdatedAt)
  return deadline !== null && now < deadline
}

/** วินาทีที่เหลือ (ปัดขึ้น ไม่ต่ำกว่า 0) */
export function secondsLeft(deadline: number, now: number): number {
  return Math.max(0, Math.ceil((deadline - now) / 1000))
}

/**
 * ตัวจับเวลาของทั้งหน้า W2: query คำของแทร็กไหนได้ E_SESSION_WARMING ครบเวลาแล้วโหลดใหม่ให้เองหนึ่งครั้ง
 * แม้ไม่มีแท็บไหนแสดงแทร็กนั้นอยู่ (ผู้ใช้อยู่แท็บภาพเฟรม) · error ก้อนเดิมโหลดใหม่แค่ครั้งเดียว
 * ได้ E_SESSION_WARMING อีก (เช่นนาฬิกาเครื่องคลาด) = error ก้อนใหม่ นับรอบใหม่ตามเวลาที่ backend บอก
 * คืนฟังก์ชันเลิกดู (ล้างตัวจับเวลาทั้งหมด)
 */
export function watchWarming(client: QueryClient): () => void {
  const cache = client.getQueryCache()
  const timers = new Map<string, { error: unknown; id: ReturnType<typeof setTimeout> }>()

  function schedule(query: Query) {
    if (query.queryKey[0] !== "subtokens") return
    const { error, errorUpdatedAt } = query.state
    const current = timers.get(query.queryHash)
    if (current?.error === error) return
    if (current) clearTimeout(current.id)
    timers.delete(query.queryHash)
    const deadline = warmingDeadline(error, errorUpdatedAt)
    if (deadline === null) return
    const id = setTimeout(() => {
      // ตัวจับเวลานี้ทำงานแล้ว: ลบออกจาก map (map เก็บเฉพาะตัวที่ยังรออยู่) ถ้า error ก้อนเดิมกลับมาอีกโดยไม่มีคำตอบใหม่
      // (react-query ยกเลิกคำขอตอนครบเวลาแล้วคืนสถานะเดิม เพราะผู้ใช้เปลี่ยนแทร็กหนี) schedule จะตั้งใหม่
      // และเพราะเลย deadline แล้วจึงยิงทันที ไม่ค้างที่ "กำลังโหลด" (I-2)
      if (timers.get(query.queryHash)?.id === id) timers.delete(query.queryHash)
      // ยังเป็น error ก้อนเดิม (ไม่มีใครโหลดใหม่ไปก่อน) ถึงจะโหลด และไม่ยกเลิกคำขอที่กำลังวิ่งอยู่
      if (query.state.error === error) {
        // เรียก fetch ของ query ตรง ๆ: refetchQueries ข้าม query ที่มีแต่ observer แบบปิด (ปุ่มโน้ตที่หัวคลิป)
        // ซึ่งเป็นสภาพตอนผู้ใช้อยู่แท็บภาพเฟรม
        query.fetch(undefined, { cancelRefetch: false }).catch(() => undefined)
      }
    }, Math.max(0, deadline - Date.now()))
    timers.set(query.queryHash, { error, id })
  }

  cache.getAll().forEach(schedule)
  const unsubscribe = cache.subscribe((event) => {
    if (event.type === "added" || event.type === "updated") schedule(event.query)
  })
  return () => {
    unsubscribe()
    timers.forEach(({ id }) => clearTimeout(id))
    timers.clear()
  }
}

/** watchWarming ตลอดอายุหน้า W2 (เรียกที่แถบแท็บซึ่งอยู่ตลอด ไม่ว่าเปิดแท็บไหน) */
export function useWarmingRefetch(): void {
  const client = useQueryClient()
  useEffect(() => watchWarming(client), [client])
}

/** วินาทีที่เหลือจนถึง deadline (null = ไม่ได้นับ) อัปเดตทุก 250 ms ให้ตัวเลขลดทีละ 1 ไม่ข้าม */
export function useSecondsLeft(deadline: number | null): number {
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    if (deadline === null) return
    const id = setInterval(() => setNow(Date.now()), 250)
    return () => clearInterval(id)
  }, [deadline])
  return deadline === null ? 0 : secondsLeft(deadline, now)
}

/**
 * ข้อความที่ให้โปรแกรมอ่านหน้าจออ่าน: เปลี่ยนเฉพาะตอนเริ่ม, ทุกครั้งที่ถึงพหุคูณของ 15 วินาที และตอนครบ (0)
 * เช่นเริ่มที่ 70 -> 70, 60, 45, 30, 15, 0 (ระหว่างนั้นคงเลขเดิมไว้ live region จึงไม่ถูกอ่านทุกวินาที)
 */
export function announcedSeconds(left: number, initial: number): number {
  if (left <= 0) return 0
  return Math.min(initial, Math.ceil(left / ANNOUNCE_EVERY_S) * ANNOUNCE_EVERY_S)
}

/**
 * แทร็กนี้กำลังรอเซสชันอยู่ไหม (หัวคลิปใช้ปิดปุ่มโน้ตระหว่างนับถอยหลัง) อ่านจาก cache อย่างเดียว ไม่ยิงคำขอ
 */
export function useTrackWarming(videoId: string, trackId: string | null): boolean {
  const tokens = useQuery({ ...tokensQuery(videoId, trackId), enabled: false })
  return Boolean(trackId) && isWarming(tokens.error)
}
