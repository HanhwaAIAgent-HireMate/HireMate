import { CalendarClock, Loader2Icon, Plus, X } from 'lucide-react'
import { useRef, useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import {
  useInterview,
  useInterviewActions,
  useInterviewPreparing,
  useStageHistory,
  type Interview,
} from '@/features/interview/api'
import { AgentChip } from '@/features/posting/AiRequestPanel'
import { STAGE_TYPE_LABELS } from '@/features/recruit/labels'
import type { CandidateDetail } from '@/features/screening/api'
import { DocumentViewer } from '@/features/screening/DocumentViewer'
import { errorMessage } from '@/lib/api/client'
import { formatMonthDay, toLocalInput } from '@/lib/format'
import { cn } from '@/lib/utils'

type Tab = 'questions' | 'documents' | 'results'

// STG-12 · STG-13 면접 전형의 지원자 카드. 맞춤 질문 · 지원 자료 · 전형 결과 탭이 있다
export function InterviewViewer({
  stageId,
  recruitmentId,
  detail,
  editable,
}: {
  stageId: string
  recruitmentId: string
  detail: CandidateDetail
  editable: boolean
}) {
  const [tab, setTab] = useState<Tab>('questions')
  const applicationId = detail.row.applicationId
  const interview = useInterview(stageId, applicationId)

  return (
    <div className="space-y-4">
      <div role="tablist" className="flex gap-5 border-b text-sm">
        {(
          [
            ['questions', '맞춤 질문'],
            ['documents', '지원 자료'],
            ['results', '전형 결과'],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={cn(
              '-mb-px border-b-2 pb-2',
              tab === key
                ? 'border-foreground font-semibold'
                : 'border-transparent text-muted-foreground',
            )}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === 'documents' && (
        <DocumentViewer stageId={stageId} recruitmentId={recruitmentId} detail={detail} />
      )}
      {tab === 'results' && <Results stageId={stageId} applicationId={applicationId} />}
      {tab === 'questions' &&
        (!interview.data ? (
          <Skeleton className="h-40 w-full" />
        ) : (
          <Questions
            key={applicationId}
            stageId={stageId}
            applicationId={applicationId}
            interview={interview.data}
            editable={editable}
          />
        ))}
    </div>
  )
}

function Questions({
  stageId,
  applicationId,
  interview,
  editable,
}: {
  stageId: string
  applicationId: string
  interview: Interview
  editable: boolean
}) {
  const actions = useInterviewActions(stageId, applicationId)
  const preparing = useInterviewPreparing(stageId, applicationId).data?.preparing === true
  const [draft, setDraft] = useState<string | null>(null)
  const fail = (error: unknown) => toast.error(errorMessage(error))
  // 카드를 연 뒤에 새로 들어온 질문(AI Chat · 자동 생성 · 직접 추가)을 잠깐 강조하고 그 위치로 내린다
  //   처음 열었을 때 이미 있던 질문 번호를 한 번만 기억해 두고(lazy 초기값), 그 뒤에 생긴 질문만 '새 질문'으로 본다
  const [initialIds] = useState(
    () => new Set(interview.questions.map((question) => question.questionId)),
  )
  const scrolledTo = useRef<string | null>(null) // 같은 질문으로 여러 번 스크롤하지 않게

  return (
    <div className="space-y-3">
      {interview.previous.map((previous) => (
        <section key={previous.stageId} className="space-y-2 rounded-xl bg-muted/60 p-3 text-sm">
          <div className="flex items-center justify-between">
            <h4 className="font-semibold">{previous.stageName} 기록</h4>
            <span className="text-xs text-muted-foreground">
              {[
                previous.schedule?.scheduledAt && formatMonthDay(previous.schedule.scheduledAt),
                previous.schedule?.interviewers,
              ]
                .filter(Boolean)
                .join(' · ')}
            </span>
          </div>
          {previous.questions.map((question, index) => (
            <div key={question.questionId}>
              <p className="font-medium">
                Q{index + 1}. {question.text}
              </p>
              <p className="text-xs text-muted-foreground">
                {question.answer || '기록한 답변이 없어요.'}
              </p>
            </div>
          ))}
        </section>
      ))}
      <div className="flex items-center gap-2 text-sm font-semibold">
        맞춤 질문
        <AgentChip name="Interview Agent" />
        <div className="ml-auto flex items-center gap-1">
          <ScheduleButton
            stageId={stageId}
            applicationId={applicationId}
            interview={interview}
            disabled={!editable}
          />
        </div>
      </div>
      {preparing && (
        <div
          role="status"
          className="flex items-center gap-2 rounded-xl border border-dashed p-4 text-sm text-muted-foreground"
        >
          <Loader2Icon className="size-4 shrink-0 animate-spin" />
          질문 생성 중이에요. 끝나면 자동으로 나타나요.
        </div>
      )}
      {!preparing && interview.questions.length === 0 && (
        <p className="rounded-xl border border-dashed p-5 text-center text-sm text-muted-foreground">
          아직 질문이 없어요. 면접 전형이 시작되면 AI가 미리 만들고, AI Chat에서 @지원자와 함께 더
          요청할 수 있어요.
        </p>
      )}
      {interview.questions.map((question) => (
        <div
          key={question.questionId}
          ref={(element) => {
            // 새 질문이 처음 그려질 때 한 번만 그 위치로 부드럽게 내린다
            if (
              element &&
              !initialIds.has(question.questionId) &&
              scrolledTo.current !== question.questionId
            ) {
              scrolledTo.current = question.questionId
              element.scrollIntoView({ behavior: 'smooth', block: 'center' })
            }
          }}
          className={cn(
            'group space-y-2 rounded-xl border p-3',
            // 3초 동안 연한 노란 배경 · 테두리로 강조했다가 원래대로 (리스트의 보라 AI 선택 표시와 헷갈리지 않는 색)
            !initialIds.has(question.questionId) && 'animate-[question-new_3s_ease-out]',
          )}
        >
          <div className="flex items-start gap-2">
            <p className="flex-1 text-sm font-semibold">{question.text}</p>
            {editable && (
              <button
                aria-label="질문 삭제"
                onClick={() => actions.remove.mutate(question.questionId, { onError: fail })}
                className="invisible text-muted-foreground group-hover:visible hover:text-foreground"
              >
                <X className="size-3.5" />
              </button>
            )}
          </div>
          <Textarea
            aria-label={`${question.text} 답변`}
            defaultValue={question.answer}
            placeholder="답변"
            disabled={!editable}
            rows={2}
            onBlur={(event) => {
              const answer = event.target.value
              if (answer !== question.answer)
                actions.answer.mutate(
                  { questionId: question.questionId, answer },
                  { onError: fail },
                )
            }}
            className="min-h-0 resize-none"
          />
        </div>
      ))}
      {editable &&
        (draft === null ? (
          <Button size="sm" variant="outline" onClick={() => setDraft('')}>
            <Plus />
            질문 추가
          </Button>
        ) : (
          <form
            className="flex gap-2"
            onSubmit={(event) => {
              event.preventDefault()
              if (!draft.trim()) return
              actions.add.mutate(draft.trim(), { onSuccess: () => setDraft(null), onError: fail })
            }}
          >
            <Input
              autoFocus
              aria-label="추가할 질문"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="면접관이 직접 묻고 싶은 질문"
            />
            <Button type="submit" size="sm" disabled={!draft.trim()}>
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

function ScheduleButton({
  stageId,
  applicationId,
  interview,
  disabled,
}: {
  stageId: string
  applicationId: string
  interview: Interview
  disabled: boolean
}) {
  const actions = useInterviewActions(stageId, applicationId)
  const [open, setOpen] = useState(false)
  const [at, setAt] = useState('')
  const [interviewers, setInterviewers] = useState('')
  return (
    <Popover
      open={open}
      onOpenChange={(value) => {
        setOpen(value)
        if (value) {
          setAt(
            interview.schedule?.scheduledAt
              ? toLocalInput(new Date(interview.schedule.scheduledAt))
              : '',
          )
          setInterviewers(interview.schedule?.interviewers ?? '')
        }
      }}
    >
      <PopoverTrigger asChild>
        <Button size="sm" variant="ghost" disabled={disabled}>
          <CalendarClock />
          일정
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72 space-y-2">
        <p className="text-xs text-muted-foreground">면접 일정은 HR이 직접 입력해요.</p>
        <input
          type="datetime-local"
          aria-label="면접 일시"
          value={at}
          onChange={(event) => setAt(event.target.value)}
          className="h-9 w-full rounded-lg border px-3 text-sm"
        />
        <Input
          aria-label="면접관"
          placeholder="예: 면접관 2명"
          value={interviewers}
          onChange={(event) => setInterviewers(event.target.value)}
        />
        <div className="flex justify-end">
          <Button
            size="sm"
            onClick={() =>
              actions.schedule.mutate(
                { scheduledAt: at ? new Date(at).toISOString() : null, interviewers },
                {
                  onSuccess: () => setOpen(false),
                  onError: (error) => toast.error(errorMessage(error)),
                },
              )
            }
          >
            저장
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  )
}

const DECISION_STYLE = {
  PASS: { label: '합격', className: 'bg-pass text-pass-foreground' },
  FAIL: { label: '불합격', className: 'bg-fail text-fail-foreground' },
  PENDING: { label: '미결정', className: 'bg-muted text-muted-foreground' },
} as const

/** 이전 전형까지의 결정 · 점수 · 메모 */
function Results({ stageId, applicationId }: { stageId: string; applicationId: string }) {
  const history = useStageHistory(stageId, applicationId)
  if (!history.data) return <Skeleton className="h-24 w-full" />
  return (
    <ul className="divide-y rounded-xl border text-sm">
      {history.data.map((item) => {
        const decision = DECISION_STYLE[item.finalResult ?? item.decision]
        return (
          <li key={item.stageId} className="space-y-1 px-4 py-3">
            <div className="flex items-center gap-2">
              <span className="font-semibold">{item.stageName}</span>
              <span className="text-xs text-muted-foreground">
                {STAGE_TYPE_LABELS[item.stageType]}
              </span>
              {item.score !== null && (
                <span className="rounded-md bg-muted px-1.5 py-0.5 text-xs font-bold">
                  {Number(item.score)}
                </span>
              )}
              <span
                className={cn(
                  'ml-auto rounded-md px-1.5 py-0.5 text-xs font-semibold',
                  decision.className,
                )}
              >
                {decision.label}
              </span>
            </div>
            {item.memo && <p className="text-xs text-muted-foreground">메모 · {item.memo}</p>}
          </li>
        )
      })}
    </ul>
  )
}
