import { useStageInterviewProgress } from '@/features/interview/live'
import { INTERVIEW_STATUS_LABELS } from '@/features/interview/sessions'
import { cn } from '@/lib/utils'

/** 지원자별로 달라지는 면접 진행과 입장 현황. 면접관 구성은 전형 상단에서만 바꾼다. */
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
      className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg bg-muted/40 px-3 py-2 text-xs"
    >
      <span
        className={cn(
          'rounded px-1.5 py-0.5 font-semibold',
          current.status === 'IN_PROGRESS'
            ? 'bg-amber-100 text-amber-800'
            : 'bg-muted text-muted-foreground',
        )}
      >
        면접 {INTERVIEW_STATUS_LABELS[current.status]}
      </span>
      <ul aria-label="면접관 입장 상태" className="flex flex-wrap gap-x-4 gap-y-1">
        {current.attendees.map((attendee) => (
          <li key={attendee.memberId} className="flex items-center gap-1.5">
            <span>
              {attendee.role === 'HR' ? '인사' : '실무'} {attendee.name}
            </span>
            <span
              className={cn(
                'flex items-center gap-1 text-muted-foreground',
                attendee.entered && attendee.online && 'text-emerald-700',
                attendee.entered && !attendee.online && 'text-amber-800',
              )}
            >
              <span aria-hidden="true" className="size-1.5 rounded-full bg-current" />
              {!attendee.entered ? '입장 대기' : attendee.online ? '접속 중' : '접속 끊김'}
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}
