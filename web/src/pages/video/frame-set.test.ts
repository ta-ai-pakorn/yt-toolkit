import { describe, expect, it } from "vitest"

import { frameSetShown } from "./frame-set"

describe("frameSetShown (spec 2)", () => {
  it("no sharp set: fast, whatever was chosen", () => {
    expect(frameSetShown({ hasFast: true, hasSharp: false, chosen: null })).toBe("fast")
    expect(frameSetShown({ hasFast: true, hasSharp: false, chosen: "sharp" })).toBe("fast")
  })
  it("no fast set (no storyboard): sharp", () => {
    expect(frameSetShown({ hasFast: false, hasSharp: true, chosen: "fast" })).toBe("sharp")
  })
  it("both: sharp by default, the user's choice wins", () => {
    expect(frameSetShown({ hasFast: true, hasSharp: true, chosen: null })).toBe("sharp")
    expect(frameSetShown({ hasFast: true, hasSharp: true, chosen: "fast" })).toBe("fast")
  })
})
