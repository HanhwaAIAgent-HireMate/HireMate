import { AlertCircle, ArrowUp, AtSign, Check, History, Sparkles, X } from 'lucide-react'
import { Fragment, useEffect, useRef, useState, type ReactNode } from 'react'

import { AgentChip } from '@/features/posting/AiRequestPanel'
import {
  useChat,
  useChatHistory,
  useForgetChat,
  useMentionCandidates,
  type ChatAnswer,
  type ChatItem,
} from '@/features/chat/api'
import { LiveSteps, StepsSummary } from '@/features/chat/ChatSteps'
import { addStep } from '@/features/chat/steps'
import { turnsToMessages, useChatStore, type ChatMessage } from '@/features/chat/store'
import { careerLabel, type StageOverview } from '@/features/screening/api'
import { useStageUi } from '@/features/screening/store'
import { errorMessage } from '@/lib/api/client'
import { cn } from '@/lib/utils'

const EMPTY: ChatMessage[] = []
const RECENT = 6
const WAITING = '지원자 자료를 살펴보고 있어요…'

/** 답을 기다리는 동안 쌓은 단계 문구와 검증을 마친 항목 */
type Progress = { steps: string[]; items: ChatItem[] }
const NO_PROGRESS: Progress = { steps: [], items: [] }

const EXAMPLES: Record<StageOverview['type'], string[]> = {
  DOCUMENT: [
    '금융 도메인 경험이 있는 지원자 찾아줘',
    '인재상이 잘 드러나는 지원자 찾아줘',
    '미결정이 몇 명 남았어?',
  ],
  ASSESSMENT: [
    '총점 85점 이상인 지원자 찾아줘',
    '평가 결과가 아직 없는 지원자 보여줘',
    '미결정이 몇 명 남았어?',
  ],
  INTERVIEW: ['면접에서 프로젝트 역할을 꼭 확인해야 할 지원자 찾아줘', '미결정이 몇 명 남았어?'],
}

