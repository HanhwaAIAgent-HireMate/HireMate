import { Plus, Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'

import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useDashboard, type StatusFilter } from '@/features/dashboard/api'
import { RecruitmentCardItem } from '@/features/dashboard/RecruitmentCardItem'
import { lastPostingStep } from '@/features/posting/posting-progress'
import { useMe } from '@/lib/auth'
import { cn } from '@/lib/utils'

const TABS: {
  key: StatusFilter
  label: string
  count: 'all' | 'draft' | 'published' | 'inProgress' | 'closed'
}[] = [
  { key: 'ALL', label: '전체', count: 'all' },
  { key: 'DRAFT', label: '작성 중', count: 'draft' },
  { key: 'PUBLISHED', label: '공고 게시 중', count: 'published' },
  { key: 'IN_PROGRESS', label: '전형 진행 중', count: 'inProgress' },
  { key: 'CLOSED', label: '종료', count: 'closed' },
]

// DSH-01 Hiring Dashboard. 진행 중인 채용과 전형 단계를 한눈에 본다
export function DashboardPage() {
  const [status, setStatus] = useState<StatusFilter>('ALL')
  const [query, setQuery] = useState('')
  const [debounced, setDebounced] = useState('')
  const dashboard = useDashboard(status, debounced)
  const me = useMe()

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(query.trim()), 250)
    return () => clearTimeout(timer)
  }, [query])

  return (
    <div>
      <div className="flex items-center justify-between border-b px-6 py-4">
        <h1 className="text-xl font-bold">채용</h1>
        <Button asChild>
          <Link to="/hr/recruitments/new">
            <Plus />새 채용
          </Link>
        </Button>
      </div>
      <div className="mx-auto max-w-[1040px] space-y-4 px-6 py-5">
        <div className="flex items-center gap-6">
          <nav role="tablist" className="flex flex-1 gap-5 border-b text-sm">
            {TABS.map((tab) => (
              <button
                key={tab.key}
                role="tab"
                aria-selected={status === tab.key}
                onClick={() => setStatus(tab.key)}
                className={cn(
                  '-mb-px border-b-2 pb-2.5',
                  status === tab.key
                    ? 'border-foreground font-bold'
                    : 'border-transparent text-muted-foreground',
                )}
              >
                {tab.label} {dashboard.data?.counts[tab.count] ?? ''}
              </button>
            ))}
          </nav>
          <label className="flex h-10 w-[220px] items-center gap-2 rounded-lg border px-3 text-sm">
            <Search className="size-4 text-muted-foreground" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="채용명 검색"
              aria-label="채용명 검색"
              className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-muted-foreground"
            />
          </label>
        </div>
        <div className="space-y-3">
          {dashboard.isPending &&
            Array.from({ length: 3 }, (_, index) => (
              <Skeleton key={index} className="h-20 w-full" />
            ))}
          {dashboard.data?.items.length === 0 && (
            <div className="rounded-xl border border-dashed px-6 py-14 text-center">
              <p className="text-sm text-muted-foreground">
                {debounced || status !== 'ALL'
                  ? '조건에 맞는 채용이 없어요.'
                  : '아직 채용이 없어요. 새 채용으로 공고 작성부터 시작해요.'}
              </p>
            </div>
          )}
          {dashboard.data?.items.map((card) => (
            <RecruitmentCardItem
              key={card.recruitmentId}
              card={card}
              resumeStep={lastPostingStep(me.data, card.recruitmentId)}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
