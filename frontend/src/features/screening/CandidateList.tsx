import { ListChecks, ListFilter, Search } from 'lucide-react'
import { Fragment, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Skeleton } from '@/components/ui/skeleton'
import {
  useCandidates,
  useRequirements,
  useSelectionActions,
  useUpdateRequirements,
  type CandidateRow,
  type CandidateSort,
  type StageOverview,
} from '@/features/screening/api'
import { RowButton } from '@/features/screening/CandidateItem'
import { CandidateTile } from '@/features/screening/CandidateTile'
import { useStageUi } from '@/features/screening/store'
import { GROUP_LABELS, useCandidateTable } from '@/features/screening/table'
import { errorMessage } from '@/lib/api/client'
import { cn } from '@/lib/utils'

type Filter = 'ALL' | 'PENDING' | 'PASS' | 'FAIL'

const FILTERS: Record<Filter, string> = {
  ALL: '전체',
  PENDING: '미결정',
  PASS: '합격',
  FAIL: '불합격',
}

const SORTS: Record<CandidateSort, string> = {
  BASIC: '기본',
  TALENT: '인재상 포함',
}

const SORT_HINTS: Record<CandidateSort, string> = {
  BASIC: '자격요건 + 우대사항에서 충족한 개수가 많은 순 (같으면 이름 순)',
  TALENT: '자격요건 + 우대사항 + 인재상(상)에서 충족한 개수가 많은 순 (같으면 이름 순)',
}

// 왼쪽 전체 지원자. 한 줄에 카드 3장이다. 서류 전형은 필수 조건을 모두 채운 지원자가 충족 개수 순으로 먼저 서고,
// 필수 조건을 못 채운 지원자는 회색으로 맨 아래에 모인다. 점수는 보여 주지 않는다
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
  const [filter, setFilter] = useState<Filter>('ALL')
  const [sort, setSort] = useState<CandidateSort>('BASIC')
  const candidates = useCandidates(stageId, tabId, debounced, sort)
  const actions = useSelectionActions(stageId, tabId ?? '')
  const { openId, open } = useStageUi()
  const sentinel = useRef<HTMLDivElement>(null)
  const documentStage = overview.type === 'DOCUMENT'

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

  const rows = (candidates.data?.pages.flatMap((page) => page.items) ?? []).filter(
    (row) => filter === 'ALL' || row.decision === filter,
  )
  const total = candidates.data?.pages[0]?.total ?? overview.counts.total
  const firstBelow = documentStage ? rows.findIndex((row) => !row.aboveLine) : -1
  // 선 위 지원자가 먼저 서므로, 거르지 않았으면 전체 수에서 선 위 수를 빼면 아직 안 불러온 카드까지 센 선 아래 수다
  const below = filter === 'ALL' ? total - firstBelow : rows.length - firstBelow
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

  return (
    <section className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-2 px-4 pt-4 pb-3">
        <h2 className="mr-auto text-sm font-bold">
          전체 지원자 <span className="ml-1 text-muted-foreground">{total}</span>
        </h2>
        {documentStage && <RequirementsMenu stageId={stageId} editable={editable} />}
        <DropdownMenu>
          <DropdownMenuTrigger
            aria-label="결정 상태로 거르기"
            className="text-muted-foreground hover:text-foreground"
          >
            <ListFilter className="size-4" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuRadioGroup
              value={filter}
              onValueChange={(value) => setFilter(value as Filter)}
            >
              {(Object.keys(FILTERS) as Filter[]).map((key) => (
                <DropdownMenuRadioItem key={key} value={key}>
                  {FILTERS[key]}
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      {documentStage && (
        <div
          role="tablist"
          aria-label="정렬"
          className="mx-4 mb-2 flex rounded-lg bg-muted p-0.5 text-xs"
        >
          {(Object.keys(SORTS) as CandidateSort[]).map((key) => (
            <button
              key={key}
              type="button"
              role="tab"
              title={SORT_HINTS[key]}
              aria-selected={sort === key}
              onClick={() => setSort(key)}
              className={cn(
                'h-7 flex-1 rounded-md',
                sort === key
                  ? 'bg-background font-semibold shadow-sm'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {SORTS[key]}
            </button>
          ))}
        </div>
      )}
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
              {debounced ? '조건에 맞는 지원자가 없어요.' : '아직 지원자가 없어요.'}
            </p>
          )}
          {rows.map((row, index) => (
            <Fragment key={row.applicationId}>
              {index === firstBelow && (
                <p className="col-span-3 mt-2 flex items-center gap-2 text-[11px] text-muted-foreground">
                  <span className="h-px flex-1 bg-border" />
                  필수 조건 미충족 {below}명
                  <span className="h-px flex-1 bg-border" />
                </p>
              )}
              <CandidateTile
                row={row}
                documentStage={documentStage}
                scoreStage={overview.type === 'ASSESSMENT'}
                active={openId === row.applicationId}
                action={action(row)}
                onOpen={() => open({ applicationId: row.applicationId, name: row.name })}
              />
            </Fragment>
          ))}
        </div>
        <div ref={sentinel} className="h-4" />
      </div>
    </section>
  )
}

/**
 * 필수 조건 체크. 자격요건 · 우대사항 가운데 체크한 항목을 모두 충족한 지원자만 선 위(AI 단계)에 오른다.
 * 체크하면 바로 저장하고 리스트를 다시 세운다
 */
function RequirementsMenu({ stageId, editable }: { stageId: string; editable: boolean }) {
  const table = useCandidateTable(stageId)
  const required = useRequirements(stageId, true)
  const update = useUpdateRequirements(stageId)
  const criteria = (table.data?.features ?? []).filter((feature) => feature.group !== 'TALENT')
  const chosen = required.data ?? []

  const toggle = (id: string, checked: boolean) => {
    const next = checked ? [...chosen, id] : chosen.filter((item) => item !== id)
    update.mutate(next, { onError: (error) => toast.error(errorMessage(error)) })
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        title="필수 조건: 모두 충족한 지원자만 선 위(AI 단계)에 올라가요"
        className="inline-flex h-7 items-center gap-1 rounded-md border px-2 text-xs text-muted-foreground hover:text-foreground"
      >
        <ListChecks className="size-3.5" />
        필수 조건 {chosen.length}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72">
        <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
          체크한 조건을 모두 충족한 지원자만 선 위(AI 단계)에 올라가요.
        </DropdownMenuLabel>
        {table.isPending && <Skeleton className="m-1.5 h-24" />}
        {(['QUALIFICATION', 'PREFERENCE'] as const).map((group) => {
          const items = criteria.filter((feature) => feature.group === group)
          if (items.length === 0) return null
          return (
            <Fragment key={group}>
              <DropdownMenuSeparator />
              <DropdownMenuLabel className="text-xs">{GROUP_LABELS[group]}</DropdownMenuLabel>
              {items.map((feature) => (
                <DropdownMenuCheckboxItem
                  key={feature.id}
                  title={feature.text}
                  checked={chosen.includes(feature.id)}
                  disabled={!editable || update.isPending || required.isPending}
                  onSelect={(event) => event.preventDefault()}
                  onCheckedChange={(checked) => toggle(feature.id, checked === true)}
                >
                  {feature.label}
                </DropdownMenuCheckboxItem>
              ))}
            </Fragment>
          )
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
