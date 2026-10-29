import { create } from 'zustand'

import type { ChatAnswer, ChatTurn } from '@/features/chat/api'
import type { Mention } from '@/features/screening/store'

export type ChatMessage =
  /** asker: 질문한 담당자 이름. 탭 대화는 같은 기업 담당자가 함께 쓴다. 예전 기록은 null이다 */
  | { role: 'user'; text: string; mentions: Mention[]; asker: string | null }
  | { role: 'ai'; answer: ChatAnswer; steps: string[]; seconds: number | null }
  | { role: 'error'; text: string }

type ChatState = {
  threads: Record<string, ChatMessage[]>
  append: (tabId: string, message: ChatMessage) => void
  /** 서버 기록으로 탭의 대화를 바꾼다 */
  load: (tabId: string, messages: ChatMessage[]) => void
}

/**
 * 서버에 남은 지난 턴을 화면 메시지로 펼친다. 질문에 쓴 @멘션, 질문한 담당자와 답을 내기까지 거친 처리 단계도
 * 같이 살린다.
 */
export function turnsToMessages(turns: ChatTurn[]): ChatMessage[] {
  return turns.flatMap((turn): ChatMessage[] => [
    { role: 'user', text: turn.message, mentions: turn.mentions, asker: turn.asker?.name ?? null },
    { role: 'ai', answer: turn.answer, steps: turn.steps, seconds: turn.seconds },
  ])
}

/**
 * 탭별 대화. 대화는 탭마다 서버에 남고 같은 기업 담당자가 함께 본다(OI-05). 화면은 탭을 열 때마다 서버 기록을
 * 불러와 바꾸고, 그 뒤의 새 대화를 여기에 쌓는다. 브라우저에는 따로 남기지 않는다.
 */
export const useChatStore = create<ChatState>()((set) => ({
  threads: {},
  append: (tabId, message) =>
    set((state) => ({
      threads: { ...state.threads, [tabId]: [...(state.threads[tabId] ?? []), message] },
    })),
  load: (tabId, messages) => set((state) => ({ threads: { ...state.threads, [tabId]: messages } })),
}))