// AI Chat (STG-02~05). 조건을 말하면 리스트에 표시하고, 특정 지원자 질문은 화면을 바꾸지 않고 대화로 답한다
export function ChatPanel({ overview }: { overview: StageOverview }) {
  const stageId = overview.stageId
  const messages = useChatStore((state) => state.threads[stageId] ?? EMPTY)
  const { append, load, clear } = useChatStore()
  const history = useChatHistory(stageId)
  const forget = useForgetChat(stageId)
  const { mentions, removeMention, addMention, checked } = useStageUi()
  const [progress, setProgress] = useState<Progress>(NO_PROGRESS)
  // 답이 오면 그때까지 쌓은 단계를 답에 붙인다. 응답 콜백은 보낼 때의 progress만 보므로 따로 들고 있는다
  const steps = useRef<string[]>([])
  const chat = useChat(stageId, {
    onStatus: (text) => {
      steps.current = addStep(steps.current, text)
      setProgress((current) => ({ ...current, steps: steps.current }))
    },
    onItem: (item) => setProgress((current) => ({ ...current, items: [...current.items, item] })),
  })
  const [text, setText] = useState('')
  const [expanded, setExpanded] = useState(false)
  const bottom = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const mentionQuery = /@([^\s@]*)$/.exec(text)?.[1]
  const suggestions = useMentionCandidates(stageId, mentionQuery ?? '', mentionQuery !== undefined)

  // 기록을 받는 동안에는 보내지 않는다. 받은 기록이 화면의 대화를 바꾸므로 그 사이에 보낸 질문이 사라진다
  const loading = history.isFetching
  useEffect(() => {
    if (history.data && !loading) load(stageId, turnsToMessages(history.data))
  }, [history.data, loading, load, stageId])

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: 'end' })
  }, [messages.length, chat.isPending, progress.items.length])

  const send = (raw: string) => {
    const message = raw.replace(/@\S*$/, '').trim()
    if (!message || chat.isPending || loading) return
    append(stageId, { role: 'user', text: message, mentions })
    setText('')
    steps.current = []
    setProgress(NO_PROGRESS)
    chat.mutate(
      {
        message,
        mentionIds: mentions.map((mention) => mention.applicationId),
        checkedIds: checked,
      },
      {
        // 쌓은 단계는 답에 붙여 접어 둔다. 다시 불러오면 ai 서버가 남긴 같은 단계가 온다
        onSuccess: ({ answer, seconds }) =>
          append(stageId, { role: 'ai', answer, steps: steps.current, seconds }),
        onError: (error) => append(stageId, { role: 'error', text: errorMessage(error) }),
        // 진행 중 화면은 최종 답이나 오류로 바뀐다
        onSettled: () => setProgress(NO_PROGRESS),
      },
    )
  }

  const visible = expanded ? messages : messages.slice(-RECENT)
  const pickMention = (applicationId: string, name: string) => {
    addMention({ applicationId, name })
    setText((current) => current.replace(/@[^\s@]*$/, ''))
    input.current?.focus()
  }

  return (
    <aside className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Sparkles className="size-4 text-ai" />
          AI Chat
        </div>
        <button
          aria-label="대화 지우기"
          title="대화 지우기"
          disabled={forget.isPending}
          onClick={() => forget.mutate(undefined, { onSuccess: () => clear(stageId) })}
          className="text-muted-foreground hover:text-foreground"
        >
          <History className="size-4" />
        </button>
      </div>
      <div className="min-h-0 flex-1 space-y-4 overflow-auto px-4 pb-4">
        {messages.length > RECENT && !expanded && (
          <button
            onClick={() => setExpanded(true)}
            className="block w-full text-center text-xs text-muted-foreground hover:text-foreground"
          >
            ··· 이전 대화
          </button>
        )}
        {messages.length === 0 && (
          <div className="space-y-2 pt-2">
            <p className="text-xs text-muted-foreground">
              {overview.name} 지원자 {overview.counts.total}명을 대상으로 물어볼 수 있어요. @로
              지원자를 고를 수도 있어요.
            </p>
            {EXAMPLES[overview.type].map((example) => (
              <button
                key={example}
                onClick={() => send(example)}
                className="block w-full rounded-xl border px-3 py-2 text-left text-sm hover:bg-muted"
              >
                {example}
              </button>
            ))}
          </div>
        )}
        {visible.map((message, index) => (
          <Fragment key={index}>{renderMessage(message)}</Fragment>
        ))}
        {chat.isPending && (
          <div className="flex gap-2">
            <Sparkles className="mt-0.5 size-4 shrink-0 text-ai" />
            <div className="min-w-0 flex-1 space-y-2">
              <LiveSteps steps={progress.steps.length ? progress.steps : [WAITING]} />
              {progress.items.length > 0 && <ItemList items={progress.items} />}
            </div>
          </div>
        )}
        <div ref={bottom} />
      </div>
      <div className="relative m-3">
        {mentionQuery !== undefined && (suggestions.data?.items.length ?? 0) > 0 && (
          <ul
            role="listbox"
            aria-label="지원자 고르기"
            className="absolute inset-x-0 bottom-full mb-2 overflow-hidden rounded-xl border bg-popover p-1 shadow-lg"
          >
            {suggestions.data?.items.map((row) => (
              <li key={row.applicationId}>
                <button
                  role="option"
                  aria-selected={false}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => pickMention(row.applicationId, row.name)}
                  className="w-full rounded-lg px-3 py-1.5 text-left hover:bg-muted"
                >
                  <div className="text-sm font-semibold">{row.name}</div>
                  <div className="text-xs text-muted-foreground">{careerLabel(row)}</div>
                </button>
              </li>
            ))}
          </ul>
        )}
        <form
          onSubmit={(event) => {
            event.preventDefault()
            send(text)
          }}
          className="flex items-center gap-2 rounded-xl border px-3 py-2"
        >
          <AtSign className="size-4 shrink-0 text-muted-foreground" />
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1">
            {mentions.map((mention) => (
              <span
                key={mention.applicationId}
                className="inline-flex items-center gap-1 rounded-md bg-ai-soft px-1.5 py-0.5 text-xs font-semibold text-ai"
              >
                {mention.name}
                <button
                  aria-label={`${mention.name} 참조 해제`}
                  type="button"
                  onClick={() => removeMention(mention.applicationId)}
                >
                  <X className="size-3" />
                </button>
              </span>
            ))}
            <input
              ref={input}
              value={text}
              aria-label="AI Chat 입력"
              onChange={(event) => setText(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && event.nativeEvent.isComposing) {
                  event.preventDefault()
                  return
                }
                if (event.key === 'Backspace' && text === '' && mentions.length > 0) {
                  removeMention(mentions[mentions.length - 1].applicationId)
                }
              }}
              placeholder={
                mentions.length
                  ? ''
                  : checked.length
                    ? `체크한 ${checked.length}명에 대해 물어보기`
                    : '조건이나 궁금한 점'
              }
              className="min-w-16 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            />
          </div>
          <button
            type="submit"
            aria-label="보내기"
            disabled={!text.trim() || chat.isPending || loading}
            className={cn(
              'flex size-7 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground',
              text.trim() && !chat.isPending && !loading && 'bg-foreground text-background',
            )}
          >
            <ArrowUp className="size-4" />
          </button>
        </form>
      </div>
    </aside>
  )
}

