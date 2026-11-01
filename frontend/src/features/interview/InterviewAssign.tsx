import { LockKeyhole, UsersRound } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useStageInterviewProgress } from '@/features/interview/live'
import { RoleTag } from '@/features/interview/RoleTag'
import {
  useAssignStageInterview,
  useInterviewMembers,
  useStageInterviewAssignment,
} from '@/features/interview/sessions'
import { ApiError, errorMessage } from '@/lib/api/client'

/** 면접 전형에 한 번 정하는 공통 면접관. 지원자별 질문, 일정, 입장 상태와 구분한다. */
export function InterviewAssign({ stageId, editable }: { stageId: string; editable: boolean }) {
  const assignment = useStageInterviewAssignment(stageId)
  const members = useInterviewMembers()
  const assign = useAssignStageInterview(stageId)
  const progress = useStageInterviewProgress(stageId)
  const [open, setOpen] = useState(false)
  const [hr, setHr] = useState('')
  const [practical, setPractical] = useState('')
  const [expectedVersion, setExpectedVersion] = useState<number | null>(null)
  const current = assignment.data
  const locked = current?.locked || progress.data?.some((row) => row.status !== 'SCHEDULED')
  const conflicting =
    assignment.error instanceof ApiError &&
    assignment.error.code === 'INTERVIEW_ASSIGNMENT_CONFLICT'
  const canEdit =
    editable && !locked && !assignment.isPending && (!assignment.isError || conflicting)
  const name = (memberId: string) =>
    members.data?.find((member) => member.memberId === memberId)?.name ?? '이름 확인 중'

  function configure() {
    setHr(conflicting ? '' : (current?.hrMemberId ?? ''))
    setPractical(conflicting ? '' : (current?.practicalMemberId ?? ''))
    setExpectedVersion(conflicting ? null : (current?.version ?? null))
    setOpen(true)
  }

  return (
    <section
      aria-label="전형 면접관"
      className="flex shrink-0 flex-wrap items-center gap-x-6 gap-y-3 border-b bg-surface/50 px-5 py-3"
    >
      <div className="mr-auto">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <UsersRound className="size-4" />
          전형 면접관
        </h2>
        <p className="mt-1 text-xs text-muted-foreground">
          이 전형의 모든 지원자에게 공통으로 적용해요.
        </p>
      </div>
      {assignment.isPending ? (
        <p role="status" className="text-xs text-muted-foreground">
          면접관을 불러오는 중이에요.
        </p>
      ) : assignment.isError ? (
        <div role="alert" className="flex items-center gap-2 text-xs text-destructive">
          {conflicting ? errorMessage(assignment.error) : '면접관 배정을 불러오지 못했어요.'}
          {!conflicting && (
            <Button size="sm" variant="outline" onClick={() => void assignment.refetch()}>
              다시 불러오기
            </Button>
          )}
        </div>
      ) : current ? (
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <span className="flex items-center gap-2">
            <RoleTag role="HR" questionText="인사 면접관" />
            <b>{name(current.hrMemberId)}</b>
          </span>
          <span className="flex items-center gap-2">
            <RoleTag role="PRACTICAL" questionText="실무 면접관" />
            <b>{name(current.practicalMemberId)}</b>
          </span>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">인사와 실무 면접관을 한 번 배정해 주세요.</p>
      )}
      {canEdit && (
        <Button size="sm" variant={current ? 'outline' : 'default'} onClick={configure}>
          {current ? '면접관 변경' : '면접관 배정'}
        </Button>
      )}
      {locked && editable && (
        <p className="flex w-full items-center gap-1.5 text-xs text-muted-foreground">
          <LockKeyhole className="size-3.5" />
          면접이 시작된 지원자가 있어 전형의 면접관을 바꿀 수 없어요.
        </p>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>전형 면접관 설정</DialogTitle>
            <DialogDescription>
              현재 지원자와 이후 이 전형에 들어오는 지원자에게 공통으로 적용해요. 면접이 하나라도
              시작되면 변경할 수 없어요.
            </DialogDescription>
          </DialogHeader>
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
                disabled={!canEdit || assign.isPending}
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
          {members.isError && (
            <p role="alert" className="text-xs text-destructive">
              면접관 계정을 불러오지 못했어요. 잠시 후 다시 열어 주세요.
            </p>
          )}
          {members.data?.length === 0 && (
            <p className="text-xs text-destructive">아직 면접관 계정이 없어요.</p>
          )}
          <p className="text-xs text-muted-foreground">
            면접관 계정은{' '}
            <Link to="/hr/settings/interviewers" className="underline underline-offset-4">
              설정 › 면접관
            </Link>
            에서 만들어요.
          </p>
          <DialogFooter>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={assign.isPending}
            >
              취소
            </Button>
            <Button
              size="sm"
              disabled={
                !canEdit ||
                !hr ||
                !practical ||
                hr === practical ||
                assign.isPending ||
                members.isError
              }
              onClick={() =>
                assign.mutate(
                  { hrMemberId: hr, practicalMemberId: practical, expectedVersion },
                  {
                    onSuccess: () => {
                      toast.success('전형의 모든 지원자에게 면접관을 적용했어요.')
                      setOpen(false)
                    },
                    onError: (error) => toast.error(errorMessage(error)),
                  },
                )
              }
            >
              {hr && hr === practical ? '서로 다른 계정을 골라 주세요' : '전형 전체에 적용'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  )
}
