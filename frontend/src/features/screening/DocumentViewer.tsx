import { Check, ExternalLink, Sparkles, X } from 'lucide-react'
import { useState, type ReactNode } from 'react'

import { Skeleton } from '@/components/ui/skeleton'
import { AgentChip } from '@/features/posting/AiRequestPanel'
import { useCandidateAnalysis, type CandidateDetail } from '@/features/screening/api'
import { cn } from '@/lib/utils'

type Tab = 'RESUME' | 'COVER_LETTER' | 'PORTFOLIO' | 'CERTIFICATE'

const TABS: { key: Tab; label: string }[] = [
  { key: 'RESUME', label: '이력서' },
  { key: 'COVER_LETTER', label: '자기소개서' },
  { key: 'PORTFOLIO', label: '포트폴리오' },
  { key: 'CERTIFICATE', label: '자격증' },
]

/** 서류 전형의 문서 Viewer (STG-06). 제출 문서를 탭으로 보고, AI 분석의 근거 문장에 밑줄을 친다. */
export function DocumentViewer({
  stageId,
  recruitmentId,
  detail,
}: {
  stageId: string
  recruitmentId: string
  detail: CandidateDetail
}) {
  const [tab, setTab] = useState<Tab>('RESUME')
  const analysis = useCandidateAnalysis(
    stageId,
    detail.row.applicationId,
    detail.row.analysisStatus,
  )
  const document = detail.documents.find((item) => item.type === tab)
  const highlights = (analysis.data?.highlights ?? [])
    .filter((item) => item.document === tab)
    .map((item) => item.sentence)

  return (
    <div className="space-y-4">
      <div role="tablist" className="flex gap-5 border-b text-sm">
        {TABS.map((item) => (
          <button
            key={item.key}
            role="tab"
            aria-selected={tab === item.key}
            onClick={() => setTab(item.key)}
            className={cn(
              '-mb-px border-b-2 pb-2',
              tab === item.key
                ? 'border-foreground font-semibold'
                : 'border-transparent text-muted-foreground',
            )}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div className="max-h-[360px] overflow-auto rounded-xl border p-4 text-sm leading-6">
        {tab === 'CERTIFICATE' ? (
          <p className={cn(!detail.certificates && 'text-muted-foreground')}>
            {detail.certificates ?? '자격증 정보가 없어요.'}
          </p>
        ) : !document ? (
          <p className="text-muted-foreground">제출하지 않은 서류예요.</p>
        ) : (
          <>
            <div className="mb-3 flex items-center justify-between text-xs text-muted-foreground">
              <span>{document.fileName}</span>
              <a
                href={`/api/recruitments/${recruitmentId}/applications/${detail.row.applicationId}/documents/${tab}`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 hover:text-foreground"
              >
                <ExternalLink className="size-3" />
                원본 PDF
              </a>
            </div>
            {document.text ? (
              <p className="whitespace-pre-wrap">{highlight(document.text, highlights)}</p>
            ) : (
              <p className="text-muted-foreground">
                PDF에서 글자를 읽지 못했어요. 원본 PDF를 확인해 주세요.
              </p>
            )}
          </>
        )}
      </div>
      <AnalysisBox
        status={detail.row.analysisStatus}
        loading={analysis.isPending}
        analysis={analysis.data}
      />
    </div>
  )
}

/** AI 분석 요약: 공고 조건 충족 · 눈여겨볼 점 · 확인 필요를 출처와 함께 */
function AnalysisBox({
  status,
  loading,
  analysis,
}: {
  status: CandidateDetail['row']['analysisStatus']
  loading: boolean
  analysis?: ReturnType<typeof useCandidateAnalysis>['data']
}) {
  return (
    <div className="space-y-3 rounded-xl border border-ai/30 bg-ai-soft/50 p-4 text-sm">
      <div className="flex items-center gap-2 font-semibold">
        <Sparkles className="size-4 text-ai" />
        AI 분석
        {analysis && <AgentChip name={analysis.agent} stub={analysis.stub} />}
      </div>
      {status !== 'DONE' ? (
        <p className="text-muted-foreground">
          {status === 'FAILED'
            ? 'AI 분석에 실패했어요.'
            : 'AI가 서류를 분석하고 있어요. 끝나면 여기에 보여 드려요.'}
        </p>
      ) : loading || !analysis ? (
        <Skeleton className="h-16 w-full" />
      ) : (
        <dl className="space-y-2.5">
          {analysis.holds.length > 0 && (
            <Row label="점수 보류">
              <div className="rounded-lg bg-muted px-3 py-2">
                <Findings items={analysis.holds} empty="" />
              </div>
            </Row>
          )}
          {analysis.fit.length > 0 && (
            <Row label="AI 적합도">
              <FitScore lines={analysis.fit} />
            </Row>
          )}
          <Row label="공고 조건">
            {analysis.conditions.length === 0 ? (
              <span className="text-muted-foreground">공고에 자격 요건이 없어요.</span>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {analysis.conditions.map((condition) => (
                  <span
                    key={condition.requirement}
                    title={condition.requirement}
                    className={cn(
                      'inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium',
                      condition.met
                        ? 'bg-pass text-pass-foreground'
                        : 'bg-muted text-muted-foreground',
                    )}
                  >
                    {condition.met ? <Check className="size-3" /> : <X className="size-3" />}
                    {condition.label}
                  </span>
                ))}
              </div>
            )}
          </Row>
          <Row label="눈여겨볼 점">
            <Findings items={analysis.notable} empty="찾은 내용이 없어요." />
          </Row>
          <Row label="확인 필요">
            <Findings items={analysis.checks} empty="없어요." />
          </Row>
        </dl>
      )}
    </div>
  )
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[72px_1fr] gap-3">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}

/** AI 적합도 점수(100점)와 항목별 점수 · 이유. 첫 줄은 우대사항 NCS 평가 조건(60점), 나머지는 직무 적합도(40점)다. */
function FitScore({
  lines,
}: {
  lines: { label: string; points: number; max: number; reason: string }[]
}) {
  const total = lines.reduce((sum, line) => sum + line.points, 0)
  return (
    <div className="space-y-1.5">
      <div className="font-semibold">
        {total}
        <span className="text-xs font-normal text-muted-foreground"> / 100점</span>
      </div>
      <ul className="space-y-1">
        {lines.map((line) => (
          <li key={line.label} className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3">
            <span className="text-xs">{line.label}</span>
            <span className="text-xs font-medium tabular-nums">
              {line.points}/{line.max}
            </span>
            <span className="col-span-2 text-xs text-muted-foreground">{line.reason}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function Findings({ items, empty }: { items: { text: string; source: string }[]; empty: string }) {
  if (items.length === 0) return <span className="text-muted-foreground">{empty}</span>
  return (
    <ul className="space-y-1">
      {items.map((item) => (
        <li key={item.text}>
          {item.text} <span className="text-xs text-muted-foreground">· 출처 {item.source}</span>
        </li>
      ))}
    </ul>
  )
}

/** 근거 문장에 밑줄을 친다. */
function highlight(text: string, sentences: string[]): ReactNode[] {
  const targets = sentences.filter((sentence) => sentence.length > 0 && text.includes(sentence))
  if (targets.length === 0) return [text]
  const pattern = new RegExp(
    `(${targets.map((sentence) => sentence.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`,
  )
  return text.split(pattern).map((part, index) =>
    targets.includes(part) ? (
      <mark
        key={index}
        className="bg-transparent underline decoration-ai decoration-2 underline-offset-4"
      >
        {part}
      </mark>
    ) : (
      part
    ),
  )
}
