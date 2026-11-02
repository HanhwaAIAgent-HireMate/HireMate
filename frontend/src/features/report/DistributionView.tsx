import { cn } from 'cn'
import type { EChartsCoreOption } from 'echarts/core'
import { ChevronLeft, ChevronRight, Loader2 } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { errorMessage } from '@/lib/api/client'

import {
  useDistributionNote,
  useReportDistribution,
  type DistributionSort,
  type ReportDistribution,
} from './api'
import { issueRate, judged, percent, insightLines } from './distribution'
import { EChart } from './EChart'
import { GRID, INK, MUTED, SEQ, STATUS, SUB } from './palette'

type Group = ReportDistribution['groups'][number]
type Criterion = ReportDistribution['criteria'][number]

/** 목표 안 · 강조 색 (화면의 ai 색과 같은 보라) */
const ACCENT = '#8E51FF'
/** 목표 인원에서 개수가 같은 구간 */
const EDGE = '#E0A33B'
/** 목표 밖 */
const OUTSIDE = '#C8CDD6'

/** 판정 막대 칸. 색만으로 구분하지 않게 늘 글자를 붙인다 */
const BANDS = [
  { key: 'met', label: '충족', color: STATUS.MET.bar },
  { key: 'partial', label: '부분 충족', color: STATUS.PARTIAL.bar },
  { key: 'notMet', label: '미충족', color: STATUS.NOT_MET.bar },
  { key: 'unknown', label: '확인 필요', color: STATUS.UNKNOWN.bar },
] as const

const SORTS: { value: DistributionSort; label: string }[] = [
  { value: 'BASIC', label: '기본' },
  { value: 'TALENT', label: '인재상 포함' },
]

const COUNT_LEGEND = [
  { label: '목표 안', color: ACCENT },
  { label: '선발이 갈리는 동점 구간', color: EDGE },
  { label: '목표 밖', color: OUTSIDE },
  { label: '누적 인원', color: SUB },
]

const CAREER_LEGEND = [
  { label: '전체', color: SEQ[1] },
  { label: '선 위', color: ACCENT },
]

/** 기준을 다시 볼 항목으로 표시하는 개수 */
const FLAGGED = 3

/**
 * 분포 리포트. 서류 전형 지원자 전원의 판정을 backend가 센 그대로 보여 준다. 모델은 쓰지 않는다.
 * 맨 위 요약 문장도 코드가 숫자로 만든다.
 * 서류 통과 목표 인원은 처음에 공고 채용 인원 × 배수이고, 바꾸면 바로 다시 센다(저장하지 않는다).
 * 경계 그룹에서 [이 N명 비교]를 누르면 그 그룹의 몇 명으로 비교 리포트를 요청한다.
 */
