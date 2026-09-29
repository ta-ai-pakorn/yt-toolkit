import { ImageOff } from "lucide-react"
import { useState } from "react"
import { cn } from "cn"

// ภาพปกโหลดจากยูทูปโดยตรง: ถ้าเน็ตหลุดหรือภาพหาย ให้ขึ้นกรอบเทาแทน ไม่ให้เห็นไอคอนภาพแตก
export function Thumbnail({ src, className }: { src: string; className?: string }) {
  const [failedSrc, setFailedSrc] = useState<string | null>(null)
  const failed = !src || failedSrc === src
  return (
    <div className={cn("aspect-video shrink-0 overflow-hidden rounded-md bg-muted", className)}>
      {failed ? (
        <div className="flex size-full items-center justify-center text-muted-foreground">
          <ImageOff aria-hidden className="size-4" />
        </div>
      ) : (
        <img
          src={src}
          alt=""
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => setFailedSrc(src)}
          className="size-full object-cover"
        />
      )}
    </div>
  )
}
