import { cn } from 'cn'
import { Loader2 } from 'lucide-react'
import { useState, type ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { errorMessage } from '@/lib/api/client'

import { useReportDistribution, type DistributionSort, type ReportDistribution } from './api'
import { STATUS } from './palette'

type Group = ReportDistribution['groups'][number]

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

/**
 * 분포 리포트. 서류 전형 지원자 전원의 판정을 backend가 센 그대로 보여 준다. 모델은 쓰지 않는다.
 * 서류 통과 목표 인원은 처음에 공고 채용 인원 × 배수이고, 바꾸면 바로 다시 센다(저장하지 않는다).
 * 경계 그룹에서 [심층 분석]을 누르면 그 그룹의 몇 명으로 비교 리포트를 요청한다.
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
  const data = query.data

  if (query.isError) {
    return <p className="text-sm text-muted-foreground">{errorMessage(query.error)}</p>
  }
  if (!data) return <Skeleton className="h-96 w-full" />

  const gap = data.aboveLine - data.target
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

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Tile label="전체 지원자" value={data.total} />
        <Tile label="서류 분석 완료" value={data.analyzed} />
        <Tile label="선 위" value={data.aboveLine} note="필수 조건 모두 충족 또는 담당자가 올림" />
        <Tile
          label="목표 대비"
          value={Math.abs(gap)}
          note={
            gap > 0
              ? '선 위가 목표보다 많아요'
              : gap < 0
                ? '선 위가 목표보다 적어요'
                : '선 위가 목표와 같아요'
          }
          prefix={gap > 0 ? '+' : gap < 0 ? '−' : ''}
        />
      </div>

      <Section
        title="필수 조건"
        caption={
          data.required.criterionIds.length === 0
            ? '체크한 필수 조건이 없어 분석이 끝난 지원자가 모두 선 위에 올라요.'
            : '필수 조건을 모두 충족한 사람, 하나라도 미충족 · 부분 충족인 사람, 확인 필요만 남은 사람이에요.'
        }
      >
        <StackBar
          parts={[
            { label: '충족', value: data.required.met, color: STATUS.MET.bar },
            { label: '미충족', value: data.required.unmet, color: STATUS.NOT_MET.bar },
            { label: '확인 필요', value: data.required.unknown, color: STATUS.UNKNOWN.bar },
          ]}
        />
      </Section>

      <Section
        title="항목별 판정"
        caption="분석이 끝난 지원자의 항목별 판정이에요. 미충족이나 확인 필요가 많은 항목은 공고 문구나 기준을 다시 볼 곳이에요."
      >
        <div className="flex flex-col gap-2.5">
          {data.criteria.map((criterion) => (
            <div
              key={criterion.criterionId}
              className="grid gap-1 md:grid-cols-[minmax(0,2fr)_3fr]"
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
              <StackBar
                compact
                parts={BANDS.map((band) => ({
                  label: band.label,
                  value: criterion[band.key],
                  color: band.color,
                }))}
              />
            </div>
          ))}
        </div>
      </Section>

      <Section
        title="선 위 충족 개수별 인원"
        caption={
          data.cut
            ? `목표 ${data.target}명째가 충족 ${data.cut.value}개예요. ${data.cut.from}~${data.cut.to}번째 ${
                data.cut.to - data.cut.from + 1
              }명이 모두 ${data.cut.value}개라 개수로는 구분되지 않아요. 이 중 ${data.cut.inside}명만 목표 안에 들어요.`
            : '선 위가 목표 인원 이하라 개수로 갈리는 구간이 없어요. 선 아래 다시 볼 사람을 먼저 보세요.'
        }
      >
        <CountBars data={data} />
      </Section>

      <Section
        title="경계 그룹"
        caption="코드가 정한 임시 기준으로 모은 사람이에요. 추천이나 순위가 아니고, 담당자가 다시 볼 사람이에요."
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

      <Section title="지원자 구성" caption="경력 구간별 전체 지원자와 선 위 인원이에요.">
        <div className="grid grid-cols-5 gap-2 text-center text-xs">
          {data.careers.map((band) => (
            <div key={band.label} className="rounded-md bg-muted/60 px-2 py-2">
              <div className="text-muted-foreground">{band.label}</div>
              <div className="mt-0.5 text-base font-bold">{band.all}</div>
              <div className="text-[11px] text-muted-foreground">선 위 {band.aboveLine}</div>
            </div>
          ))}
        </div>
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

function Tile({
  label,
  value,
  note,
  prefix = '',
}: {
  label: string
  value: number
  note?: string
  prefix?: string
}) {
  return (
    <div className="rounded-lg border bg-background px-4 py-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-xl font-bold">
        {prefix}
        {value.toLocaleString()}
        <span className="ml-0.5 text-xs font-medium text-muted-foreground">명</span>
      </div>
      {note && <div className="text-[11px] text-muted-foreground">{note}</div>}
    </div>
  )
}

function Section({
  title,
  caption,
  children,
}: {
  title: string
  caption: string
  children: ReactNode
}) {
  return (
    <section className="flex flex-col gap-3 rounded-lg border bg-background px-5 py-4">
      <div>
        <h3 className="text-sm font-bold">{title}</h3>
        <p className="mt-0.5 text-xs text-muted-foreground">{caption}</p>
      </div>
      {children}
    </section>
  )
}

/** 인원 비율 막대. 칸마다 이름과 인원을 아래에 적는다 */
function StackBar({
  parts,
  compact = false,
}: {
  parts: { label: string; value: number; color: string }[]
  compact?: boolean
}) {
  const total = parts.reduce((sum, part) => sum + part.value, 0)
  return (
    <div className="flex flex-col gap-1">
      <div className={cn('flex w-full overflow-hidden rounded bg-muted', compact ? 'h-3' : 'h-5')}>
        {total > 0 &&
          parts
            .filter((part) => part.value > 0)
            .map((part) => (
              <div
                key={part.label}
                title={`${part.label} ${part.value}명`}
                style={{ width: `${(100 * part.value) / total}%`, background: part.color }}
              />
            ))}
      </div>
      <div className="flex flex-wrap gap-x-3 text-[11px] text-muted-foreground">
        {parts.map((part) => (
          <span key={part.label} className="inline-flex items-center gap-1">
            <i className="inline-block size-2 rounded-sm" style={{ background: part.color }} />
            {part.label} {part.value}
          </span>
        ))}
      </div>
    </div>
  )
}

/** 선 위 지원자의 개수별 인원. 목표 인원 자리의 개수를 강조한다 */
function CountBars({ data }: { data: ReportDistribution }) {
  if (data.counts.length === 0) {
    return <p className="text-xs text-muted-foreground">선 위 지원자가 아직 없어요.</p>
  }
  const max = Math.max(...data.counts.map((bucket) => bucket.count))
  return (
    <div className="flex flex-col gap-1">
      {data.counts.map((bucket) => {
        const edge = data.cut?.value === bucket.value
        return (
          <div key={bucket.value} className="flex items-center gap-2 text-xs">
            <span className={cn('w-14 shrink-0 text-right', edge && 'font-bold text-ai')}>
              {bucket.value}개
            </span>
            <div className="h-4 flex-1">
              <div
                className={cn('h-full rounded-sm', edge ? 'bg-ai' : 'bg-[#98ABCC]')}
                style={{ width: `${Math.max(2, (100 * bucket.count) / max)}%` }}
              />
            </div>
            <span className={cn('w-12 shrink-0', edge && 'font-bold text-ai')}>
              {bucket.count}명
            </span>
          </div>
        )
      })}
    </div>
  )
}

/** 경계 그룹 한 칸. 심층 분석은 한 번에 size명씩 본다 */
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
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              disabled={pending || shown.length < 2}
              onClick={() => onDeepDive(shown.map((person) => person.applicationId))}
            >
              {pending && <Loader2 className="animate-spin" />}이 {shown.length}명 심층 분석
            </Button>
            {pages > 1 && (
              <Button variant="outline" size="sm" onClick={() => setPage((page + 1) % pages)}>
                다음 {size}명 ({page + 1}/{pages})
              </Button>
            )}
          </div>
          {shown.length < 2 && (
            <p className="text-[11px] text-muted-foreground">심층 분석은 2명부터 볼 수 있어요.</p>
          )}
        </>
      )}
    </div>
  )
}
