export function isMac(ua: string = navigator.userAgent): boolean {
  return /Mac OS X|Macintosh/.test(ua)
}

export function pasteShortcut(ua?: string): string {
  return isMac(ua) ? "⌘V" : "Ctrl+V"
}
