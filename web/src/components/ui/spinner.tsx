import { cn } from "cn"
import { Loader2Icon } from "lucide-react"

import { th } from "@/i18n/th"

function Spinner({ className, ...props }: React.ComponentProps<"svg">) {
  return (
    <Loader2Icon data-slot="spinner" role="status" aria-label={th.common.loading} className={cn("size-4 animate-spin", className)} {...props} />
  )
}

export { Spinner }
