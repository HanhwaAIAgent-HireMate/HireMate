import { Check, ChevronRight } from 'lucide-react'
import { Link } from 'react-router'

import { currentPath, type RecruitmentCard } from '@/features/dashboard/api'
import { RECRUITMENT_STATUS_LABELS } from '@/features/recruit/labels'
import { formatMonthDay } from '@/lib/format'
import { cn } from '@/lib/utils'
import { StageIcon } from '@/features/recruit/StageIcon'

const BADGE: Record<RecruitmentCard['status'], string> = {
  DRAFT: 'bg-muted text-muted-foreground',
  PUBLISHED: 'border text-foreground',
  IN_PROGRESS: 'bg-foreground text-background',
  CLOSED: 'border text-muted-foreground',
}

// DSH-01 채용 카드. 공고에서 정한 전형과 현재 단계를 보여 주고, 끝난 전형은 회색이다
export function RecruitmentCardItem({ card }: { card: RecruitmentCard }) {
  const meta =
    card.status === 'DRAFT'
      ? '공고 작성 중'
      : card.status === 'PUBLISHED' && card.closeAt
        ? `접수 ~${formatMonthDay(card.closeAt)} · 지원자 ${card.applicantCount}명`
        : `지원자 ${card.applicantCount}명`
  const steps = [
    {
      key: 'posting',
      label: '공고',
      count: card.status === 'PUBLISHED' ? card.applicantCount : null,
      state: card.status === 'DRAFT' ? 'draft' : card.status === 'PUBLISHED' ? 'active' : 'done',
      type: null,
      icon: null,
    },
    ...card.steps.map((step) => ({
      key: step.stageId,
      label: step.name,
      type: step.type,
      icon: step.icon,
      count:
        step.stageId === card.currentStageId && card.status === 'IN_PROGRESS'
          ? step.targetCount
          : null,
      state:
        card.status === 'DRAFT'
          ? 'draft'
          : step.status === 'DONE'
            ? 'done'
            : step.stageId === card.currentStageId && card.status === 'IN_PROGRESS'
              ? 'active'
              : 'pending',
    })),
  ]

  return (
    <Link
      to={currentPath(card)}
      className="flex items-center gap-4 rounded-xl border px-5 py-4 transition-colors hover:border-foreground/20 hover:bg-muted/30"
    >
      <div className="min-w-0 flex-1 space-y-3">
        <div className="flex items-center gap-2">
          <h2 className="truncate font-bold">{card.title}</h2>
          <span
            className={cn(
              'shrink-0 rounded-md px-1.5 py-0.5 text-xs font-semibold',
              BADGE[card.status],
            )}
          >
            {RECRUITMENT_STATUS_LABELS[card.status]}
          </span>
          <span className="truncate text-xs text-muted-foreground">{meta}</span>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {steps.map((step, index) => (
            <span key={step.key} className="inline-flex items-center gap-1.5">
              {index > 0 && <ChevronRight className="size-3 text-muted-foreground" />}
              <span
                className={cn(
                  'inline-flex h-6 items-center gap-1 rounded-full px-2.5 text-xs',
                  step.state === 'active' && 'bg-foreground font-semibold text-background',
                  step.state === 'done' && 'bg-muted text-muted-foreground/70',
                  step.state === 'pending' && 'bg-muted text-muted-foreground',
                  step.state === 'draft' && 'border border-dashed text-muted-foreground',
                )}
              >
                {step.state === 'done' && <Check className="size-3" />}
                {step.state !== 'done' && step.type && (
                  <StageIcon type={step.type} icon={step.icon} />
                )}
                {step.label}
                {step.count != null && <span>{step.count}</span>}
              </span>
            </span>
          ))}
        </div>
      </div>
      <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
    </Link>
  )
}
