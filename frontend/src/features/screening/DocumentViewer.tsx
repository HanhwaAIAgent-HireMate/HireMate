import { Check, ExternalLink, Sparkles, X } from 'lucide-react'
import { useState, type ReactNode } from 'react'

import { Skeleton } from '@/components/ui/skeleton'
import { AgentChip } from '@/features/posting/AiRequestPanel'
import {
  formatScore,
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
  // 제출 문서가 아니라 분석 Agent들이 쌓은 지원자 프로필 (AI 분석 + 확인 상태). 카드를 열면 먼저 보인다
  { key: 'PROFILE', label: '프로필' },
  { key: 'RESUME', label: '이력서' },
  { key: 'COVER_LETTER', label: '자기소개서' },
  { key: 'PORTFOLIO', label: '포트폴리오' },
  { key: 'CERTIFICATE', label: '자격증' },
]
const DOCUMENT_LABELS = Object.fromEntries(TABS.map((item) => [item.key, item.label])) as Record<
  Tab,
  string
>

/**
 * 서류 전형의 문서 Viewer (STG-06). 제출 문서를 탭으로 보고, AI 분석의 근거 문장에 밑줄을 친다.
 * 프로필 탭은 AI 분석 요약을 먼저 보여 주고, 그 아래에 분석 Agent들이 쌓은 항목을 확인 상태와 함께 보여 준다.
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
        // 프로필 탭: 1) AI 분석 요약 → 2) 프로필 항목
        <>
          <AnalysisBox
            status={detail.row.analysisStatus}
            loading={analysis.isPending}
            analysis={analysis.data}
          />
          <div className="rounded-xl border p-4 text-sm leading-6">
            <ProfilePanel stageId={stageId} applicationId={detail.row.applicationId} />
          </div>
        </>
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
 * 서류 평가 점수(자격요건 + 우대사항)와 항목별 판정. 배점은 영역 만점 × 계수 ÷ 영역 계수 합이다(일반 1, 중요 1.5).
 * 공고 조건에 대한 서류 평가일 뿐 합격 여부나 전체 역량을 뜻하지 않는다.
 */
function CriteriaScore({ analysis }: { analysis: CandidateAnalysis }) {
  const areas = [
    ['QUALIFICATION', '자격요건', analysis.qualificationScore, analysis.qualificationMax],
    ['PREFERENCE', '우대사항', analysis.preferenceScore, analysis.preferenceMax],
  ] as const
  return (
    <div className="space-y-2">
      <div className="font-semibold">
        {analysis.documentScore === null ? '점수 보류' : formatScore(analysis.documentScore)}
        {analysis.documentScore !== null && (
          <span className="text-xs font-normal text-muted-foreground"> / 100점</span>
        )}
        {analysis.qualificationStatus !== 'PASSED' && (
          <span className="ml-2 text-xs font-normal text-muted-foreground">
            자격요건 75% {analysis.qualificationStatus === 'FAILED' ? '미달' : '판단 보류'}
          </span>
        )}
      </div>
      {areas
        .filter(([, , , max]) => max > 0)
        .map(([category, label, score, max]) => (
          <div key={category} className="space-y-1">
            <div className="text-xs font-medium">
              {label} {score === null ? '확인 필요' : `${formatScore(score)}/${max}`}
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
        {line.important && (
          <span className="mr-1 text-[11px] font-semibold text-foreground">중요</span>
        )}
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
