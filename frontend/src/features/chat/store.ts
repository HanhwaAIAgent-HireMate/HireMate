import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

import type { ChatAnswer, ChatTurn } from '@/features/chat/api'
import type { Mention } from '@/features/screening/store'

export type ChatMessage =
  | { role: 'user'; text: string; mentions: Mention[] }
  | { role: 'ai'; answer: ChatAnswer }
  | { role: 'error'; text: string }

type ChatState = {
  threads: Record<string, ChatMessage[]>
  append: (stageId: string, message: ChatMessage) => void
  /** 화면에 대화가 없을 때만 서버 기록으로 채운다 */
  seed: (stageId: string, messages: ChatMessage[]) => void
  clear: (stageId: string) => void
}

/** 서버에 남은 지난 턴을 화면 메시지로 펼친다. 질문에 쓴 @멘션 칩은 남지 않는다. */
export function turnsToMessages(turns: ChatTurn[]): ChatMessage[] {
  return turns.flatMap((turn): ChatMessage[] => [
    { role: 'user', text: turn.message, mentions: [] },
    { role: 'ai', answer: turn.answer },
  ])
}

/**
 * 전형별 대화. 대화는 담당자별 · 전형별로 서버에 전형이 끝날 때까지 남고(OI-05), 화면은 처음 열 때 그 기록을
 * 불러온 뒤 새 대화를 여기에 쌓는다.
 */
export const useChatStore = create<ChatState>()(
  persist(
    (set) => ({
      threads: {},
      append: (stageId, message) =>
        set((state) => ({
          threads: { ...state.threads, [stageId]: [...(state.threads[stageId] ?? []), message] },
        })),
      seed: (stageId, messages) =>
        set((state) =>
          state.threads[stageId]?.length
            ? state
            : { threads: { ...state.threads, [stageId]: messages } },
        ),
      clear: (stageId) => set((state) => ({ threads: { ...state.threads, [stageId]: [] } })),
    }),
    { name: 'hiremate-chat', storage: createJSONStorage(() => sessionStorage) },
  ),
)
