import { Check, Clock3, LogIn, Play, Square, Users } from 'lucide-react'
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

/** 지원자 면접의 대기, 진행, 종료 상태와 입장 현황. 시작과 종료는 확인 뒤에 실행한다. */
export function InterviewSessionBar({
  interview,
  workspace,
  attendance,
  connected,
  busy,
  entering,
  onEnter,
  onStart,
  onEnd,
}: {
  interview: AssignedInterview
  workspace: InterviewerWorkspace | undefined
  attendance: InterviewAttendance | undefined
  connected: boolean
  busy: boolean
  entering: boolean
  onEnter: () => Promise<unknown>
  onStart: () => Promise<unknown>
  onEnd: () => Promise<unknown>
}) {
  const [confirm, setConfirm] = useState<'start' | 'end' | null>(null)
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
  const ready =
    !!attendance?.stageActive &&
    connected &&
    attendees.length > 0 &&
    attendees.every((attendee) => attendee.entered && attendee.online) &&
    missingOwners === 0 &&
    !!workspace?.questions.length
  const opinion = () => document.getElementById('opinion')?.scrollIntoView({ behavior: 'smooth' })

  async function execute(action: () => Promise<unknown>) {
    try {
      await action()
      setConfirm(null)
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
        {status === 'SCHEDULED' && (
          <>
            {!me?.entered && (
              <Button
                size="sm"
                variant="outline"
                disabled={!attendance?.stageActive || entering || !connected}
                onClick={() => void execute(onEnter)}
              >
                <LogIn />
                면접 입장
              </Button>
            )}
            <Button size="sm" disabled={!ready || busy} onClick={() => setConfirm('start')}>
              <Play />
              면접 시작
            </Button>
          </>
        )}
        {status === 'IN_PROGRESS' && (
          <Button
            size="sm"
            variant="outline"
            disabled={busy || !attendance?.stageActive}
            onClick={() => setConfirm('end')}
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
              : '면접관 입장 대기'}
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
                attendee.online && attendee.entered ? 'bg-emerald-600' : 'bg-muted-foreground/40',
              )}
            />
            <span>
              {attendee.role === 'HR' ? '인사' : '실무'} {attendee.name}
              {attendee.me ? ' (나)' : ''}
            </span>
            <span className="text-muted-foreground">
              {!attendee.entered ? '입장 대기' : attendee.online ? '입장 완료' : '접속 끊김'}
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
              : '배정된 면접관이 모두 입장하고 접속 중이면 시작할 수 있어요. 시작 전에는 질문만 미리 볼 수 있어요.'}
        </p>
      )}
      <AlertDialog
        open={confirm !== null}
        onOpenChange={(open) => {
          if (!open && !busy) setConfirm(null)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {confirm === 'start' ? '면접을 시작할까요?' : '면접을 종료할까요?'}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {confirm === 'start'
                ? '시작하면 모든 면접관 화면에서 답변을 기록할 수 있어요. 배정과 질문 구성은 바꿀 수 없어요.'
                : `답변이 없는 내 질문 ${mine.length - recorded}개가 있어요. 작성한 답변을 모두 저장한 뒤 종료해요. 종료하면 답변을 더 이상 고칠 수 없어요.`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>취소</AlertDialogCancel>
            <AlertDialogAction
              disabled={busy || (confirm === 'start' && !ready)}
              onClick={(event) => {
                event.preventDefault()
                void execute(confirm === 'start' ? onStart : onEnd)
              }}
            >
              {busy ? '처리 중…' : confirm === 'start' ? '시작하기' : '저장하고 종료'}
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
