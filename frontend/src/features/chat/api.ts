import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap, type Schemas } from '@/lib/api/client'
import { stageKeys } from '@/features/screening/api'

export type ChatAnswer = Schemas['ChatAnswer']

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
