import { ArrowUp, AtSign, Bot, History, Sparkles } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { cn } from '@/lib/utils'

export type AiMessage = { role: 'user' | 'ai'; text: string; agent?: string; stub?: boolean }

/**
 * 공고 작성 · 안내 초안의 [AI 수정 요청] 패널. 문서를 고치는 요청만 받고, 바뀐 부분은 본문에 표시된다.
 */
export function AiRequestPanel({
  messages,
  examples,
  pending,
  disabled,
  onSend,
  onReset,
}: {
  messages: AiMessage[]
  examples: string[]
  pending: boolean
  disabled?: boolean
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
      <div className="flex items-center justify-between px-4 py-3">
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
          </div>
        )}
        {messages.map((message, index) =>
          message.role === 'user' ? (
            <div key={index} className="ml-6 rounded-xl bg-muted px-3 py-2 text-sm">
              {message.text}
            </div>
          ) : (
            <div key={index} className="flex gap-2 text-sm">
              <Sparkles className="mt-0.5 size-4 shrink-0 text-ai" />
              <div className="space-y-1.5">
                <p className="whitespace-pre-wrap">{message.text}</p>
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
          placeholder="수정할 내용을 입력"
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
