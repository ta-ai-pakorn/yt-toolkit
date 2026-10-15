import type { Locator, Page } from "@playwright/test"

import { settleAnimations } from "./axe-settled"

type RGBA = [number, number, number, number]

function parse(color: string): RGBA {
  const m = color.match(/rgba?\(([^)]+)\)/)
  if (!m) throw new Error(`unsupported colour ${color}`)
  const parts = m[1].split(/[\s,/]+/).filter(Boolean).map(Number)
  return [parts[0], parts[1], parts[2], parts[3] ?? 1]
}

function over(top: RGBA, bottom: RGBA): RGBA {
  const a = top[3]
  return [0, 1, 2].map((i) => top[i] * a + bottom[i] * (1 - a)).concat(1) as RGBA
}

function luminance([r, g, b]: RGBA): number {
  const lin = (c: number) => {
    const s = c / 255
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
}

/** WCAG contrast ratio of colour a drawn over opaque colour b (CSS rgb()/rgba(), composited over white when translucent) */
export function contrastRatio(a: string, b: string): number {
  const bottom = over(parse(b), [255, 255, 255, 1])
  const top = over(parse(a), bottom)
  const [l1, l2] = [luminance(top), luminance(bottom)].sort((x, y) => y - x)
  return (l1 + 0.05) / (l2 + 0.05)
}

/** Colours Tailwind v4 emits (oklab, color-mix, ...) reduced to rgba() by painting one canvas pixel */
export async function colorsOf(target: Locator): Promise<{ ring: string; bg: string }> {
  return target.evaluate((el) => {
    const canvas = document.createElement("canvas")
    canvas.width = canvas.height = 1
    const ctx = canvas.getContext("2d", { willReadFrequently: true })!
    const toRgba = (color: string) => {
      ctx.clearRect(0, 0, 1, 1)
      ctx.fillStyle = "#000"
      ctx.fillStyle = color
      ctx.fillRect(0, 0, 1, 1)
      const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data
      return `rgba(${r}, ${g}, ${b}, ${a / 255})`
    }
    const isClear = (c: string) => !c || c === "transparent" || /rgba\(0, 0, 0, 0\)/.test(c) || toRgba(c).endsWith(", 0)")

    const style = getComputedStyle(el)
    // box-shadow layers are "colour x y blur spread" (colour may come first or last); the ring is the last layer with a spread
    const layers = style.boxShadow && style.boxShadow !== "none" ? style.boxShadow.split(/,(?![^(]*\))/).map((s) => s.trim()) : []
    const colourToken = /(?:rgba?|color|oklab|oklch|lab|lch|hsla?)\([^)]*\)|#[0-9a-f]{3,8}\b/i
    const ringLayer = [...layers].reverse().find((l) => {
      const colour = l.match(colourToken)?.[0]
      const spread = parseFloat(l.replace(colourToken, " ").trim().split(/\s+/)[3] ?? "0")
      return colour && !isClear(colour) && spread > 0
    })
    // what is really visible: an outline only when it is drawn (the base rule gives every element an outline-color), else the ring
    const outlineDrawn = style.outlineStyle !== "none" && parseFloat(style.outlineWidth) > 0 && !isClear(style.outlineColor)
    const ring = outlineDrawn ? style.outlineColor : ringLayer?.match(colourToken)?.[0]
    if (!ring) throw new Error("no visible focus indicator (no outline, no box-shadow ring) on " + el.tagName)

    // stack translucent ancestor backgrounds until an opaque one, then flatten them (outermost first)
    const stack: number[][] = []
    for (let node: Element | null = el.parentElement; node; node = node.parentElement) {
      const c = getComputedStyle(node).backgroundColor
      if (isClear(c)) continue
      const [r, g, b, a] = toRgba(c).match(/[\d.]+/g)!.map(Number)
      stack.push([r, g, b, a])
      if (a === 1) break
    }
    let flat = [255, 255, 255]
    for (const [r, g, b, a] of stack.reverse()) {
      flat = [r * a + flat[0] * (1 - a), g * a + flat[1] * (1 - a), b * a + flat[2] * (1 - a)]
    }
    const bg = `rgb(${flat.map(Math.round).join(", ")})`
    return { ring: toRgba(ring), bg }
  })
}

/**
 * Focus the element with the keyboard path (must match :focus-visible), then measure the indicator that is actually drawn:
 * outline if its style is not none and width > 0, else the box-shadow ring, against the opaque surface behind it.
 * Pass `owner` when the ring is drawn on a wrapper instead of the focused element (e.g. InputGroup).
 */
export async function focusRingContrast(page: Page, target: Locator, owner?: Locator): Promise<number> {
  await target.focus()
  if (!(await target.evaluate((el) => el.matches(":focus-visible")))) throw new Error("focus() did not give :focus-visible")
  await settleAnimations(page)
  const { ring, bg } = await colorsOf(owner ?? target)
  return contrastRatio(ring, bg)
}

/** Contrast of a control's text over its own (possibly translucent) fill, flattened onto the surface behind it */
export async function textContrast(target: Locator): Promise<number> {
  const { bg } = await colorsOf(target)
  const { text, fill } = await target.evaluate((el) => {
    const canvas = document.createElement("canvas")
    canvas.width = canvas.height = 1
    const ctx = canvas.getContext("2d", { willReadFrequently: true })!
    const toRgba = (color: string) => {
      ctx.clearRect(0, 0, 1, 1)
      ctx.fillStyle = "#000"
      ctx.fillStyle = color
      ctx.fillRect(0, 0, 1, 1)
      const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data
      return `rgba(${r}, ${g}, ${b}, ${a / 255})`
    }
    const style = getComputedStyle(el)
    return { text: toRgba(style.color), fill: toRgba(style.backgroundColor) }
  })
  const [r, g, b, a] = parse(fill)
  const surface = parse(bg)
  const flat = [r, g, b].map((v, i) => Math.round(v * a + surface[i] * (1 - a)))
  return contrastRatio(text, `rgb(${flat.join(", ")})`)
}
