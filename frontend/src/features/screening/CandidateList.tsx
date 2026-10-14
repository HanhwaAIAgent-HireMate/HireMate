import { ListFilter, Search } from 'lucide-react'
import { Fragment, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Skeleton } from '@/components/ui/skeleton'
import {
  useCandidates,
  useSelectionActions,
  type CandidateRow,
  type StageOverview,
} from '@/features/screening/api'
import { CandidateItem, RowButton } from '@/features/screening/CandidateItem'
import { useStageUi } from '@/features/screening/store'
import { errorMessage } from '@/lib/api/client'

type Filter = 'ALL' | 'PENDING' | 'PASS' | 'FAIL'

const FILTERS: Record<Filter, string> = {
  ALL: '전체',
  PENDING: '미결정',
  PASS: '합격',
  FAIL: '불합격',
}

// 왼쪽 전체 지원자. 서류 전형은 점수 높은 순, 기준을 넘은 지원자는 굵게, 못 미친 지원자는 선 아래 회색이다
export function CandidateList({
  overview,
  editable,
}: {
  overview: StageOverview
  editable: boolean
}) {
  const stageId = overview.stageId
  const [query, setQuery] = useState('')
  const [debounced, setDebounced] = useState('')
  const [filter, setFilter] = useState<Filter>('ALL')
  const candidates = useCandidates(stageId, debounced)
  const actions = useSelectionActions(stageId)
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
  const fail = (error: unknown) => toast.error(errorMessage(error))

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
    <section className="flex min-h-0 w-[300px] shrink-0 flex-col border-r">
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
      <div className="min-h-0 flex-1 space-y-1 overflow-auto px-3 pb-4">
        {candidates.isPending &&
          Array.from({ length: 6 }, (_, index) => <Skeleton key={index} className="h-12 w-full" />)}
        {!candidates.isPending && rows.length === 0 && (
          <p className="px-2 py-8 text-center text-sm text-muted-foreground">
            {debounced ? '조건에 맞는 지원자가 없어요.' : '아직 지원자가 없어요.'}
          </p>
        )}
        {rows.map((row, index) => (
          <Fragment key={row.applicationId}>
            {index === firstBelow && index > 0 && <hr className="mx-1 my-2 border-border" />}
            <CandidateItem
              row={row}
              documentStage={documentStage}
              active={openId === row.applicationId}
              action={action(row)}
              onOpen={() => open({ applicationId: row.applicationId, name: row.name })}
            />
          </Fragment>
        ))}
        <div ref={sentinel} className="h-4" />
      </div>
    </section>
  )
}