function renderMessage(message: ChatMessage): ReactNode {
  if (message.role === 'user') {
    return (
      <div className="ml-8 rounded-xl bg-muted px-3 py-2 text-sm">
        {message.mentions.map((mention) => (
          <span key={mention.applicationId} className="mr-1 font-semibold text-ai">
            @{mention.name}
          </span>
        ))}
        {message.text}
      </div>
    )
  }
  if (message.role === 'error') {
    return <p className="text-sm text-destructive">{message.text}</p>
  }
  return <Answer answer={message.answer} steps={message.steps} seconds={message.seconds} />
}

function Answer({
  answer,
  steps,
  seconds,
}: {
  answer: ChatAnswer
  steps: string[]
  seconds: number | null
}) {
  return (
    <div className="flex gap-2 text-sm">
      <Sparkles className="mt-0.5 size-4 shrink-0 text-ai" />
      <div className="min-w-0 space-y-1.5">
        <StepsSummary steps={steps} seconds={seconds} />
        <p className="leading-6">{bold(answer.message)}</p>
        {answer.items.length > 0 && <ItemList items={answer.items} />}
        {answer.sources.length > 0 && (
          <p className="text-xs text-muted-foreground">출처 · {answer.sources.join(' · ')}</p>
        )}
        {answer.agents.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {answer.agents.map((agent) => (
              <AgentChip key={agent} name={agent} stub={answer.stub} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

/** 답변의 항목 줄. 근거 충분은 체크, 확인 필요는 경고 표시다. 진행 중 화면과 최종 답이 같이 쓴다. */
function ItemList({ items }: { items: ChatItem[] }) {
  return (
    <ul className="space-y-1">
      {items.map((item, index) => (
        <li key={index} className="flex gap-1.5 text-[13px] leading-5">
          {item.status === 'OK' ? (
            <Check className="mt-0.5 size-3.5 shrink-0 text-pass-foreground" />
          ) : item.status === 'CHECK' ? (
            <AlertCircle className="mt-0.5 size-3.5 shrink-0 text-amber-500" />
          ) : (
            <span className="text-muted-foreground">•</span>
          )}
          <span>
            <span className="font-semibold">{item.label}</span>
            <span className="text-muted-foreground"> — {item.text}</span>
          </span>
        </li>
      ))}
    </ul>
  )
}

/** **굵게** 표시만 지원한다. */
function bold(text: string): ReactNode[] {
  return text
    .split(/(\*\*[^*]+\*\*)/g)
    .map((part, index) =>
      part.startsWith('**') && part.endsWith('**') ? (
        <strong key={index}>{part.slice(2, -2)}</strong>
      ) : (
        part
      ),
    )
}
