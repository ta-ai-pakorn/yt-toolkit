import { cn } from "cn"
import { ChevronDown, Copy } from "lucide-react"
import {
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { fill, th } from "@/i18n/th"
import { formatChapters } from "@/lib/chapters"
import { formatTimecode } from "@/lib/format"
import type { Chapter, VideoInfo } from "@/lib/types"

const t = th.video

// จอแคบ (มือถือ) ปุ่มสูง 44 px ให้นิ้วกดได้ง่าย
const TOUCH = "max-sm:h-11"

/** แสดง chapter กี่ตอนตอนพับอยู่ (เกินนี้มีปุ่ม "ดูทั้งหมด") */
const CHAPTER_PREVIEW = 5

/** เขียนข้อความลงคลิปบอร์ดตามตัวอักษรทุกตัว (ไม่ตัดช่องว่างหรือบรรทัดว่าง) แล้วแจ้งด้วย toast */
async function copyText(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text)
    toast.success(t.copied)
  } catch {
    toast.error(t.copyFailed)
  }
}

/**
 * หัวของแต่ละกล่อง: ชื่อ + ปุ่มเล็ก "คัดลอก" ติดกัน
 * ชื่อปุ่มสำหรับโปรแกรมอ่านหน้าจอบอกด้วยว่าคัดลอกอะไร ("คัดลอกคำอธิบาย" / "คัดลอก chapter") และขึ้นต้นด้วยคำที่ตาเห็น
 */
function BlockHeader({
  id,
  title,
  copyLabel,
  onCopy,
}: {
  id: string
  title: string
  copyLabel: string
  onCopy: () => void
}) {
  return (
    <div className="flex items-center gap-1">
      <h2 id={id} className="text-sm font-medium">
        {title}
      </h2>
      <Button
        variant="ghost"
        size="sm"
        className={TOUCH}
        aria-label={copyLabel}
        onClick={onCopy}
      >
        <Copy aria-hidden />
        {t.copy}
      </Button>
    </div>
  )
}

/** ปุ่ม "ดูทั้งหมด" / "ย่อ" ของกล่อง (aria-expanded + aria-controls ชี้เนื้อหาที่กาง) */
function ExpandButton({
  expanded,
  controls,
  onToggle,
}: {
  expanded: boolean
  controls: string
  onToggle: () => void
}) {
  return (
    <Button
      variant="ghost"
      size="sm"
      className={cn("group/expand -ml-2.5 w-fit", TOUCH)}
      aria-expanded={expanded}
      aria-controls={controls}
      onClick={onToggle}
    >
      {expanded ? t.showLess : t.showAll}
      <ChevronDown
        aria-hidden
        className="transition-transform group-aria-expanded/expand:rotate-180 motion-reduce:transition-none"
      />
    </Button>
  )
}

/**
 * ข้อความถูกตัดที่ 3 บรรทัดอยู่หรือไม่ (วัดใหม่เมื่อกล่องเปลี่ยนขนาด เช่นหมุนจอหรือย่อหน้าต่าง)
 * วัดเฉพาะตอนพับ ตอนกางอยู่ใช้ผลครั้งล่าสุด (ปุ่ม "ย่อ" จึงยังอยู่)
 */
function useClamped(
  box: RefObject<HTMLElement | null>,
  collapsed: boolean,
  text: string
): boolean {
  const [clamped, setClamped] = useState(false)
  useEffect(() => {
    const element = box.current
    if (!element || !collapsed) return
    const check = () =>
      setClamped(element.scrollHeight > element.clientHeight + 1)
    check()
    if (typeof ResizeObserver === "undefined") return
    const observer = new ResizeObserver(check)
    observer.observe(element)
    return () => observer.disconnect()
  }, [box, collapsed, text])
  return clamped
}

/**
 * คำอธิบายคลิป: 3 บรรทัดแรก (คงการขึ้นบรรทัดของต้นฉบับ) + "ดูทั้งหมด" เมื่อยาวกว่านั้น
 * ลิงก์ในคำอธิบายเป็นข้อความธรรมดา ไม่ทำเป็นลิงก์ (ข้อความจากเจ้าของคลิปเชื่อไม่ได้)
 */
