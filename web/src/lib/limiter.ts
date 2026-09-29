/** จำกัดจำนวนงาน async ที่รันพร้อมกัน ที่เหลือเข้าคิวตามลำดับที่ขอ (FIFO) */
export function createLimiter(max: number) {
  let running = 0
  const waiting: (() => void)[] = []

  // มีคนรออยู่ = ส่งช่องให้เขาโดยตรง (running ไม่ลด) คำขอใหม่ที่เข้ามาช่วงรอยต่อจึงเห็นว่าเต็มและต่อท้ายคิว
  function release() {
    const next = waiting.shift()
    if (next) next()
    else running -= 1
  }

  return async function limit<T>(task: () => Promise<T>): Promise<T> {
    if (running >= max) await new Promise<void>((resolve) => waiting.push(resolve))
    else running += 1
    try {
      return await task()
    } finally {
      release()
    }
  }
}
