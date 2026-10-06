import { th } from "@/i18n/th"
import { fileTooBig } from "@/lib/account"

import type { AccountDialogRequest } from "./account-store"

/**
 * สถานะของ dialog "ใช้บัญชียูทูปชั่วคราว" (spec 1.2): ไฟล์ที่เลือก (อ่านเป็นข้อความแล้ว) · ข้อความ error ใต้ช่อง · กำลังส่ง
 * ส่งไม่ได้จนกว่าจะเลือกไฟล์ที่อ่านได้ · error = dialog ยังเปิดอยู่ (ผู้ใช้เลือกไฟล์ใหม่ได้)
 */
export type DialogState = { fileName: string | null; text: string | null; error: string | null; pending: boolean }

export type DialogAction =
  | { type: "picked"; fileName: string; text: string }
  | { type: "rejected"; fileName: string | null; message: string }
  | { type: "submitting" }
  | { type: "failed"; message: string }
  | { type: "reset" }

export const EMPTY_DIALOG: DialogState = { fileName: null, text: null, error: null, pending: false }

export function dialogReducer(state: DialogState, action: DialogAction): DialogState {
  switch (action.type) {
    case "picked":
      return { fileName: action.fileName, text: action.text, error: null, pending: false }
    case "rejected":
      return { fileName: action.fileName, text: null, error: action.message, pending: false }
    case "submitting":
      return state.text === null ? state : { ...state, error: null, pending: true }
    case "failed":
      return { ...state, error: action.message, pending: false }
    case "reset":
      return EMPTY_DIALOG
  }
}

/** ไฟล์ที่ผู้ใช้เลือก (ส่วนของ File ที่ใช้) */
export type PickedFile = { name: string; size: number; text: () => Promise<string> }

/**
 * ผลของการเลือกไฟล์เป็น action: ไม่มีไฟล์ = reset · ใหญ่เกิน 1 MB หรืออ่านไม่ได้ = ข้อความ "ไฟล์นี้ใช้ไม่ได้" (ข้อความเดียวกัน) · อ่านได้ = picked
 */
export async function pickAction(file: PickedFile | undefined): Promise<DialogAction> {
  if (file === undefined) return { type: "reset" }
  const invalid: DialogAction = { type: "rejected", fileName: file.name, message: th.account.invalid }
  if (fileTooBig(file.size)) return invalid
  try {
    return { type: "picked", fileName: file.name, text: await file.text() }
  } catch {
    return invalid
  }
}

/** ปุ่มนำเข้ากดได้: มีไฟล์ที่อ่านได้ และไม่ได้กำลังส่ง */
export function canImport(state: DialogState): boolean {
  return state.text !== null && !state.pending
}

/** ปุ่มนำเข้า: เปิดจาก error = "นำเข้าแล้วลองใหม่" · จากหน้าตั้งค่า = "นำเข้า" */
export function importLabel(request: AccountDialogRequest | null): string {
  return request?.origin === "error" ? th.account.importRetry : th.account.import
}
