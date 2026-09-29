import { useRef } from "react"

import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { th } from "@/i18n/th"
import type { ResolveItem } from "@/lib/types"

type Props = {
  open: boolean
  item: ResolveItem | null
  onOpenChange: (open: boolean) => void
  onClip: (item: ResolveItem) => void
  onPlaylist: (item: ResolveItem) => void
}

// ปุ่มในกล่องนี้เป็น outline ทั้งคู่: ปุ่มสีเหลืองปุ่มเดียวของหน้าคือ "วิเคราะห์"
export function AmbiguousDialog({ open, item, onOpenChange, onClip, onPlaylist }: Props) {
  const clipRef = useRef<HTMLButtonElement>(null)
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent initialFocus={clipRef} className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="leading-relaxed text-balance">{th.home.dialog.title}</DialogTitle>
          {item && <DialogDescription className="font-mono text-xs break-all">{item.input}</DialogDescription>}
        </DialogHeader>
        <DialogFooter>
          <Button ref={clipRef} variant="outline" onClick={() => item && onClip(item)}>
            {th.home.dialog.clipOnly}
          </Button>
          <Button variant="outline" onClick={() => item && onPlaylist(item)}>
            {th.home.dialog.wholePlaylist}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
