import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

import type { ChatAnswer } from '@/features/chat/api'
import type { Mention } from '@/features/screening/store'

export type ChatMessage =
  | { role: 'user'; text: string; mentions: Mention[] }
  | { role: 'ai'; answer: ChatAnswer }
  | { role: 'error'; text: string }

type ChatState = {
  threads: Record<string, ChatMessage[]>
  append: (stageId: string, message: ChatMessage) => void
  clear: (stageId: string) => void
}

/** 전형별 대화. 탭을 닫기 전까지 남긴다 (OI-05 MVP 기본값: 대화는 브라우저 세션에만 보관). */
export const useChatStore = create<ChatState>()(
  persist(
    (set) => ({
      threads: {},
      append: (stageId, message) =>
        set((state) => ({
          threads: { ...state.threads, [stageId]: [...(state.threads[stageId] ?? []), message] },
        })),
      clear: (stageId) => set((state) => ({ threads: { ...state.threads, [stageId]: [] } })),
    }),
    { name: 'hiremate-chat', storage: createJSONStorage(() => sessionStorage) },
  ),
)
