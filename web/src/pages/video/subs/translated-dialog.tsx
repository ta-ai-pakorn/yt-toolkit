import { Search, TriangleAlert } from "lucide-react"
import { useState } from "react"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group"
import { ScrollArea } from "@/components/ui/scroll-area"
import { th } from "@/i18n/th"
import { languageName } from "@/lib/languages"
import type { SubtitleTrack } from "@/lib/types"

import { filterTranslated } from "./track-groups"

const t = th.subs

// รายการไม่เกินจำนวนนี้แสดงเต็มโดยไม่ต้องเลื่อน
const SHORT_LIST = 7

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** แทร็กทั้งหมดของคลิป (กล่องนี้เลือกเฉพาะซับแปลอัตโนมัติเอง) */
  tracks: readonly SubtitleTrack[]
  /** แทร็กที่ใช้อยู่ (ถ้าเป็นซับแปล แถวนั้นถูกทำเครื่องหมายไว้) */
  selectedId: string | null
  onChoose: (trackId: string) => void
}

/** เนื้อหาในกล่อง: แยกออกมาเพื่อให้คำค้นเริ่มว่างทุกครั้งที่เปิด (ปิดกล่องแล้วส่วนนี้ถูกถอดออก) */
function TranslatedPicker({ tracks, selectedId, onChoose }: Omit<Props, "open" | "onOpenChange">) {
  const [query, setQuery] = useState("")
  const matches = filterTranslated(tracks, query)

  return (
    <>
      {/* คำเตือนอยู่ก่อนช่องค้นหาและรายการ: ผู้ใช้เห็นก่อนเลือก */}
      <Alert>
        <TriangleAlert aria-hidden />
        <AlertDescription>{t.translatedWarning}</AlertDescription>
      </Alert>
      <InputGroup>
        <InputGroupAddon>
          <Search aria-hidden />
        </InputGroupAddon>
        <InputGroupInput
          type="search"
          aria-label={t.searchLanguage}
          placeholder={t.searchLanguage}
          autoComplete="off"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </InputGroup>
      {matches.length === 0 ? (
        <p role="status" className="py-6 text-center text-sm text-muted-foreground">
          {t.noLanguage}
        </p>
      ) : (
        // รายการยาว (ปกติราว 150 ภาษา) เลื่อนในกล่องสูงคงที่ · รายการสั้นสูงเท่าที่มี
        <ScrollArea className={matches.length > SHORT_LIST ? "h-72 max-h-[50vh]" : undefined}>
          <ul aria-label={t.translatedTitle} className="flex flex-col gap-0.5 pr-3">
            {matches.map((track) => (
              <li key={track.id}>
                <Button
                  variant={track.id === selectedId ? "secondary" : "ghost"}
                  aria-current={track.id === selectedId ? "true" : undefined}
                  className="h-auto min-h-9 w-full justify-between gap-3 py-1.5 text-left font-normal max-sm:min-h-11"
                  onClick={() => onChoose(track.id)}
                >
                  <span>{languageName(track.lang)}</span>
                  <span className="font-mono text-xs text-muted-foreground">{track.lang}</span>
                </Button>
              </li>
            ))}
          </ul>
        </ScrollArea>
      )}
    </>
  )
}

/**
 * กล่อง "ซับแปลอัตโนมัติ": คำเตือนเรื่องคุณภาพ + ช่องค้นหาภาษา + รายการภาษา (ประมาณ 150 ภาษา)
 * เลือกแล้วปิดกล่องและใช้แทร็กนั้นทันที
 */
export function TranslatedDialog({ open, onOpenChange, tracks, selectedId, onChoose }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t.translatedTitle}</DialogTitle>
        </DialogHeader>
        <TranslatedPicker
          tracks={tracks}
          selectedId={selectedId}
          onChoose={(trackId) => {
            onChoose(trackId)
            onOpenChange(false)
          }}
        />
      </DialogContent>
    </Dialog>
  )
}
