import { LockKeyhole } from 'lucide-react'
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

/**
 * 면접 전형의 [면접관 배정] 버튼. Stage 바의 결정 현황 왼쪽에 들어간다.
 * 면접관은 전형에 한 번 정하고 모든 지원자에게 공통으로 적용한다. 면접이 시작되면 바꿀 수 없어 보기만 한다.
 */
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
  // 불참은 면접을 하지 않은 것이라 배정을 잠그지 않는다 (서버와 같다)
  const locked =
    current?.locked ||
    progress.data?.some((row) => row.status === 'IN_PROGRESS' || row.status === 'ENDED')
  const conflicting =
    assignment.error instanceof ApiError &&
    assignment.error.code === 'INTERVIEW_ASSIGNMENT_CONFLICT'
  const canEdit =
    editable && !locked && !assignment.isPending && (!assignment.isError || conflicting)
  const name = (memberId: string) =>
    members.data?.find((member) => member.memberId === memberId)?.name ?? '이름 확인 중'

  if (assignment.isPending) return null
  if (assignment.isError && !conflicting) {
    return (
      <span role="alert" className="inline-flex items-center gap-2 text-xs text-destructive">
        면접관 배정을 불러오지 못했어요.
        <Button size="sm" variant="outline" onClick={() => void assignment.refetch()}>
          다시 불러오기
        </Button>
      </span>
    )
  }
  // 확정 · 종료된 전형에서 배정한 적이 없으면 보여 줄 것이 없다
  if (!canEdit && !current && !conflicting) return null

  function configure() {
    setHr(conflicting ? '' : (current?.hrMemberId ?? ''))
    setPractical(conflicting ? '' : (current?.practicalMemberId ?? ''))
    setExpectedVersion(conflicting ? null : (current?.version ?? null))
    setOpen(true)
  }

  return (
    <>
      <Button
        variant={canEdit && !current ? 'default' : 'outline'}
        title={
          current
            ? `인사 ${name(current.hrMemberId)} · 실무 ${name(current.practicalMemberId)}`
            : undefined
        }
        onClick={configure}
      >
        {canEdit ? '면접관 배정' : '면접관 보기'}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>면접관 배정</DialogTitle>
            <DialogDescription>
              이 전형의 모든 지원자에게 공통으로 적용해요. 면접이 하나라도 시작되면 바꿀 수 없어요.
            </DialogDescription>
          </DialogHeader>
          {conflicting && (
            <p role="alert" className="text-xs text-destructive">
              {errorMessage(assignment.error)}
            </p>
          )}
          {locked && editable && (
            <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <LockKeyhole className="size-3.5" />
              면접이 시작된 지원자가 있어 면접관을 바꿀 수 없어요.
            </p>
          )}
          {canEdit ? (
            <>
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
                    disabled={assign.isPending}
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
            </>
          ) : (
            current && (
              <ul className="space-y-2 text-sm">
                <li className="flex items-center gap-2">
                  <RoleTag role="HR" questionText="인사 면접관" />
                  <b>{name(current.hrMemberId)}</b>
                </li>
                <li className="flex items-center gap-2">
                  <RoleTag role="PRACTICAL" questionText="실무 면접관" />
                  <b>{name(current.practicalMemberId)}</b>
                </li>
              </ul>
            )
          )}
          <DialogFooter>
            {canEdit ? (
              <>
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
                    !hr || !practical || hr === practical || assign.isPending || members.isError
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
                  {hr && hr === practical ? '서로 다른 계정을 골라 주세요' : '적용'}
                </Button>
              </>
            ) : (
              <Button size="sm" variant="outline" onClick={() => setOpen(false)}>
                닫기
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
