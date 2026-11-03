import { attendeeState, useStageInterviewProgress } from '@/features/interview/live'
import { INTERVIEW_STATUS_LABELS, INTERVIEW_STATUS_STYLES } from '@/features/interview/sessions'
import { formatDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'

/** 지원자별로 달라지는 면접 진행과 면접관 준비 · 종료 현황. 면접관 구성은 전형 상단에서만 바꾼다. */
export function CandidateInterviewProgress({
  stageId,
  applicationId,
}: {
  stageId: string
  applicationId: string
}) {
  const progress = useStageInterviewProgress(stageId)
  const current = progress.data?.find((row) => row.applicationId === applicationId)
  if (progress.isError)
    return <p className="text-xs text-muted-foreground">면접 진행 현황을 불러오지 못했어요.</p>
  if (!current) return null
  return (
    <section
      aria-label="지원자 면접 진행 현황"
      aria-live="polite"
      className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg bg-muted/40 py-2 text-xs"
    >
      <span
        className={cn(
          'rounded px-1.5 py-0.5 font-semibold',
          INTERVIEW_STATUS_STYLES[current.status],
        )}
      >
        면접 {INTERVIEW_STATUS_LABELS[current.status]}
      </span>
      <span className="text-muted-foreground">
        {current.scheduledAt ? formatDateTime(current.scheduledAt) : '일정 미정'}
      </span>
      <ul aria-label="면접관 준비 상태" className="flex flex-wrap gap-x-4 gap-y-1">
        {current.attendees.map((attendee) => {
          const state = attendeeState(attendee, current.status)
          return (
            <li key={attendee.memberId} className="flex min-w-0 flex-wrap items-center gap-1.5">
              <span className="font-medium break-words">
                {attendee.role === 'HR' ? '인사' : '실무'} {attendee.name}
              </span>
              <span
                className={cn(
                  'flex shrink-0 items-center gap-1 whitespace-nowrap text-muted-foreground',
                  state.tone === 'active' && 'text-emerald-700',
                  state.tone === 'warn' && 'text-amber-800',
                )}
              >
                <span aria-hidden="true" className="size-1.5 rounded-full bg-current" />
                {state.label}
              </span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
