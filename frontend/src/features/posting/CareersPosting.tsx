import { FileDown, FileText, Share2 } from 'lucide-react'
import { useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { LogoMark } from '@/app/LogoMark'
import { Button } from '@/components/ui/button'
import type { PublicPosting } from '@/features/posting/api'
import { workRows } from '@/features/posting/conditions'
import { StageFlow } from '@/features/posting/StageFlow'
import { PostingPoster } from '@/features/posting/PostingPoster'
import { exportPosterPdf } from '@/features/posting/poster-design'
import { errorMessage } from '@/lib/api/client'
import { dDay, formatDateTime, formatMonthDay } from '@/lib/format'
import { cn } from '@/lib/utils'

/** 채용 페이지 상단. 지원서 화면도 같은 머리글을 쓴다. */
export function CareersHeader({
  companyName,
  postingPath,
}: {
  companyName: string
  postingPath?: string
}) {
  const link = (hash: string) => (postingPath ? `${postingPath}#${hash}` : `#${hash}`)
  return (
    <header className="flex min-h-14 shrink-0 flex-wrap items-center gap-x-8 gap-y-3 border-b px-6 py-3">
      <div className="flex items-center gap-2">
        <LogoMark />
        <span className="font-semibold">{companyName}</span>
        <span className="text-sm text-muted-foreground">Careers</span>
      </div>
      <nav className="flex gap-5 text-sm text-muted-foreground">
        <a href={link('posting')} className="font-semibold text-foreground">
          채용 공고
        </a>
        <a href={link('company')} className="hover:text-foreground">
          회사 소개
        </a>
        <a href={link('benefits')} className="hover:text-foreground">
          복지
        </a>
      </nav>
    </header>
  )
}

// APL-01 자체 채용 페이지. HR이 게시한 공고 그대로, 필수 안내 문구까지 보여 준다
export function CareersPosting({
  posting,
  applyPath,
  narrow,
  posterLogoUrl,
}: {
  posting: PublicPosting
  applyPath?: string
  /** 모바일 미리보기처럼 좁은 화면 */
  narrow?: boolean
  posterLogoUrl?: string
}) {
  const { content } = posting
  const posterRef = useRef<HTMLDivElement>(null)
  const [exporting, setExporting] = useState(false)
  const pdf = async () => {
    const element = posterRef.current?.firstElementChild
    if (!(element instanceof HTMLElement)) return
    setExporting(true)
    try {
      await exportPosterPdf(element, content.title)
      toast.info('인쇄 대상에서 ‘PDF로 저장’을 선택해 주세요.')
    } catch (error) {
      toast.error(errorMessage(error))
    } finally {
      setExporting(false)
    }
  }
  const open = posting.state === 'OPEN'
  const tags = [content.employmentType, content.career, content.location].filter(Boolean)
  const work = workRows(content)
  const category = content.jobCategory.split('›')[0]?.trim()

  const share = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href)
      toast.success('공고 주소를 복사했어요.')
    } catch {
      toast.error('주소를 복사하지 못했어요.')
    }
  }

  return (
    <div
      id="posting"
      className={cn('flex gap-8', narrow ? 'flex-col' : 'flex-col items-start md:flex-row')}
    >
      <article className="min-w-0 flex-1 space-y-6">
        <div className="space-y-3 border-b pb-5">
          <p className="text-xs text-muted-foreground">채용 공고{category && ` › ${category}`}</p>
          <h1 className="text-2xl font-bold">{content.title}</h1>
          <div className="flex flex-wrap gap-1.5">
            {tags.map((tag) => (
              <span key={tag} className="rounded-md bg-muted px-2 py-1 text-xs font-medium">
                {tag}
              </span>
            ))}
            <span className="rounded-md bg-muted px-2 py-1 text-xs font-medium">
              접수 ~{formatMonthDay(posting.closeAt)} ({dDay(posting.closeAt)})
            </span>
          </div>
        </div>
        {posting.poster?.enabled && (
          <div ref={posterRef}>
            <PostingPoster
              posting={posting}
              design={posting.poster}
              careersUrl={
                applyPath
                  ? new URL(`/careers/${posting.postingId}`, window.location.origin).href
                  : undefined
              }
              logoUrl={posterLogoUrl ?? `/api/public/postings/${posting.postingId}/poster/logo`}
            />
          </div>
        )}
        {content.intro && (
          <Block id="company" title="회사 소개">
            <p className="text-sm leading-6 whitespace-pre-wrap">{content.intro}</p>
          </Block>
        )}
        <Lines title="주요 업무" lines={content.duties} />
        <Lines title="자격 요건" lines={content.qualifications} />
        <Lines title="우대 사항" lines={content.preferred} />
        {work.length > 0 && (
          <Block title="근무 조건">
            <dl className="space-y-1.5 text-sm">
              {work.map((row) => (
                <Row key={row.label} label={row.label} value={row.value} wide />
              ))}
            </dl>
          </Block>
        )}
        <Block title="전형 절차">
          <StageFlow stages={posting.stages} showType={false} />
        </Block>
        <Block title="제출 서류">
          <div className="flex flex-wrap gap-2">
            {posting.documents.map((document) => (
              <span
                key={document.type}
                className={cn(
                  'inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs font-medium',
                  document.required ? 'bg-muted/60' : 'bg-background',
                )}
              >
                {document.format === 'PDF' && <FileText className="size-3.5" />}
                {document.label}
                {document.format === 'PDF' && ' PDF'} · {document.required ? '필수' : '선택'}
              </span>
            ))}
          </div>
        </Block>
        <Lines id="benefits" title="복지" lines={content.benefits} />
        <Lines title="유의사항" lines={posting.notices} muted />
        {posting.companyAddress && (
          <Block title="회사 주소">
            <p className="text-sm leading-6">{posting.companyAddress}</p>
          </Block>
        )}
      </article>
      <aside
        className={cn(
          'shrink-0 rounded-xl border p-5',
          narrow ? 'w-full' : 'w-full md:sticky md:top-6 md:w-[260px]',
        )}
      >
        <h2 className="font-semibold">{content.title}</h2>
        <dl className="mt-4 space-y-3 text-sm">
          <Row label="고용 형태" value={content.employmentType} />
          <Row
            label="경력"
            value={[content.career.replace(/^경력 (?=\d)/, ''), content.position]
              .filter(Boolean)
              .join(' · ')}
          />
          {content.headcount && <Row label="채용 인원" value={`${content.headcount}명`} />}
          {content.education && <Row label="학력" value={content.education} />}
          <Row label="근무지" value={content.location} />
          <Row label="접수 마감" value={formatDateTime(posting.closeAt)} />
        </dl>
        <div className="mt-5 space-y-2">
          {open && applyPath ? (
            <Button asChild className="h-10 w-full">
              <Link to={applyPath}>지원하기</Link>
            </Button>
          ) : (
            <Button className="h-10 w-full" disabled>
              {posting.state === 'UPCOMING' ? '접수 전이에요' : open ? '지원하기' : '접수 마감'}
            </Button>
          )}
          <Button variant="outline" className="h-10 w-full" onClick={() => void share()}>
            <Share2 />
            공유하기
          </Button>
          {posting.poster?.enabled && (
            <Button
              variant="outline"
              className="h-10 w-full"
              onClick={() => void pdf()}
              disabled={exporting}
            >
              <FileDown />
              PDF 내보내기
            </Button>
          )}
        </div>
      </aside>
    </div>
  )
}

function Block({ id, title, children }: { id?: string; title: string; children: ReactNode }) {
  return (
    <section id={id} className="space-y-2">
      <h2 className="text-sm font-bold">{title}</h2>
      {children}
    </section>
  )
}

function Lines({
  id,
  title,
  lines,
  muted,
}: {
  id?: string
  title: string
  lines: string[]
  muted?: boolean
}) {
  if (lines.length === 0) return null
  return (
    <Block id={id} title={title}>
      <ul className={cn('space-y-1 text-sm', muted && 'text-muted-foreground')}>
        {lines.map((line) => (
          <li key={line}>· {line}</li>
        ))}
      </ul>
    </Block>
  )
}

/** 이름과 값 한 줄. 근무 조건은 "근무 요일 · 시간"처럼 이름이 길어 이름 칸을 넓힌다(wide) */
function Row({ label, value, wide }: { label: string; value: string; wide?: boolean }) {
  return (
    <div className="flex gap-4">
      <dt className={cn('shrink-0 text-muted-foreground', wide ? 'w-28' : 'w-16')}>{label}</dt>
      <dd className="font-medium">{value || '-'}</dd>
    </div>
  )
}
