import { ChevronLeft, ChevronRight } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

/**
 * 목록 아래의 쪽 번호. page는 0부터 센다. 쪽이 하나뿐이면 그리지 않는다.
 * 쪽이 많으면 지금 쪽 앞뒤 2쪽과 처음 · 끝만 보이고 사이는 … 로 줄인다
 */
export function Pager({
  page,
  pageCount,
  onChange,
  label = '쪽 이동',
  className,
}: {
  page: number
  pageCount: number
  onChange: (page: number) => void
  label?: string
  className?: string
}) {
  if (pageCount <= 1) return null
  const shown = Array.from({ length: pageCount }, (_, index) => index).filter(
    (index) => index === 0 || index === pageCount - 1 || Math.abs(index - page) <= 2,
  )
  return (
    <nav aria-label={label} className={cn('flex items-center justify-center gap-1', className)}>
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label="이전 쪽"
        disabled={page === 0}
        onClick={() => onChange(page - 1)}
      >
        <ChevronLeft />
      </Button>
      {shown.map((index, order) => (
        <span key={index} className="inline-flex items-center gap-1">
          {order > 0 && index - shown[order - 1] > 1 && (
            <span className="px-1 text-xs text-muted-foreground">…</span>
          )}
          <Button
            variant={index === page ? 'default' : 'ghost'}
            size="icon-sm"
            aria-label={`${index + 1}쪽`}
            aria-current={index === page ? 'page' : undefined}
            onClick={() => onChange(index)}
          >
            {index + 1}
          </Button>
        </span>
      ))}
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label="다음 쪽"
        disabled={page === pageCount - 1}
        onClick={() => onChange(page + 1)}
      >
        <ChevronRight />
      </Button>
    </nav>
  )
}
