import { useState } from "react"
import { useNavigate, useParams } from "react-router"

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { th } from "@/i18n/th"

import { ShutdownScreen } from "./shutdown"
import { AboutPanel } from "./settings/about-panel"
import { AdvancedPanel } from "./settings/advanced-panel"
import { GeneralPanel } from "./settings/general-panel"
import { HealthPanel } from "./settings/health-panel"

const TABS = ["general", "advanced", "health", "about"] as const
type Tab = (typeof TABS)[number]

// แท็บที่ไม่ได้เลือก: สี muted ผ่านเกณฑ์ contrast บนพื้น bg-muted ทั้งธีมสว่างและมืด (ค่าเริ่มต้น text-foreground/60 ได้ 4.32:1
// ในธีมสว่าง ไม่ถึง 4.5:1) แบบเดียวกับแถบแท็บของหน้าคลิป
const TRIGGER = "text-muted-foreground"

export function SettingsPage() {
  const { tab } = useParams()
  const navigate = useNavigate()
  const [closed, setClosed] = useState(false)
  const current: Tab = TABS.includes(tab as Tab) ? (tab as Tab) : "general"

  if (closed) return <ShutdownScreen />

  return (
    <section className="flex flex-col gap-6 pt-6">
      <h1 className="text-2xl font-semibold">{th.settings.title}</h1>
      <Tabs value={current} onValueChange={(value) => navigate(`/settings/${value}`)}>
        <TabsList>
          <TabsTrigger value="general" className={TRIGGER}>{th.settings.tabs.general}</TabsTrigger>
          <TabsTrigger value="advanced" className={TRIGGER}>{th.settings.tabs.advanced}</TabsTrigger>
          <TabsTrigger value="health" className={TRIGGER}>{th.settings.tabs.health}</TabsTrigger>
          <TabsTrigger value="about" className={TRIGGER}>{th.settings.tabs.about}</TabsTrigger>
        </TabsList>
        <TabsContent value="general" className="pt-4">
          <GeneralPanel />
        </TabsContent>
        <TabsContent value="advanced" className="pt-4">
          <AdvancedPanel />
        </TabsContent>
        <TabsContent value="health" className="pt-4">
          <HealthPanel onShutdown={() => setClosed(true)} />
        </TabsContent>
        <TabsContent value="about" className="pt-4">
          <AboutPanel />
        </TabsContent>
      </Tabs>
    </section>
  )
}
