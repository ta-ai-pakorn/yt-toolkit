export const th = {
  app: { name: "YT Toolkit" },
  common: { loading: "กำลังโหลด", close: "ปิด", retry: "ลองใหม่", backHome: "กลับหน้าแรก" },
  time: {
    justNow: "เมื่อสักครู่",
    minutesAgo: "{n} นาทีก่อน",
    hoursAgo: "{n} ชั่วโมงก่อน",
    yesterday: "เมื่อวาน",
    daysAgo: "{n} วันก่อน",
    weeksAgo: "{n} สัปดาห์ก่อน",
    monthsAgo: "{n} เดือนก่อน",
    yearsAgo: "{n} ปีก่อน",
  },
  nav: { settings: "ตั้งค่า", home: "หน้าแรก" },
  home: {
    title: "วางลิงก์ยูทูป แล้วเลือกสิ่งที่อยากได้",
    subtitle: "วางได้หลายลิงก์ บรรทัดละลิงก์ หรือลิงก์เพลย์ลิสต์",
    pasteHint: "กด {key} ที่ไหนก็ได้",
    placeholder: "https://youtube.com/watch?v=...",
    analyze: "วิเคราะห์",
    resolveFailed: "วิเคราะห์ลิงก์ไม่สำเร็จ",
    results: {
      title: "ผลการวิเคราะห์",
      open: "เปิดดู",
      clips: "{n} คลิป",
      playlistLater: "เลือกคลิปจากเพลย์ลิสต์ได้ในเวอร์ชันถัดไป",
      truncated: "แสดงแค่ {n} คลิปแรก",
      playlistUntitled: "เพลย์ลิสต์ไม่มีชื่อ",
      playlistEmpty: "เพลย์ลิสต์นี้ไม่มีคลิปที่เปิดได้",
      playlistError: "โหลดข้อมูลเพลย์ลิสต์ไม่สำเร็จ",
      playlistLoading: "กำลังโหลดข้อมูลเพลย์ลิสต์",
      wholePlaylist: "ทั้งเพลย์ลิสต์",
      none: "ไม่พบลิงก์ในข้อความที่วาง",
    },
    dialog: {
      title: "ลิงก์นี้อยู่ในเพลย์ลิสต์ จะเอาแค่คลิปนี้ หรือทั้งเพลย์ลิสต์?",
      clipOnly: "คลิปนี้",
      wholePlaylist: "ทั้งเพลย์ลิสต์",
    },
    recent: {
      title: "ล่าสุด",
    },
    usage: "ใช้กับคลิปขององค์กร คลิปที่ได้รับอนุญาต หรือเพื่อการศึกษาภายใน",
  },
  video: {
    loadError: "เปิดข้อมูลคลิปไม่สำเร็จ",
    channel: "ช่อง",
    duration: "ความยาว",
  },
  settings: {
    title: "ตั้งค่า",
    tabs: { health: "ตรวจสุขภาพระบบ", about: "เกี่ยวกับ" },
  },
  health: {
    status: { ok: "พร้อม", warn: "เตือน", error: "ใช้ไม่ได้" },
    rows: {
      ffmpeg: "โปรแกรมแปลงไฟล์ (ffmpeg)",
      ytdlp: "ตัวโหลด (yt-dlp)",
      jsRuntime: "ตัวช่วยของ yt-dlp",
      disk: "พื้นที่ดิสก์",
      output: "โฟลเดอร์ผลลัพธ์",
      network: "การเชื่อมต่อยูทูป",
    },
    reinstallFfmpeg: "โหลด ffmpeg ใหม่",
    installing: "กำลังโหลด ffmpeg อาจใช้เวลา 1-3 นาที",
    installed: "ติดตั้ง ffmpeg แล้ว",
    recheck: "ตรวจอีกครั้ง",
    shutdown: "ปิดโปรแกรม",
    loadError: "โหลดข้อมูลสุขภาพระบบไม่สำเร็จ",
    retry: "ลองใหม่",
  },
  about: {
    version: "เวอร์ชัน",
    commit: "รหัสเวอร์ชันโค้ด",
    usage: "ใช้กับคลิปขององค์กร คลิปที่ได้รับอนุญาต หรือเพื่อการศึกษาภายใน ห้ามนำไฟล์ไปเผยแพร่ซ้ำถ้าไม่มีสิทธิ์",
  },
  shutdown: {
    done: "ปิดโปรแกรมแล้ว",
    hint: "ปิดแท็บนี้ได้เลย ครั้งหน้าเปิดใหม่ได้จาก start.bat",
    pending: "มีงานค้าง {n} งาน ปิดตอนนี้งานจะหยุดกลางคัน",
  },
  errors: {
    unknown: "มีบางอย่างผิดพลาด ถ่ายภาพหน้าจอนี้ส่งให้ผู้ดูแล",
    offline: "เชื่อมต่อโปรแกรมไม่ได้ ถ้าปิดโปรแกรมไปแล้ว เปิดใหม่ด้วย start.bat",
  },
} as const

export function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => String(values[key] ?? `{${key}}`))
}
