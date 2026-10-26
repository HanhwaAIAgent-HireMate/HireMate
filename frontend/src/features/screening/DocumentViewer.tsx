import { Check, ExternalLink, Sparkles, X } from 'lucide-react'
import { useState, type ReactNode } from 'react'

import { Skeleton } from '@/components/ui/skeleton'
import { AgentChip } from '@/features/posting/AiRequestPanel'
import {
  formatScore,
  heldScore,
  useCandidateAnalysis,
  type CandidateAnalysis,
  type CandidateDetail,
  type CriterionLine,
  type SummarySection,
} from '@/features/screening/api'
import { ProfilePanel } from '@/features/screening/ProfilePanel'
import { cn } from '@/lib/utils'

type Tab = 'RESUME' | 'COVER_LETTER' | 'PORTFOLIO' | 'CERTIFICATE' | 'PROFILE'

const TABS: { key: Tab; label: string }[] = [
  { key: 'RESUME', label: '이력서' },
  { key: 'COVER_LETTER', label: '자기소개서' },
  { key: 'PORTFOLIO', label: '포트폴리오' },
  { key: 'CERTIFICATE', label: '자격증' },
  // 제출 문서가 아니라 분석 Agent들이 쌓은 지원자 프로필 (확인 상태 포함)
  { key: 'PROFILE', label: '프로필' },
]
const DOCUMENT_LABELS = Object.fromEntries(TABS.map((item) => [item.key, item.label])) as Record<
  Tab,
  string
>

/**
 * 서류 전형의 문서 Viewer (STG-06). 제출 문서를 탭으로 보고, AI 분석의 근거 문장에 밑줄을 친다.
 * 프로필 탭은 분석 Agent들이 쌓은 항목을 확인 상태와 함께 보여 준다.
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
  const [tab, setTab] = useState<Tab>('RESUME')
  // 자기소개서는 문항별 요약을 먼저 보여 주고, 원문은 눌러서 본다
  const [fullText, setFullText] = useState(false)
  const analysis = useCandidateAnalysis(
    stageId,
    detail.row.applicationId,
    detail.row.analysisStatus,
  )
  const document = detail.documents.find((item) => item.type === tab)
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
      <div className="max-h-[360px] overflow-auto rounded-xl border p-4 text-sm leading-6">
        {tab === 'PROFILE' ? (
          <ProfilePanel stageId={stageId} applicationId={detail.row.applicationId} />
        ) : tab === 'CERTIFICATE' ? (
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
        status={detail.row.analysisStatus}
        loading={analysis.isPending}
        analysis={analysis.data}
      />
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

type AnalysisView = 'SUMMARY' | 'DETAIL'

const ANALYSIS_VIEWS: Record<AnalysisView, string> = { SUMMARY: '요약', DETAIL: '자세히' }
/** 요약에서 눈여겨볼 점 · 확인 필요를 이만큼까지 보여 준다. 나머지는 자세히에서 본다 */
const SUMMARY_FINDINGS = 2

/**
 * AI 분석. 요약은 점수 · 항목별 판정 칩 · 눈여겨볼 점 · 확인 필요를 한눈에, 자세히는 항목마다 판정 이유 · 근거 출처까지
 * 보여 준다. 처음에는 요약이다.
 */
