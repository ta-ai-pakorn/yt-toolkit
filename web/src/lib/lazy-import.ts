const FLAG = "chunk-reloaded"

type FlagStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">
type Deps = { storage?: FlagStorage; reload?: () => void }

/** error จากการโหลดไฟล์โค้ดของหน้า (ไฟล์เก่าหายหลังอัปเดตโปรแกรม) ต่างจากบั๊กในโค้ดหน้านั้น */
export function isChunkLoadError(error: unknown): boolean {
  return (
    error instanceof Error &&
    /dynamically imported module|Importing a module script failed|error loading dynamically/i.test(
      error.message
    )
  )
}

/**
 * โหลดโค้ดหน้าแบบ lazy: ถ้าพลาด (มักเพราะโปรแกรมเพิ่งอัปเดต แท็บเก่าจึงขอไฟล์ชื่อเก่า) โหลดหน้าใหม่ให้อัตโนมัติหนึ่งครั้ง
 * ธงใน sessionStorage กันวน: พลาดซ้ำหลังโหลดใหม่แล้วจึงโยน error ให้หน้าแจ้งผู้ใช้ · เก็บธงไม่ได้ = ไม่โหลดใหม่เลย
 */
export async function importWithReload<T>(
  factory: () => Promise<T>,
  deps: Deps = {}
): Promise<T> {
  const storage = deps.storage ?? sessionStorage
  const reload = deps.reload ?? (() => location.reload())
  try {
    const module = await factory()
    try {
      storage.removeItem(FLAG)
    } catch {
      // ล้างธงไม่ได้ก็ไม่เป็นไร แค่ครั้งหน้าจะไม่โหลดใหม่ให้อัตโนมัติ
    }
    return module
  } catch (error) {
    if (!claimReload(storage)) throw error
    reload()
    // ค้างไว้จนหน้าถูกแทนที่ ไม่ให้เห็นหน้า error วูบหนึ่ง
    return new Promise<T>(() => {})
  }
}

/** จองสิทธิ์โหลดใหม่หนึ่งครั้ง: คืน false ถ้าเคยโหลดใหม่แล้ว หรือเก็บธงไม่ได้ (กันวนไม่ได้จึงไม่เสี่ยง) */
function claimReload(storage: FlagStorage): boolean {
  try {
    if (storage.getItem(FLAG) !== null) return false
    storage.setItem(FLAG, "1")
    return true
  } catch {
    return false
  }
}
