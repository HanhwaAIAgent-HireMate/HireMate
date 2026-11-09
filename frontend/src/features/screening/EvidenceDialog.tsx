import { useEffect, useRef, useState, type ReactNode } from 'react'

import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import type { CandidateDetail } from '@/features/screening/api'
import {
  groupByDocument,
  locate,
  underlineSpans,
  type DocumentType,
  type EvidenceQuote,
} from '@/features/screening/evidence'
import { matchEvidence, normalizedOf } from '@/features/screening/normalized'
import { NormalizedDocumentView } from '@/features/screening/NormalizedDocumentView'
import { OriginalPdfLink } from '@/features/screening/OriginalPdfLink'
import { cn } from '@/lib/utils'

const DOCUMENT_LABELS: Partial<Record<DocumentType, string>> = {
  RESUME: '이력서',
  COVER_LETTER: '자기소개서',
  PORTFOLIO: '포트폴리오',
  CERTIFICATE: '자격증',
}

/**
 * 판정 근거를 원문 문맥과 함께 본다. 근거가 나온 서류를 탭으로 보여 주고, 서류 전체에서 근거 문장에만 밑줄을 친다.
 * 열면 첫 밑줄로 옮겨 가서 관련 프로젝트 · 내용을 앞뒤 문맥과 함께 읽을 수 있다. 판정이 이상해도 담당자가 근거를
 * 직접 확인하게 하려는 것이다. 정제를 마친 서류는 정제 문서(서류 원문)를 표 · 목록 그대로 그리고, 아니면 PDF 본문을 보인다.
 * 정제 문서에서 자리를 찾지 못한 근거는 위에 따로 적어 빠뜨리지 않는다.
 */
export function EvidenceDialog({
  open,
  recruitmentId,
  applicationId,
  onOpenChange,
  title,
  badge,
  reason,
  metric,
  quotes,
  documents,
  normalized,
  originalsWithName,
}: {
  open: boolean
  recruitmentId: string
  applicationId: string
  onOpenChange: (open: boolean) => void
  title: string
  badge?: ReactNode
  reason: string
  metric: string
  quotes: EvidenceQuote[]
  documents: CandidateDetail['documents']
  normalized?: CandidateDetail['normalized']
  originalsWithName: CandidateDetail['originalsWithName']
}) {
  const groups = groupByDocument(quotes, documents)
  const [tab, setTab] = useState<DocumentType | null>(null)
  const current = groups.find((group) => group.type === tab) ?? groups[0]
  const layout = current ? normalizedOf(normalized, current.type) : undefined
  const matched = layout && current ? matchEvidence(layout, current.sentences) : null
  const scroller = useRef<HTMLDivElement>(null)

  // 탭을 바꾸거나 열 때마다 첫 밑줄로 옮긴다
  useEffect(() => {
    if (!open) return
    const frame = requestAnimationFrame(() => {
      const first = scroller.current?.querySelector('mark')
      first?.scrollIntoView?.({ block: 'center' })
    })
    return () => cancelAnimationFrame(frame)
  }, [open, current?.type])

  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        onOpenChange(value)
        if (!value) setTab(null)
      }}
    >
      <DialogContent className="flex max-h-[85vh] flex-col gap-3 sm:max-w-3xl">
        <div className="flex items-center gap-2">
          {badge}
          <DialogTitle className="text-base font-bold">{title}</DialogTitle>
        </div>
        <DialogDescription asChild>
          <div className="space-y-1.5 text-xs leading-5">
            <p>{reason || '판정 이유가 없어요.'}</p>
            {metric && (
              <p className="text-foreground">
                <span className="text-muted-foreground">지표 </span>
                <strong>{metric}</strong>
              </p>
            )}
          </div>
        </DialogDescription>
        {groups.length === 0 ? (
          <p className="text-sm text-muted-foreground">서류에서 근거 문장을 찾지 못했어요.</p>
        ) : (
          <>
            {groups.length > 1 && (
              <div
                role="tablist"
                aria-label="근거가 나온 서류"
                className="flex gap-4 border-b text-sm"
              >
                {groups.map((group) => (
                  <button
                    key={group.type}
                    type="button"
                    role="tab"
                    aria-selected={group.type === current?.type}
                    onClick={() => setTab(group.type)}
                    className={cn(
                      '-mb-px border-b-2 pb-1.5',
                      group.type === current?.type
                        ? 'border-foreground font-semibold'
                        : 'border-transparent text-muted-foreground',
                    )}
                  >
                    {DOCUMENT_LABELS[group.type] ?? group.type}{' '}
                    <span className="tabular-nums">
                      {underlineSpans(group.text, group.sentences).length}
                    </span>
                  </button>
                ))}
              </div>
            )}
            {current && (
              <div className="flex justify-end text-xs text-muted-foreground">
                {current.type !== 'CERTIFICATE' && (
                  <OriginalPdfLink
                    href={`/api/recruitments/${recruitmentId}/applications/${applicationId}/documents/${current.type}`}
                    showsName={originalsWithName.includes(current.type)}
                  />
                )}
              </div>
            )}
            {current && (
              <div
                ref={scroller}
                className="min-h-0 flex-1 overflow-auto rounded-lg border p-4 text-sm leading-6"
              >
                <p className="mb-2 text-xs text-muted-foreground">
                  {DOCUMENT_LABELS[current.type] ?? current.type} 원문 · 밑줄이 판정 근거예요
                </p>
                {layout && matched ? (
                  <div className="space-y-3">
                    {matched.unmatched.length > 0 && (
                      <div className="space-y-1 rounded-md bg-muted/60 px-3 py-2 text-xs">
                        <p className="text-muted-foreground">원문에서 자리를 찾지 못한 근거</p>
                        {matched.unmatched.map((sentence) => (
                          <p key={sentence} className="border-l-2 border-ai/60 pl-2">
                            “{sentence}”
                          </p>
                        ))}
                      </div>
                    )}
                    <NormalizedDocumentView
                      document={layout}
                      spans={matched.spans}
                      metric={metric}
                    />
                  </div>
                ) : (
                  <p className="whitespace-pre-wrap">
                    {underline(current.text, current.sentences, metric)}
                  </p>
                )}
              </div>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

/** 원문에서 근거 문장에 밑줄을 치고, 그 안의 지표는 굵게 한다 */
function underline(text: string, sentences: string[], metric: string): ReactNode[] {
  const parts: ReactNode[] = []
  let cursor = 0
  for (const span of underlineSpans(text, sentences)) {
    parts.push(text.slice(cursor, span.index))
    const marked = text.slice(span.index, span.index + span.length)
    parts.push(
      <mark
        key={span.index}
        className="rounded-sm bg-ai/10 underline decoration-ai decoration-2 underline-offset-4"
      >
        {bold(marked, metric)}
      </mark>,
    )
    cursor = span.index + span.length
  }
  parts.push(text.slice(cursor))
  return parts
}

function bold(sentence: string, metric: string): ReactNode {
  const core = metric.replace(/\s*\([^)]*\)\s*$/, '')
  const found = core ? locate(sentence, core) : null
  if (!found) return sentence
  return (
    <>
      {sentence.slice(0, found.index)}
      <strong>{sentence.slice(found.index, found.index + found.length)}</strong>
      {sentence.slice(found.index + found.length)}
    </>
  )
}
