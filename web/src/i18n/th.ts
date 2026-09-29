export const th = {
  app: { name: "YT Toolkit" },
  nav: { settings: "ตั้งค่า", home: "หน้าแรก" },
  home: {
    title: "วางลิงก์ยูทูป แล้วเลือกสิ่งที่อยากได้",
    subtitle: "วางได้หลายลิงก์ บรรทัดละลิงก์ หรือลิงก์เพลย์ลิสต์",
    pasteHint: "กด {key} ที่ไหนก็ได้",
    placeholder: "https://youtube.com/watch?v=...",
    analyze: "วิเคราะห์",
    notReady: "ระบบวิเคราะห์ลิงก์จะเปิดใช้ในเวอร์ชันถัดไป (M2)",
    usage: "ใช้กับคลิปขององค์กร คลิปที่ได้รับอนุญาต หรือเพื่อการศึกษาภายใน",
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
    unknown: 'มีบางอย่างผิดพลาด กด "คัดลอก" แล้วส่งให้ผู้ดูแล',
  },
} as const

export function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => String(values[key] ?? `{${key}}`))
}
