import { Check, ChevronRight, X } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { currentPath, useDeleteRecruitment, type RecruitmentCard } from '@/features/dashboard/api'
import { RECRUITMENT_STATUS_LABELS } from '@/features/recruit/labels'
import { errorMessage } from '@/lib/api/client'
import { formatMonthDay } from '@/lib/format'
import { cn } from '@/lib/utils'

const BADGE: Record<RecruitmentCard['status'], string> = {
  DRAFT: 'bg-muted text-muted-foreground',
  PUBLISHED: 'border text-foreground',
  IN_PROGRESS: 'bg-foreground text-background',
  CLOSED: 'border text-muted-foreground',
}

// DSH-01 채용 카드. 공고에서 정한 전형과 현재 단계를 보여 주고, 끝난 전형은 회색이다
export function RecruitmentCardItem({ card }: { card: RecruitmentCard }) {
  const [confirming, setConfirming] = useState(false)
  const deletion = useDeleteRecruitment(card.recruitmentId)
  const draft = card.status === 'DRAFT'
  const deleteLabel = draft ? '작성 중 공고 삭제' : '종료된 공고 삭제'
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
    },
    ...card.steps.map((step) => ({
      key: step.stageId,
      label: step.name,
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
    <div className="relative">
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
                  {step.label}
                  {step.count != null && <span>{step.count}</span>}
                </span>
              </span>
            ))}
          </div>
        </div>
        <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
      </Link>
      {(draft || card.status === 'CLOSED') && (
        <AlertDialog
          open={confirming}
          onOpenChange={(open) => {
            if (!deletion.isPending) setConfirming(open)
          }}
        >
          <AlertDialogTrigger asChild>
            <button
              type="button"
              aria-label={`${card.title} ${deleteLabel}`}
              title={deleteLabel}
              className="absolute top-1 right-1 z-10 flex size-6 translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-black text-white ring-2 ring-background transition-colors hover:bg-black/75 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            >
              <X className="size-3.5" strokeWidth={2.5} aria-hidden="true" />
            </button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>
                {draft ? '작성 중인' : '종료된'} 공고를 삭제할까요?
              </AlertDialogTitle>
              <AlertDialogDescription className="break-words">
                {draft
                  ? `‘${card.title}’ 공고와 작성한 전형 구성이 함께 삭제돼요. 삭제한 내용은 복구할 수 없어요.`
                  : `‘${card.title}’ 공고를 채용 목록에서 삭제해요. 지원자와 평가 기록은 보관되며, 목록으로 되돌릴 수 없어요.`}
              </AlertDialogDescription>
            </AlertDialogHeader>
            {deletion.isError && (
              <p role="alert" className="text-sm text-destructive">
                {errorMessage(deletion.error, '공고를 삭제하지 못했어요. 다시 시도해 주세요.')}
              </p>
            )}
            <AlertDialogFooter>
              <AlertDialogCancel disabled={deletion.isPending}>취소</AlertDialogCancel>
              <Button
                variant="destructive"
                disabled={deletion.isPending}
                onClick={() =>
                  deletion.mutate(undefined, {
                    onSuccess: () => {
                      setConfirming(false)
                      toast.success(
                        draft
                          ? '작성 중인 공고를 삭제했어요.'
                          : '종료된 공고를 목록에서 삭제했어요.',
                      )
                    },
                  })
                }
              >
                {deletion.isPending ? '삭제 중…' : '삭제'}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      )}
    </div>
  )
}