export function DistributionView({
  stageId,
  onDeepDive,
  deepPending,
}: {
  stageId: string
  onDeepDive: (applicationIds: string[]) => void
  deepPending: boolean
}) {
  const [target, setTarget] = useState<number | null>(null)
  const [sort, setSort] = useState<DistributionSort>('BASIC')
  const query = useReportDistribution(stageId, target, sort, true)
  const note = useDistributionNote(stageId, target, sort)
  const charts = note.data?.charts ?? {}
  const data = query.data

  if (query.isError) {
    return <p className="text-sm text-muted-foreground">{errorMessage(query.error)}</p>
  }
  if (!data) return <Skeleton className="h-96 w-full" />

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border bg-background px-4 py-3">
        <TargetInput key={data.target} value={data.target} onChange={setTarget} />
        <span className="text-xs text-muted-foreground">
          처음 값은 공고 채용 인원 {data.hireCount}명 × {data.targetMultiplier}배예요. 바꿔도
          저장하지 않아요.
        </span>
        <div className="ml-auto flex items-center gap-1 text-xs">
          <span className="text-muted-foreground">충족 개수</span>
          {SORTS.map((option) => (
            <button
              key={option.value}
              onClick={() => setSort(option.value)}
              className={cn(
                'rounded-md px-2 py-1 font-medium',
                sort === option.value
                  ? 'bg-ai-soft text-ai'
                  : 'text-muted-foreground hover:bg-muted',
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
        {query.isFetching && <Loader2 className="size-4 animate-spin text-muted-foreground" />}
      </div>

      <Insights data={data} note={note.data?.lines} noteLoading={note.isLoading} />

      <Section
        title="서류 통과까지 남는 인원"
        caption="전체 지원자 → 서류 분석 완료 → 필수 조건을 모두 충족한 사람(선 위) → 서류 통과 목표 순서로 세고, 담당자가 실제로 합격 처리한 인원을 맨 아래에 두었어요."
        read="막대 길이는 전체 지원자 대비예요. 선 위와 목표의 차이만큼 담당자가 더 골라내거나 더 올려야 해요."
        ai={charts.funnel}
      >
        <Funnel data={data} />
      </Section>

      <Section
        title="필수 조건 충족 현황"
        caption={
          data.required.criterionIds.length === 0
            ? '체크한 필수 조건이 없어 분석이 끝난 지원자가 모두 선 위에 올라요.'
            : `필수 조건(${data.required.criterionIds.join(' · ')})을 모두 충족했는지로 지원자를 세 갈래로 나눴어요.`
        }
        read="가운데 %가 선 위에 오른 비율이에요. 확인 필요가 많으면 서류만으로는 판단하기 어려운 사람이 많다는 뜻이에요."
        ai={charts.required}
      >
        <RequiredView data={data} />
      </Section>

      <Section
        title="선 위 지원자의 충족 개수"
        caption={
          data.cut
            ? `목표 ${data.target}명째가 충족 ${data.cut.value}개예요. ${data.cut.from}~${data.cut.to}번째 ${
                data.cut.to - data.cut.from + 1
              }명이 모두 ${data.cut.value}개라 개수로는 구분되지 않아요. 이 중 ${data.cut.inside}명만 목표 안에 들어요.`
            : '선 위가 목표 인원 이하라 개수로 갈리는 구간이 없어요. 선 아래 다시 볼 사람을 먼저 보세요.'
        }
        read="막대는 충족 개수가 같은 사람 수, 회색 선은 왼쪽부터 더한 누적 인원이에요. 누적선이 보라 점선(목표)을 넘는 주황 막대에서 선발이 갈려요."
        legend={<Legend items={COUNT_LEGEND} />}
        ai={charts.counts}
      >
        <CountChart data={data} />
      </Section>

      <Section
        title="경계 그룹"
        caption="코드가 정한 임시 기준으로 모은 사람이에요. 추천이나 순위가 아니고, 담당자가 다시 볼 사람이에요."
        read={`${data.deepSize}명씩 [이 ${data.deepSize}명 비교]를 누르면 항목 판정과 원문 근거를 나란히 볼 수 있어요.`}
      >
        <div className="grid gap-3 md:grid-cols-2">
          {data.groups.map((group) => (
            <GroupCard
              key={`${group.id}-${data.target}-${sort}`}
              group={group}
              size={data.deepSize}
              onDeepDive={onDeepDive}
              pending={deepPending}
            />
          ))}
        </div>
      </Section>

      <Section
        title="항목별 판정"
        caption="분석이 끝난 지원자의 항목별 판정이에요. 충족이 아닌 판정이 많은 항목부터 놓았어요."
        read="오른쪽 %가 높을수록 많은 지원자가 걸리는 항목이에요. 표시한 항목은 공고 문구나 기준을 다시 볼 곳이에요."
        legend={<Legend items={BANDS} />}
        ai={charts.criteria}
      >
        <CriteriaView criteria={data.criteria} />
      </Section>

      <Section
        title="경력 구간별 선 위 비율"
        caption="경력 구간마다 전체 지원자와 선 위 인원을 나란히 세었어요."
        read="괄호 안 %는 그 구간 지원자 중 선 위에 오른 비율이에요. 구간끼리 비율을 견줘 보세요."
        legend={<Legend items={CAREER_LEGEND} />}
        ai={charts.careers}
      >
        <CareerChart data={data} />
      </Section>
    </div>
  )
}

/** 목표 인원 칸. 입력 중에는 다시 세지 않고, Enter나 칸을 떠날 때 넘긴다 */
function TargetInput({ value, onChange }: { value: number; onChange: (next: number) => void }) {
  const [draft, setDraft] = useState(String(value))
  const commit = () => {
    const next = Number.parseInt(draft, 10)
    if (Number.isFinite(next) && next > 0 && next !== value) onChange(next)
    else setDraft(String(value))
  }
  return (
    <label className="flex items-center gap-2 text-sm font-semibold">
      서류 통과 목표
      <Input
        aria-label="서류 통과 목표 인원"
        inputMode="numeric"
        value={draft}
        onChange={(event) => setDraft(event.target.value.replace(/\D/g, ''))}
        onBlur={commit}
        onKeyDown={(event) => event.key === 'Enter' && commit()}
        className="h-8 w-20 text-right"
      />
      명
    </label>
  )
}

/**
 * 차트 한 칸. 제목 아래 무엇을 셌는지(caption)와 어떻게 읽는지(read)를 나눠 적고, 범례는 제목 줄 오른쪽에 둔다.
 * 그림을 보기 전에 읽는 법과 색의 뜻을 먼저 알게 하고, 그림 아래에는 Report Agent의 해석(ai)을 붙인다.
 */
function Section({
  title,
  caption,
  read,
  legend,
  ai,
  children,
}: {
  title: string
  caption: string
  read?: string
  legend?: ReactNode
  /** Report Agent가 이 차트를 읽고 쓴 한 문장. 해설을 만들지 못하면 없다 */
  ai?: string
  children: ReactNode
}) {
  return (
    <section className="flex flex-col gap-3 rounded-lg border bg-background px-5 py-4">
      <div className="flex flex-col gap-1.5">
        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
          <h3 className="text-sm font-bold">{title}</h3>
          {legend}
        </div>
        <p className="text-xs text-muted-foreground">{caption}</p>
        {read && (
          <p className="flex gap-1.5 rounded-md bg-muted/60 px-2.5 py-1.5 text-xs">
            <span className="shrink-0 font-semibold text-ai">읽는 법</span>
            <span>{read}</span>
          </p>
        )}
      </div>
      {children}
      {ai && (
        <p className="flex gap-1.5 rounded-md border border-ai/20 bg-ai-soft/50 px-2.5 py-1.5 text-xs">
          <span className="shrink-0 font-semibold text-ai">◇ AI 해석</span>
          <span>{ai}</span>
        </p>
      )}
    </section>
  )
}

/** 제목 줄 오른쪽 범례. 색 칸과 글자를 함께 적는다 */
function Legend({ items }: { items: readonly { label: string; color: string }[] }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
      {items.map((item) => (
        <span key={item.label} className="inline-flex items-center gap-1">
          <i className="inline-block size-2.5 rounded-sm" style={{ background: item.color }} />
          {item.label}
        </span>
      ))}
    </div>
  )
}

/**
 * 맨 위 요약. 코드가 센 숫자 요약과, Report Agent가 그 숫자를 읽고 먼저 볼 점을 쓴 AI 해설을 나눠 보여 준다.
 * 해설은 따로 불러오고, 만들지 못하면 숫자 요약만 남는다
 */
function Insights({
  data,
  note,
  noteLoading,
}: {
  data: ReportDistribution
  note?: string[]
  noteLoading: boolean
}) {
  const lines = insightLines(data)
  return (
    <section className="flex flex-col gap-3 rounded-lg border border-ai/30 bg-ai-soft/60 px-5 py-4">
      <div>
        <div className="flex items-baseline gap-2">
          <h3 className="text-sm font-bold text-ai">한눈에 보기</h3>
          <span className="text-[11px] text-muted-foreground">숫자로 센 요약이에요</span>
        </div>
        <ul className="mt-2 flex flex-col gap-1.5 text-sm">
          {lines.map((line) => (
            <li key={line} className="flex gap-2">
              <span className="mt-2 size-1.5 shrink-0 rounded-full bg-ai" />
              {line}
            </li>
          ))}
        </ul>
      </div>
      {(noteLoading || (note?.length ?? 0) > 0) && (
        <div className="rounded-md border border-ai/20 bg-background px-3 py-2.5">
          <div className="flex items-baseline gap-2">
            <span className="text-xs font-bold text-ai">◇ AI 해설</span>
            <span className="text-[11px] text-muted-foreground">
              Report Agent가 위 숫자를 읽고 먼저 볼 점을 정리했어요
            </span>
          </div>
          {noteLoading ? (
            <p className="mt-1.5 flex items-center gap-1.5 text-xs text-muted-foreground">
              <Loader2 className="size-3.5 animate-spin" />
              숫자를 읽고 해설을 쓰는 중이에요
            </p>
          ) : (
            <ul className="mt-1.5 flex flex-col gap-1 text-sm">
              {note?.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}

/** 전체 → 분석 완료 → 선 위 → 목표. 막대 폭은 전체 지원자 대비다 */
function Funnel({ data }: { data: ReportDistribution }) {
  const gap = data.aboveLine - data.target
  const passed = data.passed ?? null
  const steps = [
    { label: '전체 지원자', value: data.total, color: SEQ[1] },
    { label: '서류 분석 완료', value: data.analyzed, color: SEQ[2] },
    { label: '선 위 (필수 조건 충족)', value: data.aboveLine, color: SEQ[4] },
    { label: '서류 통과 목표', value: data.target, color: ACCENT },
    // 담당자가 실제로 합격 처리한 인원. 목표를 넘겨도 막지 않고 차이만 보여 준다
    ...(passed === null ? [] : [{ label: '합격 처리', value: passed, color: STATUS.MET.fg }]),
  ]
  const max = Math.max(1, ...steps.map((step) => step.value))
  return (
    <div className="flex flex-col gap-2">
      {steps.map((step, index) => (
        <div key={step.label} className="flex items-center gap-3">
          <span className="w-36 shrink-0 text-right text-xs font-medium text-muted-foreground">
            {step.label}
          </span>
          <div className="flex h-9 flex-1 justify-center rounded-md bg-muted/50">
            <div
              className="flex items-center justify-center rounded-md text-sm font-bold text-white transition-[width]"
              style={{ width: `${Math.max(6, (100 * step.value) / max)}%`, background: step.color }}
            >
              {step.value.toLocaleString()}명
            </div>
          </div>
          <span className="w-24 shrink-0 text-xs text-muted-foreground">
            {index === 0 ? '' : `전체의 ${percent(step.value, data.total)}%`}
          </span>
        </div>
      ))}
      <div className="flex justify-end">
        <span
          className={cn(
            'rounded-full px-2.5 py-0.5 text-xs font-semibold',
            gap > 0
              ? 'bg-[#F6EDD9] text-[#7A5A1E]'
              : gap < 0
                ? 'bg-[#F5E3DF] text-[#8E3F33]'
                : 'bg-[#E4EFE8] text-[#2F6B4C]',
          )}
        >
          {gap > 0
            ? `선 위가 목표보다 ${gap}명 많아요`
            : gap < 0
              ? `선 위가 목표보다 ${-gap}명 적어요`
              : '선 위가 목표와 같아요'}
        </span>
        {passed !== null && passed > 0 && (
          <span
            className={cn(
              'ml-2 rounded-full px-2.5 py-0.5 text-xs font-semibold',
              passed > data.target ? 'bg-[#F6EDD9] text-[#7A5A1E]' : 'bg-[#E4EFE8] text-[#2F6B4C]',
            )}
          >
            {passed > data.target
              ? `합격 처리가 목표보다 ${passed - data.target}명 많아요`
              : `합격 처리 ${passed}명 · 목표까지 ${data.target - passed}명`}
          </span>
        )}
      </div>
    </div>
  )
}

/** 필수 조건 도넛과, 많이 걸리는 필수 조건 */
function RequiredView({ data }: { data: ReportDistribution }) {
  const { met, unmet, unknown } = data.required
  const parts = useMemo(
    () => [
      { label: '모두 충족', value: met, color: STATUS.MET.bar },
      { label: '미충족', value: unmet, color: STATUS.NOT_MET.bar },
      { label: '확인 필요', value: unknown, color: STATUS.UNKNOWN.bar },
    ],
    [met, unmet, unknown],
  )
  const whole = met + unmet + unknown
  const option = useMemo<EChartsCoreOption>(
    () => ({
      tooltip: { trigger: 'item', formatter: '{b} {c}명 ({d}%)' },
      title: {
        text: `${percent(met, whole)}%`,
        subtext: '모두 충족',
        left: 'center',
        top: '36%',
        textStyle: { fontSize: 24, fontWeight: 700, color: INK },
        subtextStyle: { fontSize: 11, color: SUB },
      },
      series: [
        {
          type: 'pie',
          radius: ['58%', '84%'],
          label: { show: false },
          itemStyle: { borderColor: '#fff', borderWidth: 2 },
          data: parts.map((part) => ({
            name: part.label,
            value: part.value,
            itemStyle: { color: part.color },
          })),
        },
      ],
    }),
    [parts, met, whole],
  )
  const hardest = data.criteria
    .filter((criterion) => criterion.required && judged(criterion) > 0)
    .sort((a, b) => issueRate(b) - issueRate(a))
    .slice(0, 3)
  return (
    <div className="grid items-center gap-4 md:grid-cols-[200px_1fr_1.4fr]">
      <EChart option={option} height={190} label="필수 조건 판정 도넛" />
      <ul className="flex flex-col gap-2">
        {parts.map((part) => (
          <li key={part.label} className="flex items-center gap-2">
            <i className="inline-block size-3 rounded-sm" style={{ background: part.color }} />
            <span className="text-xs text-muted-foreground">{part.label}</span>
            <b className="ml-auto text-base">{part.value.toLocaleString()}명</b>
            <span className="w-10 text-right text-xs text-muted-foreground">
              {percent(part.value, whole)}%
            </span>
          </li>
        ))}
      </ul>
      {hardest.length > 0 && (
        <div className="flex flex-col gap-2 rounded-md bg-muted/50 px-3 py-2.5">
          <span className="text-xs font-semibold">많이 걸리는 필수 조건</span>
          {hardest.map((criterion) => (
            <div key={criterion.criterionId} className="flex flex-col gap-1">
              <div className="flex items-baseline gap-1.5 text-xs">
                <b className="text-muted-foreground">{criterion.criterionId}</b>
                <span className="line-clamp-1">{criterion.text}</span>
                <span className="ml-auto shrink-0 font-semibold text-[#8E3F33]">
                  {issueRate(criterion)}%
                </span>
              </div>
              <StackBar compact bare parts={bands(criterion)} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const bands = (criterion: Criterion) =>
  BANDS.map((band) => ({ label: band.label, value: criterion[band.key], color: band.color }))

/** 인원 비율 막대. 넓은 칸 안에는 비율을, 아래에는 칸마다 이름과 인원을 적는다 */
function StackBar({
  parts,
  compact = false,
  bare = false,
}: {
  parts: { label: string; value: number; color: string }[]
  compact?: boolean
  /** 아래 이름표를 뺀다 */
  bare?: boolean
}) {
  const total = parts.reduce((sum, part) => sum + part.value, 0)
  return (
    <div className="flex flex-col gap-1">
      <div className={cn('flex w-full overflow-hidden rounded bg-muted', compact ? 'h-4' : 'h-6')}>
        {total > 0 &&
          parts
            .filter((part) => part.value > 0)
            .map((part) => {
              const share = (100 * part.value) / total
              return (
                <div
                  key={part.label}
                  title={`${part.label} ${part.value}명`}
                  className="flex items-center justify-center text-[10px] font-semibold text-[#22262B]/80"
                  style={{ width: `${share}%`, background: part.color }}
                >
                  {share >= 12 && `${Math.round(share)}%`}
                </div>
              )
            })}
      </div>
      {!bare && (
        <div className="flex flex-wrap gap-x-3 text-[11px] text-muted-foreground">
          {parts.map((part) => (
            <span key={part.label} className="inline-flex items-center gap-1">
              <i className="inline-block size-2 rounded-sm" style={{ background: part.color }} />
              {part.label} {part.value}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

/** 선 위 지원자의 개수별 인원과 누적 인원. 누적이 목표선을 넘는 개수가 선발이 갈리는 곳이다 */
function CountChart({ data }: { data: ReportDistribution }) {
  const option = useMemo<EChartsCoreOption>(() => {
    const bars = data.counts.map((bucket, index) => {
      const cumulative = data.counts
        .slice(0, index + 1)
        .reduce((sum, earlier) => sum + earlier.count, 0)
      const inside = cumulative <= data.target
      const color = inside ? ACCENT : data.cut?.value === bucket.value ? EDGE : OUTSIDE
      return {
        value: bucket.count,
        cumulative,
        itemStyle: { color, borderRadius: [3, 3, 0, 0] },
      }
    })
    return {
      tooltip: { trigger: 'axis' },
      grid: { left: 52, right: 60, top: 32, bottom: 36 },
      xAxis: {
        type: 'category',
        name: '충족한 항목 수',
        nameLocation: 'middle',
        nameGap: 24,
        data: data.counts.map((bucket) => `${bucket.value}개`),
        axisLabel: { color: SUB },
        axisLine: { lineStyle: { color: GRID } },
      },
      yAxis: [
        {
          type: 'value',
          name: '인원(막대)',
          axisLabel: { color: MUTED },
          splitLine: { lineStyle: { color: GRID } },
        },
        {
          type: 'value',
          name: '누적 인원(선)',
          axisLabel: { color: MUTED },
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name: '인원',
          type: 'bar',
          barMaxWidth: 44,
          data: bars,
          itemStyle: { color: ACCENT },
          label: { show: true, position: 'top', formatter: '{c}명', color: INK, fontSize: 11 },
        },
        {
          name: '누적 인원',
          type: 'line',
          yAxisIndex: 1,
          data: bars.map((bar) => bar.cumulative),
          symbol: 'circle',
          symbolSize: 6,
          lineStyle: { color: SUB, width: 1.5 },
          itemStyle: { color: SUB },
          markLine: {
            silent: true,
            symbol: 'none',
            lineStyle: { color: ACCENT, type: 'dashed', width: 1.5 },
            label: { formatter: `목표 ${data.target}명`, color: ACCENT, position: 'insideEndTop' },
            data: [{ yAxis: data.target }],
          },
        },
      ],
    }
  }, [data.counts, data.cut, data.target])

  if (data.counts.length === 0) {
    return <p className="text-xs text-muted-foreground">선 위 지원자가 아직 없어요.</p>
  }
  return <EChart option={option} height={280} label="선 위 충족 개수별 인원" />
}

/** 항목별 판정. 충족이 아닌 판정이 많은 순으로 놓고 앞 몇 개를 표시한다 */
function CriteriaView({ criteria }: { criteria: Criterion[] }) {
  const sorted = [...criteria].sort((a, b) => issueRate(b) - issueRate(a))
  const flagged = new Set(
    sorted
      .filter((criterion) => issueRate(criterion) > 0)
      .slice(0, FLAGGED)
      .map((criterion) => criterion.criterionId),
  )
  return (
    <div className="flex flex-col gap-2.5">
      {sorted.map((criterion) => (
        <div
          key={criterion.criterionId}
          className={cn(
            'grid gap-1 rounded-md px-2 py-1.5 md:grid-cols-[minmax(0,2fr)_3fr_auto] md:items-center',
            flagged.has(criterion.criterionId) && 'bg-[#F5E3DF]/50',
          )}
        >
          <div className="flex items-start gap-1.5 text-xs">
            <span className="shrink-0 font-semibold text-muted-foreground">
              {criterion.criterionId}
            </span>
            {criterion.required && (
              <span className="shrink-0 rounded bg-ai-soft px-1 text-[10.5px] font-semibold text-ai">
                필수
              </span>
            )}
            <span className="line-clamp-2">{criterion.text}</span>
          </div>
          <StackBar compact bare={!flagged.has(criterion.criterionId)} parts={bands(criterion)} />
          <div className="flex items-center gap-1.5 text-xs md:w-32 md:justify-end">
            {flagged.has(criterion.criterionId) && (
              <span className="rounded bg-[#F5E3DF] px-1.5 py-0.5 text-[10.5px] font-semibold text-[#8E3F33]">
                기준 다시 볼 항목
              </span>
            )}
            <span
              className="font-semibold"
              title="충족이 아닌 판정(부분 · 미충족 · 확인 필요)의 비율"
            >
              {issueRate(criterion)}%
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}

/** 경력 구간별 전체와 선 위 인원. 선 위 막대 위에 그 구간의 선 위 비율을 적는다 */
function CareerChart({ data }: { data: ReportDistribution }) {
  const option = useMemo<EChartsCoreOption>(
    () => ({
      tooltip: { trigger: 'axis' },
      grid: { left: 40, right: 16, top: 24, bottom: 24 },
      xAxis: {
        type: 'category',
        data: data.careers.map((band) => band.label),
        axisLabel: { color: SUB },
        axisLine: { lineStyle: { color: GRID } },
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: MUTED },
        splitLine: { lineStyle: { color: GRID } },
      },
      series: [
        {
          name: '전체',
          type: 'bar',
          barGap: '8%',
          barMaxWidth: 36,
          itemStyle: { color: SEQ[1], borderRadius: [3, 3, 0, 0] },
          label: { show: true, position: 'top', color: SUB, fontSize: 11 },
          data: data.careers.map((band) => band.all),
        },
        {
          name: '선 위',
          type: 'bar',
          barMaxWidth: 36,
          itemStyle: { color: ACCENT, borderRadius: [3, 3, 0, 0] },
          label: {
            show: true,
            position: 'top',
            color: ACCENT,
            fontSize: 11,
            fontWeight: 700,
            formatter: ({ dataIndex }: { dataIndex: number }) => {
              const band = data.careers[dataIndex]
              return band ? `${band.aboveLine} (${percent(band.aboveLine, band.all)}%)` : ''
            },
          },
          data: data.careers.map((band) => band.aboveLine),
        },
      ],
    }),
    [data.careers],
  )
  return <EChart option={option} height={240} label="경력 구간별 인원" />
}

/** 경계 그룹 한 칸. 비교는 한 번에 size명씩 보고, 이전 · 다음으로 넘긴다 */
function GroupCard({
  group,
  size,
  onDeepDive,
  pending,
}: {
  group: Group
  size: number
  onDeepDive: (applicationIds: string[]) => void
  pending: boolean
}) {
  const [page, setPage] = useState(0)
  const pages = Math.ceil(group.people.length / size)
  const shown = group.people.slice(page * size, page * size + size)
  return (
    <div className="flex flex-col gap-2 rounded-md border px-4 py-3">
      <div className="flex items-baseline justify-between gap-2">
        <h4 className="text-sm font-bold">{group.label}</h4>
        <span className="text-xs text-muted-foreground">{group.people.length}명</span>
      </div>
      <p className="text-xs text-muted-foreground">{group.reason}</p>
      {group.people.length === 0 ? (
        <p className="py-2 text-xs text-muted-foreground">해당하는 지원자가 없어요.</p>
      ) : (
        <>
          <ul className="flex flex-col divide-y text-xs">
            {shown.map((person) => (
              <li key={person.applicationId} className="flex flex-col gap-0.5 py-1.5">
                <div className="flex items-center gap-2">
                  <b>{person.name}</b>
                  <span className="text-muted-foreground">
                    {person.careerYears == null
                      ? ''
                      : person.careerYears === 0
                        ? '신입'
                        : `경력 ${person.careerYears}년`}
                  </span>
                  <span className="ml-auto text-muted-foreground">
                    충족 {person.metCount}/{person.criterionTotal}
                    {person.unknownCount > 0 && ` · 확인 필요 ${person.unknownCount}`}
                    {person.partialCount > 0 && ` · 부분 ${person.partialCount}`}
                  </span>
                </div>
                {person.missingRequired.length > 0 && (
                  <span className="line-clamp-1 text-muted-foreground">
                    필수 조건: {person.missingRequired.join(', ')}
                  </span>
                )}
              </li>
            ))}
          </ul>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              disabled={pending || shown.length < 2}
              onClick={() => onDeepDive(shown.map((person) => person.applicationId))}
            >
              {pending && <Loader2 className="animate-spin" />}이 {shown.length}명 비교
            </Button>
            {pages > 1 && (
              <div className="ml-auto flex items-center gap-1">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page === 0}
                  onClick={() => setPage(page - 1)}
                >
                  <ChevronLeft />
                  이전 {size}명
                </Button>
                <span className="w-10 text-center text-xs text-muted-foreground">
                  {page + 1}/{pages}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page === pages - 1}
                  onClick={() => setPage(page + 1)}
                >
                  다음 {size}명
                  <ChevronRight />
                </Button>
              </div>
            )}
          </div>
          {shown.length < 2 && (
            <p className="text-[11px] text-muted-foreground">비교는 2명부터 볼 수 있어요.</p>
          )}
        </>
      )}
    </div>
  )
}
