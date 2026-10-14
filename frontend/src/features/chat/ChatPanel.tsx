import { ArrowUp, AtSign, History, Sparkles } from 'lucide-react'

/** AI Chat 자리. 다음 작업에서 Root Agent와 연결한다. */
export function ChatPanel() {
  return (
    <aside className="flex min-h-0 w-[340px] shrink-0 flex-col border-l">
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Sparkles className="size-4 text-ai" />
          AI Chat
        </div>
        <History className="size-4 text-muted-foreground" />
      </div>
      <div className="flex-1" />
      <div className="m-3 flex items-center gap-2 rounded-xl border px-3 py-2 text-sm text-muted-foreground">
        <AtSign className="size-4" />
        <span className="flex-1">조건이나 궁금한 점</span>
        <span className="flex size-7 items-center justify-center rounded-full bg-muted">
          <ArrowUp className="size-4" />
        </span>
      </div>
    </aside>
  )
}
