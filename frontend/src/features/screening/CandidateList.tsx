import { ListFilter, Search } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Skeleton } from '@/components/ui/skeleton'
import { OpinionBadges } from '@/features/interview/OpinionBadges'
import { useStageOpinions } from '@/features/interview/opinions'
import {
  useCandidates,
  useSelectionActions,
  type CandidateRow,
  type CandidateSort,
  type StageOverview,
} from '@/features/screening/api'
import { CandidateItem, RowButton } from '@/features/screening/CandidateItem'
import { useStageUi } from '@/features/screening/store'
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
  QUALIFICATION: '자격요건 순',
  TOTAL: '총점 순',
}

// 왼쪽 전체 지원자. 서류 전형은 자격요건 순(같으면 총점 순)으로 한 줄로 서고 총점 순으로도 볼 수 있다.
// AI 추천(선발 인원 10배수)은 굵게, 추천 밖은 회색이다
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
  const [sort, setSort] = useState<CandidateSort>('QUALIFICATION')
  const candidates = useCandidates(stageId, tabId, debounced, sort)
  const actions = useSelectionActions(stageId, tabId ?? '')
  const { openId, open } = useStageUi()
  const sentinel = useRef<HTMLDivElement>(null)
  const documentStage = overview.type === 'DOCUMENT'
  // 면접 전형은 지원자마다 면접관 의견을 배지로 보인다 (결정은 HR이 결정 바에서 한다)
  const opinions = useStageOpinions(stageId, overview.type === 'INTERVIEW')

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
  const fail = (error: unknown) => toast.error(errorMessage(error))

  const action = (row: CandidateRow) => {
    if (!editable) return null
    if (documentStage && !row.aboveLine) {
      return (
        <RowButton
          kind="up"
          label={`${row.name} AI 추천으로 올리기`}
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
      <div className="flex items-center justify-between px-4 pt-4 pb-3">
        <h2 className="text-sm font-bold">
          전체 지원자 <span className="ml-1 text-muted-foreground">{total}</span>
        </h2>
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
      <div className="min-h-0 flex-1 space-y-1 overflow-auto px-3 pt-1.5 pb-4">
        {candidates.isPending &&
          Array.from({ length: 6 }, (_, index) => <Skeleton key={index} className="h-12 w-full" />)}
        {!candidates.isPending && rows.length === 0 && (
          <p className="px-2 py-8 text-center text-sm text-muted-foreground">
            {debounced ? '조건에 맞는 지원자가 없어요.' : '아직 지원자가 없어요.'}
          </p>
        )}
        {rows.map((row) => (
          <CandidateItem
            key={row.applicationId}
            row={row}
            documentStage={documentStage}
            scoreStage={overview.type === 'ASSESSMENT'}
            active={openId === row.applicationId}
            action={action(row)}
            note={
              overview.type === 'INTERVIEW' ? (
                <OpinionBadges
                  row={opinions.data?.find((item) => item.applicationId === row.applicationId)}
                />
              ) : undefined
            }
            onOpen={() => open({ applicationId: row.applicationId, name: row.name })}
          />
        ))}
        <div ref={sentinel} className="h-4" />
      </div>
    </section>
  )
}
