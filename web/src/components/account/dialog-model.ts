import { th } from "@/i18n/th"

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

/** ปุ่มนำเข้ากดได้: มีไฟล์ที่อ่านได้ และไม่ได้กำลังส่ง */
export function canImport(state: DialogState): boolean {
  return state.text !== null && !state.pending
}

/** ปุ่มนำเข้า: เปิดจาก error = "นำเข้าแล้วลองใหม่" · จากหน้าตั้งค่า = "นำเข้า" */
export function importLabel(request: AccountDialogRequest | null): string {
  return request?.origin === "error" ? th.account.importRetry : th.account.import
}
