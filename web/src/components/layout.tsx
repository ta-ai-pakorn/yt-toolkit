import { History, House, Settings, type LucideIcon } from "lucide-react"
import { Link, Outlet, ScrollRestoration, useLocation, useSearchParams } from "react-router"

import { QueueBar } from "@/components/queue/queue-bar"
import { ShutdownDialog } from "@/components/queue/shutdown-dialog"
import { useServerEvents } from "@/components/queue/use-queue"
import { Toaster } from "@/components/ui/sonner"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { th } from "@/i18n/th"
import { useAppShutdown } from "@/lib/events"
import { useNarrowScreen } from "@/lib/use-narrow-screen"
import { ShutdownScreen } from "@/pages/shutdown"
import { cn } from "cn"

type NavItem = { to: string; label: string; icon: LucideIcon; active: (pathname: string) => boolean }

// เมนูบนหัว = ทางไปหน้าหลักทุกหน้า
const NAV: NavItem[] = [
  { to: "/", label: th.nav.home, icon: House, active: (pathname) => pathname === "/" },
  { to: "/history", label: th.nav.history, icon: History, active: (pathname) => pathname.startsWith("/history") },
  { to: "/settings", label: th.nav.settings, icon: Settings, active: (pathname) => pathname.startsWith("/settings") },
]

// พื้นที่กดสูง 44 px · หน้าที่อยู่ = ตัวอักษรเข้ม + ขีดสีอำพันด้านล่าง
const NAV_LINK =
  "relative inline-flex h-11 items-center gap-1.5 rounded-md px-3 text-sm text-muted-foreground transition-colors outline-none hover:bg-muted hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 [&_svg]:size-4"
const NAV_ACTIVE =
  "font-medium text-foreground after:absolute after:inset-x-3 after:bottom-1 after:h-0.5 after:rounded-full after:bg-primary"

/** ลิงก์ที่ tray เปิดเมื่อสั่งปิดโปรแกรมทั้งที่ยังมีงานค้าง: /?confirmShutdown=1 */
const CONFIRM_SHUTDOWN = "confirmShutdown"

export function Layout() {
  const { pathname } = useLocation()
  const [params, setParams] = useSearchParams()
  const closed = useAppShutdown()
  // จอแคบ (< 640 px): เมนูเหลือแต่ไอคอน ชื่อเมนูขึ้นเป็น tooltip (โปรแกรมอ่านหน้าจออ่านจาก aria-label)
  const narrow = useNarrowScreen()
  useServerEvents()

  const closeConfirm = () =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        next.delete(CONFIRM_SHUTDOWN)
        return next
      },
      { replace: true },
    )

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
              const link = (
                <Link to={to} aria-label={label} aria-current={current ? "page" : undefined} className={cn(NAV_LINK, current && NAV_ACTIVE)}>
                  <Icon aria-hidden />
                  <span className="max-sm:hidden">{label}</span>
                </Link>
              )
              return (
                <li key={to}>
                  {narrow ? (
                    <Tooltip>
                      <TooltipTrigger render={link} />
                      <TooltipContent side="bottom">{label}</TooltipContent>
                    </Tooltip>
                  ) : (
                    link
                  )}
                </li>
              )
            })}
          </ul>
        </nav>
      </header>
      {/* เว้นที่ท้ายหน้าเท่าความสูงแถบคิว เนื้อหาล่างสุดจึงไม่ถูกแถบบัง */}
      <main className="mx-auto max-w-[960px] px-4 pb-[calc(4rem+var(--dock-bottom-offset))]">
        {closed ? <ShutdownScreen /> : <Outlet />}
      </main>
      {!closed && <QueueBar />}
      {!closed && <ShutdownDialog open={params.get(CONFIRM_SHUTDOWN) === "1"} onClose={closeConfirm} />}
      {/* ระยะจากขอบล่างมาจากตัวแปร CSS (index.css): ตัวเล่นลอยอยู่ = toast ขึ้นเหนือตัวเล่น · แถบคิวตั้ง --dock-bottom-offset เท่าความสูงของตัวเอง */}
      <Toaster position="bottom-right" offset={{ bottom: "var(--toast-bottom-offset)" }} mobileOffset={{ bottom: "var(--toast-mobile-bottom-offset)" }} />
      {/* ย้อนกลับ (ปุ่ม back / "รายการที่วาง") = กลับไปตำแหน่งเลื่อนเดิม · เปิดหน้าใหม่ = เริ่มบนสุด */}
      <ScrollRestoration />
    </div>
  )
}
