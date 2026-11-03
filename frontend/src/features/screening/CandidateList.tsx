import { CalendarClock, CalendarX, ListFilter, Search } from 'lucide-react'
import { Fragment, useEffect, useRef, useState, type ReactNode } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Skeleton } from '@/components/ui/skeleton'
import {
  useInterviewStageLive,
  useStageInterviewProgress,
  type SessionProgress,
} from '@/features/interview/live'
import { useStageSchedules } from '@/features/interview/api'
import { INTERVIEW_STATUS_LABELS, INTERVIEW_STATUS_STYLES } from '@/features/interview/sessions'
import { interviewSlots, slotStatus, type InterviewSlot } from '@/features/interview/slots'
import { OpinionBadges } from '@/features/interview/OpinionBadges'
import { useStageOpinions } from '@/features/interview/opinions'
import {
  isFiltered,
  NO_FILTER,
  useCandidates,
  useSelectionActions,
  type CandidateFilter,
  type CandidateRow,
  type Decision,
  type StageOverview,
} from '@/features/screening/api'
import { RowButton } from '@/features/screening/CandidateItem'
import { CandidateTile } from '@/features/screening/CandidateTile'
import { useStageUi } from '@/features/screening/store'
import { GROUP_LABELS, useCandidateTable, type TableFeature } from '@/features/screening/table'
import { errorMessage } from '@/lib/api/client'
import { formatDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'

const DECISION_LABELS: Record<Decision, string> = {
  PENDING: '미결정',
  PASS: '합격',
  FAIL: '불합격',
}

// 왼쪽 전체 지원자. 한 줄에 카드 3장이다. 서류 전형은 공고의 필수 자격요건을 모두 채운 지원자가
// 자격요건 + 우대사항 충족 개수에 상인 인재상 개수를 더한 순으로 먼저 서고, 필수 자격요건을 못 채운 지원자는
// 회색으로 맨 아래에 모인다. 점수는 보여 주지 않는다
export function CandidateList({
  overview,
  tabId,
  editable,
}: {
  overview: StageOverview
  /** 선택 표시 · 넣기 · 빼기의 기준 탭. 시작하지 않은 전형은 탭이 없다 */
  tabId: string | null
  editable: boolean
}) {
  const stageId = overview.stageId
  const [query, setQuery] = useState('')
  const [debounced, setDebounced] = useState('')
  const [filter, setFilter] = useState<CandidateFilter>(NO_FILTER)
  const candidates = useCandidates(stageId, tabId, debounced, filter)
  const actions = useSelectionActions(stageId, tabId ?? '')
  const { openId, open } = useStageUi()
  const sentinel = useRef<HTMLDivElement>(null)
  const documentStage = overview.type === 'DOCUMENT'
  // 면접 전형은 지원자마다 면접관 의견을 배지로 보인다 (결정은 HR이 결정 바에서 한다)
  const interviewStage = overview.type === 'INTERVIEW'
  const opinions = useStageOpinions(stageId, interviewStage)
  const progress = useStageInterviewProgress(stageId, interviewStage)
  useInterviewStageLive(stageId, interviewStage)
  const progressByApplication = new Map(
    (progress.data ?? []).map((row) => [row.applicationId, row.status]),
  )
  // 면접 전형은 면접 시간별로 나눈다. 같은 시간의 지원자는 한 면접으로 함께 본다
  const schedules = useStageSchedules(stageId, interviewStage)
  const scheduleByApplication = new Map(
    (schedules.data ?? []).map((row) => [row.applicationId, row.scheduledAt]),
  )

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(query.trim()), 250)
    return () => clearTimeout(timer)
  }, [query])

  const { hasNextPage, isFetchingNextPage, fetchNextPage } = candidates
  useEffect(() => {
    const target = sentinel.current
    if (!target) return
    const observer = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting && hasNextPage && !isFetchingNextPage) void fetchNextPage()
    })
    observer.observe(target)
    return () => observer.disconnect()
  }, [hasNextPage, isFetchingNextPage, fetchNextPage])

  const rows = candidates.data?.pages.flatMap((page) => page.items) ?? []
  const total = candidates.data?.pages[0]?.total ?? overview.counts.total
  const filtered = isFiltered(filter)
  const firstBelow = documentStage ? rows.findIndex((row) => !row.aboveLine) : -1
  // 선 위 지원자가 먼저 서므로, 전체 수에서 선 위 수를 빼면 아직 안 불러온 카드까지 센 선 아래 수다 (거르기는 서버가 한다)
  const below = total - firstBelow
  const fail = (error: unknown) => toast.error(errorMessage(error))

  // 회색(필수 조건 미충족) 카드는 ↑로 선 위에 올린다. 올리면 줄을 다시 서고 ↑ 대신 넣기(+)가 생긴다
  const action = (row: CandidateRow) => {
    if (!editable) return null
    if (documentStage && !row.aboveLine) {
      return (
        <RowButton
          kind="up"
          label={`${row.name} 선 위로 올리기`}
          onClick={() => actions.promote.mutate(row.applicationId, { onError: fail })}
        />
      )
    }
    if (!tabId) return null
    if (row.selected) {
      return (
        <RowButton
          kind="remove"
          label={`${row.name} 선택 지원자에서 빼기`}
          onClick={() => actions.remove.mutate([row.applicationId], { onError: fail })}
        />
      )
    }
    return (
      <RowButton
        kind="add"
        label={`${row.name} 선택 지원자에 넣기`}
        disabled={row.decision !== 'PENDING'}
        onClick={() => actions.add.mutate([row.applicationId], { onError: fail })}
      />
    )
  }

  const tile = (row: CandidateRow) => {
    const status = progressByApplication.get(row.applicationId)
    return (
      <CandidateTile
        key={row.applicationId}
        row={row}
        documentStage={documentStage}
        scoreStage={overview.type === 'ASSESSMENT'}
        active={openId === row.applicationId}
        action={action(row)}
        note={
          interviewStage ? (
            <div className="space-y-0.5">
              {/* 면접 상태는 시간 칸 머리글에 한 번 보이고, 카드에는 그 시간에서 빠진 불참만 붙인다 */}
              {status === 'ABSENT' && <InterviewProgressBadge status={status} />}
              {/* 의견은 면접을 마친 뒤에 내므로 종료된 지원자에게만 보인다 */}
              {status === 'ENDED' && (
                <OpinionBadges
                  row={opinions.data?.find((item) => item.applicationId === row.applicationId)}
                />
              )}
            </div>
          ) : undefined
        }
        onOpen={() => open({ applicationId: row.applicationId, name: row.name })}
      />
    )
  }

  return (
    <section className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-2 px-4 pt-4 pb-3">
        <h2 className="shrink-0 text-sm font-bold">
          전체 지원자 <span className="ml-1 text-muted-foreground">{total}</span>
        </h2>
        <FilterMenu
          stageId={stageId}
          documentStage={documentStage}
          filter={filter}
          onApply={setFilter}
        />
      </div>
      <div className="px-4 pb-3">
        <label className="flex h-10 items-center gap-2 rounded-lg border px-3 text-sm">
          <Search className="size-4 text-muted-foreground" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="이름, 경력, 키워드"
            aria-label="지원자 검색"
            className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-muted-foreground"
          />
        </label>
      </div>
      <div className="min-h-0 flex-1 overflow-auto px-3 pt-1.5 pb-4">
        <div className="grid grid-cols-3 gap-2">
          {candidates.isPending &&
            Array.from({ length: 9 }, (_, index) => <Skeleton key={index} className="h-14" />)}
          {!candidates.isPending && rows.length === 0 && (
            <p className="col-span-3 px-2 py-8 text-center text-sm text-muted-foreground">
              {debounced || filtered ? '조건에 맞는 지원자가 없어요.' : '아직 지원자가 없어요.'}
            </p>
          )}
          {interviewStage
            ? interviewSlots(rows, (row) => scheduleByApplication.get(row.applicationId)).map(
                (slot) => (
                  <Fragment key={slot.key}>
                    <SlotHeader
                      slot={slot}
                      statuses={slot.items.flatMap((row) => {
                        const status = progressByApplication.get(row.applicationId)
                        return status ? [status] : []
                      })}
                    />
                    {slot.items.map(tile)}
                  </Fragment>
                ),
              )
            : rows.map((row, index) => (
                <Fragment key={row.applicationId}>
                  {index === firstBelow && (
                    <p className="col-span-3 mt-2 flex items-center gap-2 text-[11px] text-muted-foreground">
                      <span className="h-px flex-1 bg-border" />
                      필수 조건 미충족 {below}명
                      <span className="h-px flex-1 bg-border" />
                    </p>
                  )}
                  {tile(row)}
                </Fragment>
              ))}
        </div>
        <div ref={sentinel} className="h-4" />
      </div>
    </section>
  )
}

