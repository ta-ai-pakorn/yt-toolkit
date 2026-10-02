import {
  closestCenter,
  DndContext,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type Announcements,
  type DragEndEvent,
  type UniqueIdentifier,
} from "@dnd-kit/core"
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable"
import { CSS } from "@dnd-kit/utilities"
import { GripVertical } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { fill, th } from "@/i18n/th"
import type { Job } from "@/lib/types"
import { cn } from "cn"

import { QueuedRow } from "./job-row"
import { jobTitle } from "./job-text"
import { resetQueueDrag, startQueueDrag, useReorder } from "./use-queue"

function SortableRow({ job }: { job: Job }) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({
    id: job.id,
    attributes: { roleDescription: th.queue.dnd.roleDescription },
  })
  const handle = (
    <button
      ref={setActivatorNodeRef}
      type="button"
      {...attributes}
      {...listeners}
      aria-label={fill(th.queue.dragHandle, { title: jobTitle(job) })}
      className="-ml-1 inline-flex size-8 shrink-0 cursor-grab touch-none items-center justify-center rounded-md text-muted-foreground outline-none hover:bg-muted hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 active:cursor-grabbing [&_svg]:size-4"
    >
      <GripVertical aria-hidden />
    </button>
  )
  return (
    <QueuedRow
      ref={setNodeRef}
      job={job}
      handle={handle}
      style={{ transform: CSS.Translate.toString(transform), transition }}
      className={cn(isDragging && "relative z-10 rounded-md shadow-md")}
    />
  )
}

/**
 * งานที่รอคิว เรียงตามลำดับคิว ลากเปลี่ยนลำดับได้ทั้งเมาส์และคีย์บอร์ด (Space ยก · ลูกศรขึ้น/ลง ย้าย · Space วาง · Esc ยกเลิก)
 * โปรแกรมอ่านหน้าจอได้ยินข้อความไทยทุกขั้น · วางแล้วส่งลำดับใหม่ (useReorder เรียงในแคชทันที พลาด = ย้อนกลับ)
 */
export function SortableQueued({ jobs }: { jobs: Job[] }) {
  const reorder = useReorder()
  // ถูกถอดออกกลางการลาก (งานสุดท้ายในคิวเริ่มทำ, ชีตปิด) dnd-kit ไม่เรียก onDragEnd/onDragCancel ให้
  useEffect(() => resetQueueDrag, [])
  // ข้อความประกาศต้องอยู่ในชีต: ชีตเป็น modal ส่วนนอกชีตถูกซ่อนจากโปรแกรมอ่านหน้าจอ
  const [announcer, setAnnouncer] = useState<HTMLDivElement | null>(null)
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )
  const ids = jobs.map((job) => job.id)
  const titleOf = (id: UniqueIdentifier) => {
    const job = jobs.find((j) => j.id === String(id))
    return job ? jobTitle(job) : String(id)
  }
  const placeOf = (id: UniqueIdentifier) => ids.indexOf(String(id)) + 1
  // dnd-kit เรียก onDragOver ทันทีหลังยก (over = แถวตัวเอง) และเมื่อวัดตำแหน่งใหม่ ข้อความ "ยก…ขึ้นแล้ว" จึงถูกทับ
  // ประกาศเฉพาะตอนตำแหน่งเปลี่ยนจริง
  const lastOver = useRef<UniqueIdentifier | null>(null)

  const announcements: Announcements = {
    onDragStart: ({ active }) => {
      lastOver.current = active.id
      return fill(th.queue.dnd.picked, { title: titleOf(active.id) })
    },
    onDragOver: ({ active, over }) => {
      if (!over || over.id === lastOver.current) return undefined
      lastOver.current = over.id
      return fill(th.queue.dnd.moved, { title: titleOf(active.id), n: placeOf(over.id) })
    },
    onDragEnd: ({ active, over }) =>
      over
        ? fill(th.queue.dnd.dropped, { title: titleOf(active.id), n: placeOf(over.id) })
        : fill(th.queue.dnd.cancelled, { title: titleOf(active.id) }),
    onDragCancel: ({ active }) => fill(th.queue.dnd.cancelled, { title: titleOf(active.id) }),
  }

  const onDragEnd = ({ active, over }: DragEndEvent) => {
    resetQueueDrag()
    if (!over || active.id === over.id) return
    const from = ids.indexOf(String(active.id))
    const to = ids.indexOf(String(over.id))
    if (from === -1 || to === -1) return
    void reorder(arrayMove(ids, from, to))
  }

  return (
    <>
      <div ref={setAnnouncer} />
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragStart={startQueueDrag}
        onDragEnd={onDragEnd}
        onDragCancel={resetQueueDrag}
        accessibility={{
          announcements,
          // คำแนะนำวิธีลากอยู่ในข้อความตอนยกแล้ว (dnd.picked) ไม่ใช้คำแนะนำภาษาอังกฤษของ dnd-kit
          screenReaderInstructions: { draggable: "" },
          container: announcer ?? undefined,
        }}
      >
        <SortableContext items={ids} strategy={verticalListSortingStrategy}>
          <ul className="divide-y">
            {jobs.map((job) => (
              <SortableRow key={job.id} job={job} />
            ))}
          </ul>
        </SortableContext>
      </DndContext>
    </>
  )
}
