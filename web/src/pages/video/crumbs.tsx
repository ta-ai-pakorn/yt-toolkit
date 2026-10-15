import { Link, useNavigate } from "react-router"

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"
import { Skeleton } from "@/components/ui/skeleton"
import { fill, th } from "@/i18n/th"

// พื้นที่กดสูง 32 px และวงโฟกัสชัด (margin ติดลบให้ตัวอักษรยังตรงแนวเดิม)
const CRUMB =
  "-mx-1.5 inline-flex min-h-8 items-center rounded-md px-1.5 outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring"

type Props = {
  /** ชื่อคลิป · undefined = ยังโหลดอยู่ */
  title: string | undefined
  /** ชื่อสำรองเมื่อโหลดข้อมูลคลิปไม่สำเร็จ */
  fallback: string
  /** มาจากรายการผลของ W1: จำนวนลิงก์ในรายการ · undefined = ไม่ได้มาจากรายการ */
  listCount: number | undefined
  className?: string
}

/**
 * breadcrumb ของ W2: หน้าแรก › (รายการที่วาง (N ลิงก์) ›) ชื่อคลิป
 * "รายการที่วาง" = ย้อนกลับไปหน้าแรกแบบปุ่ม back (รายการ ข้อความ และตำแหน่งเลื่อนอยู่ครบ)
 */
export function VideoCrumbs({ title, fallback, listCount, className }: Props) {
  const navigate = useNavigate()
  return (
    <Breadcrumb className={className}>
      <BreadcrumbList>
        <BreadcrumbItem>
          <BreadcrumbLink className={CRUMB} render={<Link to="/" />}>
            {th.nav.home}
          </BreadcrumbLink>
        </BreadcrumbItem>
        <BreadcrumbSeparator />
        {listCount !== undefined && (
          <>
            <BreadcrumbItem>
              <BreadcrumbLink
                className={CRUMB}
                render={
                  <Link
                    to="/"
                    onClick={(event) => {
                      // หน้านี้เปิดจากรายการ (ประวัติก่อนหน้าคือหน้าแรกที่มีรายการอยู่): ย้อนกลับจึงได้ตำแหน่งเลื่อนเดิมด้วย
                      event.preventDefault()
                      void navigate(-1)
                    }}
                  />
                }
              >
                {fill(th.video.crumbList, { n: listCount })}
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
          </>
        )}
        <BreadcrumbItem className="min-w-0 flex-1">
          {title === undefined && !fallback ? (
            <>
              <span className="sr-only">{th.video.crumbLoading}</span>
              <Skeleton aria-hidden="true" className="h-4 w-48" />
            </>
          ) : (
            <BreadcrumbPage className="block min-h-8 truncate py-1.5" title={title ?? fallback}>
              {title ?? fallback}
            </BreadcrumbPage>
          )}
        </BreadcrumbItem>
      </BreadcrumbList>
    </Breadcrumb>
  )
}
