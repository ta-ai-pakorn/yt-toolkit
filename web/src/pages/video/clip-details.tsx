import { useQuery } from "@tanstack/react-query"
import { cn } from "cn"
import { ChevronDown, Copy, ThumbsUp } from "lucide-react"
import {
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { fill, th } from "@/i18n/th"
import { formatChapters } from "@/lib/chapters"
import {
  formatCompact,
  formatCount,
  formatTags,
  formatTimecode,
} from "@/lib/format"
import type { Chapter, PinnedComment, VideoInfo } from "@/lib/types"

import { LoadError } from "./load-error"
import { pinnedCommentQuery } from "./queries"
import { Stat } from "./stats"

const t = th.video

// จอแคบ (มือถือ) ปุ่มสูง 44 px ให้นิ้วกดได้ง่าย
const TOUCH = "max-sm:h-11"

/** แสดง chapter กี่ตอนตอนพับอยู่ (เกินนี้มีปุ่ม "ดูทั้งหมด") */
const CHAPTER_PREVIEW = 5

/** จอแคบกว่า sm ของ Tailwind (640 px): chapter เริ่มแบบพับ แถบแท็บจะได้ไม่ถูกดันลงไปนอกจอ */
const NARROW = "(max-width: 639.98px)"

const isNarrow = () =>
  typeof window !== "undefined" &&
  typeof window.matchMedia === "function" &&
  window.matchMedia(NARROW).matches

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
 * ปุ่มเล็ก "คัดลอก" ข้างชื่อกล่อง
 * ชื่อปุ่มสำหรับโปรแกรมอ่านหน้าจอบอกด้วยว่าคัดลอกอะไร ("คัดลอกคำอธิบาย" / "คัดลอก chapter") และขึ้นต้นด้วยคำที่ตาเห็น
 */
function CopyButton({ label, onCopy }: { label: string; onCopy: () => void }) {
  return (
    <Button
      variant="ghost"
      size="sm"
      className={TOUCH}
      aria-label={label}
      onClick={onCopy}
    >
      <Copy aria-hidden />
      {t.copy}
    </Button>
  )
}

/** หัวของกล่องที่กางไม่ได้ (คำอธิบาย): ชื่อ + ปุ่มคัดลอก */
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
      <CopyButton label={copyLabel} onCopy={onCopy} />
    </div>
  )
}

/**
 * หัวของกล่องที่พับได้ (chapter, แท็ก, คอมเมนต์ปักหมุด): ทั้งชื่อเป็นปุ่มกาง/พับในหัวข้อ (แบบ accordion)
 * ลูกศรหมุนตามสถานะ · aria-expanded + aria-controls ชี้เนื้อหา (เนื้อหาอยู่ในหน้าเสมอ แค่ซ่อนตอนพับ)
 */
function ToggleHeading({
  id,
  title,
  expanded,
  controls,
  onToggle,
}: {
  id: string
  title: string
  expanded: boolean
  controls: string
  onToggle: () => void
}) {
  return (
    <h2 id={id} className="min-w-0 text-sm font-medium">
      <Button
        variant="ghost"
        size="sm"
        className={cn(
          "group/toggle -ml-2.5 h-auto min-h-7 text-left font-medium whitespace-normal aria-expanded:not-hover:bg-transparent",
          TOUCH
        )}
        aria-expanded={expanded}
        aria-controls={controls}
        onClick={onToggle}
      >
        {title}
        <ChevronDown
          aria-hidden
          className="transition-transform group-aria-expanded/toggle:rotate-180 motion-reduce:transition-none"
        />
      </Button>
    </h2>
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

/**
 * รายการ chapter: บรรทัดละ "HH:MM:SS ชื่อตอน" เรียงตามเวลา แสดง 5 ตอนแรก + "ดูทั้งหมด"
 * ทั้งกล่องพับได้จากหัวข้อ: จอแคบเริ่มแบบพับ (เห็นแค่หัวข้อกับปุ่มคัดลอก) จอกว้างเริ่มแบบกาง
 * ปุ่มคัดลอกได้ครบทุกตอนเสมอ ไม่ว่ากล่องพับอยู่หรือไม่
 */
function ChapterBlock({ chapters }: { chapters: Chapter[] }) {
  const headingId = useId()
  const bodyId = useId()
  const listId = useId()
  const [open, setOpen] = useState(() => !isNarrow())
  const [expanded, setExpanded] = useState(false)
  const sorted = [...chapters].sort((a, b) => a.startS - b.startS)
  const shown = expanded ? sorted : sorted.slice(0, CHAPTER_PREVIEW)

  return (
    <section
      aria-labelledby={headingId}
      className="flex min-w-0 flex-col gap-1"
    >
      <div className="flex items-center gap-1">
        <ToggleHeading
          id={headingId}
          title={fill(t.chaptersTitle, { n: chapters.length })}
          expanded={open}
          controls={bodyId}
          onToggle={() => setOpen((value) => !value)}
        />
        <CopyButton
          label={t.copyChapters}
          onCopy={() => void copyText(formatChapters(chapters))}
        />
      </div>
      <div id={bodyId} hidden={!open} className="flex flex-col gap-1">
        <ol
          id={listId}
          className="flex flex-col gap-0.5 text-sm leading-relaxed"
        >
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
            onToggle={() => setExpanded((value) => !value)}
          />
        )}
      </div>
    </section>
  )
}

