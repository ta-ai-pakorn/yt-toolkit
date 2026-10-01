import { useQuery } from "@tanstack/react-query"
import { cn } from "cn"
import { Copy, Flame, Play, ThumbsUp } from "lucide-react"
import { useId, type ReactNode } from "react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { fill, th } from "@/i18n/th"
import { formatChapters } from "@/lib/chapters"
import { formatCompact, formatCount, formatTags, formatTimecode } from "@/lib/format"
import type { Chapter, PinnedComment, ReplaySegment, VideoInfo } from "@/lib/types"

import { cleanTags, creditLine, infoSections } from "./info-sections"
import { LoadError } from "./load-error"
import { playerActions } from "./player/player-store"
import { pinnedCommentQuery } from "./queries"
import { Stat } from "./stats"

const t = th.video

// จอแคบ (มือถือ) ปุ่มสูง 44 px ให้นิ้วกดได้ง่าย
const TOUCH = "max-sm:h-11"

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
 * ปุ่มเล็ก "คัดลอก" ข้างหัวข้อ
 * ชื่อปุ่มสำหรับโปรแกรมอ่านหน้าจอบอกด้วยว่าคัดลอกอะไร ("คัดลอกคำอธิบาย" / "คัดลอก chapter") และขึ้นต้นด้วยคำที่ตาเห็น
 */
function CopyButton({ label, onCopy }: { label: string; onCopy: () => void }) {
  return (
    <Button variant="ghost" size="sm" className={TOUCH} aria-label={label} onClick={onCopy}>
      <Copy aria-hidden />
      {t.copy}
    </Button>
  )
}

/**
 * ส่วนหนึ่งของแท็บข้อมูลคลิป: หัวข้อ h2 + ปุ่มคัดลอกของส่วนนั้น (ถ้ามี) + เนื้อหาเต็ม (ไม่มีพับ/กาง)
 * extra = ของที่อยู่ต่อท้ายหัวข้อ เช่นป้าย "เจ้าของช่อง"
 */
function InfoSection({
  title,
  copy,
  extra,
  children,
}: {
  title: string
  copy?: { label: string; text: string }
  extra?: ReactNode
  children: ReactNode
}) {
  const headingId = useId()
  return (
    <section aria-labelledby={headingId} className="flex min-w-0 flex-col gap-2">
      <div className="flex min-h-7 flex-wrap items-center gap-x-2 gap-y-1">
        <h2 id={headingId} className="text-base font-medium">
          {title}
        </h2>
        {extra}
        {copy && <CopyButton label={copy.label} onCopy={() => void copyText(copy.text)} />}
      </div>
      {children}
    </section>
  )
}

/**
 * ปุ่มเวลา (HH:MM:SS) ที่เล่นคลิปจากเวลานั้นในตัวเล่นที่หัวคลิป (M3.5) ชื่อปุ่ม "เล่นจาก HH:MM:SS"
 * อยู่แท็บเดิม ไม่พาไปแท็บภาพเฟรมแล้ว (เวลาใน URL ?at= ไม่เปลี่ยน) · ไม่ต้องรอข้อมูลอะไร จึงไม่มีสถานะกำลังโหลด
 */
function TimeButton({ ms }: { ms: number }) {
  const time = formatTimecode(ms)
  return (
    <Button
      variant="outline"
      size="xs"
      className="font-mono text-foreground tabular-nums max-sm:h-11 max-sm:px-3"
      aria-label={fill(t.info.playFrom, { time })}
      onClick={() => playerActions.playFrom(ms)}
    >
      <Play aria-hidden className="fill-current" />
      {time}
    </Button>
  )
}

/**
 * เครดิต (FR-OUT-7, Q6): บรรทัดที่มาของคลิป + ปุ่ม "คัดลอกเครดิต" ได้ข้อความเดียวกับที่เห็น
 * ปุ่มรองแบบ ghost (ไม่ใช่ปุ่มหลักสีเหลือง) ชื่อปุ่มเห็นเต็ม ๆ ไม่ย่อเป็น "คัดลอก"
 */
function CreditSection({ video, children }: { video: VideoInfo; children?: ReactNode }) {
  const line = creditLine(video)
  const headingId = useId()
  return (
    <section aria-labelledby={headingId} className="flex min-w-0 flex-col gap-2">
      <div className="flex min-h-7 flex-wrap items-center gap-x-2 gap-y-1">
        <h2 id={headingId} className="text-base font-medium">
          {t.info.creditTitle}
        </h2>
        <Button variant="ghost" size="sm" className={TOUCH} onClick={() => void copyText(line)}>
          <Copy aria-hidden />
          {t.info.copyCredit}
        </Button>
      </div>
      <p className="text-sm leading-relaxed [overflow-wrap:anywhere] text-muted-foreground">{line}</p>
      {children}
    </section>
  )
}

