import { Power } from "lucide-react"

import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import { th } from "@/i18n/th"

export function ShutdownScreen() {
  return (
    <Empty className="pt-24">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <Power aria-hidden />
        </EmptyMedia>
        <EmptyTitle>{th.shutdown.done}</EmptyTitle>
        <EmptyDescription>{th.shutdown.hint}</EmptyDescription>
      </EmptyHeader>
    </Empty>
  )
}
