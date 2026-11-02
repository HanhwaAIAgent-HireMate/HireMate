import { useQueryClient } from '@tanstack/react-query'
import { AlertCircle, ArrowUp, AtSign, Check, FileChartColumn, Sparkles, X } from 'lucide-react'
import { Fragment, useEffect, useRef, useState, type ReactNode } from 'react'

import { AgentChip } from '@/features/posting/AiRequestPanel'
import { AgentReportModal } from '@/features/report/AgentReportModal'
import {
  useChat,
  useChatHistory,
  useMentionCandidates,
  type ChatAnswer,
  type ChatItem,
} from '@/features/chat/api'
import { LiveSteps, StepsSummary } from '@/features/chat/ChatSteps'
import { addStep } from '@/features/chat/steps'
import { turnsToMessages, useChatStore, type ChatMessage } from '@/features/chat/store'
import { careerLabel, stageKeys, type StageOverview } from '@/features/screening/api'
import { useStageUi } from '@/features/screening/store'
import type { StageTab } from '@/features/screening/tabs'
import { errorMessage } from '@/lib/api/client'
import { useMe } from '@/lib/auth'
import { cn } from '@/lib/utils'

const EMPTY: ChatMessage[] = []
const RECENT = 6
const WAITING = '지원자 자료를 살펴보고 있어요…'

/** 답을 기다리는 동안 쌓은 단계 문구와 검증을 마친 항목 */
type Progress = { steps: string[]; items: ChatItem[] }
const NO_PROGRESS: Progress = { steps: [], items: [] }

/**
 * AI Chat (STG-02~05). 조건을 말하면 리스트에 표시하고, 특정 지원자 질문은 화면을 바꾸지 않고 대화로 답한다.
 * 대화는 지금 탭(tabId)의 것이고 같은 기업 담당자가 함께 본다. 답을 기다리는 동안 다른 탭으로 옮겨도 답은 물은 탭에
 * 쌓이고, 그동안에는 어느 탭에서도 새로 묻지 않는다.
 */
/** Chat이 쓰는 전형 정보. HR 전형 화면은 전형 개요를, 면접관 모드는 배정된 면접으로 채운다 */
export type ChatStage = Pick<StageOverview, 'stageId' | 'name' | 'type'> & {
  counts: Pick<StageOverview['counts'], 'total'>
}

