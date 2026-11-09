import { Check, CircleCheck, Clock3, Square, UserX, Users } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { toast } from 'sonner'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { ApplicantAvatar } from '@/components/ApplicantAvatar'
import { Button } from '@/components/ui/button'
import { attendeeState, type InterviewAttendance } from '@/features/interview/live'
import { RoleTag } from '@/features/interview/RoleTag'
import {
  INTERVIEW_STATUS_STYLES,
  type AssignedInterview,
  type InterviewerWorkspace,
} from '@/features/interview/sessions'
import { errorMessage } from '@/lib/api/client'
import { formatDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'

/**
 * 면접 시간 한 칸(같은 일시의 지원자 묶음)의 대기, 진행, 종료 상태와 준비 현황. 두 면접관이 모두 [준비 완료]를 누르면
 * 서버가 그 시간 면접자를 한꺼번에 시작한다. [면접 종료]는 확인 뒤에 그 시간 면접자에 대한 내 면접을 마치고,
 * 두 면접관이 모두 마치면 면접이 함께 끝난다. 지금 연 지원자가 오지 않았으면 불참으로 빼고 나머지만 진행한다.
 * memo는 [메모] 버튼 자리다.
 */
export function InterviewSessionBar({
  interview,
  workspace,
  attendance,
  connected,
  busy,
  readying,
  absentPending,
  onReady,
  onCancelReady,
  onEnd,
  onAbsent,
  memo,
}: {
  interview: AssignedInterview
  workspace: InterviewerWorkspace | undefined
  attendance: InterviewAttendance | undefined
  connected: boolean
  busy: boolean
  readying: boolean
  absentPending: boolean
  onReady: () => Promise<unknown>
  onCancelReady: () => Promise<unknown>
  onEnd: () => Promise<unknown>
  onAbsent: (absent: boolean) => Promise<unknown>
  memo?: ReactNode
}) {
  const [confirm, setConfirm] = useState(false)
  const group = workspace?.group
  const status = group?.status ?? workspace?.session.status
  const self = workspace?.session.status
  const scheduledAt = group?.scheduledAt ?? null
  const members = group?.members ?? []
  const present = members.filter((member) => member.status !== 'ABSENT')
  const blocked = present.filter((member) => member.blocker)
  const answered = members.find(
    (member) => member.applicationId === interview.applicationId,
  )?.answered
  const mine = (workspace?.questions ?? []).filter(
    (item) => item.question.interviewerRole === workspace?.myRole,
  )
  const recorded = mine.filter((item) => item.question.answer.trim()).length
  const attendees = attendance?.attendees ?? []
  const me = attendees.find((attendee) => attendee.me)
  const myEnded = status === 'IN_PROGRESS' && !!me?.ended
  const together = present.length > 1 ? ` ${present.length}명` : ''
  // 준비 완료를 받아도 시작할 수 없는 상태면 누를 수 없게 한다 (서버도 같은 조건으로 거절한다)
  const canReady =
    !!attendance?.stageActive &&
    connected &&
    !!scheduledAt &&
    present.length > 0 &&
    blocked.length === 0
  const canMarkAbsent =
    !!attendance?.stageActive &&
    !!scheduledAt &&
    (self === 'SCHEDULED' || self === 'IN_PROGRESS') &&
    !answered
  const opinion = () => document.getElementById('opinion')?.scrollIntoView({ behavior: 'smooth' })

  async function execute(action: () => Promise<unknown>) {
    try {
      await action()
      setConfirm(false)
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  return (
    <section aria-label="면접 진행 현황" className="space-y-3 border-b bg-surface/50 px-5 py-4">
      <div className="flex flex-wrap items-center gap-3">
        {/* HR 선택 지원자 상세처럼 이름 옆에 원형 예시 사진을 둔다 */}
        <ApplicantAvatar
          applicationId={interview.applicationId}
          recruitmentId={interview.recruitmentId}
        />
        <div className="mr-auto min-w-0">
          <h2 className="flex items-center gap-2 text-lg font-bold">
            {interview.applicantName}
            <RoleTag role={interview.myRole} questionText={`${interview.applicantName} 내 담당`} />
            {self === 'ABSENT' && (
              <span
                className={cn(
                  'rounded-full px-2 py-0.5 text-[11px] font-semibold',
                  INTERVIEW_STATUS_STYLES.ABSENT,
                )}
              >
                불참
              </span>
            )}
          </h2>
          <p className="text-xs text-muted-foreground">
            {scheduledAt
              ? `${formatDateTime(scheduledAt)} 면접${present.length > 1 ? ` · ${present.length}명 함께` : ''}`
              : '일정 미정'}
          </p>
        </div>
        {memo}
        {self === 'ABSENT' && status !== 'ENDED' && (
          <Button
            size="sm"
            variant="ghost"
            disabled={absentPending || !attendance?.stageActive}
            onClick={() => void execute(() => onAbsent(false))}
          >
            불참 취소
          </Button>
        )}
        {canMarkAbsent && (
          <Button
            size="sm"
            variant="ghost"
            disabled={absentPending}
            onClick={() => void execute(() => onAbsent(true))}
          >
            <UserX />
            불참
          </Button>
        )}
        {status === 'SCHEDULED' &&
          (me?.ready ? (
            <Button
              size="sm"
              variant="outline"
              disabled={readying}
              onClick={() => void execute(onCancelReady)}
            >
              준비 취소
            </Button>
          ) : (
            <Button
              size="sm"
              disabled={!canReady || readying}
              onClick={() => void execute(onReady)}
            >
              <CircleCheck />
              준비 완료
            </Button>
          ))}
        {status === 'IN_PROGRESS' && !myEnded && (
          <Button
            size="sm"
            variant="outline"
            disabled={busy || !attendance?.stageActive || !me}
            onClick={() => setConfirm(true)}
          >
            <Square />
            {busy ? '답변을 저장하고 있어요…' : '면접 종료'}
          </Button>
        )}
        {myEnded && self !== 'ABSENT' && (
          <Button size="sm" variant="outline" onClick={opinion}>
            의견 남기기
          </Button>
        )}
        {status === 'ENDED' && self !== 'ABSENT' && (
          <Button size="sm" variant="outline" onClick={opinion}>
            의견 남기기
          </Button>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs">
        <span className="inline-flex items-center gap-1.5 font-semibold">
          {status === 'IN_PROGRESS' ? (
            <span className="size-2 rounded-full bg-amber-500" />
          ) : status === 'ENDED' ? (
            <Check className="size-3.5" />
          ) : (
            <Users className="size-3.5" />
          )}
          {myEnded
            ? '내 면접을 마쳤어요. 다른 면접관도 종료하면 면접이 끝나요.'
            : status === 'IN_PROGRESS'
              ? '면접 진행 중'
              : status === 'ENDED'
                ? '면접이 끝났어요. 의견을 남겨 주세요.'
                : status === 'ABSENT'
                  ? '이 시간 면접자가 모두 불참했어요.'
                  : '면접관 준비 대기'}
        </span>
        {workspace?.session.startedAt && (
          <ElapsedTime from={workspace.session.startedAt} to={workspace.session.endedAt} />
        )}
        {self === 'IN_PROGRESS' && !myEnded && (
          <span className="text-muted-foreground">
            내 질문 {recorded}/{mine.length} 기록
          </span>
        )}
      </div>
      <ul aria-label="배정 면접관 접속 현황" className="flex flex-wrap gap-2">
        {attendees.map((attendee) => {
          const state = attendeeState(attendee, status)
          return (
            <li
              key={attendee.memberId}
              className="flex items-center gap-2 rounded-md border bg-background px-2.5 py-1.5 text-xs"
            >
              <span
                className={cn(
                  'size-1.5 rounded-full',
                  state.tone === 'active'
                    ? 'bg-emerald-600'
                    : state.tone === 'warn'
                      ? 'bg-amber-500'
                      : 'bg-muted-foreground/40',
                )}
              />
              <span>
                {attendee.role === 'HR' ? '인사' : '실무'} {attendee.name}
                {attendee.me ? ' (나)' : ''}
              </span>
              <span className="text-muted-foreground">{state.label}</span>
            </li>
          )
        })}
      </ul>
      {!connected && (
        <p role="status" className="text-xs text-muted-foreground">
          실시간 연결을 다시 잇고 있어요. 연결되면 최신 상태를 확인할 수 있어요.
        </p>
      )}
      {self === 'ABSENT' && status !== 'ENDED' && (
        <p className="text-xs text-muted-foreground">
          불참으로 표시한 지원자예요. 이 시간 면접에서 빠지고, 다시 오면 불참을 취소할 수 있어요.
        </p>
      )}
      {status === 'SCHEDULED' && (
        <p className="text-xs text-muted-foreground">
          {!scheduledAt ? (
            '면접 일시가 정해지면 면접을 시작할 수 있어요. 채용 담당자에게 일정을 요청하세요.'
          ) : blocked.length > 0 ? (
            <span className="font-medium text-amber-800">
              시작하기 전에 채용 담당자에게 요청하세요:{' '}
              {blocked.map((member) => `${member.applicantName} ${member.blocker}`).join(' · ')}
            </span>
          ) : me?.ready ? (
            `다른 면접관이 준비 완료하면 이 시간 면접자${together}의 면접이 바로 함께 시작돼요. 그 전에는 준비를 취소할 수 있어요.`
          ) : (
            `두 면접관이 모두 [준비 완료]를 누르면 이 시간 면접자${together}의 면접이 바로 함께 시작돼요. 시작하면 배정과 질문 구성은 바꿀 수 없어요.`
          )}
        </p>
      )}
      <AlertDialog
        open={confirm}
        onOpenChange={(open) => {
          if (!open && !busy) setConfirm(false)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {present.length > 1
                ? `이 시간 면접자 ${present.length}명에 대한 내 면접을 종료할까요?`
                : '내 면접을 종료할까요?'}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {`${self === 'IN_PROGRESS' ? `${interview.applicantName} 님에게 답변이 없는 내 질문 ${mine.length - recorded}개가 있어요. ` : ''}작성한 답변을 모두 저장한 뒤 종료해요. 종료하면 내 답변은 더 이상 고칠 수 없고, 나만 보는 메모는 계속 고칠 수 있어요. 다른 면접관도 종료하면 면접이 끝나요.`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>취소</AlertDialogCancel>
            <AlertDialogAction
              disabled={busy}
              onClick={(event) => {
                event.preventDefault()
                void execute(onEnd)
              }}
            >
              {busy ? '처리 중…' : '저장하고 종료'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  )
}

function ElapsedTime({ from, to }: { from: string; to: string | null }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (to) return
    const timer = window.setInterval(() => setNow(Date.now()), 1_000)
    return () => window.clearInterval(timer)
  }, [to])
  const seconds = Math.max(0, Math.floor(((to ? Date.parse(to) : now) - Date.parse(from)) / 1_000))
  return (
    <span className="inline-flex items-center gap-1 text-muted-foreground">
      <Clock3 className="size-3.5" />
      경과 {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')}
    </span>
  )
}
