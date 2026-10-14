import { Check, ChevronRight } from 'lucide-react'
import { Link } from 'react-router'

import { cn } from '@/lib/utils'

export type StepItem = {
  key: string
  label: string
  count?: number | null
  state: 'done' | 'active' | 'pending'
  to?: string
}

/** 공고에서 정한 전형 순서와 대상 인원. 끝난 단계는 회색 체크, 현재 단계는 검은 칩이다. */
export function WorkflowStepper({ items }: { items: StepItem[] }) {
  return (
    <nav
      aria-label="채용 단계"
      className="flex items-center gap-1.5 overflow-x-auto border-b px-5 py-2.5"
    >
      {items.map((item, index) => {
        const chip = (
          <span
            className={cn(
              'inline-flex h-7 items-center gap-1 rounded-full px-3 text-xs whitespace-nowrap',
              item.state === 'active' && 'bg-foreground font-semibold text-background',
              item.state === 'done' && 'text-muted-foreground',
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
  )
}