/** คำอธิบายคลิปเต็ม ขึ้นบรรทัดตามต้นฉบับ · ลิงก์ในคำอธิบายเป็นข้อความธรรมดา (ข้อความจากเจ้าของคลิปเชื่อไม่ได้) */
function DescriptionSection({ description }: { description: string }) {
  return (
    <InfoSection title={t.descriptionTitle} copy={{ label: t.copyDescription, text: description }}>
      <p className="text-sm leading-relaxed [overflow-wrap:anywhere] whitespace-pre-line text-muted-foreground">
        {description}
      </p>
    </InfoSection>
  )
}

/** รายการ chapter ทุกตอน เรียงตามเวลา: ปุ่มเวลา (เล่นจากต้นตอนนั้น) + ชื่อตอน · คัดลอกได้ครบทุกตอน */
function ChapterSection({ chapters }: { chapters: Chapter[] }) {
  const sorted = [...chapters].sort((a, b) => a.startS - b.startS)
  return (
    <InfoSection
      title={fill(t.chaptersTitle, { n: chapters.length })}
      copy={{ label: t.copyChapters, text: formatChapters(chapters) }}
    >
      <ol className="flex flex-col gap-1 text-sm leading-relaxed">
        {sorted.map((chapter, index) => (
          <li key={index} className="flex items-baseline gap-3">
            <TimeButton ms={chapter.startS * 1000} />
            <span className="min-w-0 [overflow-wrap:anywhere]">{chapter.title}</span>
          </li>
        ))}
      </ol>
    </InfoSection>
  )
}

/** ช่วงละบรรทัด "HH:MM:SS - HH:MM:SS" สำหรับคัดลอก */
const formatSegments = (segments: readonly ReplaySegment[]) =>
  segments.map((segment) => `${formatTimecode(segment.startMs)} - ${formatTimecode(segment.endMs)}`).join("\n")

/**
 * ช่วงที่คนดูซ้ำบ่อย (ไม่เกิน 3 ช่วง): ไอคอนเดียวกับป้ายบนภาพเฟรม + ปุ่มเวลาเริ่มของแต่ละช่วง
 * กดแล้วเล่นคลิปจากเวลาเริ่มของช่วงนั้น (M3.5) · ไม่ขอ storyboard (ไม่ต้องหาภาพเฟรมของช่วงแล้ว)
 */
function ReplayedSection({ segments }: { segments: ReplaySegment[] }) {
  return (
    <InfoSection
      title={t.info.replayedTitle}
      copy={{ label: t.info.copyReplayed, text: formatSegments(segments) }}
      extra={<Flame aria-hidden className="size-4 shrink-0 text-accent-text" />}
    >
      <ul className="flex flex-wrap gap-2">
        {segments.map((segment, index) => (
          <li key={`${segment.startMs}-${index}`}>
            <TimeButton ms={segment.startMs} />
          </li>
        ))}
      </ul>
    </InfoSection>
  )
}

