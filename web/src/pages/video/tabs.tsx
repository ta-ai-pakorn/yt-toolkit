import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { th } from "@/i18n/th"
import type { VideoInfo } from "@/lib/types"

import { ClipInfoPanel } from "./clip-details"
import { AudioPanel } from "./download/audio-panel"
import { audioPanelHasControls, useDownloadChoices, videoPanelHasControls } from "./download/use-download-state"
import { VideoPanel } from "./download/video-panel"
import { FramesSection } from "./frames"
import { infoSections } from "./info-sections"
import { useWarmingRefetch } from "./session-warming"
import { SubsPanel } from "./subs-panel"
import { TranscriptPanel } from "./transcript-panel"
import { useVideoParams, VIDEO_TABS, type VideoTab } from "./url-state"

const t = th.video.tabs

// ลำดับแท็บบนแถบ (M4 Q8): ภาพเฟรม · วิดีโอ · เสียง · ซับ · ทรานสคริปต์ · ข้อมูลคลิป (เริ่มที่ภาพเฟรมเหมือนเดิม)
const TABS = VIDEO_TABS

const isTab = (value: unknown): value is VideoTab => TABS.some((tab) => tab === value)

// แท็บที่ไม่ได้เลือก: สีตัวอักษรแบบ muted ผ่านเกณฑ์ contrast บนพื้น bg-muted ทั้งธีมสว่างและมืด (สีของแท็บที่เลือกคงเดิม)
// after:hidden = ปิดเส้นใต้ของแบบ line ที่ซ่อนอยู่ (โปร่งใส แต่ยื่นต่ำกว่าแท็บ 5 px จนแถวสูงเกินกล่อง
// Windows จึงขึ้นแถบเลื่อนแนวตั้งที่ปลายแถว) แถบแท็บของเราเป็นแบบพื้นทึบ ไม่ใช้เส้นใต้นี้
const TRIGGER = "h-11 flex-none shrink-0 px-4 text-muted-foreground after:hidden"

// จอแคบแถวแท็บเลื่อนแนวนอนได้ (ลากด้วยนิ้ว หรือกดลูกศรแล้วแท็บที่โฟกัสเลื่อนมาให้เห็นเอง) แต่ไม่แสดงแถบเลื่อน
// และไม่เลื่อนแนวตั้งเลย (overflow-x-auto อย่างเดียวทำให้แนวตั้งเป็น auto ตามไปด้วย)
const LIST =
  "w-full flex-nowrap justify-start overflow-x-auto overflow-y-hidden [scrollbar-width:none] [&::-webkit-scrollbar]:hidden group-data-horizontal/tabs:h-auto"

// แผงของแท็บรับโฟกัสได้ (Base UI ตั้ง tabIndex 0) จึงต้องมีวงโฟกัสให้เห็น แบบเดียวกับ breadcrumb
const PANEL = "rounded-md pt-2 focus-visible:ring-3 focus-visible:ring-ring/50"

/** แท็บข้อมูลคลิปมีปุ่มที่โฟกัสได้แน่นอนเมื่อมีส่วนเครดิต (ปุ่ม "คัดลอกเครดิต", M4 T16): ใช้เงื่อนไขเดียวกับ infoSections */
function panelHasButtons(video: VideoInfo | undefined): boolean {
  return video !== undefined && infoSections(video).credit
}

type Props = {
  videoId: string
  enabled: boolean
  /** ข้อมูลคลิป (ยังโหลดไม่เสร็จ = undefined) ใช้ทำแท็บข้อมูลคลิป และป้ายช่วงที่คนดูซ้ำที่ภาพเฟรม/บรรทัดทรานสคริปต์ */
  video: VideoInfo | undefined
}