/**
 * 거르기. 상태 · 자격요건 · 우대사항 · 인재상을 체크하고 적용하면 맞는 지원자만 보인다. 상태는 하나라도 맞으면 남고,
 * 자격요건 · 우대사항 · 인재상은 고른 항목이 모두 표 보기 표기로 O 또는 중 이상이어야 남는다. 거르는 중이면 아이콘이
 * 보라색이고, 고른 조건을 아이콘 왼쪽에 회색 글씨로 줄여 보여 준다
 */
function FilterMenu({
  stageId,
  documentStage,
  filter,
  onApply,
}: {
  stageId: string
  documentStage: boolean
  filter: CandidateFilter
  onApply: (filter: CandidateFilter) => void
}) {
  const table = useCandidateTable(stageId)
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<CandidateFilter>(filter)
  const features = documentStage ? (table.data?.features ?? []) : []
  const labels = new Map(features.map((feature) => [feature.id, feature.label]))
  const summary = [
    ...filter.decisions.map((decision) => DECISION_LABELS[decision]),
    ...[...filter.criteria, ...filter.talents].map((id) => labels.get(id) ?? id),
  ]
  const filtered = isFiltered(filter)

  const toggle = <K extends keyof CandidateFilter>(
    key: K,
    value: CandidateFilter[K][number],
    checked: boolean,
  ) =>
    setDraft((current) => ({
      ...current,
      [key]: checked
        ? [...current[key], value]
        : (current[key] as string[]).filter((item) => item !== value),
    }))

  return (
    <div className="flex min-w-0 flex-1 items-center justify-end gap-2">
      {filtered && (
        <span title={summary.join('\n')} className="truncate text-xs text-muted-foreground">
          {summary.join(' · ')}
        </span>
      )}
      <Popover
        open={open}
        onOpenChange={(value) => {
          setOpen(value)
          if (value) setDraft(filter)
        }}
      >
        <PopoverTrigger
          aria-label="지원자 거르기"
          className={cn(
            'shrink-0',
            filtered ? 'text-ai hover:text-ai/80' : 'text-muted-foreground hover:text-foreground',
          )}
        >
          <ListFilter className="size-4" />
        </PopoverTrigger>
        <PopoverContent align="end" className="w-72 p-0">
          <div className="max-h-[60vh] space-y-3 overflow-auto p-3">
            <FilterGroup title="상태">
              {(Object.keys(DECISION_LABELS) as Decision[]).map((decision) => (
                <FilterOption
                  key={decision}
                  label={DECISION_LABELS[decision]}
                  checked={draft.decisions.includes(decision)}
                  onChange={(checked) => toggle('decisions', decision, checked)}
                />
              ))}
            </FilterGroup>
            {documentStage && table.isPending && <Skeleton className="h-24" />}
            {(['QUALIFICATION', 'PREFERENCE', 'TALENT'] as const).map((group) => {
              const items = features.filter((feature) => feature.group === group)
              if (items.length === 0) return null
              const key = group === 'TALENT' ? 'talents' : 'criteria'
              return (
                <FilterGroup key={group} title={GROUP_LABELS[group]}>
                  {items.map((feature) => (
                    <FilterOption
                      key={feature.id}
                      feature={feature}
                      label={feature.label}
                      checked={draft[key].includes(feature.id)}
                      onChange={(checked) => toggle(key, feature.id, checked)}
                    />
                  ))}
                </FilterGroup>
              )
            })}
          </div>
          <div className="flex justify-end gap-2 border-t p-2">
            <Button size="sm" variant="ghost" onClick={() => setDraft(NO_FILTER)}>
              초기화
            </Button>
            <Button
              size="sm"
              onClick={() => {
                onApply(draft)
                setOpen(false)
              }}
            >
              적용
            </Button>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  )
}

function FilterGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <fieldset className="space-y-1.5">
      <legend className="mb-1.5 text-xs font-semibold text-muted-foreground">{title}</legend>
      {children}
    </fieldset>
  )
}

function FilterOption({
  label,
  feature,
  checked,
  onChange,
}: {
  label: string
  feature?: TableFeature
  checked: boolean
  onChange: (checked: boolean) => void
}) {
  return (
    <label title={feature?.text} className="flex cursor-pointer items-center gap-2 text-sm">
      <Checkbox checked={checked} onCheckedChange={(value) => onChange(value === true)} />
      <span className="min-w-0 truncate">{label}</span>
      {/* 공고 평가 기준에서 필수로 표시한 자격요건 */}
      {feature?.important && (
        <span className="shrink-0 rounded border bg-muted px-1 text-[10px] leading-4 text-muted-foreground">
          필수
        </span>
      )}
    </label>
  )
}

/** 면접 시간 칸의 머리글: 일시 · 인원 · 그 시간 면접의 상태. 일정 미정 칸은 회색으로 두어 정할 일이 남았음을 보인다 */
function SlotHeader({
  slot,
  statuses,
}: {
  slot: InterviewSlot<CandidateRow>
  statuses: SessionProgress['status'][]
}) {
  const status = statuses.length > 0 ? slotStatus(statuses) : null
  return (
    <div
      role="heading"
      aria-level={3}
      className={cn(
        'col-span-3 mt-3 flex items-center gap-1.5 px-1 text-xs font-semibold first:mt-0',
        !slot.scheduledAt && 'text-muted-foreground',
      )}
    >
      {slot.scheduledAt ? (
        <CalendarClock className="size-3.5" />
      ) : (
        <CalendarX className="size-3.5" />
      )}
      <span>
        {slot.scheduledAt ? formatDateTime(slot.scheduledAt) : '일정 미정'} · {slot.items.length}명
      </span>
      {slot.scheduledAt && status && (
        <span
          className={cn(
            'ml-auto rounded px-1 text-[11px] font-semibold',
            INTERVIEW_STATUS_STYLES[status],
          )}
        >
          면접 {INTERVIEW_STATUS_LABELS[status]}
        </span>
      )}
      {!slot.scheduledAt && (
        <span className="ml-auto font-normal">카드를 열어 면접 일정을 정해 주세요</span>
      )}
    </div>
  )
}

function InterviewProgressBadge({ status }: { status: SessionProgress['status'] | undefined }) {
  if (!status) return null
  return (
    <span
      aria-label={`면접 상태: ${INTERVIEW_STATUS_LABELS[status]}`}
      className={cn(
        'inline-flex rounded px-1 text-[11px] font-semibold',
        INTERVIEW_STATUS_STYLES[status],
      )}
    >
      면접 {INTERVIEW_STATUS_LABELS[status]}
    </span>
  )
}