/** แท็กของคลิป: พับไว้ตั้งแต่แรก (หัวข้อ "แท็ก (N)" + ปุ่มคัดลอก) กางแล้วเห็นแท็กเป็นชิป */
function TagsBlock({ tags }: { tags: string[] }) {
  const headingId = useId()
  const listId = useId()
  const [open, setOpen] = useState(false)

  return (
    <section
      aria-labelledby={headingId}
      className="flex min-w-0 flex-col gap-1"
    >
      <div className="flex items-center gap-1">
        <ToggleHeading
          id={headingId}
          title={fill(t.tagsTitle, { n: tags.length })}
          expanded={open}
          controls={listId}
          onToggle={() => setOpen((value) => !value)}
        />
        <CopyButton
          label={t.copyTags}
          onCopy={() => void copyText(formatTags(tags))}
        />
      </div>
      <ul id={listId} hidden={!open} className="flex flex-wrap gap-1.5 pt-1">
        {tags.map((tag, index) => (
          <li key={index} className="min-w-0">
            <Badge
              variant="secondary"
              className="h-auto max-w-full font-normal whitespace-normal [overflow-wrap:anywhere]"
            >
              {tag}
            </Badge>
          </li>
        ))}
      </ul>
    </section>
  )
}

function PinnedSkeleton() {
  return (
    <div className="flex flex-col gap-2" aria-busy="true">
      <span className="sr-only" role="status">
        {t.pinned.loading}
      </span>
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-2/3" />
    </div>
  )
}

/** ข้อความคอมเมนต์ (ขึ้นบรรทัดตามต้นฉบับ ลิงก์เป็นข้อความธรรมดา) + ยอดถูกใจถ้ามี */
function PinnedText({ comment }: { comment: PinnedComment }) {
  return (
    <div className="flex flex-col gap-1">
      <p className="text-sm leading-relaxed [overflow-wrap:anywhere] whitespace-pre-line">
        {comment.text}
      </p>
      {comment.likes !== undefined && (
        <p className="text-xs text-muted-foreground">
          <Stat
            icon={ThumbsUp}
            text={formatCompact(comment.likes)}
            label={fill(t.stats.likesLabel, { n: formatCount(comment.likes) })}
          />
        </p>
      )}
    </div>
  )
}

/**
 * คอมเมนต์ปักหมุดจากเจ้าของช่อง: พับไว้ตั้งแต่แรก ยังไม่ขอข้อมูลจนกว่าผู้ใช้จะกาง (ขอจากยูทูปช้าและเปลืองโควตา)
 * กางแล้ว: กำลังโหลด = Skeleton · ไม่มีคอมเมนต์ปักหมุด = ข้อความจาง · ผิดพลาด = Alert (ลองใหม่เมื่อช่วยได้)
 * มีคอมเมนต์ = ข้อความ + ปุ่มคัดลอกที่หัวกล่อง
 */
