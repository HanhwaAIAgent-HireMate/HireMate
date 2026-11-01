import { UsersRound } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useStageInterviewProgress } from '@/features/interview/live'
import { RoleTag } from '@/features/interview/RoleTag'
import { cn } from '@/lib/utils'
import {
  INTERVIEW_STATUS_LABELS,
  useAssignInterview,
  useInterviewAssignment,
  useInterviewMembers,
} from '@/features/interview/sessions'
import { errorMessage } from '@/lib/api/client'

/**
 * 지원자 카드의 [면접관 배정]: 인사와 실무 면접관 계정을 고른다. 배정된 계정만 면접관 모드에서 이 지원자를 연다.
 * 면접이 시작되면 배정을 바꿀 수 없다.
 */
export function InterviewAssign({
  stageId,
  applicationId,
  editable,
}: {
  stageId: string
  applicationId: string
  /** 진행 중이거나 시작 전인 전형 */
  editable: boolean
}) {
  const [open, setOpen] = useState(false)
  const assignment = useInterviewAssignment(stageId, applicationId)
  const members = useInterviewMembers()
  const assign = useAssignInterview(stageId, applicationId)
  const [hr, setHr] = useState('')
  const [practical, setPractical] = useState('')
  const progress = useStageInterviewProgress(stageId)
  const current = assignment.data
  const live = progress.data?.find((row) => row.applicationId === applicationId)
  const status = live?.status ?? current?.status
  const name = (memberId: string | undefined) =>
    members.data?.find((member) => member.memberId === memberId)?.name ??
    live?.attendees.find((attendee) => attendee.memberId === memberId)?.name ??
    ''
  const locked = !editable || (current != null && status !== 'SCHEDULED')
  const summary = current
    ? `인사 ${name(current.hrMemberId)}, 실무 ${name(current.practicalMemberId)}`
    : '면접관 배정'

  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center justify-end gap-1.5">
        {status && (
          <span
            className={cn(
              'rounded-md px-1.5 py-0.5 text-xs font-medium',
              status === 'IN_PROGRESS'
                ? 'bg-amber-100 text-amber-800'
                : 'bg-muted text-muted-foreground',
            )}
          >
            면접 {INTERVIEW_STATUS_LABELS[status]}
          </span>
        )}
        <Popover
          open={open}
          onOpenChange={(value) => {
            if (value) {
              setHr(current?.hrMemberId ?? '')
              setPractical(current?.practicalMemberId ?? '')
            }
            setOpen(value)
          }}
        >
          <PopoverTrigger asChild>
            <Button size="sm" variant="ghost">
              <UsersRound />
              {summary}
            </Button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-80 space-y-3">
            <div>
              <p className="text-sm font-semibold">면접관 배정</p>
              <p className="text-xs text-muted-foreground">
                배정된 계정만 면접관 모드에서 이 지원자를 열고, 자기 담당 질문에 기록해요.
              </p>
            </div>
            {(
              [
                ['HR', '인사', hr, setHr],
                ['PRACTICAL', '실무', practical, setPractical],
              ] as const
            ).map(([role, label, value, setValue]) => (
              <label key={role} className="block space-y-1.5">
                <RoleTag role={role} questionText={`${label} 면접관`} />
                <select
                  aria-label={`${label} 면접관`}
                  value={value}
                  disabled={locked}
                  onChange={(event) => setValue(event.target.value)}
                  className="h-9 w-full rounded-md border bg-background px-2 text-sm"
                >
                  <option value="">고르기</option>
                  {(members.data ?? []).map((member) => (
                    <option key={member.memberId} value={member.memberId}>
                      {member.name} ({member.email})
                    </option>
                  ))}
                </select>
              </label>
            ))}
            {members.data?.length === 0 && (
              <p className="text-xs text-destructive">아직 면접관 계정이 없어요.</p>
            )}
            <p className="text-xs text-muted-foreground">
              면접관 계정만 배정할 수 있어요. 계정은{' '}
              <Link to="/hr/settings/interviewers" className="underline underline-offset-4">
                설정 › 면접관
              </Link>
              에서 만들어요.
            </p>
            {locked ? (
              <p className="text-xs text-muted-foreground">
                {editable ? '면접이 시작돼 배정을 바꿀 수 없어요.' : '결과를 확정한 전형이에요.'}
              </p>
            ) : (
              <Button
                size="sm"
                className="w-full"
                disabled={!hr || !practical || hr === practical || assign.isPending}
                onClick={() =>
                  assign.mutate(
                    {
                      hrMemberId: hr,
                      practicalMemberId: practical,
                      expectedVersion: current?.version ?? null,
                    },
                    {
                      onSuccess: () => {
                        toast.success('면접관을 배정했어요.')
                        setOpen(false)
                      },
                      onError: (error) => toast.error(errorMessage(error)),
                    },
                  )
                }
              >
                {hr && hr === practical ? '서로 다른 계정을 골라 주세요' : '저장'}
              </Button>
            )}
          </PopoverContent>
        </Popover>
      </div>
      {current && live && (
        <ul
          aria-label="면접관 입장 상태"
          className="flex flex-wrap justify-end gap-x-3 gap-y-1 text-xs"
        >
          {live.attendees.map((attendee) => (
            <li key={attendee.memberId} className="flex items-center gap-1.5">
              <span>
                {attendee.role === 'HR' ? '인사' : '실무'}{' '}
                {attendee.name || name(attendee.memberId)}
              </span>
              <span
                className={cn(
                  'inline-flex items-center gap-1 text-muted-foreground',
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
      )}
      {current && progress.isError && (
        <p className="text-right text-xs text-muted-foreground">입장 현황을 불러오지 못했어요.</p>
      )}
    </div>
  )
}
