import { Sparkles } from 'lucide-react'
import { useState, type ReactNode } from 'react'

import { Skeleton } from '@/components/ui/skeleton'
import { AgentChip } from '@/features/posting/AiRequestPanel'
import {
  useCandidateAnalysis,
  type CandidateAnalysis,
  type CandidateDetail,
  type CriterionLine,
  type SummarySection,
} from '@/features/screening/api'
import {
  criterionMark,
  markTone,
  TALENT_MARKS,
  TONE_CLASSES,
  useCandidateTable,
  useTalentFit,
  type Mark,
  type TalentFit,
} from '@/features/screening/table'
import { OriginalPdfLink } from '@/features/screening/OriginalPdfLink'
import { cn } from '@/lib/utils'

type Tab = 'RESUME' | 'COVER_LETTER' | 'PORTFOLIO' | 'CERTIFICATE' | 'PROFILE'

const TABS: { key: Tab; label: string }[] = [
  // 제출 문서가 아니라 AI 분석을 보여 주는 탭. 카드를 열면 먼저 보인다
  { key: 'PROFILE', label: '프로필' },
  { key: 'RESUME', label: '이력서' },
  { key: 'COVER_LETTER', label: '자기소개서' },
  { key: 'PORTFOLIO', label: '포트폴리오' },
  { key: 'CERTIFICATE', label: '자격증' },
]

/**
 * 서류 전형의 문서 Viewer (STG-06). 제출 문서를 탭으로 보고, AI 분석의 근거 문장에 밑줄을 친다.
 * 프로필 탭은 AI 분석을 보여 준다.
 */
