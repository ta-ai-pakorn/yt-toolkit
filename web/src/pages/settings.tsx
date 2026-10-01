import { useState } from "react"
import { useNavigate, useParams } from "react-router"

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { th } from "@/i18n/th"

import { ShutdownScreen } from "./shutdown"
import { AboutPanel } from "./settings/about-panel"
import { GeneralPanel } from "./settings/general-panel"
import { HealthPanel } from "./settings/health-panel"

const TABS = ["general", "health", "about"] as const
type Tab = (typeof TABS)[number]

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
          <TabsTrigger value="general">{th.settings.tabs.general}</TabsTrigger>
          <TabsTrigger value="health">{th.settings.tabs.health}</TabsTrigger>
          <TabsTrigger value="about">{th.settings.tabs.about}</TabsTrigger>
        </TabsList>
        <TabsContent value="general" className="pt-4">
          <GeneralPanel />
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
