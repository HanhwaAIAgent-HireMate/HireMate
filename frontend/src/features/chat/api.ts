import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap, type Schemas } from '@/lib/api/client'
import { stageKeys } from '@/features/screening/api'

export type ChatAnswer = Schemas['ChatAnswer']
export type ChatTurn = Schemas['ChatTurn']

const historyKey = (stageId: string) => ['stage', stageId, 'chat'] as const

export function useChat(stageId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { message: string; mentionIds: string[]; checkedIds: string[] }) =>
      unwrap(api.POST('/api/stages/{stageId}/chat', { params: { path: { stageId } }, body })),
    onSuccess: (answer) => {
      // 찾기 · 편집이면 리스트의 AI 표시와 선택 지원자가 바뀐다
      if (answer.selectionChanged)
        void queryClient.invalidateQueries({ queryKey: stageKeys.all(stageId) })
    },
  })
}

/** 담당자의 이 전형 대화 기록. 전형이 끝나면 지워진다. */
export function useChatHistory(stageId: string) {
  return useQuery({
    queryKey: historyKey(stageId),
    queryFn: () => unwrap(api.GET('/api/stages/{stageId}/chat', { params: { path: { stageId } } })),
    staleTime: Infinity,
  })
}

/** [대화 지우기]. 서버의 대화방을 지워 Root도 앞 대화를 잊는다. */
export function useForgetChat(stageId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () =>
      unwrap(api.DELETE('/api/stages/{stageId}/chat', { params: { path: { stageId } } })),
    onSuccess: () => queryClient.setQueryData(historyKey(stageId), []),
  })
}

/** @ 입력 중에 고를 지원자. 이름으로 서버에서 찾는다. */
export function useMentionCandidates(stageId: string, query: string, enabled: boolean) {
  return useQuery({
    queryKey: ['stage', stageId, 'mention', query],
    enabled,
    queryFn: () =>
      unwrap(
        api.GET('/api/stages/{stageId}/candidates', {
          params: { path: { stageId }, query: { query: query || undefined, page: 0, size: 8 } },
        }),
      ),
    staleTime: 30_000,
  })
}
