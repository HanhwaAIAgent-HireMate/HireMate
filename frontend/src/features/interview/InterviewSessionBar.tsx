import { Check, CircleCheck, Clock3, Square, Users } from 'lucide-react'
import { useEffect, useState } from 'react'
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
import { Button } from '@/components/ui/button'
import type { InterviewAttendance } from '@/features/interview/live'
import { RoleTag } from '@/features/interview/RoleTag'
import type { AssignedInterview, InterviewerWorkspace } from '@/features/interview/sessions'
import { errorMessage } from '@/lib/api/client'
import { formatDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'

/**
 * 지원자 면접의 대기, 진행, 종료 상태와 준비 현황. 두 면접관이 모두 [준비 완료]를 누르면 서버가 바로 면접을 시작하고,
 * 종료는 확인 뒤에 실행한다.
 */
export function InterviewSessionBar({
  interview,
  workspace,
  attendance,
  connected,
  busy,
  readying,
  onReady,
  onCancelReady,
  onEnd,
}: {
  interview: AssignedInterview
  workspace: InterviewerWorkspace | undefined
  attendance: InterviewAttendance | undefined
  connected: boolean
  busy: boolean
  readying: boolean
  onReady: () => Promise<unknown>
  onCancelReady: () => Promise<unknown>
  onEnd: () => Promise<unknown>
}) {
  const [confirm, setConfirm] = useState(false)
  const status = workspace?.session.status
  const mine = (workspace?.questions ?? []).filter(
    (item) => item.question.interviewerRole === workspace?.myRole,
  )
  const recorded = mine.filter((item) => item.question.answer.trim()).length
  const missingOwners = (workspace?.questions ?? []).filter(
    (item) => !item.question.interviewerRole,
  ).length
  const attendees = attendance?.attendees ?? []
  const me = attendees.find((attendee) => attendee.me)
  // 준비 완료를 받아도 시작할 수 없는 상태면 누를 수 없게 한다 (서버도 같은 조건으로 거절한다)
  const canReady =
    !!attendance?.stageActive && connected && missingOwners === 0 && !!workspace?.questions.length
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
        <div className="mr-auto min-w-0">
          <h2 className="flex items-center gap-2 text-lg font-bold">
            {interview.applicantName}
            <RoleTag role={interview.myRole} questionText={`${interview.applicantName} 내 담당`} />
          </h2>
          <p className="text-xs text-muted-foreground">
            {workspace?.schedule?.scheduledAt
              ? formatDateTime(workspace.schedule.scheduledAt)
              : '일정 미정'}
          </p>
        </div>
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
        {status === 'IN_PROGRESS' && (
          <Button
            size="sm"
            variant="outline"
            disabled={busy || !attendance?.stageActive}
            onClick={() => setConfirm(true)}
          >
            <Square />
            {busy ? '답변을 저장하고 있어요…' : '면접 종료'}
          </Button>
        )}
        {status === 'ENDED' && (
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
          {status === 'IN_PROGRESS'
            ? '면접 진행 중'
            : status === 'ENDED'
              ? '면접이 끝났어요. 의견을 남겨 주세요.'
              : '면접관 준비 대기'}
        </span>
        {workspace?.session.startedAt && (
          <ElapsedTime from={workspace.session.startedAt} to={workspace.session.endedAt} />
        )}
        {status === 'IN_PROGRESS' && (
          <span className="text-muted-foreground">
            내 질문 {recorded}/{mine.length} 기록
          </span>
        )}
      </div>
      <ul aria-label="배정 면접관 접속 현황" className="flex flex-wrap gap-2">
        {attendees.map((attendee) => (
          <li
            key={attendee.memberId}
            className="flex items-center gap-2 rounded-md border bg-background px-2.5 py-1.5 text-xs"
          >
            <span
              className={cn(
                'size-1.5 rounded-full',
                attendee.online && attendee.ready ? 'bg-emerald-600' : 'bg-muted-foreground/40',
              )}
            />
            <span>
              {attendee.role === 'HR' ? '인사' : '실무'} {attendee.name}
              {attendee.me ? ' (나)' : ''}
            </span>
            <span className="text-muted-foreground">
              {!attendee.ready ? '준비 전' : attendee.online ? '준비 완료' : '접속 끊김'}
            </span>
          </li>
        ))}
      </ul>
      {!connected && (
        <p role="status" className="text-xs text-muted-foreground">
          실시간 연결을 다시 잇고 있어요. 연결되면 최신 상태를 확인할 수 있어요.
        </p>
      )}
      {status === 'SCHEDULED' && (
        <p className="text-xs text-muted-foreground">
          {missingOwners > 0
            ? `담당이 없는 질문 ${missingOwners}개가 있어요. 채용 담당자에게 담당 지정을 요청하세요.`
            : !workspace?.questions.length
              ? '질문을 준비한 뒤 면접을 시작할 수 있어요.'
              : me?.ready
                ? '다른 면접관이 준비 완료하면 바로 면접이 시작돼요. 그 전에는 준비를 취소할 수 있어요.'
                : '두 면접관이 모두 [준비 완료]를 누르면 바로 면접이 시작돼요. 시작하면 배정과 질문 구성은 바꿀 수 없어요.'}
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
            <AlertDialogTitle>면접을 종료할까요?</AlertDialogTitle>
            <AlertDialogDescription>
              {`답변이 없는 내 질문 ${mine.length - recorded}개가 있어요. 작성한 답변을 모두 저장한 뒤 종료해요. 종료하면 답변을 더 이상 고칠 수 없어요.`}
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
