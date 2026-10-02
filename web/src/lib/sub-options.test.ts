import { describe, expect, it } from "vitest"

import { clampOptions, isPresetName, LIMITS, PRESET_NAMES, presetOf, PRESETS } from "./sub-options"

describe("presetOf", () => {
  it("รู้จักค่าสำเร็จรูปทั้งสี่แบบ", () => {
    expect(presetOf(PRESETS.short)).toBe("short")
    expect(presetOf(PRESETS.medium)).toBe("medium")
    expect(presetOf(PRESETS.long)).toBe("long")
    expect(presetOf(PRESETS.word)).toBe("word")
  })

  it("ทีละคำ = นับเป็นคำ 1 คำต่อซับ 1 บรรทัด ค่าอื่นเท่ากับสั้น (ตรงกับ core/srt_builder.py)", () => {
    expect(PRESETS.word).toEqual({ maxChars: 15, lines: 1, minMs: 800, maxMs: 3000, mode: "tokens", tokensPerCue: 1 })
    expect(PRESET_NAMES).toEqual(["short", "medium", "long", "word"])
    // ปิด "นับเป็นคำ" จากทีละคำ = ค่าของสั้นพอดี · คำต่อซับ 2 = ปรับเอง
    expect(presetOf({ ...PRESETS.word, mode: "chars" })).toBe("short")
    expect(presetOf({ ...PRESETS.word, tokensPerCue: 2 })).toBeNull()
  })

  it("isPresetName รู้จักเฉพาะชื่อสำเร็จรูป", () => {
    for (const name of PRESET_NAMES) expect(isPresetName(name)).toBe(true)
    for (const value of ["custom", "huge", "", null, undefined, 1]) expect(isPresetName(value)).toBe(false)
  })

  it("ค่าที่แก้แล้วให้ null", () => {
    expect(presetOf({ ...PRESETS.medium, maxChars: 26 })).toBeNull()
    expect(presetOf({ ...PRESETS.medium, mode: "tokens", tokensPerCue: 3 })).toBeNull()
  })
})

describe("clampOptions", () => {
  it("บีบทุกช่องให้อยู่ในช่วง LIMITS", () => {
    const low = clampOptions({ maxChars: 1, lines: 1, minMs: 1, maxMs: 1, mode: "chars" })
    expect(low.maxChars).toBe(LIMITS.maxChars[0])
    expect(low.minMs).toBe(LIMITS.minMs[0])
    expect(low.maxMs).toBeGreaterThan(low.minMs)

    const high = clampOptions({ maxChars: 999, lines: 2, minMs: 99999, maxMs: 99999, mode: "chars" })
    expect(high.maxChars).toBe(LIMITS.maxChars[1])
    expect(high.minMs).toBe(LIMITS.minMs[1])
    expect(high.maxMs).toBe(LIMITS.maxMs[1])
  })

  it("lines นอกช่วงกลายเป็น 1 หรือ 2", () => {
    expect(clampOptions({ ...PRESETS.medium, lines: 9 as unknown as 2 }).lines).toBe(2)
    expect(clampOptions({ ...PRESETS.medium, lines: 0 as unknown as 1 }).lines).toBe(1)
  })

  it("บังคับ minMs < maxMs โดยยก maxMs เป็น minMs + 500", () => {
    const out = clampOptions({ ...PRESETS.medium, minMs: 3000, maxMs: 1000 })
    expect(out.minMs).toBe(3000)
    expect(out.maxMs).toBe(3500)
    expect(clampOptions({ ...PRESETS.medium, minMs: 2000, maxMs: 2000 }).maxMs).toBe(2500)
  })

  it("โหมดตัวอักษรตัด tokensPerCue ทิ้ง โหมดคำเติมค่าเริ่มต้น 3 และบีบให้อยู่ในช่วง", () => {
    expect(clampOptions({ ...PRESETS.medium, tokensPerCue: 5 })).not.toHaveProperty("tokensPerCue")
    expect(clampOptions({ ...PRESETS.medium, mode: "tokens" }).tokensPerCue).toBe(3)
    expect(clampOptions({ ...PRESETS.medium, mode: "tokens", tokensPerCue: 99 }).tokensPerCue).toBe(20)
    expect(clampOptions({ ...PRESETS.medium, mode: "tokens", tokensPerCue: 0 }).tokensPerCue).toBe(1)
  })

  it("ค่าที่ถูกอยู่แล้วไม่เปลี่ยน", () => {
    for (const p of Object.values(PRESETS)) expect(clampOptions(p)).toEqual(p)
  })

  it("ค่าที่ไม่ใช่ตัวเลขไม่ทำให้ได้ NaN", () => {
    const out = clampOptions({ ...PRESETS.medium, maxChars: Number.NaN })
    expect(out.maxChars).toBe(LIMITS.maxChars[0])
  })
})
