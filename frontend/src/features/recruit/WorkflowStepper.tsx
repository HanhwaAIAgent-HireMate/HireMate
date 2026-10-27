import { Check, ChevronRight } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'

import { cn } from '@/lib/utils'

export type StepItem = {
  key: string
  label: string
  count?: number | null
  /** done: 끝난 단계, active: 보고 있는 단계, ongoing: 진행 중이지만 보고 있지 않은 단계, pending: 아직 시작 전 */
  state: 'done' | 'active' | 'ongoing' | 'pending'
  to?: string
}

/**
 * 공고에서 정한 전형 순서와 대상 인원. 끝난 단계는 회색 체크, 보고 있는 단계는 검은 칩, 진행 중인 단계는 진한 글자다.
 * 시작한 단계는 모두 눌러 볼 수 있다. 끝난 단계는 화면만 보고 고치지 못한다 (전형 화면이 막는다).
 * actions는 같은 줄 오른쪽 끝에 둔다. 단계가 많아 넘치면 단계만 가로로 스크롤된다.
 */
export function WorkflowStepper({ items, actions }: { items: StepItem[]; actions?: ReactNode }) {
  return (
    <div className="flex items-center gap-3 border-b px-5 py-2.5">
      <nav aria-label="채용 단계" className="flex min-w-0 items-center gap-1.5 overflow-x-auto">
        {items.map((item, index) => {
          const chip = (
            <span
              className={cn(
                'inline-flex h-7 items-center gap-1 rounded-full px-3 text-xs whitespace-nowrap',
                item.state === 'active' && 'bg-foreground font-semibold text-background',
                item.state === 'done' && 'text-muted-foreground',
                item.state === 'ongoing' && 'font-semibold text-foreground',
                item.state === 'pending' && 'text-muted-foreground',
                item.to && item.state !== 'active' && 'hover:bg-muted',
              )}
            >
              {item.state === 'done' && <Check className="size-3" />}
              {item.label}
              {item.count != null && (
                <span className={cn(item.state !== 'active' && 'font-semibold')}>{item.count}</span>
              )}
            </span>
          )
          return (
            <span key={item.key} className="inline-flex items-center gap-1.5">
              {index > 0 && <ChevronRight className="size-3 shrink-0 text-muted-foreground" />}
              {item.to && item.state !== 'pending' ? <Link to={item.to}>{chip}</Link> : chip}
            </span>
          )
        })}
      </nav>
      {actions && <div className="ml-auto flex shrink-0 items-center gap-4 text-sm">{actions}</div>}
    </div>
  )
}