export function ChatPanel({
  overview,
  tabId,
  people,
  examples,
}: {
  overview: ChatStage
  tabId: string
  /** @로 고를 지원자. 없으면 전형의 지원자를 서버에서 찾는다 (면접관 모드는 배정된 지원자만 준다) */
  people?: { applicationId: string; name: string }[]
  /** 빈 대화의 추천 질문. HR 전형 화면은 전형 상황에 맞춰 고르고(useStageSuggestions), 면접관 모드는 고정 예시다 */
  examples: string[]
}) {
  const stageId = overview.stageId
  const messages = useChatStore((state) => state.threads[tabId] ?? EMPTY)
  const { append, load } = useChatStore()
  const history = useChatHistory(stageId, tabId)
  const { mentions, removeMention, addMention, checked } = useStageUi()
  const me = useMe()
  const queryClient = useQueryClient()
  // 답을 기다리는 탭. 그 탭의 기록을 다시 받아도 방금 보낸 질문을 지우지 않는다
  const asking = useRef<string | null>(null)
  const [progress, setProgress] = useState<Progress>(NO_PROGRESS)
  // 답이 오면 그때까지 쌓은 단계를 답에 붙인다. 응답 콜백은 보낼 때의 progress만 보므로 따로 들고 있는다
  const steps = useRef<string[]>([])
  const chat = useChat(stageId, {
    onStatus: (text) => {
      steps.current = addStep(steps.current, text)
      setProgress((current) => ({ ...current, steps: steps.current }))
    },
    onItem: (item) => setProgress((current) => ({ ...current, items: [...current.items, item] })),
    // 탭의 첫 대화 뒤에 자동으로 바뀐 이름을 탭 바에 바로 보인다. 답 직후 다시 받던 탭 목록은 제목을 저장하기 전
    // 이름이라 그 요청을 취소하고 다시 받는다
    onTitle: ({ tabId: named, name }) => {
      queryClient.setQueryData<StageTab[]>(stageKeys.tabs(stageId), (tabs) =>
        tabs?.map((tab) => (tab.id === named ? { ...tab, name } : tab)),
      )
      void queryClient.invalidateQueries({ queryKey: stageKeys.tabs(stageId) })
    },
  })
  const [text, setText] = useState('')
  const [expanded, setExpanded] = useState(false)
  const [reportId, setReportId] = useState<string | null>(null)
  const bottom = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const mentionQuery = /@([^\s@]*)$/.exec(text)?.[1]
  const remote = useMentionCandidates(
    stageId,
    mentionQuery ?? '',
    mentionQuery !== undefined && !people,
  )
  const suggestions = people
    ? people
        .filter((person) => person.name.includes(mentionQuery ?? ''))
        .slice(0, 8)
        .map((person) => ({ ...person, detail: '' }))
    : (remote.data?.items ?? []).map((row) => ({
        applicationId: row.applicationId,
        name: row.name,
        detail: careerLabel(row),
      }))
  // 키보드로 고를 후보. 찾는 이름이 바뀌면 첫 후보로 돌아간다
  const [cursor, setCursor] = useState({ query: '', index: 0 })
  const active = cursor.query === mentionQuery ? Math.min(cursor.index, suggestions.length - 1) : 0
  // Esc로 닫은 입력. 글자를 더 치면 다시 연다
  const [closedAt, setClosedAt] = useState<string | null>(null)
  const suggesting = mentionQuery !== undefined && suggestions.length > 0 && closedAt !== text

  // 기록을 받는 동안에는 보내지 않는다. 받은 기록이 화면의 대화를 바꾸므로 그 사이에 보낸 질문이 사라진다
  const loading = history.isFetching
  useEffect(() => {
    if (history.data && !loading && asking.current !== tabId)
      load(tabId, turnsToMessages(history.data))
  }, [history.data, loading, load, tabId])

  const waitingHere = chat.isPending && chat.variables?.tabId === tabId
  const waitingElsewhere = chat.isPending && !waitingHere
  useEffect(() => {
    bottom.current?.scrollIntoView({ block: 'end' })
  }, [messages.length, waitingHere, progress.items.length])

  const send = (raw: string) => {
    const message = raw.replace(/@\S*$/, '').trim()
    if (!message || chat.isPending || loading) return
    // 답이 올 때 지금 탭이 바뀌어 있어도 물은 탭에 쌓는다
    const tab = tabId
    append(tab, { role: 'user', text: message, mentions, asker: me.data?.name ?? null })
    asking.current = tab
    setText('')
    steps.current = []
    setProgress(NO_PROGRESS)
    chat.mutate(
      {
        tabId: tab,
        message,
        mentionIds: mentions.map((mention) => mention.applicationId),
        checkedIds: checked,
      },
      {
        // 쌓은 단계는 답에 붙여 접어 둔다. 다시 불러오면 ai 서버가 남긴 같은 단계가 온다
        onSuccess: ({ answer, seconds }) =>
          append(tab, { role: 'ai', answer, steps: steps.current, seconds }),
        onError: (error) => append(tab, { role: 'error', text: errorMessage(error) }),
        // 진행 중 화면은 최종 답이나 오류로 바뀐다
        onSettled: () => {
          asking.current = null
          setProgress(NO_PROGRESS)
        },
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
      <div className="flex items-center px-4 py-3">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Sparkles className="size-4 text-ai" />
          AI Chat
        </div>
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
            {examples.map((example) => (
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
          <Fragment key={index}>{renderMessage(message, setReportId)}</Fragment>
        ))}
        {waitingHere && (
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
        {suggesting && (
          <ul
            id="chat-mentions"
            role="listbox"
            aria-label="지원자 고르기"
            className="absolute inset-x-0 bottom-full mb-2 overflow-hidden rounded-xl border bg-popover p-1 shadow-lg"
          >
            {suggestions.map((row, index) => (
              <li key={row.applicationId}>
                <button
                  id={`chat-mention-${index}`}
                  type="button"
                  role="option"
                  aria-selected={index === active}
                  tabIndex={-1}
                  onMouseDown={(event) => event.preventDefault()}
                  onMouseEnter={() => setCursor({ query: mentionQuery ?? '', index })}
                  onClick={() => pickMention(row.applicationId, row.name)}
                  className={cn(
                    'w-full rounded-lg px-3 py-1.5 text-left',
                    index === active && 'bg-muted',
                  )}
                >
                  <div className="text-sm font-semibold">{row.name}</div>
                  {row.detail && <div className="text-xs text-muted-foreground">{row.detail}</div>}
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
              aria-controls={suggesting ? 'chat-mentions' : undefined}
              aria-activedescendant={suggesting ? `chat-mention-${active}` : undefined}
              onChange={(event) => setText(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && event.nativeEvent.isComposing) {
                  event.preventDefault()
                  return
                }
                if (suggesting) {
                  // 한글을 조합하는 중에도 위아래로 옮길 수 있다. 고르기와 닫기는 조합을 마친 뒤에 한다
                  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                    event.preventDefault()
                    const count = suggestions.length
                    const move = event.key === 'ArrowDown' ? 1 : -1
                    setCursor({ query: mentionQuery, index: (active + move + count) % count })
                    return
                  }
                  if (event.nativeEvent.isComposing) return
                  if (event.key === 'Enter' || event.key === 'Tab') {
                    event.preventDefault()
                    const row = suggestions[active]
                    pickMention(row.applicationId, row.name)
                    return
                  }
                  if (event.key === 'Escape') {
                    event.preventDefault()
                    setClosedAt(text)
                    return
                  }
                }
                if (event.key === 'Backspace' && text === '' && mentions.length > 0) {
                  removeMention(mentions[mentions.length - 1].applicationId)
                }
              }}
              placeholder={
                waitingElsewhere
                  ? '다른 탭에서 답을 기다리고 있어요'
                  : mentions.length
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
      <AgentReportModal
        stageId={overview.stageId}
        reportId={reportId}
        onClose={() => setReportId(null)}
      />
    </aside>
  )
}

function renderMessage(message: ChatMessage, openReport: (reportId: string) => void): ReactNode {
  if (message.role === 'user') {
    return (
      <div className="ml-8 space-y-1">
        {message.asker && (
          <p className="text-right text-[11px] text-muted-foreground">{message.asker}</p>
        )}
        <div className="rounded-xl bg-muted px-3 py-2 text-sm">
          {message.mentions.map((mention) => (
            <span key={mention.applicationId} className="mr-1 font-semibold text-ai">
              @{mention.name}
            </span>
          ))}
          {message.text}
        </div>
      </div>
    )
  }
  if (message.role === 'error') {
    return <p className="text-sm text-destructive">{message.text}</p>
  }
  return (
    <Answer
      answer={message.answer}
      steps={message.steps}
      seconds={message.seconds}
      openReport={openReport}
    />
  )
}

function Answer({
  answer,
  steps,
  seconds,
  openReport,
}: {
  answer: ChatAnswer
  steps: string[]
  seconds: number | null
  openReport: (reportId: string) => void
}) {
  return (
    <div className="flex gap-2 text-sm">
      <Sparkles className="mt-0.5 size-4 shrink-0 text-ai" />
      <div className="min-w-0 space-y-1.5">
        <StepsSummary steps={steps} seconds={seconds} />
        <p className="leading-6">{bold(answer.message)}</p>
        {answer.items.length > 0 && <ItemList items={answer.items} />}
        {answer.reportId && <ReportCard onOpen={() => openReport(answer.reportId ?? '')} />}
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

/** 리포트 카드. 누르면 리포트 모달이 열린다. 쓰는 중이면 모달이 진행 화면을 보여 준다 */
function ReportCard({ onOpen }: { onOpen: () => void }) {
  return (
    <button
      onClick={onOpen}
      className="flex w-full items-center gap-2.5 rounded-lg border border-ai/30 bg-ai-soft/60 px-3 py-2 text-left hover:bg-ai-soft"
    >
      <FileChartColumn className="size-4 shrink-0 text-ai" />
      <span className="flex-1">
        <span className="block text-sm font-semibold">Report Agent 리포트</span>
        <span className="block text-xs text-muted-foreground">
          눌러서 미리보기 · PDF는 모달 위 작은 버튼
        </span>
      </span>
      <span className="text-xs font-semibold text-ai">보기</span>
    </button>
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
