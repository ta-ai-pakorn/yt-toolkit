/** จำกัดจำนวนงาน async ที่รันพร้อมกัน ที่เหลือเข้าคิวตามลำดับที่ขอ (FIFO) */
export function createLimiter(max: number) {
  let running = 0
  const waiting: (() => void)[] = []

  function release() {
    running -= 1
    waiting.shift()?.()
  }

  return async function limit<T>(task: () => Promise<T>): Promise<T> {
    if (running >= max) await new Promise<void>((resolve) => waiting.push(resolve))
    running += 1
    try {
      return await task()
    } finally {
      release()
    }
  }
}
