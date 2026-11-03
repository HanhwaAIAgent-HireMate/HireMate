import { ArrowUp, AtSign, BookOpen, Bot, ChevronDown, History, Sparkles, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import type { NcsSource } from '@/features/posting/api'
import { cn } from '@/lib/utils'

/**
 * focus는 HR이 줄을 골라 보낸 요청의 줄 이름이다 (예: 우대 사항 3번).
 * sources는 AI가 자격 요건 · 우대 사항을 쓴 NCS 근거다. 답 아래에 접어 보여 준다
 */
export type AiMessage = {
  role: 'user' | 'ai'
  text: string
  agent?: string
  stub?: boolean
  focus?: string
  sources?: NcsSource[]
}

/**
 * 공고 작성 · 안내 초안의 [AI 수정 요청] 패널. 문서를 고치는 요청만 받고, 바뀐 부분은 본문에 표시된다.
 * focus가 있으면 입력칸 위에 고른 줄을 보여 주고, ×로 고르기를 푼다.
 */
export function AiRequestPanel({
  messages,
  examples,
  hint,
  pending,
  disabled,
  focus,
  onSend,
  onReset,
}: {
  messages: AiMessage[]
  examples: string[]
  hint?: string
  pending: boolean
  disabled?: boolean
  focus?: { label: string; onClear: () => void }
  onSend: (message: string) => void
  onReset?: () => void
}) {
  const [text, setText] = useState('')
  const bottom = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: 'end' })
  }, [messages.length, pending])

  const send = (message: string) => {
    const trimmed = message.trim()
    if (!trimmed || pending || disabled) return
    onSend(trimmed)
    setText('')
  }

  return (
    <aside className="flex min-h-0 w-[300px] shrink-0 flex-col border-l">
      <div className="flex h-12 shrink-0 items-center justify-between px-4">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Sparkles className="size-4 text-ai" />
          AI 수정 요청
        </div>
        {onReset && (
          <button
            aria-label="대화 지우기"
            onClick={onReset}
            className="text-muted-foreground hover:text-foreground"
          >
            <History className="size-4" />
          </button>
        )}
      </div>
      <div className="min-h-0 flex-1 space-y-4 overflow-auto px-4 pb-4">
        {messages.length === 0 && (
          <div className="space-y-2 pt-2">
            <p className="text-xs text-muted-foreground">이렇게 요청해 보세요</p>
            {examples.map((example) => (
              <button
                key={example}
                onClick={() => send(example)}
                disabled={pending || disabled}
                className="block w-full rounded-xl border px-3 py-2 text-left text-sm hover:bg-muted"
              >
                {example}
              </button>
            ))}
            {hint && <p className="pt-1 text-xs text-muted-foreground">{hint}</p>}
          </div>
        )}
        {messages.map((message, index) =>
          message.role === 'user' ? (
            <div key={index} className="ml-6 rounded-xl bg-muted px-3 py-2 text-sm">
              {message.focus && (
                <div className="mb-0.5 text-xs font-medium text-ai">{message.focus}</div>
              )}
              {message.text}
            </div>
          ) : (
            <div key={index} className="flex gap-2 text-sm">
              <Sparkles className="mt-0.5 size-4 shrink-0 text-ai" />
              <div className="space-y-1.5">
                <p className="whitespace-pre-wrap">{message.text}</p>
                {message.sources && message.sources.length > 0 && (
                  <NcsSources sources={message.sources} />
                )}
                {message.agent && <AgentChip name={message.agent} stub={message.stub} />}
              </div>
            </div>
          ),
        )}
        {pending && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Sparkles className="size-4 animate-pulse text-ai" />
            수정안을 만들고 있어요…
          </div>
        )}
        <div ref={bottom} />
      </div>
      {focus && (
        <div className="mx-3 -mb-1 flex items-center gap-1 self-start rounded-md bg-ai-soft px-2 py-1 text-xs font-medium text-ai">
          선택: {focus.label}
          <button
            type="button"
            aria-label="고른 줄 풀기"
            onClick={focus.onClear}
            className="rounded hover:bg-ai/15"
          >
            <X className="size-3" />
          </button>
        </div>
      )}
      <form
        className="m-3 flex items-center gap-2 rounded-xl border px-3 py-2"
        onSubmit={(event) => {
          event.preventDefault()
          send(text)
        }}
      >
        <AtSign className="size-4 shrink-0 text-muted-foreground" />
        <input
          aria-label="수정할 내용"
          value={text}
          disabled={disabled}
          onChange={(event) => setText(event.target.value)}
          placeholder={focus ? '고른 줄을 어떻게 고칠지 입력' : '수정할 내용을 입력'}
          className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
        />
        <button
          type="submit"
          aria-label="보내기"
          disabled={!text.trim() || pending || disabled}
          className={cn(
            'flex size-7 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground',
            text.trim() && !pending && 'bg-foreground text-background',
          )}
        >
          <ArrowUp className="size-4" />
        </button>
      </form>
    </aside>
  )
}

/** AI가 쓴 자격 요건 · 우대 사항의 NCS 근거. 접어 두고, 누르면 능력단위마다 세분류 · 수준 · 정의를 보여 준다 */
function NcsSources({ sources }: { sources: NcsSource[] }) {
  return (
    <details className="group rounded-lg border text-xs">
      <summary className="flex cursor-pointer list-none items-center gap-1 px-2.5 py-1.5 text-muted-foreground hover:text-foreground">
        <BookOpen className="size-3.5" />
        NCS 근거 {sources.length}개
        <ChevronDown className="ml-auto size-3.5 transition-transform group-open:rotate-180" />
      </summary>
      <ul className="space-y-2 border-t px-2.5 py-2">
        {sources.map((source) => (
          <li key={source.code}>
            <div className="font-medium">
              {source.name}
              <span className="font-normal text-muted-foreground">
                {' '}
                · {source.subdivision} · 수준 {source.level}
              </span>
            </div>
            <p className="mt-0.5 leading-5 text-muted-foreground">{source.definition}</p>
          </li>
        ))}
      </ul>
    </details>
  )
}

/** 응답을 만든 Agent. 개발용 Stub 응답이면 함께 표시한다. */
export function AgentChip({ name, stub }: { name: string; stub?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-ai-soft px-2 py-0.5 text-xs font-medium text-ai">
      <Bot className="size-3" />
      {name}
      {stub && <span className="font-normal opacity-70">· 개발용</span>}
    </span>
  )
}