function AnalysisBox({
  status,
  loading,
  analysis,
}: {
  status: CandidateDetail['row']['analysisStatus']
  loading: boolean
  analysis?: ReturnType<typeof useCandidateAnalysis>['data']
}) {
  const [view, setView] = useState<AnalysisView>('SUMMARY')
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
        <AnalysisSummary analysis={analysis} />
      ) : (
        <dl className="space-y-2.5">
          {analysis.holds.length > 0 && (
            <Row label="점수 보류">
              <div className="rounded-lg bg-muted px-3 py-2">
                <Findings items={analysis.holds} empty="" />
              </div>
            </Row>
          )}
          {analysis.criteria.length > 0 && (
            <Row label="서류 평가">
              <CriteriaScore analysis={analysis} />
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

/** 요약: 총점(보류면 확인 필요를 0점으로 계산한 점수) · 영역 점수, 항목별 판정 칩, 눈여겨볼 점 · 확인 필요 몇 개 */
function AnalysisSummary({ analysis }: { analysis: CandidateAnalysis }) {
  const checks = [...analysis.holds, ...analysis.checks]
  return (
    <dl className="space-y-2.5">
      {analysis.criteria.length > 0 && (
        <Row label="서류 평가">
          <div className="space-y-1.5">
            <ScoreHeadline analysis={analysis} />
            <ul className="flex flex-wrap gap-1">
              {analysis.criteria.map((line) => (
                <li
                  key={line.criterionId}
                  title={`${line.text} · ${VERDICTS[line.verdict].label}`}
                  className={cn(
                    'max-w-[11rem] truncate rounded px-1.5 py-0.5 text-[11px] font-medium',
                    VERDICTS[line.verdict].className,
                  )}
                >
                  {line.criterionId} {shortText(line.text)}
                </li>
              ))}
            </ul>
          </div>
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

/** "45.8 / 100점 · 자격 37.5 · 우대 8.3". 보류면 "보류 45.8 / 100점" (확인 필요는 0점) */
function ScoreHeadline({ analysis }: { analysis: CandidateAnalysis }) {
  const areas = [
    ['자격', analysis.qualificationScore, analysis.qualificationMax],
    ['우대', analysis.preferenceScore, analysis.preferenceMax],
  ] as const
  return (
    <div className="flex flex-wrap items-baseline gap-x-2">
      {analysis.documentScore !== null ? (
        <span className="font-semibold">
          {formatScore(analysis.documentScore)}
          <span className="text-xs font-normal text-muted-foreground"> / 100점</span>
        </span>
      ) : (
        <HeldScore score={analysis.documentScoreLow} />
      )}
      <span className="text-xs text-muted-foreground">
        {areas
          .filter(([, , max]) => max > 0)
          .map(([label, score, max]) =>
            score === null
              ? `${label} 확인 필요`
              : `${label} ${formatScore(score)}${max === 50 ? '' : `/${max}`}`,
          )
          .join(' · ')}
      </span>
      {analysis.qualificationStatus !== 'PASSED' && (
        <span className="text-xs text-muted-foreground">
          자격요건 75% {analysis.qualificationStatus === 'FAILED' ? '미달' : '판단 보류'}
        </span>
      )}
    </div>
  )
}

/** 보류 점수: 확인 필요를 0점으로 계산한 점수를 회색으로, '보류'를 붙여 보여 준다 */
function HeldScore({ score }: { score: number | null }) {
  return (
    <span
      title="점수 보류: 확인 필요 항목을 0점으로 계산한 점수예요"
      className="font-semibold text-muted-foreground"
    >
      <span className="mr-1 rounded bg-muted px-1 text-[11px] font-medium">보류</span>
      {heldScore(score)}
      <span className="text-xs font-normal"> / 100점</span>
    </span>
  )
}

/** 판정 칩에 넣을 짧은 항목 이름. 앞쪽 낱말 몇 개만 쓴다 */
function shortText(text: string) {
  const words = text.split(/\s+/)
  return words.length > 3 ? `${words.slice(0, 3).join(' ')}…` : text
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[72px_1fr] gap-3">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}

const VERDICTS: Record<CriterionLine['verdict'], { label: string; className: string }> = {
  MET: { label: '충족', className: 'bg-pass text-pass-foreground' },
  PARTIAL: { label: '부분 충족', className: 'bg-ai-soft text-ai' },
  NOT_MET: { label: '미충족', className: 'bg-muted text-muted-foreground' },
  UNKNOWN: { label: '확인 필요', className: 'border border-dashed text-muted-foreground' },
}

const CERTIFICATE_STATUS: Record<NonNullable<CriterionLine['certificateStatus']>, string> = {
  SELF_REPORTED: '본인 기재 · 미검증',
  EVIDENCE_SUBMITTED: '증빙 제출',
  ISSUER_VERIFIED: '발급기관 확인',
}

/**
 * 서류 평가 점수(자격요건 + 우대사항)와 항목별 판정. 영역 안의 항목은 모두 같은 비중이라 배점은 영역 만점 ÷ 항목 수다.
 * 점수를 보류했으면 확인 필요를 0점으로 계산한 점수를 회색으로 보여 준다.
 * 공고 조건에 대한 서류 평가일 뿐 합격 여부나 전체 역량을 뜻하지 않는다.
 */
function CriteriaScore({ analysis }: { analysis: CandidateAnalysis }) {
  const areas = [
    [
      'QUALIFICATION',
      '자격요건',
      analysis.qualificationScore,
      analysis.qualificationMax,
      analysis.qualificationScoreLow,
    ],
    [
      'PREFERENCE',
      '우대사항',
      analysis.preferenceScore,
      analysis.preferenceMax,
      analysis.preferenceScoreLow,
    ],
  ] as const
  return (
    <div className="space-y-2">
      <div className="font-semibold">
        {analysis.documentScore === null ? (
          <HeldScore score={analysis.documentScoreLow} />
        ) : (
          <>
            {formatScore(analysis.documentScore)}
            <span className="text-xs font-normal text-muted-foreground"> / 100점</span>
          </>
        )}
        {analysis.qualificationStatus !== 'PASSED' && (
          <span className="ml-2 text-xs font-normal text-muted-foreground">
            자격요건 75% {analysis.qualificationStatus === 'FAILED' ? '미달' : '판단 보류'}
          </span>
        )}
      </div>
      {areas
        .filter(([, , , max]) => max > 0)
        .map(([category, label, score, max, zeroed]) => (
          <div key={category} className="space-y-1">
            <div className="text-xs font-medium">
              {label}{' '}
              {score !== null ? (
                `${formatScore(score)}/${max}`
              ) : (
                <span className="text-muted-foreground">
                  보류 {heldScore(zeroed)}/{max}
                </span>
              )}
            </div>
            <ul className="space-y-1.5">
              {analysis.criteria
                .filter((line) => line.category === category)
                .map((line) => (
                  <CriterionItem key={line.criterionId} line={line} />
                ))}
            </ul>
          </div>
        ))}
      <p className="text-[11px] text-muted-foreground">
        공고 조건에 대한 서류 평가예요. 합격 여부를 뜻하지 않아요.
        {analysis.criteriaVersion && ` · 평가 기준 ${analysis.criteriaVersion}`}
      </p>
    </div>
  )
}

function CriterionItem({ line }: { line: CriterionLine }) {
  const details = [
    line.careerYears !== null && `확인 경력 ${line.careerYears}년`,
    line.certificateStatus && CERTIFICATE_STATUS[line.certificateStatus],
    line.satisfiedParts.length > 0 && `충족: ${line.satisfiedParts.join(', ')}`,
    line.unsatisfiedParts.length > 0 && `미충족: ${line.unsatisfiedParts.join(', ')}`,
    line.unknownParts.length > 0 && `확인 안 됨: ${line.unknownParts.join(', ')}`,
    line.recheckCount > 0 && `재확인 ${line.recheckCount}회`,
  ].filter(Boolean)
  const sources = [...new Set(line.evidence.map((item) => DOCUMENT_LABELS[item.document]))]
  return (
    <li className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-0.5">
      <span className="text-xs">
        <span
          className={cn(
            'mr-1.5 inline-block rounded px-1.5 text-[11px] font-medium',
            VERDICTS[line.verdict].className,
          )}
        >
          {VERDICTS[line.verdict].label}
        </span>
        {line.text}
      </span>
      <span className="text-xs font-medium tabular-nums">
        {line.earned === null ? '–' : formatScore(line.earned)}/{formatScore(line.allotted)}
      </span>
      <span className="col-span-2 text-xs text-muted-foreground">
        {line.reason}
        {details.length > 0 && ` · ${details.join(' · ')}`}
        {sources.length > 0 && ` · 출처 ${sources.join(' · ')}`}
      </span>
    </li>
  )
}

function Findings({
  items,
  empty,
  more = 0,
}: {
  items: { text: string; source: string }[]
  empty: string
  /** 요약에서 줄인 나머지 개수. 자세히에서 볼 수 있다 */
  more?: number
}) {
  if (items.length === 0) return <span className="text-muted-foreground">{empty}</span>
  return (
    <ul className="space-y-1">
      {items.map((item) => (
        <li key={item.text}>
          {item.text} <span className="text-xs text-muted-foreground">· 출처 {item.source}</span>
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
