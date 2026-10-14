/**
 * ตัวอย่างชื่อไฟล์ในหน้าเว็บต้องตรงกับชื่อจริงที่ backend ตั้งทุกตัวอักษร (M6 รอบ A spec 2.5, C10)
 *
 * อ่าน tests/fixtures/names/cases.json (ข้อมูลเข้า) และ golden.json (ผลจาก files.plan_names ที่
 * tests/unit/test_names_golden.py สร้าง) แล้วเทียบกับ planNames ตรง ๆ ถ้าไม่ตรงคือฝั่งใดฝั่งหนึ่งผิด ห้ามแก้ golden
 */
import { describe, expect, it } from "vitest"

import { PathTooLongError, planNames, type NameInput } from "./filename"

const files = import.meta.glob("../../../tests/fixtures/names/*.json", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>

type Case = NameInput & { name: string }
type Golden = Record<string, { folder: string; file: string } | { error: string }>

function load<T>(name: string): T {
  const entry = Object.entries(files).find(([path]) => path.endsWith(`/${name}`))
  if (!entry) throw new Error(`missing fixture ${name}`)
  return JSON.parse(entry[1]) as T
}

const cases = load<Case[]>("cases.json")
const golden = load<Golden>("golden.json")

function actual(input: NameInput): { folder: string; file: string } | { error: string } {
  try {
    return planNames(input)
  } catch (error) {
    if (error instanceof PathTooLongError) return { error: error.message }
    throw error
  }
}

describe("planNames ตรงกับ files.plan_names (golden)", () => {
  it("มี golden ครบทุกกรณี และไม่มี golden เกิน", () => {
    expect(Object.keys(golden).sort()).toEqual(cases.map((c) => c.name).sort())
    expect(cases.length).toBeGreaterThanOrEqual(50)
  })

  it.each(cases.map((c) => [c.name, c] as const))("%s", (name, input) => {
    expect(actual(input)).toEqual(golden[name])
  })
})
