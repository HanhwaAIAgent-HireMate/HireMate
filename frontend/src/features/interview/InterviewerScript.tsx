import { Plus, X } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { AnswerBox } from '@/features/interview/AnswerBox'
import { QuestionReason } from '@/features/interview/QuestionReason'
import { RoleTag, type InterviewerRole } from '@/features/interview/RoleTag'
import {
  useWorkspaceActions,
  workspaceAnswerActions,
  type InterviewerQuestion,
  type InterviewerWorkspace,
} from '@/features/interview/sessions'
import { errorMessage } from '@/lib/api/client'
import { cn } from '@/lib/utils'

const ROLE_LABELS: Record<InterviewerRole, string> = { HR: '인사', PRACTICAL: '실무' }

/** 꼬리질문 단계(처음 질문 0). 목록에 없는 부모를 만나면 거기서 멈춘다 */
function depthOf(item: InterviewerQuestion, items: InterviewerQuestion[]) {
  const parents = new Map(
    items.map((other) => [other.question.questionId, other.question.parentQuestionId]),
  )
  let depth = 0
  for (
    let at = item.question.parentQuestionId;
    at && parents.has(at) && depth < 3;
    at = parents.get(at) ?? null
  )
    depth++
  return depth
}

/**
 * 면접관 모드의 질문 대본. 질문별 권한(canAnswer · canDelete · 꼬리질문)은 서버가 정해 준다.
 * 내 담당 질문은 왼쪽 담당 색 선과 답변 칸, 다른 면접관 질문은 흐린 카드에 기록만 보인다.
 * 면접 중 다른 사람이 넣은 질문은 화면을 옮기지 않고 "새 질문" 알림으로 알린다.
 */
export function InterviewerScript({
  stageId,
  applicationId,
  workspace,
  filter,
  ownerNames,
}: {
  stageId: string
  applicationId: string
  workspace: InterviewerWorkspace
  filter: 'all' | 'mine'
  /** 담당별 면접관 이름 ("인사 담당 · 최은영") */
  ownerNames: Partial<Record<InterviewerRole, string>>
}) {
  const actions = useWorkspaceActions(stageId, applicationId)
  const answerActions = workspaceAnswerActions(actions)
  const [draft, setDraft] = useState<string | null>(null)
  const [initialIds] = useState(
    () => new Set(workspace.questions.map((item) => item.question.questionId)),
  )
  const [seen, setSeen] = useState<Set<string>>(new Set())
  const fail = (error: unknown) => toast.error(errorMessage(error))
  const mine = (item: InterviewerQuestion) => item.question.interviewerRole === workspace.myRole
  const fresh = workspace.questions.filter(
    (item) => !initialIds.has(item.question.questionId) && !seen.has(item.question.questionId),
  )
  const shown = workspace.questions.filter((item) => filter === 'all' || mine(item))

  return (
    <div className="space-y-3">
      {fresh.length > 0 && (
        <button
          type="button"
          className="sticky top-0 z-10 mx-auto flex items-center gap-1.5 rounded-full bg-primary px-3 py-1 text-xs font-semibold text-primary-foreground shadow"
          onClick={() => {
            document
              .getElementById(`question-${fresh[0].question.questionId}`)
              ?.scrollIntoView({ behavior: 'smooth', block: 'center' })
            setSeen(new Set([...seen, ...fresh.map((item) => item.question.questionId)]))
          }}
        >
          새 질문 {fresh.length}개
        </button>
      )}
      {shown.map((item) => {
        const { question } = item
        const depth = depthOf(item, workspace.questions)
        const role = question.interviewerRole
        return (
          <div
            key={question.questionId}
            id={`question-${question.questionId}`}
            className={cn(
              'group space-y-2 rounded-xl border p-3',
              depth === 1 && 'ml-6 border-fuchsia-100',
              depth >= 2 && 'ml-12 border-fuchsia-100',
              !initialIds.has(question.questionId) && 'animate-[question-new_3s_ease-out]',
              mine(item) && role === 'PRACTICAL' && 'border-l-[3px] border-l-emerald-600',
              mine(item) && role === 'HR' && 'border-l-[3px] border-l-indigo-600',
              !mine(item) && 'bg-muted/40',
            )}
          >
            <div className="flex items-start gap-2">
              <QuestionReason
                text={question.text}
                reason={question.reason}
                source={question.source}
                leading={<RoleTag role={role} questionText={question.text} />}
              />
              <span className="shrink-0 pt-0.5 text-xs text-muted-foreground">
                {mine(item)
                  ? '내 질문'
                  : role
                    ? `${ROLE_LABELS[role]} 담당${ownerNames[role] ? ` · ${ownerNames[role]}` : ''}`
                    : '담당 없음'}
              </span>
              {item.canDelete && (
                <button
                  aria-label="질문 삭제"
                  onClick={() => actions.remove.mutate(question.questionId, { onError: fail })}
                  className="invisible text-muted-foreground group-hover:visible hover:text-foreground"
                >
                  <X className="size-3.5" />
                </button>
              )}
            </div>
            {mine(item) ? (
              <>
                <AnswerBox
                  stageId={stageId}
                  applicationId={applicationId}
                  question={question}
                  editable={item.canAnswer}
                  canFollowUp={item.canRequestFollowUp}
                  answerActions={answerActions}
                />
                {!item.canAnswer && item.readOnlyReason && (
                  <p className="text-xs text-muted-foreground">
                    {item.readOnlyReason}이라 기록할 수 없어요.
                  </p>
                )}
              </>
            ) : (
              <p className="rounded-lg border border-dashed px-3 py-2 text-sm whitespace-pre-wrap text-muted-foreground">
                {question.answer.trim() || '아직 기록 없음 · 보기만 할 수 있어요'}
              </p>
            )}
          </div>
        )
      })}
      {workspace.session.status !== 'ENDED' &&
        (draft === null ? (
          <Button size="sm" variant="outline" onClick={() => setDraft('')}>
            <Plus />내 질문 추가
          </Button>
        ) : (
          <form
            className="flex gap-2"
            onSubmit={(event) => {
              event.preventDefault()
              if (!draft.trim()) return
              actions.add.mutate(
                { text: draft.trim(), interviewerRole: workspace.myRole },
                { onSuccess: () => setDraft(null), onError: fail },
              )
            }}
          >
            <Input
              autoFocus
              aria-label="추가할 질문"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="직접 묻고 싶은 질문 (내 담당으로 들어가요)"
            />
            <Button type="submit" size="sm" disabled={!draft.trim() || actions.add.isPending}>
              추가
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setDraft(null)}>
              취소
            </Button>
          </form>
        ))}
    </div>
  )
}
