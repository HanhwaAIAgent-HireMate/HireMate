import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'

import { ApiError, api, unwrap, type Schemas } from '@/lib/api/client'
import { readEvents } from '@/lib/api/sse'
import { stageKeys } from '@/features/screening/api'

export type ChatAnswer = Schemas['ChatAnswer']
export type ChatTurn = Schemas['ChatTurn']
export type ChatItem = Schemas['ChatItem']

/** 받은 답과 보낸 때부터 답을 받기까지 걸린 초 */
export type ChatReply = { answer: ChatAnswer; seconds: number }

/** 답을 기다리는 동안 받는 진행 알림. 단계 문구와 검증을 마친 항목이다. */
export type ChatProgress = {
  onStatus: (text: string) => void
  onItem: (item: ChatItem) => void
}

// 선택 지원자 갱신으로 대화 기록을 다시 받아 방금 보낸 메시지를 덮어쓰지 않는다.
const historyKey = (tabId: string) => ['chat', tabId] as const

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

/** 탭의 대화방으로 묻는다. 같은 전형 안에서 탭을 옮겨도 요청은 이어지고 답은 물은 탭(tabId)의 것이다 */
export function useChat(stageId: string, progress: ChatProgress) {
  const queryClient = useQueryClient()
  // 답을 받기 전에 화면을 떠나거나 다른 전형으로 옮기면 요청을 끊는다.
  // 서버는 끊긴 요청의 선택 변경과 대화 기록을 남기지 않는다
  const waiting = useRef<AbortController | null>(null)
  useEffect(() => () => waiting.current?.abort(), [stageId])
  return useMutation({
    mutationFn: async ({
      tabId,
      ...body
    }: {
      tabId: string
      message: string
      mentionIds: string[]
      checkedIds: string[]
    }): Promise<ChatReply> => {
      const startedAt = Date.now()
      const controller = new AbortController()
      waiting.current = controller
      // 권한 · 입력 오류는 스트림을 열기 전에 일반 오류 응답으로 온다
      const stream = await unwrap(
        api.POST('/api/stages/{stageId}/tabs/{tabId}/chat', {
          params: { path: { stageId, tabId } },
          body,
          parseAs: 'stream',
          signal: controller.signal,
        }),
      )
      if (!stream) throw new ApiError(502, 'AI_UNAVAILABLE', '')
      const answer = await readChat(stream, progress)
      // 끊은 뒤에 도착한 답으로 선택 지원자나 카드를 다시 불러오지 않는다
      controller.signal.throwIfAborted()
      return { answer, seconds: Math.round((Date.now() - startedAt) / 1000) }
    },
    onSuccess: ({ answer }) => {
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
 * 탭의 대화 기록. 같은 기업 담당자가 함께 쓰는 대화방이라, 다른 담당자나 다른 브라우저 탭에서 나눈 대화도 보이도록
 * 화면을 열거나 탭을 옮길 때마다 다시 받고, 대화 중에는 다시 받지 않는다. 탭을 지우면 함께 지워진다.
 */
export function useChatHistory(stageId: string, tabId: string) {
  return useQuery({
    queryKey: historyKey(tabId),
    queryFn: () =>
      unwrap(
        api.GET('/api/stages/{stageId}/tabs/{tabId}/chat', {
          params: { path: { stageId, tabId } },
        }),
      ),
    refetchOnMount: 'always',
    refetchOnWindowFocus: false,
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