/**
 * แถบแท็บของ W2 ใต้หัวคลิป: ภาพเฟรม · วิดีโอ · เสียง · ซับ · ทรานสคริปต์ · ข้อมูลคลิป (แท็บที่เปิดอยู่เก็บใน URL ?tab=…)
 * เปลี่ยนแท็บแบบแทนที่ประวัติ ปุ่ม back จึงกลับหน้าก่อนหน้าในก้าวเดียว และล้างเวลาที่ไฮไลต์ไว้ (at)
 * จอแคบแถวแท็บเลื่อนแนวนอนได้ ไม่ตัดขึ้นบรรทัดใหม่ · แท็บที่ไม่ได้เปิดไม่ถูกเรนเดอร์ (ข้อมูลอยู่ใน cache)
 * ตัวเลือกการโหลดที่ผู้ใช้เลือกกับคลิปนี้เก็บที่นี่ แท็บวิดีโอและเสียงจึงใช้ค่าเดียวกัน (เช่น ภาษาเสียง) แม้สลับแท็บไปมา
 */
export function VideoTabs({ videoId, enabled, video }: Props) {
  const mostReplayed = video?.mostReplayed
  const { tab, update } = useVideoParams()
  // ซับแปลที่รอเซสชัน: นับถอยหลังครั้งเดียวทั้งหน้า ครบแล้วโหลดใหม่ให้เอง แม้อยู่แท็บอื่น
  useWarmingRefetch()
  const [choices, choose] = useDownloadChoices(videoId)

  function onValueChange(value: unknown) {
    if (isTab(value) && value !== tab) update({ tab: value, at: null })
  }

  return (
    <Tabs value={tab} onValueChange={onValueChange}>
      <TabsList
        aria-label={t.label}
        className={LIST}
      >
        {TABS.map((value) => (
          <TabsTrigger key={value} value={value} className={TRIGGER}>
            {t[value]}
          </TabsTrigger>
        ))}
      </TabsList>
      {/* แท็บภาพเฟรมเริ่มด้วยปุ่มโหลดและภาพที่โฟกัสได้อยู่แล้ว: ไม่ให้แผงเป็นจุด Tab เพิ่ม (ลำดับ Tab เหมือน M2) */}
      <TabsContent value="frames" tabIndex={-1} className={PANEL}>
        <FramesSection videoId={videoId} enabled={enabled} mostReplayed={mostReplayed} />
      </TabsContent>
      {/* แท็บวิดีโอ/เสียงที่มีตัวเลือกเริ่มด้วยช่องเลือกที่โฟกัสได้อยู่แล้ว = แผงไม่เป็นจุด Tab เพิ่ม
          ยังโหลดอยู่หรือคลิปไม่มีไฟล์ให้โหลด (ไม่มีปุ่ม) = แผงรับโฟกัสเอง */}
      <TabsContent value="video" tabIndex={videoPanelHasControls(video) ? -1 : undefined} className={PANEL}>
        <VideoPanel video={video} enabled={enabled} choices={choices} choose={choose} />
      </TabsContent>
      <TabsContent value="audio" tabIndex={audioPanelHasControls(video) ? -1 : undefined} className={PANEL}>
        <AudioPanel video={video} choices={choices} choose={choose} />
      </TabsContent>
      <TabsContent value="subs" className={PANEL}>
        <SubsPanel videoId={videoId} enabled={enabled} />
      </TabsContent>
      {/* แท็บทรานสคริปต์เริ่มด้วยช่องค้นหา (หรือปุ่มไปแท็บซับ) ที่โฟกัสได้อยู่แล้ว: แผงไม่เป็นจุด Tab เพิ่ม */}
      <TabsContent value="transcript" tabIndex={-1} className={PANEL}>
        <TranscriptPanel videoId={videoId} enabled={enabled} mostReplayed={mostReplayed} />
      </TabsContent>
      {/* แท็บข้อมูลคลิป: คอมเมนต์ปักหมุดเริ่มขอข้อมูลเมื่อแท็บนี้ถูกเปิดครั้งแรก (แผงถูกสร้างตอนนั้น)
          ข้อมูลคลิปมาแล้ว = มีปุ่มคัดลอกเครดิตเสมอ แผงไม่เป็นจุด Tab เพิ่ม · ยังโหลดอยู่ = แผงรับโฟกัสเอง */}
      <TabsContent value="info" tabIndex={panelHasButtons(video) ? -1 : undefined} className={PANEL}>
        <ClipInfoPanel video={video} />
      </TabsContent>
    </Tabs>
  )
}
