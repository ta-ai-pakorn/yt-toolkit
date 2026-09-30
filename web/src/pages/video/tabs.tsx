import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { th } from "@/i18n/th"

import { FramesSection } from "./frames"
import { SubsPanel } from "./subs-panel"
import { TranscriptPanel } from "./transcript-panel"
import { useVideoParams, type VideoTab } from "./url-state"

const t = th.video.tabs

// ลำดับแท็บบนแถบ (M4 จะเพิ่มวิดีโอ/เสียงระหว่างภาพเฟรมกับซับ)
const TABS: readonly VideoTab[] = ["frames", "subs", "transcript"]

const isTab = (value: unknown): value is VideoTab => TABS.some((tab) => tab === value)

// แท็บที่ไม่ได้เลือก: สีตัวอักษรแบบ muted ผ่านเกณฑ์ contrast บนพื้น bg-muted ทั้งธีมสว่างและมืด (สีของแท็บที่เลือกคงเดิม)
const TRIGGER = "h-11 flex-none shrink-0 px-4 text-muted-foreground"

// แผงของแท็บรับโฟกัสได้ (Base UI ตั้ง tabIndex 0) จึงต้องมีวงโฟกัสให้เห็น แบบเดียวกับ breadcrumb
const PANEL = "rounded-md pt-2 focus-visible:ring-3 focus-visible:ring-ring/50"

type Props = { videoId: string; enabled: boolean }

/**
 * แถบแท็บของ W2 ใต้หัวคลิป: ภาพเฟรม · ซับ · ทรานสคริปต์ (แท็บที่เปิดอยู่เก็บใน URL ?tab=…)
 * เปลี่ยนแท็บแบบแทนที่ประวัติ ปุ่ม back จึงกลับหน้าก่อนหน้าในก้าวเดียว และล้างเวลาที่ไฮไลต์ไว้ (at)
 * จอแคบแถวแท็บเลื่อนแนวนอนได้ ไม่ตัดขึ้นบรรทัดใหม่ · แท็บที่ไม่ได้เปิดไม่ถูกเรนเดอร์ (ข้อมูลอยู่ใน cache)
 */
export function VideoTabs({ videoId, enabled }: Props) {
  const { tab, update } = useVideoParams()

  function onValueChange(value: unknown) {
    if (isTab(value) && value !== tab) update({ tab: value, at: null })
  }

  return (
    <Tabs value={tab} onValueChange={onValueChange}>
      <TabsList
        aria-label={t.label}
        className="w-full flex-nowrap justify-start overflow-x-auto group-data-horizontal/tabs:h-auto"
      >
        {TABS.map((value) => (
          <TabsTrigger key={value} value={value} className={TRIGGER}>
            {t[value]}
          </TabsTrigger>
        ))}
      </TabsList>
      {/* แท็บภาพเฟรมเริ่มด้วยปุ่มโหลดและภาพที่โฟกัสได้อยู่แล้ว: ไม่ให้แผงเป็นจุด Tab เพิ่ม (ลำดับ Tab เหมือน M2) */}
      <TabsContent value="frames" tabIndex={-1} className={PANEL}>
        <FramesSection videoId={videoId} enabled={enabled} />
      </TabsContent>
      <TabsContent value="subs" className={PANEL}>
        <SubsPanel videoId={videoId} enabled={enabled} />
      </TabsContent>
      <TabsContent value="transcript" className={PANEL}>
        <TranscriptPanel videoId={videoId} enabled={enabled} />
      </TabsContent>
    </Tabs>
  )
}
