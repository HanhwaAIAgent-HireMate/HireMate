import { ChevronRight } from 'lucide-react'

import { STAGE_TYPE_LABELS, type StageType } from '@/features/recruit/labels'
import { cn } from '@/lib/utils'

type Stage = { name: string; type: StageType }

/** 전형 절차를 가로로 나열한다. 종류는 "· 서류"처럼 이름 옆에 붙인다 (기획 v7 §4). */
export function StageFlow({
  stages,
  showType = true,
  highlight,
  className,
}: {
  stages: Stage[]
  showType?: boolean
  highlight?: boolean
  className?: string
}) {
  const items = [
    ...stages.map((stage) => ({ ...stage, final: false })),
    { name: '최종 합격', type: null, final: true },
  ]
  return (
    <div className={cn('flex flex-wrap items-center gap-1.5', className)}>
      {items.map((stage, index) => (
        <span key={`${stage.name}-${index}`} className="inline-flex items-center gap-1.5">
          {index > 0 && <ChevronRight className="size-3 text-muted-foreground" />}
          <span
            className={cn(
              'inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs',
              highlight && !stage.final
                ? 'bg-pass text-foreground'
                : 'bg-muted text-muted-foreground',
            )}
          >
            {stage.name}
            {showType && stage.type && (
              <span className="font-semibold text-ai">· {STAGE_TYPE_LABELS[stage.type]}</span>
            )}
          </span>
        </span>
      ))}
    </div>
  )
}