function DescriptionBlock({ description }: { description: string }) {
  const headingId = useId()
  const textId = useId()
  const [expanded, setExpanded] = useState(false)
  const textRef = useRef<HTMLParagraphElement>(null)
  const clamped = useClamped(textRef, !expanded, description)

  return (
    <section
      aria-labelledby={headingId}
      className="flex min-w-0 flex-col gap-1"
    >
      <BlockHeader
        id={headingId}
        title={t.descriptionTitle}
        copyLabel={t.copyDescription}
        onCopy={() => void copyText(description)}
      />
      <p
        id={textId}
        ref={textRef}
        className={cn(
          "text-sm leading-relaxed [overflow-wrap:anywhere] whitespace-pre-line text-muted-foreground",
          !expanded && "line-clamp-3"
        )}
      >
        {description}
      </p>
      {(clamped || expanded) && (
        <ExpandButton
          expanded={expanded}
          controls={textId}
          onToggle={() => setExpanded((open) => !open)}
        />
      )}
    </section>
  )
}

/** รายการ chapter: บรรทัดละ "HH:MM:SS ชื่อตอน" เรียงตามเวลา แสดง 5 ตอนแรก + "ดูทั้งหมด" */
function ChapterBlock({ chapters }: { chapters: Chapter[] }) {
  const headingId = useId()
  const listId = useId()
  const [expanded, setExpanded] = useState(false)
  const sorted = [...chapters].sort((a, b) => a.startS - b.startS)
  const shown = expanded ? sorted : sorted.slice(0, CHAPTER_PREVIEW)

  return (
    <section
      aria-labelledby={headingId}
      className="flex min-w-0 flex-col gap-1"
    >
      <BlockHeader
        id={headingId}
        title={fill(t.chaptersTitle, { n: chapters.length })}
        copyLabel={t.copyChapters}
        onCopy={() => void copyText(formatChapters(chapters))}
      />
      <ol id={listId} className="flex flex-col gap-0.5 text-sm leading-relaxed">
        {shown.map((chapter, index) => (
          <li key={index} className="flex gap-3">
            <span className="shrink-0 font-mono text-muted-foreground tabular-nums">
              {formatTimecode(chapter.startS * 1000)}
            </span>
            <span className="min-w-0 [overflow-wrap:anywhere]">
              {chapter.title}
            </span>
          </li>
        ))}
      </ol>
      {sorted.length > CHAPTER_PREVIEW && (
        <ExpandButton
          expanded={expanded}
          controls={listId}
          onToggle={() => setExpanded((open) => !open)}
        />
      )}
    </section>
  )
}

/**
 * คำอธิบายและ chapter ใต้ข้อมูลคลิป เห็นก่อนว่าจะคัดลอกอะไร (เดิมเป็นปุ่มคัดลอกเปล่า ๆ ที่มองไม่เห็นเนื้อหา)
 * ไม่มีคำอธิบาย/ไม่มี chapter = ไม่แสดงกล่องนั้น · มีทั้งคู่บนจอกว้าง = วางคู่กัน 2 คอลัมน์ แถบแท็บจะได้ไม่ถูกดันลงไปไกล
 * ("คัดลอกเครดิต" มากับการโหลดไฟล์ในเวอร์ชันถัดไป)
 */
export function ClipDetails({ video }: { video: VideoInfo }) {
  const description = video.description ?? ""
  const hasDescription = description.trim() !== ""
  const hasChapters = video.chapters.length > 0
  if (!hasDescription && !hasChapters) return null

  const blocks: ReactNode[] = []
  if (hasDescription)
    blocks.push(
      <DescriptionBlock key="description" description={description} />
    )
  if (hasChapters)
    blocks.push(<ChapterBlock key="chapters" chapters={video.chapters} />)
  return (
    <div
      className={cn(
        "grid gap-x-6 gap-y-3 pt-1",
        blocks.length === 2 && "lg:grid-cols-2"
      )}
    >
      {blocks}
    </div>
  )
}
