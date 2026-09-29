import { useEffect, useState } from "react"

/** true เมื่อผ่านไป `ms` มิลลิวินาทีหลังคอมโพเนนต์แสดง: ใช้เลื่อนโครงรอ ไม่ให้วูบตอนโหลดเร็ว */
export function useElapsed(ms: number): boolean {
  const [elapsed, setElapsed] = useState(false)
  useEffect(() => {
    const timer = setTimeout(() => setElapsed(true), ms)
    return () => clearTimeout(timer)
  }, [ms])
  return elapsed
}
