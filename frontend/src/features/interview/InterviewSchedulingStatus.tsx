import { Link } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import {
  useInterviewScheduling,
  useRetryInterviewScheduling,
} from '@/features/interview/scheduling'
import { ApiError, errorMessage } from '@/lib/api/client'

/**
 * 결과 확정 뒤 면접 일정 배정 상태를 알린다. 합격 안내는 배정을 마친 뒤에 보낸다.
 * guidesPath는 다음 전형 안내(면접 날짜)를 고치는 합격 안내 메일 화면이다
 */
export function InterviewSchedulingStatus({
  stageId,
  guidesPath,
}: {
  stageId: string
  guidesPath: string
}) {
  const state = useInterviewScheduling(stageId)
  const retry = useRetryInterviewScheduling(stageId)
  if (state.data?.status === 'NOT_APPLICABLE') return null
  const status = state.data?.status
  return (
    <section
      aria-label="면접 일정 배정"
      className="space-y-2 rounded-lg border bg-muted/30 p-3 text-sm"
    >
      <p role="status" aria-live="polite">
        {state.isError
          ? '면접 일정 배정 상태를 불러오지 못했어요.'
          : !state.data
            ? '면접 일정 배정 상태를 확인하고 있어요.'
            : status === 'READY'
              ? '면접 일정 배정 완료. 면접 화면에 지원자별 일정을 반영했어요.'
              : status === 'DATE_REQUIRED'
                ? '합격 안내 메일 화면의 다음 전형 안내에 면접 날짜를 정해 주세요. 정하면 바로 배정해요.'
                : status === 'FAILED'
                  ? errorMessage(
                      new ApiError(409, state.data.errorCode ?? 'INTERVIEW_SCHEDULE_FAILED', ''),
                    )
                  : status === 'NOT_REQUESTED'
                    ? '면접 일정 배정이 필요해요.'
                    : '면접 일정을 배정하고 있어요. 완료된 일정은 면접 화면에서 확인할 수 있어요.'}
      </p>
      {state.isError && (
        <Button size="sm" variant="outline" onClick={() => void state.refetch()}>
          다시 불러오기
        </Button>
      )}
      {['DATE_REQUIRED', 'FAILED', 'NOT_REQUESTED', 'PENDING'].includes(status ?? '') && (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" asChild>
            <Link to={guidesPath}>면접 날짜 정하기</Link>
          </Button>
          <Button
            size="sm"
            disabled={retry.isPending}
            onClick={() =>
              retry.mutate(undefined, {
                onError: (error) => toast.error(errorMessage(error)),
              })
            }
          >
            일정 배정 다시 시도
          </Button>
        </div>
      )}
    </section>
  )
}
