import { Loader2Icon, MessageSquarePlus, PenLine, RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type FocusEvent, type ReactNode } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import {
  useInterviewActions,
  type FollowUps,
  type InterviewQuestion,
} from '@/features/interview/api'
import { ApiError, errorMessage } from '@/lib/api/client'

/** 💾 타이핑을 멈추고 이만큼 지나면 DB에만 자동 저장한다 (분석은 하지 않는다) */
export const AUTOSAVE_MS = 2_000

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

/**
 * 질문 하나의 답변 칸과 꼬리질문 받기.
 *
 * 💾 자동 저장: 타이핑을 멈추고 2초 뒤 DB에만 저장한다 (모델 호출 없음). "저장 중… / 저장됨"을 보여 주고,
 *   저장 안 된 글이 있으면 페이지를 떠날 때 브라우저가 경고한다.
 * 🧠 답변 분석: 면접관이 이 칸을 떠나 다른 곳(다른 질문)으로 갈 때만 요청한다. 같은 카드 안의 꼬리질문 버튼으로
 *   옮겨 갈 때는 저장만 한다. 같은 답으로 여러 번 드나들어도 서버가 한 번만 분석한다.
 * 🎤 꼬리질문: [꼬리질문 받기]를 누를 때만 모델을 부른다 (canFollowUp: 2단계 전이고 아직 꼬리질문이 없는 질문).
 */
