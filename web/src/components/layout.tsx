import { Settings } from "lucide-react"
import { Link, NavLink, Outlet } from "react-router"

import { Button } from "@/components/ui/button"
import { Toaster } from "@/components/ui/sonner"
import { th } from "@/i18n/th"

export function Layout() {
  return (
    <div className="min-h-svh">
      <header className="mx-auto flex max-w-[960px] items-center justify-between px-4 py-3">
        <Link to="/" className="flex items-center gap-2 font-medium" aria-label={th.nav.home}>
          <img src="/favicon.svg" alt="" className="size-6" />
          {th.app.name}
        </Link>
        <nav>
          <Button variant="ghost" size="sm" nativeButton={false} render={<NavLink to="/settings/health" />}>
            <Settings aria-hidden />
            {th.nav.settings}
          </Button>
        </nav>
      </header>
      <main className="mx-auto max-w-[960px] px-4 pb-16">
        <Outlet />
      </main>
      <Toaster position="bottom-right" />
    </div>
  )
}
