import { create } from 'zustand'

import type { ChatAnswer, ChatTurn } from '@/features/chat/api'
import type { Mention } from '@/features/screening/store'

export type ChatMessage =
  | { role: 'user'; text: string; mentions: Mention[] }
  | { role: 'ai'; answer: ChatAnswer; steps: string[]; seconds: number | null }
  | { role: 'error'; text: string }

type ChatState = {
  threads: Record<string, ChatMessage[]>
  append: (stageId: string, message: ChatMessage) => void
  /** 서버 기록으로 전형의 대화를 바꾼다 */
  load: (stageId: string, messages: ChatMessage[]) => void
  clear: (stageId: string) => void
}

/** 서버에 남은 지난 턴을 화면 메시지로 펼친다. 질문에 쓴 @멘션과 답을 내기까지 거친 처리 단계도 같이 살린다. */
export function turnsToMessages(turns: ChatTurn[]): ChatMessage[] {
  return turns.flatMap((turn): ChatMessage[] => [
    { role: 'user', text: turn.message, mentions: turn.mentions },
    { role: 'ai', answer: turn.answer, steps: turn.steps, seconds: turn.seconds },
  ])
}

/**
 * 전형별 대화. 대화는 담당자별 · 전형별로 서버에 전형이 끝날 때까지 남는다(OI-05). 화면은 열 때마다 서버 기록을
 * 불러와 바꾸고, 그 뒤의 새 대화를 여기에 쌓는다. 브라우저에는 따로 남기지 않는다.
 */
export const useChatStore = create<ChatState>()((set) => ({
  threads: {},
  append: (stageId, message) =>
    set((state) => ({
      threads: { ...state.threads, [stageId]: [...(state.threads[stageId] ?? []), message] },
    })),
  load: (stageId, messages) =>
    set((state) => ({ threads: { ...state.threads, [stageId]: messages } })),
  clear: (stageId) => set((state) => ({ threads: { ...state.threads, [stageId]: [] } })),
}))
