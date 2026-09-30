import { House, Settings, type LucideIcon } from "lucide-react"
import { Link, Outlet, ScrollRestoration, useLocation } from "react-router"

import { Toaster } from "@/components/ui/sonner"
import { th } from "@/i18n/th"
import { cn } from "cn"

type NavItem = { to: string; label: string; icon: LucideIcon; active: (pathname: string) => boolean }

// เมนูบนหัว = ทางไปหน้าหลักทุกหน้า (ประวัติ W5 มาแทรกระหว่างสองรายการนี้ใน M4)
const NAV: NavItem[] = [
  { to: "/", label: th.nav.home, icon: House, active: (pathname) => pathname === "/" },
  { to: "/settings/health", label: th.nav.settings, icon: Settings, active: (pathname) => pathname.startsWith("/settings") },
]

// พื้นที่กดสูง 44 px · หน้าที่อยู่ = ตัวอักษรเข้ม + ขีดสีอำพันด้านล่าง
const NAV_LINK =
  "relative inline-flex h-11 items-center gap-1.5 rounded-md px-3 text-sm text-muted-foreground transition-colors outline-none hover:bg-muted hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 [&_svg]:size-4"
const NAV_ACTIVE =
  "font-medium text-foreground after:absolute after:inset-x-3 after:bottom-1 after:h-0.5 after:rounded-full after:bg-primary"

export function Layout() {
  const { pathname } = useLocation()
  return (
    <div className="min-h-svh">
      <header className="mx-auto flex max-w-[960px] items-center justify-between gap-2 px-4 py-2">
        <Link
          to="/"
          className="-ml-2 inline-flex h-11 items-center gap-2 rounded-md px-2 font-medium transition-colors outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          <img src="/favicon.svg" alt="" className="size-6" />
          {th.app.name}
        </Link>
        <nav aria-label={th.nav.main}>
          <ul className="flex items-center gap-1">
            {NAV.map(({ to, label, icon: Icon, active }) => {
              const current = active(pathname)
              return (
                <li key={to}>
                  <Link to={to} aria-current={current ? "page" : undefined} className={cn(NAV_LINK, current && NAV_ACTIVE)}>
                    <Icon aria-hidden />
                    {label}
                  </Link>
                </li>
              )
            })}
          </ul>
        </nav>
      </header>
      <main className="mx-auto max-w-[960px] px-4 pb-16">
        <Outlet />
      </main>
      <Toaster position="bottom-right" />
      {/* ย้อนกลับ (ปุ่ม back / "รายการที่วาง") = กลับไปตำแหน่งเลื่อนเดิม · เปิดหน้าใหม่ = เริ่มบนสุด */}
      <ScrollRestoration />
    </div>
  )
}