export function DocumentViewer({
  stageId,
  recruitmentId,
  detail,
}: {
  stageId: string
  recruitmentId: string
  detail: CandidateDetail
}) {
  const [tab, setTab] = useState<Tab>('PROFILE')
  // 자기소개서는 문항별 요약을 먼저 보여 주고, 원문은 눌러서 본다
  const [fullText, setFullText] = useState(false)
  const analysis = useCandidateAnalysis(
    stageId,
    detail.row.applicationId,
    detail.row.analysisStatus,
  )
  const document = detail.documents.find((item) => item.type === tab)
  // 블라인드 채용에서 원본을 열면 이름이 보이는 서류
  const originalShowsName = detail.originalsWithName.some((type) => type === tab)
  const sections = (analysis.data?.summaries ?? []).filter((item) => item.document === tab)
  const showSummary = sections.length > 0 && !fullText
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
            onClick={() => {
              setTab(item.key)
              setFullText(false)
            }}
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
      {tab === 'PROFILE' ? (
        <AnalysisBox
          stageId={stageId}
          applicationId={detail.row.applicationId}
          status={detail.row.analysisStatus}
          loading={analysis.isPending}
          analysis={analysis.data}
        />
      ) : (
        <>
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
                  {sections.length > 0 && (
                    <button
                      type="button"
                      onClick={() => setFullText((value) => !value)}
                      className="mr-3 ml-auto hover:text-foreground"
                    >
                      {fullText ? '문항별 요약 보기' : '원문 보기'}
                    </button>
                  )}
                  <OriginalPdfLink
                    href={`/api/recruitments/${recruitmentId}/applications/${detail.row.applicationId}/documents/${tab}`}
                    showsName={originalShowsName}
                  />
                </div>
                {showSummary ? (
                  <SectionSummaries sections={sections} />
                ) : document.text ? (
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
            stageId={stageId}
            applicationId={detail.row.applicationId}
            status={detail.row.analysisStatus}
            loading={analysis.isPending}
            analysis={analysis.data}
          />
        </>
      )}
    </div>
  )
}

/** 자기소개서 문항별 요약 분석: 문항 · 요약 · 핵심 · 원문 근거. 판단 없이 무엇을 썼는지만 보여 준다. */
function SectionSummaries({ sections }: { sections: SummarySection[] }) {
  return (
    <ol className="space-y-4">
      {sections.map((section, index) => (
        <li key={section.title} className="space-y-1.5">
          <div className="font-semibold">
            {index + 1}. {section.title}
          </div>
          <p>{section.summary}</p>
          {section.points.length > 0 && (
            <ul className="list-disc space-y-0.5 pl-5 text-xs text-muted-foreground">
              {section.points.map((point) => (
                <li key={point}>{point}</li>
              ))}
            </ul>
          )}
          {section.evidence.map((item) => (
            <p
              key={item.sentence}
              className="border-l-2 border-ai/60 pl-2 text-xs text-muted-foreground"
            >
              “{item.sentence}”
            </p>
          ))}
        </li>
      ))}
    </ol>
  )
}

type AnalysisView = 'DETAIL' | 'SUMMARY'

const ANALYSIS_VIEWS: Record<AnalysisView, string> = { DETAIL: '자세히', SUMMARY: '요약' }
/** 요약에서 눈여겨볼 점 · 확인 필요를 이만큼까지 보여 준다. 나머지는 자세히에서 본다 */
const SUMMARY_FINDINGS = 2

type LevelFilter = 'ALL' | '상' | '중' | '하' | '확인 필요'

const LEVEL_FILTERS: LevelFilter[] = ['ALL', '상', '중', '하', '확인 필요']

const GROUP_NAMES: Record<CriterionLine['category'] | 'TALENT', string> = {
  QUALIFICATION: '자격요건',
  PREFERENCE: '우대사항',
  TALENT: '인재상',
}

/** 역량 분석 한 줄: 경험형 평가 항목이나 인재상 하나 */
type Ability = {
  key: string
  group: keyof typeof GROUP_NAMES
  label: string
  mark: Mark
  reason: string
  quote: string | null
  metric: string
}

/**
 * AI 분석. 점수 없이 자세히 · 요약으로 본다. 처음에는 자세히다.
 * 자세히는 위에 조건 확인(조건형 항목의 O · X), 아래에 역량 분석(경험형 항목과 인재상을 상 · 중 · 하 · 확인 필요로
 * 거르며 판정 이유와 원문 근거)을 둔다. 정량 지표는 근거 안에서 굵게 보인다.
 * 요약은 항목별 판정 칩 · 눈여겨볼 점 · 확인 필요를 한눈에 보여 준다.
 */
function AnalysisBox({
  stageId,
  applicationId,
  status,
  loading,
  analysis,
}: {
  stageId: string
  applicationId: string
  status: CandidateDetail['row']['analysisStatus']
  loading: boolean
  analysis?: ReturnType<typeof useCandidateAnalysis>['data']
}) {
  const [view, setView] = useState<AnalysisView>('DETAIL')
  const talents = useTalentFit(stageId, applicationId, status)
  const table = useCandidateTable(stageId)
  // 항목 이름은 표 보기의 열 이름(짧은 키워드)을 쓰고, 없으면 항목 문장을 쓴다
  const labels = new Map((table.data?.features ?? []).map((item) => [item.id, item.label]))
  const ready = status === 'DONE' && !loading && analysis
  return (
    <div className="space-y-3 rounded-xl border border-ai/30 bg-ai-soft/50 p-4 text-sm">
      <div className="flex items-center gap-2 font-semibold">
        <Sparkles className="size-4 text-ai" />
        AI 분석
        {analysis && <AgentChip name={analysis.agent} stub={analysis.stub} />}
        {ready && (
          <div
            role="tablist"
            aria-label="AI 분석 보기"
            className="ml-auto flex rounded-md bg-background/70 p-0.5 text-xs font-normal"
          >
            {(Object.keys(ANALYSIS_VIEWS) as AnalysisView[]).map((key) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={view === key}
                onClick={() => setView(key)}
                className={cn(
                  'h-6 rounded px-2.5',
                  view === key
                    ? 'bg-background font-semibold shadow-sm'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {ANALYSIS_VIEWS[key]}
              </button>
            ))}
          </div>
        )}
      </div>
      {status !== 'DONE' ? (
        <p className="text-muted-foreground">
          {status === 'FAILED'
            ? 'AI 분석에 실패했어요.'
            : 'AI가 서류를 분석하고 있어요. 끝나면 여기에 보여 드려요.'}
        </p>
      ) : loading || !analysis ? (
        <Skeleton className="h-16 w-full" />
      ) : view === 'SUMMARY' ? (
        <AnalysisSummary analysis={analysis} talents={talents.data} />
      ) : (
        <div className="space-y-4">
          <section className="space-y-2">
            <h4 className="text-xs font-medium text-muted-foreground">조건 확인</h4>
            <ConditionCheck analysis={analysis} labels={labels} />
          </section>
          <section className="space-y-2 border-t pt-3">
            <h4 className="text-xs font-medium text-muted-foreground">역량 분석</h4>
            <AbilityAnalysis
              analysis={analysis}
              labels={labels}
              talents={talents.data}
              talentsLoading={talents.isPending}
            />
          </section>
        </div>
      )}
    </div>
  )
}

/** 요약: 항목별 판정 칩(자격요건 · 우대사항 · 인재상), 눈여겨볼 점 · 확인 필요 몇 개 */
function AnalysisSummary({
  analysis,
  talents,
}: {
  analysis: CandidateAnalysis
  talents: TalentFit | undefined
}) {
  const checks = [...analysis.holds, ...analysis.checks]
  return (
    <dl className="space-y-2.5">
      {analysis.criteria.length > 0 && (
        <Row label="평가 항목">
          <ul className="flex flex-wrap gap-1">
            {analysis.criteria.map((line) => {
              const mark = criterionMark(line.criterionType === 'CONDITION', line)
              return (
                <li
                  key={line.criterionId}
                  title={`${line.text} · ${mark}`}
                  className={cn(
                    'max-w-[11rem] truncate rounded px-1.5 py-0.5 text-[11px] font-medium',
                    TONE_CLASSES[markTone(mark)],
                  )}
                >
                  {shortText(line.text)}
                </li>
              )
            })}
          </ul>
        </Row>
      )}
      {talents && talents.items.length > 0 && (
        <Row label="인재상">
          <ul className="flex flex-wrap gap-1">
            {talents.items.map((item) => {
              const mark = TALENT_MARKS[item.level]
              return (
                <li
                  key={item.title}
                  title={`${item.title} · ${mark}`}
                  className={cn(
                    'max-w-[11rem] truncate rounded px-1.5 py-0.5 text-[11px] font-medium',
                    TONE_CLASSES[markTone(mark)],
                  )}
                >
                  {item.title} {mark}
                </li>
              )
            })}
          </ul>
        </Row>
      )}
      <Row label="눈여겨볼 점">
        <Findings
          items={analysis.notable.slice(0, SUMMARY_FINDINGS)}
          empty="찾은 내용이 없어요."
          more={analysis.notable.length - SUMMARY_FINDINGS}
        />
      </Row>
      <Row label="확인 필요">
        <Findings
          items={checks.slice(0, SUMMARY_FINDINGS)}
          empty="없어요."
          more={checks.length - SUMMARY_FINDINGS}
        />
      </Row>
    </dl>
  )
}

/** 판정 칩에 넣을 짧은 항목 이름. 앞쪽 낱말 몇 개만 쓴다 */
function shortText(text: string) {
  const words = text.split(/\s+/)
  return words.length > 3 ? `${words.slice(0, 3).join(' ')}…` : text
}

/** 조건 확인: 조건형 항목마다 이름과 O · X. 판정 이유는 마우스를 올리면 보인다 */
function ConditionCheck({
  analysis,
  labels,
}: {
  analysis: CandidateAnalysis
  labels: Map<string, string>
}) {
  const lines = analysis.criteria.filter((line) => line.criterionType === 'CONDITION')
  if (lines.length === 0) {
    return <p className="text-muted-foreground">조건으로 확인할 항목이 없어요.</p>
  }
  return (
    <ul className="flex flex-wrap gap-x-8 gap-y-2">
      {lines.map((line) => (
        <li
          key={line.criterionId}
          title={[line.text, line.reason, conditionNote(line)].filter(Boolean).join('\n')}
          className="flex min-w-0 cursor-help items-center gap-2"
        >
          <span className="min-w-0 truncate">{labels.get(line.criterionId) ?? line.text}</span>
          <MarkChip mark={criterionMark(true, line)} />
        </li>
      ))}
    </ul>
  )
}

/** 조건 칸에 마우스를 올리면 판정 이유 아래에 붙는 확인 내용 */
function conditionNote(line: CriterionLine) {
  if (line.careerYears !== null) return `확인 경력 ${line.careerYears}년`
  return line.certificateStatus ? CERTIFICATE_STATUS[line.certificateStatus] : ''
}

/** 역량 분석: 상 · 중 · 하 · 확인 필요로 거르고, 항목마다 판정 이유 한 줄과 원문 근거 */
function AbilityAnalysis({
  analysis,
  labels,
  talents,
  talentsLoading,
}: {
  analysis: CandidateAnalysis
  labels: Map<string, string>
  talents: TalentFit | undefined
  talentsLoading: boolean
}) {
  const [filter, setFilter] = useState<LevelFilter>('ALL')
  const abilities: Ability[] = [
    ...analysis.criteria
      .filter((line) => line.criterionType !== 'CONDITION')
      .map((line) => ({
        key: line.criterionId,
        group: line.category,
        label: labels.get(line.criterionId) ?? line.text,
        mark: criterionMark(false, line),
        reason: line.reason,
        quote: line.evidence[0]?.sentence ?? null,
        metric: line.metric,
      })),
    ...(talents?.items ?? []).map((item) => ({
      key: `talent-${item.title}`,
      group: 'TALENT' as const,
      label: item.title,
      mark: TALENT_MARKS[item.level],
      reason: item.reason,
      quote: item.quote,
      metric: item.metric,
    })),
  ]
  const count = (key: LevelFilter) =>
    key === 'ALL' ? abilities.length : abilities.filter((item) => item.mark === key).length
  const shown = filter === 'ALL' ? abilities : abilities.filter((item) => item.mark === filter)
  const checks = [...analysis.holds, ...analysis.checks]
  return (
    <div className="space-y-3">
      <div role="tablist" aria-label="판정으로 거르기" className="flex flex-wrap gap-1">
        {LEVEL_FILTERS.map((key) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={filter === key}
            onClick={() => setFilter(key)}
            className={cn(
              'h-6 rounded-full border px-2.5 text-xs',
              filter === key
                ? 'border-foreground/40 bg-background font-semibold'
                : 'border-transparent bg-background/60 text-muted-foreground hover:text-foreground',
            )}
          >
            {key === 'ALL' ? '전체' : key} <span className="tabular-nums">{count(key)}</span>
          </button>
        ))}
      </div>
      {talentsLoading && <Skeleton className="h-10 w-full" />}
      {shown.length === 0 ? (
        <p className="text-muted-foreground">해당하는 항목이 없어요.</p>
      ) : (
        <ul className="space-y-3">
          {shown.map((item) => (
            <li key={item.key} className="space-y-1">
              <div className="flex items-center gap-2">
                <MarkChip mark={item.mark} />
                <span className="font-medium">{item.label}</span>
                <span className="text-[11px] text-muted-foreground">{GROUP_NAMES[item.group]}</span>
              </div>
              {item.reason && <p className="text-xs text-muted-foreground">{item.reason}</p>}
              {item.quote && (
                <p className="border-l-2 border-ai/50 pl-2 text-xs">
                  “{emphasize(item.quote, item.metric)}”
                </p>
              )}
              {item.metric && !findMetric(item.quote, item.metric) && (
                <p className="text-xs">
                  <span className="text-muted-foreground">지표 </span>
                  <strong>{item.metric}</strong>
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
      {filter === 'ALL' && (analysis.notable.length > 0 || checks.length > 0) && (
        <dl className="space-y-2.5 border-t pt-3">
          {analysis.notable.length > 0 && (
            <Row label="눈여겨볼 점">
              <Findings items={analysis.notable} />
            </Row>
          )}
          {checks.length > 0 && (
            <Row label="확인할 점">
              <Findings items={checks} />
            </Row>
          )}
        </dl>
      )}
    </div>
  )
}

/** 근거 문장 안의 정량 지표를 굵게 한다 */
function emphasize(quote: string, metric: string): ReactNode {
  const found = findMetric(quote, metric)
  if (!found) return quote
  return (
    <>
      {quote.slice(0, found.index)}
      <strong>{found.text}</strong>
      {quote.slice(found.index + found.text.length)}
    </>
  )
}

/** 근거 문장 안의 지표 위치. PDF에서 읽은 글은 띄어쓰기가 다를 수 있어 공백 차이는 무시한다 */
function findMetric(quote: string | null, metric: string) {
  const words = metric.split(/\s+/).filter(Boolean)
  if (!quote || words.length === 0) return null
  const escaped = words.map((word) => word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  const match = new RegExp(escaped.join('\\s*')).exec(quote)
  return match ? { index: match.index, text: match[0] } : null
}

function MarkChip({ mark }: { mark: Mark }) {
  return (
    <span
      className={cn(
        'inline-flex shrink-0 rounded px-1.5 py-0.5 text-[11px] font-semibold',
        TONE_CLASSES[markTone(mark)],
      )}
    >
      {mark}
    </span>
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

const CERTIFICATE_STATUS: Record<NonNullable<CriterionLine['certificateStatus']>, string> = {
  SELF_REPORTED: '본인 기재 · 미검증',
  EVIDENCE_SUBMITTED: '증빙 제출',
  ISSUER_VERIFIED: '발급기관 확인',
}

function Findings({
  items,
  empty = '',
  more = 0,
}: {
  items: { text: string; source: string }[]
  empty?: string
  /** 요약에서 줄인 나머지 개수. 자세히에서 볼 수 있다 */
  more?: number
}) {
  if (items.length === 0) return <span className="text-muted-foreground">{empty}</span>
  return (
    <ul className="space-y-1">
      {items.map((item) => (
        <li key={item.text}>
          {item.text} <span className="text-xs text-muted-foreground">· {item.source}</span>
        </li>
      ))}
      {more > 0 && (
        <li className="text-xs text-muted-foreground">외 {more}개 · 자세히에서 볼 수 있어요</li>
      )}
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