/** แท็กทั้งหมดเป็นชิป + คัดลอกเป็น "แท็ก1, แท็ก2" */
function TagsSection({ tags }: { tags: string[] }) {
  return (
    <InfoSection title={fill(t.tagsTitle, { n: tags.length })} copy={{ label: t.copyTags, text: formatTags(tags) }}>
      <ul className="flex flex-wrap gap-1.5">
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
    </InfoSection>
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
      <p className="text-sm leading-relaxed [overflow-wrap:anywhere] whitespace-pre-line">{comment.text}</p>
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
 * ป้ายบอกว่าใครเขียนคอมเมนต์ที่ปักหมุด: "เจ้าของช่อง" หรือ "ผู้ชม" (ไม่มีชื่อผู้เขียน ตาม PDPA)
 * โปรแกรมอ่านหน้าจอได้ "ผู้เขียน: เจ้าของช่อง" · ไม่มีคีย์ byUploader (backend รุ่นก่อน) = "ผู้ชม" (ไม่รู้ว่าเป็นของเจ้าของช่อง)
 */
function AuthorBadge({ byUploader }: { byUploader: boolean }) {
  const owner = byUploader === true
  return (
    <Badge variant={owner ? "secondary" : "outline"} data-author={owner ? "owner" : "viewer"}>
      <span className="sr-only">{t.pinned.author} </span>
      {owner ? t.pinned.byOwner : t.pinned.byViewer}
    </Badge>
  )
}

/**
 * คอมเมนต์ปักหมุด: ขอข้อมูลเมื่อแท็บข้อมูลคลิปถูกเปิดครั้งแรก (ส่วนนี้ถูกสร้างตอนนั้น) แล้วเก็บไว้ใน cache ตลอดหน้า
 * กำลังโหลด = Skeleton · ไม่มีคอมเมนต์ปักหมุด = ข้อความจาง · ผิดพลาด = Alert (ลองใหม่เมื่อช่วยได้)
 * มีคอมเมนต์ = ป้ายผู้เขียน + ข้อความ + ปุ่มคัดลอกที่หัวข้อ
 */
function PinnedSection({ videoId }: { videoId: string }) {
  const pinned = useQuery(pinnedCommentQuery(videoId, true))
  const comment = pinned.data?.comment ?? null

  let body: ReactNode
  if (pinned.isError) {
    body = <LoadError title={t.pinned.loadError} error={pinned.error} onRetry={() => void pinned.refetch()} />
  } else if (!pinned.isSuccess) body = <PinnedSkeleton />
  else if (comment) body = <PinnedText comment={comment} />
  else body = <p className="text-sm text-muted-foreground">{t.pinned.none}</p>

  return (
    <InfoSection
      title={t.pinned.title}
      extra={comment && <AuthorBadge byUploader={comment.byUploader} />}
      copy={comment ? { label: t.pinned.copy, text: comment.text } : undefined}
    >
      {body}
    </InfoSection>
  )
}

/**
 * แท็บ "ข้อมูลคลิป" (?tab=info): ทุกส่วนแสดงเต็ม ไม่มีพับ/กาง (เปิดแท็บ = เปิดดู) แต่ละส่วนมีหัวข้อและปุ่มคัดลอกของตัวเอง
 * จอกว้าง (lg ขึ้นไป) 2 คอลัมน์: ซ้าย เครดิต → คำอธิบาย · ขวา Chapter → ช่วงที่คนดูซ้ำบ่อย → คอมเมนต์ปักหมุด → แท็ก (owner round 5-6, M4 Q6)
 * จอแคบกว่านั้น คอลัมน์เดียว: เครดิต → คำอธิบาย → Chapter → ช่วงที่คนดูซ้ำบ่อย → คอมเมนต์ปักหมุด → แท็ก
 * ลำดับใน DOM = ลำดับที่อ่านทั้งสองขนาดจอ (คอลัมน์ซ้ายก่อน) ลำดับ Tab จึงตามที่ตาเห็น · ไม่มีข้อมูลอื่นเลย = ข้อความจางบรรทัดเดียวใต้เครดิต
 */
export function ClipInfoPanel({ video }: { video: VideoInfo | undefined }) {
  if (!video) {
    return (
      <div className="flex flex-col gap-2" aria-busy="true">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-2/3" />
      </div>
    )
  }
  const has = infoSections(video)

  const empty = !has.description && !has.chapters && !has.replayed && !has.pinned && !has.tags
  const emptyNote = <p className="py-2 text-sm text-muted-foreground">{t.info.empty}</p>

  // เครดิตอยู่บนสุดของคอลัมน์ซ้าย (เหนือคำอธิบาย) · ไม่มีส่วนอื่นเลย = "คลิปนี้ไม่มีข้อมูลเพิ่มเติม" อยู่ใต้เครดิต
  const left: ReactNode[] = []
  if (has.credit) {
    left.push(
      <CreditSection key="credit" video={video}>
        {empty && emptyNote}
      </CreditSection>,
    )
  }
  if (has.description) left.push(<DescriptionSection key="description" description={video.description ?? ""} />)
  const right: ReactNode[] = []
  // owner round 6: Chapter อยู่คอลัมน์ขวา เหนือช่วงที่คนดูซ้ำบ่อย (คอลัมน์เดียว: คำอธิบาย, Chapter, ดูซ้ำบ่อย, ...)
  if (has.chapters) right.push(<ChapterSection key="chapters" chapters={video.chapters} />)
  if (has.replayed && video.mostReplayed) {
    right.push(<ReplayedSection key="replayed" segments={video.mostReplayed} />)
  }
  if (has.pinned) right.push(<PinnedSection key="pinned" videoId={video.videoId} />)
  if (has.tags) right.push(<TagsSection key="tags" tags={cleanTags(video.tags)} />)

  const columns = [left, right].filter((sections) => sections.length > 0)
  if (columns.length === 0) return emptyNote
  return (
    <div className={cn("grid gap-x-8 gap-y-6", columns.length === 2 && "lg:grid-cols-2")}>
      {columns.map((sections, index) => (
        <div key={index} className="flex min-w-0 flex-col gap-6">
          {sections}
        </div>
      ))}
    </div>
  )
}