export function AnswerBox({
  stageId,
  applicationId,
  question,
  editable,
  canFollowUp,
}: {
  stageId: string
  applicationId: string
  question: InterviewQuestion
  editable: boolean
  canFollowUp: boolean
}) {
  const actions = useInterviewActions(stageId, applicationId)
  const card = useRef<HTMLDivElement>(null)
  const [value, setValue] = useState(question.answer)
  const [saved, setSaved] = useState(question.answer) // 서버가 저장했다고 알려 준 마지막 답
  const [status, setStatus] = useState<SaveStatus>('idle')
  const latest = useRef(question.answer) // 지금 칸에 적힌 답 (타이머 · 정리 함수가 읽는다)
  const sent = useRef<string | null>(question.answer) // 서버에 마지막으로 보낸 답. 실패하면 null로 두어 다시 보낸다
  const version = useRef(question.version)
  const conflicted = useRef(false)
  const pending = useRef(false) // 자동 저장만 하고 아직 분석에 넘기지 않은 답이 있음
  const timer = useRef<number | undefined>(undefined)
  const queue = useRef<Promise<unknown>>(Promise.resolve()) // 저장 요청을 보낸 순서대로 처리한다
  const { mutateAsync: saveAnswer } = actions.answer

  /** 지금 칸의 답을 저장한다. analyze가 true면 분석도 요청한다. 보낼 것이 없으면 앞선 저장이 끝나기를 기다린다. */
  const save = useCallback(
    (analyze: boolean) => {
      window.clearTimeout(timer.current)
      if (conflicted.current) return queue.current
      const answer = latest.current
      if (answer === sent.current && !(analyze && pending.current)) return queue.current
      const wasPending = pending.current
      sent.current = answer
      pending.current = !analyze
      setStatus('saving')
      queue.current = queue.current
        .then(() => {
          if (conflicted.current) throw new ApiError(409, 'ANSWER_CONFLICT', '')
          return saveAnswer({
            questionId: question.questionId,
            answer,
            analyze,
            expectedVersion: version.current,
          })
        })
        .then(
          (result) => {
            const stored = result.questions?.find((item) => item.questionId === question.questionId)
            if (stored) version.current = stored.version
            if (sent.current !== answer) return // 그 사이 새 저장이 나갔다
            setSaved(answer)
            setStatus('saved')
          },
          (error: unknown) => {
            if (
              error instanceof ApiError &&
              ['ANSWER_CONFLICT', 'UPDATE_CONFLICT'].includes(error.code)
            )
              conflicted.current = true
            sent.current = null
            pending.current = wasPending
            setStatus('error')
            toast.error(errorMessage(error))
          },
        )
      return queue.current
    },
    [question.questionId, saveAnswer],
  )

  // 담당 태그만 바뀌고 답변은 같다면 최신 버전을 쓴다. 다른 답변이 들어오면 기존 초안으로 덮어쓰지 않는다.
  useEffect(() => {
    if (!conflicted.current && question.answer === latest.current)
      version.current = question.version
  }, [question.answer, question.version])

  // 카드가 사라질 때(다른 지원자로 넘어감) 저장 안 된 답이나 분석에 안 넘긴 답이 있으면 보낸다
  useEffect(
    () => () => {
      if (latest.current !== sent.current || pending.current) void save(true)
    },
    [save],
  )

  // 저장 안 된 글이 있는 채로 페이지를 떠나면 브라우저가 경고한다
  const unsaved = value !== saved || status === 'saving'
  useEffect(() => {
    if (!unsaved) return
    const warn = (event: BeforeUnloadEvent) => event.preventDefault()
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [unsaved])

  return (
    <div ref={card} className="space-y-2">
      <Textarea
        aria-label={`${question.text} 답변`}
        value={value}
        placeholder="답변"
        disabled={!editable}
        rows={2}
        onChange={(event) => {
          setValue(event.target.value)
          latest.current = event.target.value
          window.clearTimeout(timer.current)
          timer.current = window.setTimeout(() => void save(false), AUTOSAVE_MS)
        }}
        onBlur={(event: FocusEvent<HTMLTextAreaElement>) => {
          // 같은 카드의 꼬리질문 버튼으로 옮겨 가면 저장만, 카드 밖(다른 질문)으로 가면 분석까지
          const stays =
            event.relatedTarget instanceof Node && card.current?.contains(event.relatedTarget)
          void save(!stays)
        }}
        className="min-h-0 resize-none"
      />
      {editable && (
        <FollowUpArea
          stageId={stageId}
          applicationId={applicationId}
          question={question}
          canAsk={canFollowUp && value.trim() !== ''}
          beforeAsk={async () => {
            await save(false)
            if (conflicted.current) throw new ApiError(409, 'ANSWER_CONFLICT', '')
          }}
          status={<SaveIndicator status={status} unsaved={value !== saved} />}
        />
      )}
    </div>
  )
}

function SaveIndicator({ status, unsaved }: { status: SaveStatus; unsaved: boolean }) {
  const text =
    status === 'saving'
      ? '저장 중…'
      : status === 'error'
        ? '저장하지 못했어요'
        : status === 'saved' && !unsaved
          ? '저장됨'
          : ''
  return (
    <span
      role="status"
      aria-live="polite"
      className={`ml-auto text-xs ${status === 'error' ? 'text-destructive' : 'text-muted-foreground'}`}
    >
      {text}
    </span>
  )
}

type Mode = 'idle' | 'loading' | 'none' | 'suggestions' | 'manual'

/**
 * 🎤 꼬리질문 받기 → 답이 충분하면 "추가로 확인할 점이 없어요", 아니면 확인 포인트가 붙은 제안 2개 중 하나를 고른다.
 * [다시 제안]은 질문마다 한 번, [직접 쓰기]는 면접관이 쓴 질문을 넣고, [선택 안 함]은 아무것도 저장하지 않고 닫는다.
 */
function FollowUpArea({
  stageId,
  applicationId,
  question,
  canAsk,
  beforeAsk,
  status,
}: {
  stageId: string
  applicationId: string
  question: InterviewQuestion
  canAsk: boolean
  beforeAsk: () => Promise<unknown>
  status: ReactNode
}) {
  const actions = useInterviewActions(stageId, applicationId)
  const [mode, setMode] = useState<Mode>('idle')
  const [found, setFound] = useState<FollowUps['suggestions']>([])
  const [retried, setRetried] = useState(false)
  const [manual, setManual] = useState('')
  const adding = actions.addFollowUp.isPending

  async function ask(avoid: string[]) {
    const back = mode
    setMode('loading')
    try {
      await beforeAsk() // 서버가 읽는 답이 화면과 같도록 먼저 저장한다 (분석은 하지 않는다)
      const result = await actions.suggestFollowUps.mutateAsync({
        questionId: question.questionId,
        avoid,
      })
      setFound(result.suggestions)
      setMode(result.needed && result.suggestions.length ? 'suggestions' : 'none')
    } catch (error) {
      toast.error(errorMessage(error))
      setMode(back)
    }
  }

  function add(text: string, source: 'AI' | 'MANUAL', check: string | null) {
    actions.addFollowUp.mutate(
      { questionId: question.questionId, text, source, check },
      {
        onSuccess: () => {
          setMode('idle')
          setManual('')
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    )
  }

  const close = () => setMode('idle')

  if (!canAsk || mode === 'idle' || mode === 'loading')
    return (
      // 받기 버튼이 없으면(꼬리질문이 이미 있거나 2단계) 버튼 높이만큼 비워 두지 않는다
      <div className={canAsk ? 'flex min-h-7 items-center gap-2' : 'flex items-center gap-2'}>
        {canAsk &&
          (mode === 'loading' ? (
            <span role="status" className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Loader2Icon className="size-3.5 animate-spin" />
              꼬리질문을 찾는 중이에요
            </span>
          ) : (
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-7 border-fuchsia-200 px-2 text-xs text-fuchsia-800 hover:bg-fuchsia-50"
              onClick={() => void ask([])}
            >
              <MessageSquarePlus className="size-3.5" />
              꼬리질문 받기
            </Button>
          ))}
        {status}
      </div>
    )

  return (
    <div className="space-y-2">
      <div className="space-y-2 rounded-lg border border-fuchsia-200 bg-fuchsia-50/40 p-3">
        {mode === 'none' && (
          <p role="status" className="text-sm text-muted-foreground">
            추가로 확인할 점이 없어요.
          </p>
        )}
        {mode === 'suggestions' && (
          <>
            <p className="text-xs font-semibold text-fuchsia-800">
              꼬리질문 제안 · 하나를 골라 주세요
            </p>
            <ul className="space-y-1.5">
              {found.map((suggestion) => (
                <li key={suggestion.text}>
                  <button
                    type="button"
                    disabled={adding}
                    onClick={() => add(suggestion.text, 'AI', suggestion.check)}
                    className="w-full rounded-md border bg-background px-3 py-2 text-left transition-colors hover:border-fuchsia-300 hover:bg-fuchsia-50 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none disabled:opacity-60"
                  >
                    <span className="block text-sm font-medium">{suggestion.text}</span>
                    <span className="mt-0.5 block text-xs text-muted-foreground">
                      확인 포인트 · {suggestion.check}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
        {mode === 'manual' ? (
          <form
            className="flex gap-2"
            onSubmit={(event) => {
              event.preventDefault()
              if (manual.trim()) add(manual.trim(), 'MANUAL', null)
            }}
          >
            <Input
              autoFocus
              aria-label="직접 쓸 꼬리질문"
              value={manual}
              maxLength={500}
              onChange={(event) => setManual(event.target.value)}
              placeholder="이어서 묻고 싶은 질문"
              className="h-8 bg-background"
            />
            <Button type="submit" size="sm" disabled={!manual.trim() || adding}>
              추가
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={close}>
              취소
            </Button>
          </form>
        ) : (
          <div className="flex flex-wrap items-center gap-1">
            {mode === 'suggestions' && (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="h-7 px-2 text-xs"
                disabled={retried}
                title={retried ? '다시 제안은 질문마다 한 번만 받을 수 있어요' : undefined}
                onClick={() => {
                  setRetried(true)
                  void ask(found.map((suggestion) => suggestion.text))
                }}
              >
                <RefreshCw className="size-3.5" />
                다시 제안
              </Button>
            )}
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-7 px-2 text-xs"
              onClick={() => setMode('manual')}
            >
              <PenLine className="size-3.5" />
              직접 쓰기
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="ml-auto h-7 px-2 text-xs text-muted-foreground"
              onClick={close}
            >
              {mode === 'none' ? '닫기' : '선택 안 함'}
            </Button>
          </div>
        )}
      </div>
      <div className="flex min-h-5 items-center">{status}</div>
    </div>
  )
}
