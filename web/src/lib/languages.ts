/** ชื่อภาษาเป็นภาษาไทยจากรหัสภาษา (th → ไทย, en-US → อังกฤษ - สหรัฐอเมริกา) รหัสที่ไม่รู้จักคืนรหัสเดิม */
export function languageName(code: string): string {
  try {
    // fallback "none" ทำให้รหัสที่ไม่รู้จักได้ undefined แทนที่จะได้ข้อความเดาเช่น "xx (BOGUS)"
    const names = new Intl.DisplayNames(["th"], { type: "language", fallback: "none" })
    return names.of(code) ?? code
  } catch {
    // รหัสที่รูปแบบผิด (เช่น "x") ทำให้ Intl โยน error
    return code
  }
}
