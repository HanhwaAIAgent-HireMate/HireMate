import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError, api, unwrap, type Schemas } from '@/lib/api/client'
import { readEvents } from '@/lib/api/sse'
import { stageKeys } from '@/features/screening/api'

export type ChatAnswer = Schemas['ChatAnswer']
export type ChatTurn = Schemas['ChatTurn']
export type ChatItem = Schemas['ChatItem']

/** 답을 기다리는 동안 받는 진행 알림. 단계 문구와 검증을 마친 항목이다. */
export type ChatProgress = {
  onStatus: (text: string) => void
  onItem: (item: ChatItem) => void
}

const historyKey = (stageId: string) => ['stage', stageId, 'chat'] as const

/**
 * Chat 응답 스트림(SSE)을 읽는다. status · item은 progress로 넘기고 done의 답을 돌려준다.
 * error 이벤트나 done 없이 끝난 스트림은 ApiError로 던진다.
 */
export async function readChat(
  body: ReadableStream<Uint8Array>,
  progress: ChatProgress,
): Promise<ChatAnswer> {
  for await (const { event, data } of readEvents(body)) {
    if (event === 'status') progress.onStatus((JSON.parse(data) as Schemas['ChatStatus']).text)
    else if (event === 'item') progress.onItem(JSON.parse(data) as ChatItem)
    else if (event === 'done') return JSON.parse(data) as ChatAnswer
    else if (event === 'error') {
      const error = JSON.parse(data) as Schemas['ChatError']
      throw new ApiError(error.status, error.code, '')
    }
  }
  throw new ApiError(502, 'AI_UNAVAILABLE', '')
}

export function useChat(stageId: string, progress: ChatProgress) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: { message: string; mentionIds: string[]; checkedIds: string[] }) => {
      // 권한 · 입력 오류는 스트림을 열기 전에 일반 오류 응답으로 온다
      const stream = await unwrap(
        api.POST('/api/stages/{stageId}/chat', {
          params: { path: { stageId } },
          body,
          parseAs: 'stream',
        }),
      )
      if (!stream) throw new ApiError(502, 'AI_UNAVAILABLE', '')
      return readChat(stream, progress)
    },
    onSuccess: (answer) => {
      // 찾기 · 편집이면 리스트의 AI 표시와 선택 지원자가 바뀐다
      if (answer.selectionChanged)
        void queryClient.invalidateQueries({ queryKey: stageKeys.all(stageId) })
      // 맞춤 질문을 만들었으면 지원자 카드의 질문을 다시 불러온다 (새로고침 없이 카드에 나타나게)
      else if (madeQuestions(answer))
        void queryClient.invalidateQueries({ queryKey: [...stageKeys.all(stageId), 'interview'] })
    },
  })
}

/** Interview Agent가 질문을 만든 답인가. 이때 카드의 맞춤 질문이 바뀐다 */
export function madeQuestions(answer: Pick<ChatAnswer, 'agents'>) {
  return answer.agents.includes('Interview Agent')
}

/**
 * 담당자의 이 전형 대화 기록. 전형이 끝나면 지워진다. 다른 탭에서 나눈 대화도 보이도록 화면을 열 때마다 다시 받고,
 * 대화 중에는 다시 받지 않는다.
 */
export function useChatHistory(stageId: string) {
  return useQuery({
    queryKey: historyKey(stageId),
    queryFn: () => unwrap(api.GET('/api/stages/{stageId}/chat', { params: { path: { stageId } } })),
    refetchOnMount: 'always',
    refetchOnWindowFocus: false,
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
