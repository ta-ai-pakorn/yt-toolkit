import { th } from "@/i18n/th"

import { useHealth } from "./health-panel"

export function AboutPanel() {
  const health = useHealth()
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
      <dt className="text-muted-foreground">{th.about.version}</dt>
      <dd className="font-mono">{health.data?.version ?? "…"}</dd>
      <dt className="text-muted-foreground">{th.about.commit}</dt>
      <dd className="font-mono">{health.data?.commit ?? "…"}</dd>
      <dd className="col-span-2 pt-4 text-muted-foreground">{th.about.usage}</dd>
    </dl>
  )
}