function PinnedBlock({ videoId }: { videoId: string }) {
  const headingId = useId()
  const bodyId = useId()
  const [open, setOpen] = useState(false)
  // ขอข้อมูลเมื่อกางครั้งแรก แล้วเปิดคำขอไว้ตลอด: พับแล้วกางใหม่ไม่ยิงซ้ำ (ผิดพลาดแบบลองใหม่ได้ ให้กด "ลองใหม่" เอง)
  const [requested, setRequested] = useState(false)
  const pinned = useQuery(pinnedCommentQuery(videoId, requested))
  const comment = pinned.data?.comment ?? null

  let body: ReactNode = null
  if (open) {
    if (pinned.isError) {
      body = (
        <LoadError
          title={t.pinned.loadError}
          error={pinned.error}
          onRetry={() => void pinned.refetch()}
        />
      )
    } else if (!pinned.isSuccess) body = <PinnedSkeleton />
    else if (comment) body = <PinnedText comment={comment} />
    else
      body = <p className="text-sm text-muted-foreground">{t.pinned.none}</p>
  }

  return (
    <section
      aria-labelledby={headingId}
      className="flex min-w-0 flex-col gap-1"
    >
      <div className="flex items-center gap-1">
        <ToggleHeading
          id={headingId}
          title={t.pinned.title}
          expanded={open}
          controls={bodyId}
          onToggle={() => {
            setOpen((value) => !value)
            setRequested(true)
          }}
        />
        {open && comment && (
          <CopyButton
            label={t.pinned.copy}
            onCopy={() => void copyText(comment.text)}
          />
        )}
      </div>
      <div id={bodyId} hidden={!open} className="pt-1">
        {body}
      </div>
    </section>
  )
}

/** แท็กที่ใช้ได้ (ตัดช่องว่างหัวท้าย ข้ามแท็กว่าง) */
const cleanTags = (tags: readonly string[] | undefined) =>
  (tags ?? []).map((tag) => tag.trim()).filter((tag) => tag !== "")

/**
 * กล่องข้อมูลใต้หัวคลิป เห็นก่อนว่าจะคัดลอกอะไร: คำอธิบาย · คอมเมนต์ปักหมุด · chapter · แท็ก
 * ไม่มีข้อมูลของกล่องไหน = ไม่แสดงกล่องนั้น · คอมเมนต์ปักหมุดแสดงเมื่อคลิปมีคอมเมนต์ (หรือไม่รู้จำนวน)
 * จอกว้าง: 2 คอลัมน์ (ซ้าย คำอธิบาย + คอมเมนต์ปักหมุด · ขวา chapter + แท็ก) แถบแท็บจะได้ไม่ถูกดันลงไปไกล
 * จอแคบ: เรียงต่อกัน กล่องที่พับได้เหลือแค่หัวข้อบรรทัดเดียว
 */
export function ClipDetails({ video, className }: { video: VideoInfo; className?: string }) {
  const description = video.description ?? ""
  const tags = cleanTags(video.tags)
  const comments = video.stats?.comments
  const showPinned = comments === undefined || comments > 0

  const left: ReactNode[] = []
  if (description.trim() !== "")
    left.push(<DescriptionBlock key="description" description={description} />)
  if (showPinned)
    left.push(<PinnedBlock key="pinned" videoId={video.videoId} />)
  const right: ReactNode[] = []
  if (video.chapters.length > 0)
    right.push(<ChapterBlock key="chapters" chapters={video.chapters} />)
  if (tags.length > 0) right.push(<TagsBlock key="tags" tags={tags} />)

  const columns = [left, right].filter((blocks) => blocks.length > 0)
  if (columns.length === 0) return null
  return (
    <div
      className={cn(
        "grid gap-x-6 gap-y-2 pt-1",
        columns.length === 2 && "lg:grid-cols-2",
        className
      )}
    >
      {columns.map((blocks, index) => (
        <div key={index} className="flex min-w-0 flex-col gap-2">
          {blocks}
        </div>
      ))}
    </div>
  )
}
