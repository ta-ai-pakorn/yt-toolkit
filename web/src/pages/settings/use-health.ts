import { useQuery } from "@tanstack/react-query"

import { api } from "@/lib/api"
import type { Health } from "@/lib/types"

export function useHealth() {
  return useQuery({ queryKey: ["health"], queryFn: () => api<Health>("/health") })
}
